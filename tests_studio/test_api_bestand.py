# SPDX-FileCopyrightText: © Anzeigen-Studio contributors
# SPDX-ArtifactOfProjectHomePage: https://github.com/TingelTangelBob/Kleinanzeigen.de-botUI/
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# Tests des Bestands auf HTTP-Ebene (AP-2.6, AP-2.7).
#
# Bewusst gegen die echte Anwendung statt gegen einzelne Funktionen: Was hier
# geprueft wird - Groessengrenze beim Hochladen, abgelehnte Formate, abgelehnte
# Reihenfolgen - entsteht erst im Zusammenspiel von Endpunkt, Dienst und
# Fehlerbehandlung. Ein Funktionstest allein wuerde nicht auffangen, dass ein
# Fehler unterwegs zu einem 500 wird.
#
# Kein Test spricht mit kleinanzeigen.de. Der Hochladeweg wird ausschliesslich
# auf seinem Ablehnungspfad geprueft - der endet vor der Warteschlange, es wird
# also kein Lauf eingereiht.

from __future__ import annotations

import base64
import textwrap
import urllib.request
from typing import TYPE_CHECKING

import httpx
import pytest
from fastapi.testclient import TestClient

from anzeigen_studio.bestand import MAX_BYTES
from anzeigen_studio.core.settings import Settings
from anzeigen_studio.main import create_app

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path

SCHLUESSEL = base64.b64encode(b"0123456789abcdef0123456789abcdef").decode()
PASSWORT = "ein-ausreichend-langes-Passwort"
PROFIL = "testprofil"
DATEI = "downloaded-ads/ad_1/ad_1.yaml"

# Gueltige Dateikoepfe. Mehr als der Kopf ist nicht noetig: Erkannt wird am
# Inhalt, und der Rest der Datei spielt fuer die Formatpruefung keine Rolle.
JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 60
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 60
GIF = b"GIF89a" + b"\x00" * 60
WEBP = b"RIFF" + b"\x00\x00\x00\x00" + b"WEBP" + b"\x00" * 60

ANZEIGE = """
    active: true
    type: OFFER
    title: 1CH Wi-Fi Dimmer Module
    description: Unbenutzt und originalverpackt
    category: 161/168
    price: 10
    price_type: NEGOTIABLE
    shipping_type: SHIPPING
    shipping_costs: 5.49
    shipping_options:
      - Hermes_Päckchen
    sell_directly: false
    images: []
    republication_interval: 30
    id: 3310837392
    created_on: '2026-01-27T00:00:00+01:00'
    updated_on:
    """


@pytest.fixture
def client(tmp_path:Path) -> Iterator[TestClient]:
    cfg = Settings(data_dir = tmp_path, secret_key = SCHLUESSEL, dev_mode = True,
                   chromium = "/usr/bin/chromium")
    cfg.profiles_dir.mkdir(parents = True, exist_ok = True)
    with TestClient(create_app(cfg)) as c:
        c.post("/api/auth/einrichten", json = {"name": "steffen", "passwort": PASSWORT})
        c.post("/api/profile", json = {"slug": PROFIL, "anzeigename": "Testprofil"})
        yield c


@pytest.fixture
def anzeige(tmp_path:Path) -> Path:
    """Legt eine Anzeigendatei im Profil an und gibt ihren Ordner zurueck."""
    ordner = tmp_path / "profiles" / PROFIL / "downloaded-ads" / "ad_1"
    ordner.mkdir(parents = True, exist_ok = True)
    (ordner / "ad_1.yaml").write_text(textwrap.dedent(ANZEIGE), encoding = "utf-8")
    return ordner


def _hochladen(client:TestClient, inhalt:bytes, name:str = "bild.jpg") -> httpx.Response:
    # Zwischenschritt statt direktem `return`: TestClient ist nicht durchgehend
    # typisiert, mypy sieht sonst ein Any an einer Stelle mit Typzusage.
    antwort:httpx.Response = client.post(
        "/api/bestand/bild",
        params = {"profil": PROFIL, "datei": DATEI},
        files = {"bild": (name, inhalt, "application/octet-stream")},
    )
    return antwort


