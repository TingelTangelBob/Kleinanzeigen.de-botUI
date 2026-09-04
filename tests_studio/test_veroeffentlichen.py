# SPDX-FileCopyrightText: © Anzeigen-Studio contributors
# SPDX-ArtifactOfProjectHomePage: https://github.com/TingelTangelBob/Kleinanzeigen.de-botUI/
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# Neue Anzeige veroeffentlichen (AP-3.8).
#
# Die Anzeigennummer entscheidet, welcher Bot-Befehl laeuft. Der teure Fehler
# waere `publish` fuer eine Anzeige MIT Nummer: Das loescht die bestehende und
# stellt eine neue ein - Nummer, Aufrufe, Merker und Alter waeren weg
# (docs/RUNDLAUF.md, Abschnitt 4). Genau dagegen richten sich die Tests hier.

from __future__ import annotations

import base64
import textwrap
from typing import TYPE_CHECKING, Any

import pytest
from fastapi.testclient import TestClient

from anzeigen_studio.botbridge import konfiguration
from anzeigen_studio.core import db
from anzeigen_studio.core.settings import Settings
from anzeigen_studio.jobs import speicher
from anzeigen_studio.main import create_app

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path

SCHLUESSEL = base64.b64encode(b"0123456789abcdef0123456789abcdef").decode()
PASSWORT = "ein-ausreichend-langes-Passwort"
PROFIL = "testprofil"

#: Mit Nummer - war schon einmal online.
VEROEFFENTLICHT = """
    active: true
    type: OFFER
    title: 1CH Wi-Fi Dimmer Module
    description: Unbenutzt und originalverpackt
    category: 161/168
    price: 10
    price_type: NEGOTIABLE
    shipping_type: PICKUP
    sell_directly: false
    images: []
    republication_interval: 30
    id: 3310837392
    created_on: '2026-01-27T00:00:00+01:00'
    updated_on:
    """

#: Ohne Nummer - lokal angelegt, nie online (der Samsung-SSD-Fall).
NEU = """
    active: true
    type: OFFER
    title: Samsung SSD 980 1TB NVMe
    description: Wenig genutzt, aus einem Aufruestprojekt uebrig geblieben.
    category: 161/168
    price: 45
    price_type: FIXED
    shipping_type: PICKUP
    sell_directly: false
    images: []
    """


@pytest.fixture
def client(tmp_path: Path) -> Iterator[TestClient]:
    cfg = Settings(data_dir = tmp_path, secret_key = SCHLUESSEL, dev_mode = True,
                   chromium = "/usr/bin/chromium")
    cfg.profiles_dir.mkdir(parents = True, exist_ok = True)
    with TestClient(create_app(cfg)) as c:
        c.post("/api/auth/einrichten", json = {"name": "steffen", "passwort": PASSWORT})
        c.post("/api/profile", json = {"slug": PROFIL, "anzeigename": "Testprofil"})
        yield c


def _anlegen(tmp_path: Path, bucket: str, ordner: str, inhalt: str) -> Path:
    ziel = tmp_path / "profiles" / PROFIL / bucket / ordner
    ziel.mkdir(parents = True, exist_ok = True)
    datei = ziel / f"{ordner}.yaml"
    datei.write_text(textwrap.dedent(inhalt), encoding = "utf-8")
    return datei


@pytest.fixture
def mit_nummer(tmp_path: Path) -> str:
    _anlegen(tmp_path, "downloaded-ads", "ad_1", VEROEFFENTLICHT)
    return "downloaded-ads/ad_1/ad_1.yaml"


@pytest.fixture
def ohne_nummer(tmp_path: Path) -> str:
    _anlegen(tmp_path, "ads", "ad_9", NEU)
    return "ads/ad_9/ad_9.yaml"


def _job(client: TestClient, job_id: int) -> dict[str, Any]:
    antwort = client.get(f"/api/jobs/{job_id}")
    assert antwort.status_code == 200, antwort.text
    daten: dict[str, Any] = antwort.json()
    return daten


