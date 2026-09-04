# SPDX-FileCopyrightText: © Anzeigen-Studio contributors
# SPDX-ArtifactOfProjectHomePage: https://github.com/TingelTangelBob/Kleinanzeigen.de-botUI/
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# Taeglicher Abgleich der eigenen Anzeigen (AP-3.12).
#
# Die wichtigsten Tests dieser Datei sind die, die belegen, dass NICHTS
# passiert: `test_ohne_schalter_kein_lauf`, `test_ohne_zugangsdaten_kein_lauf`
# und `test_zweiter_tick_am_selben_tag_reiht_nichts_ein`. Der Abgleich ist der
# einzige Weg, auf dem ohne Knopfdruck ein Lauf gegen das echte Konto entsteht -
# jede seiner Bremsen braucht einen Beleg.
#
# Kein Test spricht mit kleinanzeigen.de. Die Warteschlange wird durch eine
# Attrappe ersetzt, die sich das Einreihen nur merkt.

from __future__ import annotations

import base64
import sqlite3
import textwrap
from typing import TYPE_CHECKING, Any

import pytest

from anzeigen_studio.bestand import tagesabgleich
from anzeigen_studio.core import db, zugang
from anzeigen_studio.core import profile as profile_dienst
from anzeigen_studio.core.settings import Settings
from anzeigen_studio.jobs import speicher
from anzeigen_studio.jobs.modelle import JobZustand
from anzeigen_studio.jobs.zeitgeber import Zeitgeber

if TYPE_CHECKING:
    from pathlib import Path

SCHLUESSEL = base64.b64encode(b"0123456789abcdef0123456789abcdef").decode()

ANZEIGE = """
    active: {aktiv}
    type: OFFER
    title: {titel}
    description: Unbenutzt
    price: 10
    images: []
    id: {nummer}
    """


def _anzeige(
    wurzel: Path, ordner: str, name: str, *,
    titel: str = "Dimmer", nummer: str = "3310837392", aktiv: str = "true",
) -> Path:
    ziel = wurzel / ordner / name
    ziel.mkdir(parents = True, exist_ok = True)
    datei = ziel / f"ad_{name}.yaml"
    datei.write_text(
        textwrap.dedent(ANZEIGE.format(titel = titel, nummer = nummer, aktiv = aktiv)),
        encoding = "utf-8",
    )
    return datei