class TestBildformate:
    """K-2.6-001: Backend und Fehlermeldung nennen dieselben Formate."""

    @pytest.mark.parametrize(("inhalt", "endung"), [
        (JPEG, ".jpg"), (PNG, ".png"), (GIF, ".gif"),
    ])
    def test_erlaubte_formate_werden_angenommen(
        self, client:TestClient, anzeige:Path, inhalt:bytes, endung:str,
    ) -> None:
        antwort = _hochladen(client, inhalt)
        assert antwort.status_code == 201, antwort.text
        assert antwort.json()["name"].endswith(endung)

    def test_webp_wird_abgelehnt(self, client:TestClient, anzeige:Path) -> None:
        """WebP bringt sonst den ganzen naechsten Lauf zu Fall.

        `ad_loading.resolve_ad_images` wirft dabei einen AssertionError, der in
        der Ladeschleife nicht abgefangen wird - es scheitert also nicht nur
        die betroffene Anzeige.
        """
        antwort = _hochladen(client, WEBP, name = "bild.webp")
        assert antwort.status_code == 415, antwort.text
        meldung = antwort.json()["fehler"]["meldung"]
        assert "JPEG, PNG und GIF" in meldung
        assert not list(anzeige.glob("*__img*")), "es darf keine Datei entstanden sein"

    def test_keine_bilddatei(self, client:TestClient, anzeige:Path) -> None:
        antwort = _hochladen(client, b"nur Text, kein Bild")
        assert antwort.status_code == 415
        assert not list(anzeige.glob("*__img*"))


class TestUploadgroesse:
    """K-2.6-002: Grenze greift vor dem Schreiben, nicht danach."""

    def test_leere_datei(self, client:TestClient, anzeige:Path) -> None:
        antwort = _hochladen(client, b"")
        assert antwort.status_code == 400
        assert not list(anzeige.glob("*__img*"))

    def test_genau_zulaessig(self, client:TestClient, anzeige:Path) -> None:
        inhalt = JPEG + b"\x00" * (MAX_BYTES - len(JPEG))
        assert len(inhalt) == MAX_BYTES
        antwort = _hochladen(client, inhalt)
        assert antwort.status_code == 201, antwort.text

    def test_knapp_zu_gross(self, client:TestClient, anzeige:Path) -> None:
        inhalt = JPEG + b"\x00" * (MAX_BYTES + 1 - len(JPEG))
        assert len(inhalt) == MAX_BYTES + 1
        antwort = _hochladen(client, inhalt)
        assert antwort.status_code == 413, antwort.text
        assert not list(anzeige.glob("*__img*")), "kein halbes Bild zurücklassen"

    def test_deutlich_zu_gross(self, client:TestClient, anzeige:Path) -> None:
        """Rund 20 MB - die Groessenordnung eines Handyfotos aus dem Auftrag."""
        inhalt = JPEG + b"\x00" * (20 * 1024 * 1024)
        antwort = _hochladen(client, inhalt)
        assert antwort.status_code == 413, antwort.text
        assert not list(anzeige.glob("*__img*"))


class TestSpeicherdeckel:
    """K-2.6-002: Es darf nie mehr als MAX_BYTES + 1 im Speicher landen."""

    async def test_liest_hoechstens_die_grenze_plus_eins(self) -> None:
        from anzeigen_studio.api.bestand import _begrenzt_lesen  # noqa: PLC2701 - genau das ist der Prüfgegenstand
        from anzeigen_studio.core.errors import FachlicherFehler

        class RiesigerUpload:
            """Tut so, als kaeme unendlich viel - und zaehlt mit."""

            def __init__(self) -> None:
                self.geliefert = 0

            async def read(self, groesse:int = -1) -> bytes:
                menge = 64 * 1024 if groesse < 0 else groesse
                self.geliefert += menge
                return b"\x00" * menge

        upload = RiesigerUpload()
        grenze = 1024 * 1024
        with pytest.raises(FachlicherFehler) as fehler:
            await _begrenzt_lesen(upload, grenze)  # type: ignore[arg-type]

        assert fehler.value.status == 413
        assert upload.geliefert <= grenze + 1, (
            f"es wurden {upload.geliefert} Bytes gelesen, erlaubt sind {grenze + 1}"
        )


