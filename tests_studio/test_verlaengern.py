# SPDX-FileCopyrightText: © Anzeigen-Studio contributors
# SPDX-ArtifactOfProjectHomePage: https://github.com/TingelTangelBob/Kleinanzeigen.de-botUI/
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# Automatisches kostenloses Verlaengern (AP-3.15).
#
# Die wichtigsten Tests belegen Bremsen: ohne Schalter kein Lauf, ohne Zugang
# kein Lauf, zweiter Tick am selben Tag kein zweiter extend. Dazu der Glob-
# Fix: `extend` zielt auf downloaded-ads, nicht auf ./ads.

from __future__ import annotations

import base64
import sqlite3
from typing import TYPE_CHECKING, Any

import pytest

from anzeigen_studio.bestand import tagesabgleich, verlaengern
from anzeigen_studio.core import db, zugang
from anzeigen_studio.core import profile as profile_dienst
from anzeigen_studio.core.settings import Settings
from anzeigen_studio.jobs import speicher
from anzeigen_studio.jobs.modelle import JobZustand
from anzeigen_studio.jobs.warteschlange import (
    GLOB_HERUNTERGELADEN,
    GLOB_LOKAL,
    standard_anzeigen_glob,
)
from anzeigen_studio.jobs.zeitgeber import Zeitgeber

if TYPE_CHECKING:
    from pathlib import Path

SCHLUESSEL = base64.b64encode(b"0123456789abcdef0123456789abcdef").decode()