class ErsatzWarteschlange:
    """Merkt sich, was eingereiht wurde. Startet nichts."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn
        self.eingereiht: list[tuple[int, str, list[str]]] = []

    async def einreihen(
        self, conn: sqlite3.Connection, profil_id: int, befehl: str, argumente: list[str],
        *, profil_verzeichnis: Path, anzeigen_glob: str | None = None,
    ) -> int:
        _ = profil_verzeichnis, anzeigen_glob
        self.eingereiht.append((profil_id, befehl, list(argumente)))
        with db.transaction(conn):
            return speicher.einreihen(conn, profil_id, befehl, argumente)


@pytest.fixture
def umgebung(tmp_path: Path) -> tuple[Settings, sqlite3.Connection, int, Path]:
    cfg = Settings(data_dir = tmp_path, secret_key = SCHLUESSEL, dev_mode = True,
                   chromium = "/usr/bin/chromium")
    cfg.profiles_dir.mkdir(parents = True, exist_ok = True)
    conn = db.connect(cfg.database_path)
    db.migrate(conn)
    p = profile_dienst.anlegen(conn, cfg.profiles_dir, "haushalt", "Haushalt")
    return cfg, conn, p.id, profile_dienst.pfade_fuer(cfg.profiles_dir, "haushalt").wurzel


def _mit_zugang(conn: sqlite3.Connection, profil_id: int) -> None:
    zugang.setzen(conn, profil_id, benutzername = "u@example.org",
                  passwort = "geheim", schluessel = SCHLUESSEL)


def _zeitgeber(cfg: Settings, ws: Any) -> Zeitgeber:  # noqa: ANN401 - Attrappe statt Warteschlange
    return Zeitgeber(cfg, ws)


# -- Stand aufnehmen ---------------------------------------------------------

class TestStandAufnehmen:

    def test_nur_eigene_mit_nummer(self, tmp_path: Path) -> None:
        _anzeige(tmp_path, "downloaded-ads", "eins", titel = "Eigene", nummer = "111")
        _anzeige(tmp_path, "fremde-ads", "zwei", titel = "Fremde", nummer = "222")
        # Ein Entwurf ohne Nummer war nie online - er hat keinen Plattformstatus.
        entwurf = tmp_path / "ads" / "drei"
        entwurf.mkdir(parents = True)
        (entwurf / "ad_drei.yaml").write_text(
            "active: true\ntype: OFFER\ntitle: Entwurf\ndescription: x\nprice: 1\nimages: []\n",
            encoding = "utf-8",
        )

        stand = tagesabgleich.stand_aufnehmen(tmp_path)

        assert set(stand) == {"111"}
        assert stand["111"] == {"titel": "Eigene", "online": True}

    def test_inaktive_eigene_gilt_als_nicht_online(self, tmp_path: Path) -> None:
        _anzeige(tmp_path, "downloaded-ads", "eins", nummer = "111", aktiv = "false")
        assert tagesabgleich.stand_aufnehmen(tmp_path)["111"]["online"] is False


# -- Vergleich ---------------------------------------------------------------

class TestVergleichen:

    def test_neu_geloescht(self) -> None:
        vorher = {"1": {"titel": "Tisch", "online": True}}
        nachher = {"1": {"titel": "Tisch", "online": False}}
        aenderungen = tagesabgleich.vergleichen(vorher, nachher)
        assert aenderungen.nicht_mehr_online == ["Tisch"]
        assert aenderungen.leer is False

    def test_wieder_online_und_neu_dazu(self) -> None:
        vorher = {"1": {"titel": "Tisch", "online": False}}
        nachher = {
            "1": {"titel": "Tisch", "online": True},
            "2": {"titel": "Stuhl", "online": True},
        }
        aenderungen = tagesabgleich.vergleichen(vorher, nachher)
        assert aenderungen.wieder_online == ["Tisch"]
        assert aenderungen.neu_dazu == ["Stuhl"]

    def test_verschwunden(self) -> None:
        aenderungen = tagesabgleich.vergleichen({"1": {"titel": "Tisch", "online": True}}, {})
        assert aenderungen.verschwunden == ["Tisch"]

    def test_unveraendert_meldet_nichts(self) -> None:
        gleich = {"1": {"titel": "Tisch", "online": True}}
        assert tagesabgleich.vergleichen(gleich, dict(gleich)).leer is True

    def test_ohne_vorherigen_stand_keine_erfundenen_aenderungen(self) -> None:
        # Sonst waere beim allerersten Lauf das ganze Konto "neu dazu".
        assert tagesabgleich.vergleichen({}, {"1": {"titel": "Tisch", "online": True}}).leer


class TestMeldungstext:

    def test_ohne_aenderung_keine_meldung(self) -> None:
        assert tagesabgleich.meldungstext(tagesabgleich.Aenderungen()) is None

    def test_zaehlt_statt_alle_zu_nennen(self) -> None:
        viele = tagesabgleich.Aenderungen(nicht_mehr_online = ["a", "b", "c", "d", "e"])
        gemeldet = tagesabgleich.meldungstext(viele)
        assert gemeldet is not None
        titel, text = gemeldet
        assert titel == "Täglicher Abgleich: 5 Änderungen"
        assert "und 2 weitere" in text

    def test_sagt_nicht_geloescht(self) -> None:
        # Die Plattform wirft Loeschen, Pausieren und "in Pruefung" zusammen -
        # "gelöscht" waere eine Behauptung, die die Daten nicht hergeben.
        gemeldet = tagesabgleich.meldungstext(
            tagesabgleich.Aenderungen(nicht_mehr_online = ["Tisch"]),
        )
        assert gemeldet is not None
        assert "gelöscht" not in gemeldet[1].lower()
        assert "Nicht mehr online" in gemeldet[1]


# -- Zeitgeber ---------------------------------------------------------------

class TestZeitgeber:

    @pytest.mark.asyncio
    async def test_ohne_schalter_kein_lauf(
        self, umgebung: tuple[Settings, sqlite3.Connection, int, Path],
    ) -> None:
        cfg, conn, profil_id, wurzel = umgebung
        _mit_zugang(conn, profil_id)
        _anzeige(wurzel, "downloaded-ads", "eins", nummer = "111")
        ws = ErsatzWarteschlange(conn)

        await _zeitgeber(cfg, ws).tick()

        assert ws.eingereiht == []
        assert tagesabgleich.lesen(conn, profil_id).letzter_tag is None

    @pytest.mark.asyncio
    async def test_ohne_zugangsdaten_kein_lauf(
        self, umgebung: tuple[Settings, sqlite3.Connection, int, Path],
    ) -> None:
        cfg, conn, profil_id, _ = umgebung
        with db.transaction(conn):
            tagesabgleich.einschalten(conn, profil_id, an = True)
        ws = ErsatzWarteschlange(conn)

        await _zeitgeber(cfg, ws).tick()

        assert ws.eingereiht == []
        ergebnis = tagesabgleich.lesen(conn, profil_id).letztes_ergebnis or ""
        assert "Zugangsdaten" in ergebnis

    @pytest.mark.asyncio
    async def test_eingeschaltet_reiht_einen_download_ein(
        self, umgebung: tuple[Settings, sqlite3.Connection, int, Path],
    ) -> None:
        cfg, conn, profil_id, wurzel = umgebung
        _mit_zugang(conn, profil_id)
        _anzeige(wurzel, "downloaded-ads", "eins", nummer = "111")
        with db.transaction(conn):
            tagesabgleich.einschalten(conn, profil_id, an = True)
        ws = ErsatzWarteschlange(conn)

        await _zeitgeber(cfg, ws).tick()

        # `download` ohne Nummernliste ist der Konto-Download. Mit `--ads=`
        # waere es das Nachladen einzelner fremder Anzeigen (AP-3.7).
        assert ws.eingereiht == [(profil_id, "download", [])]
        zustand = tagesabgleich.lesen(conn, profil_id)
        assert zustand.letzter_tag == tagesabgleich.heutiger_tag()
        assert zustand.job_id is not None
        assert zustand.vorher == {"111": {"titel": "Dimmer", "online": True}}

    @pytest.mark.asyncio
    async def test_zweiter_tick_am_selben_tag_prueft_reihenfolge_statt_download(
        self, umgebung: tuple[Settings, sqlite3.Connection, int, Path],
    ) -> None:
        cfg, conn, profil_id, wurzel = umgebung
        _mit_zugang(conn, profil_id)
        _anzeige(wurzel, "downloaded-ads", "eins", nummer = "111")
        with db.transaction(conn):
            tagesabgleich.einschalten(conn, profil_id, an = True)
        ws = ErsatzWarteschlange(conn)
        zeitgeber = _zeitgeber(cfg, ws)

        await zeitgeber.tick()
        job_id = tagesabgleich.lesen(conn, profil_id).job_id
        assert job_id is not None
        # Nach dem Tageslauf wird nur der kleine Reihenfolgenabgleich fällig;
        # ein zweiter vollständiger Download wird am selben Tag nicht erzeugt.
        with db.transaction(conn):
            speicher.zustand_setzen(conn, job_id, JobZustand.FERTIG)
        await zeitgeber.tick()
        await zeitgeber.tick()

        assert ws.eingereiht == [
            (profil_id, "download", []),
            (profil_id, "sync-order", []),
        ]

    @pytest.mark.asyncio
    async def test_geloeschte_anzeige_landet_in_der_glocke(
        self, umgebung: tuple[Settings, sqlite3.Connection, int, Path],
    ) -> None:
        cfg, conn, profil_id, wurzel = umgebung
        _mit_zugang(conn, profil_id)
        datei = _anzeige(wurzel, "downloaded-ads", "eins", titel = "Tisch", nummer = "111")
        with db.transaction(conn):
            tagesabgleich.einschalten(conn, profil_id, an = True)
        ws = ErsatzWarteschlange(conn)
        zeitgeber = _zeitgeber(cfg, ws)

        await zeitgeber.tick()
        job_id = tagesabgleich.lesen(conn, profil_id).job_id
        assert job_id is not None
        # Der Lauf hat den Stand der Plattform uebernommen: nicht mehr aktiv.
        datei.write_text(datei.read_text(encoding = "utf-8").replace(
            "active: true", "active: false"), encoding = "utf-8")
        with db.transaction(conn):
            speicher.zustand_setzen(conn, job_id, JobZustand.FERTIG)

        await zeitgeber.tick()

        gemeldet = tagesabgleich.meldungen(conn)
        assert len(gemeldet) == 1
        assert gemeldet[0]["art"] == "aenderung"
        assert "Tisch" in gemeldet[0]["text"]
        zustand = tagesabgleich.lesen(conn, profil_id)
        assert zustand.job_id is None
        assert "Tisch" in (zustand.letztes_ergebnis or "")

    @pytest.mark.asyncio
    async def test_ohne_aenderung_keine_meldung(
        self, umgebung: tuple[Settings, sqlite3.Connection, int, Path],
    ) -> None:
        cfg, conn, profil_id, wurzel = umgebung
        _mit_zugang(conn, profil_id)
        _anzeige(wurzel, "downloaded-ads", "eins", nummer = "111")
        with db.transaction(conn):
            tagesabgleich.einschalten(conn, profil_id, an = True)
        ws = ErsatzWarteschlange(conn)
        zeitgeber = _zeitgeber(cfg, ws)

        await zeitgeber.tick()
        job_id = tagesabgleich.lesen(conn, profil_id).job_id
        assert job_id is not None
        with db.transaction(conn):
            speicher.zustand_setzen(conn, job_id, JobZustand.FERTIG)
        await zeitgeber.tick()

        assert tagesabgleich.meldungen(conn) == []
        assert tagesabgleich.lesen(conn, profil_id).letztes_ergebnis == "Ohne Änderung durchgelaufen."

    @pytest.mark.asyncio
    async def test_gescheiterter_lauf_warnt_und_wird_spaeter_zurueckgenommen(
        self, umgebung: tuple[Settings, sqlite3.Connection, int, Path],
    ) -> None:
        cfg, conn, profil_id, wurzel = umgebung
        _mit_zugang(conn, profil_id)
        _anzeige(wurzel, "downloaded-ads", "eins", nummer = "111")
        with db.transaction(conn):
            tagesabgleich.einschalten(conn, profil_id, an = True)
        ws = ErsatzWarteschlange(conn)
        zeitgeber = _zeitgeber(cfg, ws)

        await zeitgeber.tick()
        job_id = tagesabgleich.lesen(conn, profil_id).job_id
        assert job_id is not None
        with db.transaction(conn):
            speicher.zustand_setzen(conn, job_id, JobZustand.GESCHEITERT)
        await zeitgeber.tick()

        gemeldet = tagesabgleich.meldungen(conn)
        assert [m["art"] for m in gemeldet] == ["fehlschlag"]

        # Am naechsten Tag laeuft es durch - die Warnung darf dann nicht stehen
        # bleiben, sonst lernt man, Warnungen zu ueberlesen.
        with db.transaction(conn):
            conn.execute("UPDATE abgleich SET letzter_tag = '2000-01-01' WHERE profil_id = ?",
                         (profil_id,))
        await zeitgeber.tick()
        zweiter = tagesabgleich.lesen(conn, profil_id).job_id
        assert zweiter is not None
        with db.transaction(conn):
            speicher.zustand_setzen(conn, zweiter, JobZustand.FERTIG)
        await zeitgeber.tick()

        assert tagesabgleich.meldungen(conn) == []


# -- HTTP --------------------------------------------------------------------

class TestApi:
    """Der Schalter auf HTTP-Ebene.

    Kein Test schaltet ein und wartet dann: Der Zeitgeber der laufenden
    Anwendung prueft erst nach seinem Takt, ein Lauf entsteht hier also nicht.
    """

    @pytest.fixture
    def client(self, tmp_path: Path) -> Any:  # noqa: ANN401 - TestClient, Import unten
        from fastapi.testclient import TestClient  # noqa: PLC0415 - nur hier gebraucht

        from anzeigen_studio.main import create_app  # noqa: PLC0415 - nur hier gebraucht

        cfg = Settings(data_dir = tmp_path, secret_key = SCHLUESSEL, dev_mode = True,
                       chromium = "/usr/bin/chromium")
        cfg.profiles_dir.mkdir(parents = True, exist_ok = True)
        with TestClient(create_app(cfg)) as c:
            c.post("/api/auth/einrichten",
                   json = {"name": "steffen", "passwort": "ein-ausreichend-langes-Passwort"})
            c.post("/api/profile", json = {"slug": "haushalt", "anzeigename": "Haushalt"})
            yield c

    def test_vorgabe_ist_aus(self, client: Any) -> None:  # noqa: ANN401
        antwort = client.get("/api/abgleich?profil=haushalt")
        assert antwort.status_code == 200
        daten = antwort.json()
        assert daten["eingeschaltet"] is False
        assert daten["letzter_lauf_am"] is None
        assert daten["zugang_vorhanden"] is False

    def test_schalten_und_zuruecknehmen(self, client: Any) -> None:  # noqa: ANN401
        an = client.put("/api/abgleich?profil=haushalt", json = {"eingeschaltet": True})
        assert an.status_code == 200
        assert an.json()["eingeschaltet"] is True
        assert client.get("/api/abgleich?profil=haushalt").json()["eingeschaltet"] is True

        aus = client.put("/api/abgleich?profil=haushalt", json = {"eingeschaltet": False})
        assert aus.json()["eingeschaltet"] is False

    def test_unbekanntes_profil(self, client: Any) -> None:  # noqa: ANN401
        assert client.get("/api/abgleich?profil=gibtsnicht").status_code == 404

    def test_meldungen_sind_anfangs_leer(self, client: Any) -> None:  # noqa: ANN401
        antwort = client.get("/api/abgleich/meldungen")
        assert antwort.status_code == 200
        assert antwort.json() == []

    def test_ohne_anmeldung_kein_zugriff(self, tmp_path: Path) -> None:
        from fastapi.testclient import TestClient  # noqa: PLC0415 - nur hier gebraucht

        from anzeigen_studio.main import create_app  # noqa: PLC0415 - nur hier gebraucht

        cfg = Settings(data_dir = tmp_path, secret_key = SCHLUESSEL, dev_mode = True,
                       chromium = "/usr/bin/chromium")
        cfg.profiles_dir.mkdir(parents = True, exist_ok = True)
        with TestClient(create_app(cfg)) as c:
            c.post("/api/auth/einrichten",
                   json = {"name": "steffen", "passwort": "ein-ausreichend-langes-Passwort"})
            c.post("/api/auth/abmelden")
            assert c.get("/api/abgleich?profil=haushalt").status_code == 401


class TestVerschwundeneAnzeige:
    """Die Lücke, die der reine Dateivergleich lässt (Befund 2026-09-05).

    `_download_all_ads` besucht nur, was auf der Übersichtsseite steht. Eine
    Anzeige, die ganz aus dem Konto verschwunden ist, wird nie angefasst - ihre
    Datei behält `active: true`, vorher und nachher sind identisch, und der
    Abgleich hätte geschwiegen. Die geordnete Kontoliste aus AP-3.14 beantwortet
    genau diese Frage.
    """

    def test_ohne_kontoliste_bleibt_es_beim_dateivergleich(self) -> None:
        gleich = {"111": {"titel": "Tisch", "online": True}}
        assert tagesabgleich.vergleichen(gleich, dict(gleich)).leer is True

    def test_fehlt_im_konto_heisst_nicht_mehr_online(self) -> None:
        gleich = {"111": {"titel": "Tisch", "online": True}}

        aenderungen = tagesabgleich.vergleichen(
            gleich, dict(gleich), plattform_ids = set(),
        )

        assert aenderungen.nicht_mehr_online == ["Tisch"]

    def test_im_konto_bleibt_still(self) -> None:
        gleich = {"111": {"titel": "Tisch", "online": True}}

        aenderungen = tagesabgleich.vergleichen(
            gleich, dict(gleich), plattform_ids = {"111"},
        )

        assert aenderungen.leer is True

    def test_kontoliste_meldet_nicht_zweimal(self) -> None:
        # Datei sagt schon "nicht online", Konto bestaetigt es - das ist keine
        # Aenderung gegenueber gestern.
        vorher = {"111": {"titel": "Tisch", "online": False}}
        nachher = {"111": {"titel": "Tisch", "online": False}}

        assert tagesabgleich.vergleichen(vorher, nachher, plattform_ids = set()).leer is True

    def test_neue_anzeige_bleibt_neu(self) -> None:
        # Die Kontoliste korrigiert nur den Online-Status bekannter Anzeigen.
        vorher = {"111": {"titel": "Tisch", "online": True}}
        nachher = {
            "111": {"titel": "Tisch", "online": True},
            "222": {"titel": "Stuhl", "online": True},
        }

        aenderungen = tagesabgleich.vergleichen(
            vorher, nachher, plattform_ids = {"111", "222"},
        )

        assert aenderungen.neu_dazu == ["Stuhl"]


class TestKontolisteFrische:
    """Eine veraltete Kontoliste wäre schlimmer als keine."""

    @pytest.mark.asyncio
    async def test_veraltete_liste_wird_nicht_benutzt(
        self, umgebung: tuple[Settings, sqlite3.Connection, int, Path],
    ) -> None:
        from anzeigen_studio.bestand import plattform_reihenfolge  # noqa: PLC0415

        cfg, conn, profil_id, wurzel = umgebung
        _mit_zugang(conn, profil_id)
        _anzeige(wurzel, "downloaded-ads", "eins", titel = "Tisch", nummer = "111")
        with db.transaction(conn):
            tagesabgleich.einschalten(conn, profil_id, an = True)
        ws = ErsatzWarteschlange(conn)
        zeitgeber = _zeitgeber(cfg, ws)

        await zeitgeber.tick()
        job_id = tagesabgleich.lesen(conn, profil_id).job_id
        assert job_id is not None

        # Eine Kontoliste von vorgestern, die 111 nicht kennt. Sie darf nicht
        # zaehlen - sonst meldete jeder Lauf eine Anzeige als verschwunden,
        # nur weil der Index alt ist.
        with db.transaction(conn):
            conn.execute(
                "INSERT INTO plattform_reihenfolge "
                "(profil_id, reihenfolge, geprueft_am, geaendert_am) VALUES (?, ?, ?, ?)",
                (profil_id, "[999]", "2020-01-01T00:00:00+00:00", "2020-01-01T00:00:00+00:00"),
            )
            speicher.zustand_setzen(conn, job_id, JobZustand.FERTIG)

        await zeitgeber.tick()

        assert tagesabgleich.meldungen(conn) == []

    @pytest.mark.asyncio
    async def test_frische_liste_meldet_die_verschwundene(
        self, umgebung: tuple[Settings, sqlite3.Connection, int, Path],
    ) -> None:
        from datetime import UTC, datetime, timedelta  # noqa: PLC0415

        cfg, conn, profil_id, wurzel = umgebung
        _mit_zugang(conn, profil_id)
        _anzeige(wurzel, "downloaded-ads", "eins", titel = "Tisch", nummer = "111")
        with db.transaction(conn):
            tagesabgleich.einschalten(conn, profil_id, an = True)
        ws = ErsatzWarteschlange(conn)
        zeitgeber = _zeitgeber(cfg, ws)

        await zeitgeber.tick()
        job_id = tagesabgleich.lesen(conn, profil_id).job_id
        assert job_id is not None

        # Der Lauf hat die Datei NICHT angefasst - sie steht weiter auf
        # active: true. Nur die Kontoliste weiss, dass 111 weg ist.
        frisch = (datetime.now(UTC) + timedelta(seconds = 5)).isoformat(timespec = "seconds")
        with db.transaction(conn):
            conn.execute(
                "INSERT INTO plattform_reihenfolge "
                "(profil_id, reihenfolge, geprueft_am, geaendert_am) VALUES (?, ?, ?, ?)",
                (profil_id, "[222]", frisch, frisch),
            )
            speicher.zustand_setzen(conn, job_id, JobZustand.FERTIG)

        await zeitgeber.tick()

        gemeldet = tagesabgleich.meldungen(conn)
        assert len(gemeldet) == 1
        assert "Tisch" in gemeldet[0]["text"]
        assert "Nicht mehr online" in gemeldet[0]["text"]