class TestBildreihenfolge:
    """K-2.6-003: Die neue Reihenfolge muss dieselben Bilder genau einmal nennen."""

    def _zwei_bilder(self, client:TestClient) -> list[str]:
        erstes = _hochladen(client, JPEG).json()["name"]
        zweites = _hochladen(client, PNG).json()["name"]
        return [erstes, zweites]

    def _sortieren(self, client:TestClient, bilder:list[str]) -> httpx.Response:
        antwort:httpx.Response = client.put(
            "/api/bestand/anzeige",
            params = {"profil": PROFIL},
            json = {"datei": DATEI, "felder": {"images": bilder}},
        )
        return antwort

    def _gespeicherte_reihenfolge(self, client:TestClient) -> list[str]:
        """Die Liste aus der Datei - `kopf.bilder` ist nur die Anzahl."""
        antwort = client.get(
            "/api/bestand/anzeige", params = {"profil": PROFIL, "datei": DATEI},
        )
        assert antwort.status_code == 200, antwort.text
        return [str(b) for b in antwort.json()["felder"]["images"]]

    def test_gueltiges_umsortieren(self, client:TestClient, anzeige:Path) -> None:
        a, b = self._zwei_bilder(client)
        antwort = self._sortieren(client, [b, a])
        assert antwort.status_code == 200, antwort.text
        assert self._gespeicherte_reihenfolge(client) == [b, a]

    def test_doppelter_name_wird_abgelehnt(self, client:TestClient, anzeige:Path) -> None:
        """Mit Mengenvergleich fiel das nicht auf - `[a, b, b]` ist mengengleich `{a, b}`."""
        a, b = self._zwei_bilder(client)
        antwort = self._sortieren(client, [a, b, b])
        assert antwort.status_code == 400, antwort.text
        assert "mehrfach" in antwort.json()["fehler"]["meldung"]

    def test_fehlendes_bild_wird_abgelehnt(self, client:TestClient, anzeige:Path) -> None:
        a, _b = self._zwei_bilder(client)
        antwort = self._sortieren(client, [a])
        assert antwort.status_code == 400, antwort.text

    def test_zusaetzliches_bild_wird_abgelehnt(self, client:TestClient, anzeige:Path) -> None:
        a, b = self._zwei_bilder(client)
        antwort = self._sortieren(client, [a, b, "gibtsnicht.jpg"])
        assert antwort.status_code == 400, antwort.text

    def test_fuenf_bilder_behalten_ihre_reihenfolge(self, client:TestClient, anzeige:Path) -> None:
        """Aus dem Auftrag: Pruefung mit fuenf Bildern."""
        namen = [_hochladen(client, JPEG).json()["name"] for _ in range(5)]
        assert len(set(namen)) == 5, "jede Datei braucht einen eigenen Namen"

        umgedreht = list(reversed(namen))
        antwort = self._sortieren(client, umgedreht)
        assert antwort.status_code == 200, antwort.text
        assert self._gespeicherte_reihenfolge(client) == umgedreht


class TestVersandgroessen:
    """K-2.7-001: Gemischte Groessen werden serverseitig abgelehnt."""

    def _speichern(self, client:TestClient, pakete:list[str]) -> httpx.Response:
        antwort:httpx.Response = client.put(
            "/api/bestand/anzeige",
            params = {"profil": PROFIL},
            json = {"datei": DATEI, "felder": {"shipping_options": pakete}},
        )
        return antwort

    def test_gleiche_groesse_wird_gespeichert(self, client:TestClient, anzeige:Path) -> None:
        antwort = self._speichern(client, ["Hermes_Päckchen", "Hermes_S"])
        assert antwort.status_code == 200, antwort.text

    def test_gemischte_groessen_werden_abgelehnt(self, client:TestClient, anzeige:Path) -> None:
        antwort = self._speichern(client, ["Hermes_Päckchen", "Hermes_L"])
        assert antwort.status_code == 422, antwort.text
        assert antwort.json()["fehler"]["feld"] == "shipping_options"

    def test_datei_bleibt_bei_ablehnung_unveraendert(self, client:TestClient, anzeige:Path) -> None:
        """Eine abgelehnte Aenderung darf die Datei nicht angefasst haben."""
        vorher = (anzeige / "ad_1.yaml").read_text(encoding = "utf-8")

        antwort = self._speichern(client, ["Hermes_Päckchen", "DHL_20"])
        assert antwort.status_code == 422

        assert (anzeige / "ad_1.yaml").read_text(encoding = "utf-8") == vorher

    def test_hochladen_lehnt_gemischte_groessen_ab(self, client:TestClient, anzeige:Path) -> None:
        """Der Ablehnungspfad endet vor der Warteschlange - es laeuft kein Bot."""
        (anzeige / "ad_1.yaml").write_text(
            textwrap.dedent(ANZEIGE).replace(
                "shipping_options:\n  - Hermes_Päckchen\n",
                "shipping_options:\n  - Hermes_Päckchen\n  - Hermes_L\n",
            ),
            encoding = "utf-8",
        )
        # Gegenprobe: Ohne sie liefe der Test gruen, falls die Ersetzung
        # danebengeht - und wuerde dabei sogar einen Lauf einreihen.
        assert "Hermes_L" in (anzeige / "ad_1.yaml").read_text(encoding = "utf-8")
        antwort = client.post(
            "/api/bestand/hochladen",
            params = {"profil": PROFIL},
            json = {"datei": DATEI},
        )
        assert antwort.status_code == 422, antwort.text
        assert antwort.json()["fehler"]["feld"] == "shipping_options"