class ErsatzWarteschlange:
    """Merkt sich, was eingereiht wurde. Startet nichts."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn
        self.eingereiht: list[tuple[int, str, list[str], str | None]] = []

    async def einreihen(
        self, conn: sqlite3.Connection, profil_id: int, befehl: str, argumente: list[str],
        *, profil_verzeichnis: Path, anzeigen_glob: str | None = None,
    ) -> int:
        _ = profil_verzeichnis
        self.eingereiht.append((profil_id, befehl, list(argumente), anzeigen_glob))
        with db.transaction(conn):
            return speicher.einreihen(
                conn, profil_id, befehl, argumente, anzeigen_glob = anzeigen_glob,
            )


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


def _zeitgeber(cfg: Settings, ws: Any) -> Zeitgeber:  # noqa: ANN401
    return Zeitgeber(cfg, ws)


# -- Glob -------------------------------------------------------------------

class TestExtendGlob:
    def test_extend_ohne_glob_nimmt_downloaded_ads(self) -> None:
        assert standard_anzeigen_glob("extend") == GLOB_HERUNTERGELADEN
        assert standard_anzeigen_glob("extend", None) == GLOB_HERUNTERGELADEN

    def test_andere_befehle_behalten_lokalen_ordner(self) -> None:
        assert standard_anzeigen_glob("publish") == GLOB_LOKAL
        assert standard_anzeigen_glob("download") == GLOB_LOKAL

    def test_expliziter_glob_gewinnt(self) -> None:
        assert standard_anzeigen_glob("extend", "./ads/x.yaml") == "./ads/x.yaml"


# -- Zeitgeber --------------------------------------------------------------

class TestZeitgeberVerlaengern:
    @pytest.mark.asyncio
    async def test_ohne_schalter_kein_lauf(
        self, umgebung: tuple[Settings, sqlite3.Connection, int, Path],
    ) -> None:
        cfg, conn, profil_id, _ = umgebung
        _mit_zugang(conn, profil_id)
        ws = ErsatzWarteschlange(conn)
        await _zeitgeber(cfg, ws).tick()
        assert ws.eingereiht == []

    @pytest.mark.asyncio
    async def test_ohne_zugangsdaten_kein_lauf(
        self, umgebung: tuple[Settings, sqlite3.Connection, int, Path],
    ) -> None:
        cfg, conn, profil_id, _ = umgebung
        with db.transaction(conn):
            verlaengern.einschalten(conn, profil_id, an = True)
        ws = ErsatzWarteschlange(conn)
        await _zeitgeber(cfg, ws).tick()
        assert ws.eingereiht == []
        zustand = verlaengern.lesen(conn, profil_id)
        assert zustand.letztes_ergebnis is not None
        assert "Zugangsdaten" in zustand.letztes_ergebnis

    @pytest.mark.asyncio
    async def test_eingeschaltet_reiht_extend_mit_downloaded_glob_ein(
        self, umgebung: tuple[Settings, sqlite3.Connection, int, Path],
    ) -> None:
        cfg, conn, profil_id, _ = umgebung
        _mit_zugang(conn, profil_id)
        with db.transaction(conn):
            verlaengern.einschalten(conn, profil_id, an = True)
        ws = ErsatzWarteschlange(conn)
        await _zeitgeber(cfg, ws).tick()
        assert len(ws.eingereiht) == 1
        _, befehl, _, glob = ws.eingereiht[0]
        assert befehl == "extend"
        assert glob == GLOB_HERUNTERGELADEN
        zustand = verlaengern.lesen(conn, profil_id)
        assert zustand.letzter_tag == verlaengern.heutiger_tag()
        assert zustand.job_id is not None

    @pytest.mark.asyncio
    async def test_zweiter_tick_am_selben_tag_kein_zweiter_extend(
        self, umgebung: tuple[Settings, sqlite3.Connection, int, Path],
    ) -> None:
        cfg, conn, profil_id, _ = umgebung
        _mit_zugang(conn, profil_id)
        with db.transaction(conn):
            verlaengern.einschalten(conn, profil_id, an = True)
        ws = ErsatzWarteschlange(conn)
        zeitgeber = _zeitgeber(cfg, ws)
        await zeitgeber.tick()
        job_id = verlaengern.lesen(conn, profil_id).job_id
        assert job_id is not None
        # Lauf als fertig markieren, sonst wertet der naechste Tick nur aus.
        with db.transaction(conn):
            speicher.zustand_setzen(conn, job_id, JobZustand.FERTIG, meldung = "ok")
        await zeitgeber.tick()  # wertet aus
        await zeitgeber.tick()  # wuerde sonst erneut einreihen
        extend_laeufe = [e for e in ws.eingereiht if e[1] == "extend"]
        assert len(extend_laeufe) == 1

    @pytest.mark.asyncio
    async def test_abgleich_hat_vorrang_am_selben_tag(
        self, umgebung: tuple[Settings, sqlite3.Connection, int, Path],
    ) -> None:
        cfg, conn, profil_id, _ = umgebung
        _mit_zugang(conn, profil_id)
        with db.transaction(conn):
            tagesabgleich.einschalten(conn, profil_id, an = True)
            verlaengern.einschalten(conn, profil_id, an = True)
        ws = ErsatzWarteschlange(conn)
        await _zeitgeber(cfg, ws).tick()
        assert len(ws.eingereiht) == 1
        assert ws.eingereiht[0][1] == "download"


# -- HTTP -------------------------------------------------------------------

class TestVerlaengernApi:
    """Schalter-API. Kein Test startet den Zeitgeber gegen ein echtes Konto."""

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
        antwort = client.get("/api/verlaengern?profil=haushalt")
        assert antwort.status_code == 200
        daten = antwort.json()
        assert daten["eingeschaltet"] is False
        assert daten["heute_gelaufen"] is False

    def test_schalten_und_zuruecknehmen(self, client: Any) -> None:  # noqa: ANN401
        an = client.put("/api/verlaengern?profil=haushalt", json = {"eingeschaltet": True})
        assert an.status_code == 200
        assert an.json()["eingeschaltet"] is True
        assert client.get("/api/verlaengern?profil=haushalt").json()["eingeschaltet"] is True

        aus = client.put("/api/verlaengern?profil=haushalt", json = {"eingeschaltet": False})
        assert aus.json()["eingeschaltet"] is False

    def test_unbekanntes_profil(self, client: Any) -> None:  # noqa: ANN401
        assert client.get("/api/verlaengern?profil=gibt-es-nicht").status_code == 404