class TestBefehlswahl:

    def test_mit_nummer_wird_update(self, client: TestClient, mit_nummer: str) -> None:
        antwort = client.post(
            "/api/bestand/hochladen", params = {"profil": PROFIL}, json = {"datei": mit_nummer},
        )
        assert antwort.status_code == 202, antwort.text
        assert antwort.json()["befehl"] == "update"

        job = _job(client, antwort.json()["job_id"])
        assert job["befehl"] == "update"
        assert job["argumente"] == ["--ads=3310837392"]

    def test_ohne_nummer_wird_publish(self, client: TestClient, ohne_nummer: str) -> None:
        antwort = client.post(
            "/api/bestand/hochladen", params = {"profil": PROFIL}, json = {"datei": ohne_nummer},
        )
        assert antwort.status_code == 202, antwort.text
        assert antwort.json()["befehl"] == "publish"

        job = _job(client, antwort.json()["job_id"])
        assert job["befehl"] == "publish"
        # `--ads=new` statt leer (AP-3.11): waehlt Anzeigen OHNE Nummer und
        # ignoriert `republication_interval` - der `publish`-Standard `--ads=due`
        # wuerde eine nie online gewesene Anzeige mit frischem `created_on` still
        # ueberspringen (der Samsung-SSD-Fall).
        assert job["argumente"] == ["--ads=new"]

    def test_ohne_nummer_umgeht_den_created_on_skip(
        self, client: TestClient, tmp_path: Path,
    ) -> None:
        """Selbst mit von Hand gesetztem `created_on` laeuft `publish --ads=new`.

        `--ads=due` haelt eine Anzeige mit `updated_on or created_on` juenger als
        `republication_interval` fuer "schon veroeffentlicht" und laedt sie gar
        nicht erst. `--ads=new` sieht nur die fehlende Nummer.
        """
        inhalt = textwrap.dedent(NEU) + "created_on: '2026-09-01T00:00:00+00:00'\n"
        _anlegen(tmp_path, "ads", "ad_7", inhalt)

        antwort = client.post(
            "/api/bestand/hochladen", params = {"profil": PROFIL},
            json = {"datei": "ads/ad_7/ad_7.yaml"},
        )
        assert antwort.status_code == 202, antwort.text
        job = _job(client, antwort.json()["job_id"])
        assert job["befehl"] == "publish"
        assert job["argumente"] == ["--ads=new"]

    def test_mit_nummer_niemals_publish(self, client: TestClient, mit_nummer: str) -> None:
        """Der teure Fehler: `publish` loescht die bestehende Anzeige.

        Eigener Test, obwohl `test_mit_nummer_wird_update` dasselbe abdeckt -
        diese Zusage ist der Grund fuer das ganze Paket und soll beim Lesen der
        Testnamen ins Auge fallen.
        """
        antwort = client.post(
            "/api/bestand/hochladen", params = {"profil": PROFIL}, json = {"datei": mit_nummer},
        )
        job = _job(client, antwort.json()["job_id"])
        assert job["befehl"] != "publish"

    def test_lauf_sieht_nur_diese_datei(
        self, client: TestClient, ohne_nummer: str, tmp_path: Path,
    ) -> None:
        """`--ads=new` waehlt nach Kennung, nicht nach Datei - die Grenze
        liegt trotzdem in der Konfiguration.

        Der Dateiausschnitt steht am Job und nicht in der HTTP-Ausgabe -
        gelesen wird er deshalb aus dem Jobspeicher, nicht aus der Antwort.
        Ohne diese Grenze stellte ein `publish --ads=new`-Lauf jede Anzeige
        ohne Nummer im Bestand ein.
        """
        antwort = client.post(
            "/api/bestand/hochladen", params = {"profil": PROFIL}, json = {"datei": ohne_nummer},
        )
        assert antwort.status_code == 202, antwort.text

        conn = db.connect(Settings(data_dir = tmp_path, secret_key = SCHLUESSEL, dev_mode = True,
                               chromium = "/usr/bin/chromium").database_path)
        try:
            job = speicher.holen(conn, antwort.json()["job_id"])
        finally:
            conn.close()
        assert job is not None
        assert job.anzeigen_glob == f"./{ohne_nummer}"
        assert "*" not in (job.anzeigen_glob or "")


class TestPruefungBleibt:
    """Was vor AP-3.8 abgewiesen wurde, wird weiter abgewiesen."""

    def test_gemischte_versandgroessen_bleiben_422(
        self, client: TestClient, tmp_path: Path,
    ) -> None:
        inhalt = textwrap.dedent(NEU).replace(
            "shipping_type: PICKUP\n",
            "shipping_type: SHIPPING\nshipping_costs: 5.49\n"
            "shipping_options:\n  - Hermes_Päckchen\n  - Hermes_L\n",
        )
        _anlegen(tmp_path, "ads", "ad_8", inhalt)
        assert "Hermes_L" in (
            tmp_path / "profiles" / PROFIL / "ads" / "ad_8" / "ad_8.yaml"
        ).read_text(encoding = "utf-8")

        antwort = client.post(
            "/api/bestand/hochladen", params = {"profil": PROFIL},
            json = {"datei": "ads/ad_8/ad_8.yaml"},
        )
        assert antwort.status_code == 422, antwort.text
        assert antwort.json()["fehler"]["feld"] == "shipping_options"

    def test_unlesbare_anzeige_bleibt_422(self, client: TestClient, tmp_path: Path) -> None:
        ziel = tmp_path / "profiles" / PROFIL / "ads" / "kaputt"
        ziel.mkdir(parents = True)
        (ziel / "kaputt.yaml").write_text("title: [unbalanciert\n", encoding = "utf-8")

        antwort = client.post(
            "/api/bestand/hochladen", params = {"profil": PROFIL},
            json = {"datei": "ads/kaputt/kaputt.yaml"},
        )
        assert antwort.status_code == 422, antwort.text


class TestTitelloeschenGesperrt:
    """Beim Veroeffentlichen darf keine fremde Anzeige online verschwinden.

    `delete_flow.delete_ad` sucht fuer eine Anzeige OHNE Nummer bei
    eingeschaltetem `delete_old_ads_by_title` unter den veroeffentlichten
    Anzeigen nach demselben Titel und loescht den Treffer, bevor es neu
    einstellt. Aus "neu einstellen" wuerde sonst stillschweigend "eine andere
    Anzeige ersetzen".
    """

    def test_einzelner_publish_lauf_sperrt_titelloeschen(self, tmp_path: Path) -> None:
        ziel = tmp_path / "config.yaml"
        konfiguration.schreiben(
            ziel, {"publishing": {"delete_old_ads_by_title": True}},
            anzeigen_glob = "./ads/ad_9/ad_9.yaml",
            titelloeschen_sperren = True,
        )
        text = ziel.read_text(encoding = "utf-8")
        assert "delete_old_ads_by_title: false" in text.lower()

    def test_ohne_sperre_bleibt_die_einstellung(self, tmp_path: Path) -> None:
        """Gegenprobe: Von der Laufliste gestartete Laeufe behalten die Wahl."""
        ziel = tmp_path / "config.yaml"
        konfiguration.schreiben(
            ziel, {"publishing": {"delete_old_ads_by_title": True}},
            anzeigen_glob = "./ads/**/ad_*.{yaml,yml,json}",
        )
        text = ziel.read_text(encoding = "utf-8")
        assert "delete_old_ads_by_title: true" in text.lower()