class TestKatalogRoute:
    """K-2.7-003: Eine kaputte Preisantwort darf keinen 500 erzeugen."""

    @pytest.fixture(autouse = True)
    def _kaputte_preisliste(self, monkeypatch:pytest.MonkeyPatch) -> None:
        from anzeigen_studio.katalog import daten

        class Antwort:
            def read(self) -> bytes:
                # Formal gueltiges JSON, aber die Eintraege sind keine Objekte.
                return b'{"data": {"shippingOptionsResponse": {"options": ["kaputt", 1, null]}}}'

            def __enter__(self) -> Antwort:
                return self

            def __exit__(self, *_:object) -> None:
                return

        monkeypatch.setattr(daten, "_preise_zwischenspeicher", None)
        monkeypatch.setattr(urllib.request, "urlopen", lambda *a, **k: Antwort())

    def test_versandpakete_bleiben_abrufbar(self, client:TestClient) -> None:
        antwort = client.get("/api/katalog/versandpakete")
        assert antwort.status_code == 200, antwort.text

        pakete = antwort.json()
        assert len(pakete) == 9, "die Auswahl muss vollständig bleiben"
        assert all(p["preis"] is None for p in pakete), "ohne Preise, aber vorhanden"
        assert all(p["groesse"] in {"Klein", "Mittel", "Groß"} for p in pakete)


class TestSonderzeichen:
    """K-2.6-004: Sonderzeichen duerfen weder im Anzeigennamen noch im Dateinamen stoeren."""

    def test_umlaute_im_anzeigennamen(self, client:TestClient, tmp_path:Path) -> None:
        """Der Bildname wird aus dem Dateinamen der Anzeige gebildet.

        Steht dort ein Umlaut, steht er anschliessend auch im Bildnamen - und
        muss den ganzen Weg durch YAML, Dateisystem und URL ueberstehen.
        """
        ordner = tmp_path / "profiles" / PROFIL / "downloaded-ads" / "büro-stuhl"
        ordner.mkdir(parents = True, exist_ok = True)
        (ordner / "büro-stuhl.yaml").write_text(textwrap.dedent(ANZEIGE), encoding = "utf-8")
        pfad = "downloaded-ads/büro-stuhl/büro-stuhl.yaml"

        antwort = client.post(
            "/api/bestand/bild",
            params = {"profil": PROFIL, "datei": pfad},
            files = {"bild": ("foto.jpg", JPEG, "application/octet-stream")},
        )
        assert antwort.status_code == 201, antwort.text

        name = antwort.json()["name"]
        assert name == "büro-stuhl__img1.jpg"
        assert (ordner / name).is_file()

        # Und wieder ausliefern lassen - daran scheitert es sonst als Naechstes.
        bild = client.get(
            "/api/bestand/bild",
            params = {"profil": PROFIL, "datei": pfad, "name": name},
        )
        assert bild.status_code == 200, bild.text

    def test_sonderzeichen_im_hochgeladenen_dateinamen(
        self, client:TestClient, anzeige:Path,
    ) -> None:
        """Der mitgeschickte Name wird verworfen - er darf nichts kaputtmachen."""
        antwort = client.post(
            "/api/bestand/bild",
            params = {"profil": PROFIL, "datei": DATEI},
            files = {"bild": ("mein Foto (2) – Kopie #1.jpg", JPEG, "application/octet-stream")},
        )
        assert antwort.status_code == 201, antwort.text
        assert antwort.json()["name"] == "ad_1__img1.jpg"

    def test_pfadausbruch_im_dateinamen(self, client:TestClient, anzeige:Path) -> None:
        """Ein `..` im mitgeschickten Namen darf nirgendwo landen."""
        antwort = client.post(
            "/api/bestand/bild",
            params = {"profil": PROFIL, "datei": DATEI},
            files = {"bild": ("../../entwischt.jpg", JPEG, "application/octet-stream")},
        )
        assert antwort.status_code == 201, antwort.text
        assert antwort.json()["name"] == "ad_1__img1.jpg"
        assert not (anzeige.parent.parent.parent / "entwischt.jpg").exists()
