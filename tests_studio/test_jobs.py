# SPDX-FileCopyrightText: © Anzeigen-Studio contributors
# SPDX-ArtifactOfProjectHomePage: https://github.com/TingelTangelBob/Kleinanzeigen.de-botUI/
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# Tests der Warteschlange (AP-1.6) und der Protokollspeicherung (AP-1.7).

from __future__ import annotations

import asyncio
import base64
import sqlite3
from typing import TYPE_CHECKING

import pytest

from anzeigen_studio.botbridge.events import Aufmerksamkeit, Ereignis, LaufErgebnis, Stufe
from anzeigen_studio.core import db
from anzeigen_studio.core import profile as profile_dienst
from anzeigen_studio.core import zugang
from anzeigen_studio.core.settings import Settings
from anzeigen_studio.jobs import speicher
from anzeigen_studio.jobs.modelle import JobZustand
from anzeigen_studio.jobs.taktung import Taktung
from anzeigen_studio.jobs.warteschlange import Warteschlange

if TYPE_CHECKING:
    from collections.abc import AsyncIterator
    from pathlib import Path

    from anzeigen_studio.botbridge.runner import LaufAuftrag

SCHLUESSEL = base64.b64encode(b"0123456789abcdef0123456789abcdef").decode()

#: In den Tests soll die Taktung nicht bremsen - sie hat eigene Tests.
OHNE_TAKT = Taktung(mindestpause_s = 0, fenster_aktiv = False)


class ErsatzLauf:
    """Ein Bot-Lauf, der nichts startet, sondern vorgegebene Zeilen liefert.

    Damit laesst sich die Warteschlange pruefen, ohne Prozesse, Browser oder
    Konto - und vor allem deterministisch.
    """

    def __init__(self, auftrag:LaufAuftrag, *, zeilen:list[Ereignis] | None = None,
                 code:int = 0, verzoegerung:float = 0.0) -> None:
        self.auftrag = auftrag
        self._zeilen = zeilen or []
        self._code = code
        self._verzoegerung = verzoegerung
        self.ergebnis = LaufErgebnis(befehl = auftrag.befehl, rueckgabecode = None)
        self.eingaben:list[str] = []
        self.gestartet = False

    async def starten(self) -> None:
        self.gestartet = True

    async def ereignisse(self) -> AsyncIterator[Ereignis]:
        for ereignis in self._zeilen:
            if self._verzoegerung:
                await asyncio.sleep(self._verzoegerung)
            if ereignis.aufmerksamkeit and ereignis.aufmerksamkeit not in self.ergebnis.aufmerksamkeit:
                self.ergebnis.aufmerksamkeit.append(ereignis.aufmerksamkeit)
            yield ereignis
        self.ergebnis.rueckgabecode = self._code

    async def eingabe_senden(self, text:str = "") -> None:
        self.eingaben.append(text)

    async def abbrechen(self) -> None:
        self.ergebnis.abgebrochen = True
        self.ergebnis.rueckgabecode = -15


def _ereignis(text:str, **kwargs:object) -> Ereignis:
    from anzeigen_studio.botbridge.events import zeile_auswerten
    e = zeile_auswerten(text)
    return Ereignis(zeitpunkt = e.zeitpunkt, text = e.text, stufe = e.stufe,
                    aufmerksamkeit = kwargs.get("aufmerksamkeit") or e.aufmerksamkeit,  # type: ignore[arg-type]
                    eingriff = kwargs.get("eingriff") or e.eingriff)  # type: ignore[arg-type]


@pytest.fixture
def umgebung(tmp_path:Path) -> tuple[Settings, sqlite3.Connection, int, Path]:
    cfg = Settings(data_dir = tmp_path, secret_key = SCHLUESSEL, dev_mode = True,
                   chromium = "/usr/bin/chromium")
    cfg.profiles_dir.mkdir(parents = True, exist_ok = True)
    conn = db.connect(cfg.database_path)
    db.migrate(conn)
    p = profile_dienst.anlegen(conn, cfg.profiles_dir, "haushalt", "Haushalt")
    zugang.setzen(conn, p.id, benutzername = "u@example.org",
                  passwort = "geheim", schluessel = SCHLUESSEL)
    return cfg, conn, p.id, profile_dienst.pfade_fuer(cfg.profiles_dir, "haushalt").wurzel


class TestSpeicher:

    def test_einreihen_und_holen(self, umgebung:tuple[Settings, sqlite3.Connection, int, Path]) -> None:
        _, conn, profil_id, _ = umgebung
        with db.transaction(conn):
            job_id = speicher.einreihen(conn, profil_id, "verify", ["--ads=all"])
        job = speicher.holen(conn, job_id)
        assert job is not None
        assert job.zustand is JobZustand.WARTET
        assert job.argumente == ["--ads=all"]
        assert job.profil_slug == "haushalt"

    def test_kein_zweiter_lauf_bei_aktivem_job(self, umgebung:tuple[Settings, sqlite3.Connection, int, Path]) -> None:
        _, conn, profil_id, _ = umgebung
        with db.transaction(conn):
            erster = speicher.einreihen(conn, profil_id, "verify", [])
            speicher.einreihen(conn, profil_id, "verify", [])
            speicher.zustand_setzen(conn, erster, JobZustand.LAEUFT)
        # Solange einer laeuft, wird kein zweiter ausgegeben - das ist die
        # Serialisierung je Profil.
        assert speicher.naechster_wartender(conn, profil_id) is None

    def test_log_grenze_haelt(self, umgebung:tuple[Settings, sqlite3.Connection, int, Path]) -> None:
        _, conn, profil_id, _ = umgebung
        with db.transaction(conn):
            job_id = speicher.einreihen(conn, profil_id, "verify", [])
        grenze = speicher.LOG_GRENZE_JE_JOB
        with db.transaction(conn):
            for i in range(grenze + 25):
                speicher.log_anhaengen(conn, job_id, _ereignis(f"Zeile {i}"))
        zeilen = speicher.log_lesen(conn, job_id)
        # Ohne Grenze waechst die Datenbank unbegrenzt.
        assert len(zeilen) == grenze
        assert zeilen[-1]["text"] == f"Zeile {grenze + 24}"

    def test_verwaiste_werden_abgebrochen(self, umgebung:tuple[Settings, sqlite3.Connection, int, Path]) -> None:
        _, conn, profil_id, _ = umgebung
        with db.transaction(conn):
            a = speicher.einreihen(conn, profil_id, "verify", [])
            b = speicher.einreihen(conn, profil_id, "verify", [])
            speicher.zustand_setzen(conn, a, JobZustand.LAEUFT)
            speicher.zustand_setzen(conn, b, JobZustand.BRAUCHT_EINGABE)
        with db.transaction(conn):
            anzahl = speicher.verwaiste_aufraeumen(conn)
        assert anzahl == 2
        for job_id in (a, b):
            job = speicher.holen(conn, job_id)
            assert job is not None
            assert job.zustand is JobZustand.ABGEBROCHEN

    def test_eingereihte_werden_ebenfalls_abgebrochen(
            self, umgebung:tuple[Settings, sqlite3.Connection, int, Path]) -> None:
        """Regression vom 2026-08-23.

        Ein eingereihter Job wird von `asyncio.create_task` getragen und lebt
        nur im Speicher des Backends. Nach einem Neustart nimmt ihn niemand
        wieder auf - er blieb bis dahin fuer immer auf "wartet" stehen.
        """
        _, conn, profil_id, _ = umgebung
        with db.transaction(conn):
            job_id = speicher.einreihen(conn, profil_id, "verify", [])
        vorher = speicher.holen(conn, job_id)
        assert vorher is not None
        assert vorher.zustand is JobZustand.WARTET

        with db.transaction(conn):
            anzahl = speicher.verwaiste_aufraeumen(conn)

        assert anzahl == 1
        job = speicher.holen(conn, job_id)
        assert job is not None
        assert job.zustand is JobZustand.ABGEBROCHEN
        assert job.meldung == "Beim Neustart des Dienstes abgebrochen."

    def test_abgeschlossene_bleiben_unberuehrt(
            self, umgebung:tuple[Settings, sqlite3.Connection, int, Path]) -> None:
        _, conn, profil_id, _ = umgebung
        with db.transaction(conn):
            fertig = speicher.einreihen(conn, profil_id, "verify", [])
            speicher.zustand_setzen(conn, fertig, JobZustand.FERTIG, rueckgabecode = 0)
        with db.transaction(conn):
            assert speicher.verwaiste_aufraeumen(conn) == 0
        job = speicher.holen(conn, fertig)
        assert job is not None
        assert job.zustand is JobZustand.FERTIG


class TestWarteschlange:

    @pytest.mark.asyncio
    async def test_erfolgreicher_lauf(self, umgebung:tuple[Settings, sqlite3.Connection, int, Path]) -> None:
        cfg, conn, profil_id, verzeichnis = umgebung
        ws = Warteschlange(cfg, taktung = OHNE_TAKT, lauf_fabrik = lambda a: ErsatzLauf(  # type: ignore[arg-type,return-value]
            a, zeilen = [_ereignis("INFO Start"), _ereignis("INFO Ende")]))
        job_id = await ws.einreihen(conn, profil_id, "verify", [], profil_verzeichnis = verzeichnis)
        await asyncio.gather(*list(ws._aufgaben))  # noqa: SLF001

        job = speicher.holen(conn, job_id)
        assert job is not None
        assert job.zustand is JobZustand.FERTIG
        assert job.rueckgabecode == 0
        assert len(speicher.log_lesen(conn, job_id)) == 2

    @pytest.mark.asyncio
    async def test_aufmerksamkeitsfall_wird_nicht_als_erfolg_gemeldet(
        self, umgebung:tuple[Settings, sqlite3.Connection, int, Path],
    ) -> None:
        cfg, conn, profil_id, verzeichnis = umgebung
        ws = Warteschlange(cfg, taktung = OHNE_TAKT, lauf_fabrik = lambda a: ErsatzLauf(  # type: ignore[arg-type,return-value]
            a, zeilen = [_ereignis("ERROR PostPublishPersistenceError: ad is live")], code = 0))
        job_id = await ws.einreihen(conn, profil_id, "publish", [], profil_verzeichnis = verzeichnis)
        await asyncio.gather(*list(ws._aufgaben))  # noqa: SLF001

        job = speicher.holen(conn, job_id)
        assert job is not None
        # Rueckgabecode 0, trotzdem PRUEFEN - lokaler und entfernter Zustand
        # koennen auseinanderlaufen.
        assert job.rueckgabecode == 0
        assert job.zustand is JobZustand.PRUEFEN
        assert str(Aufmerksamkeit.VEROEFFENTLICHT_NICHT_GESPEICHERT) in job.aufmerksamkeit

    @pytest.mark.asyncio
    async def test_fehlschlag(self, umgebung:tuple[Settings, sqlite3.Connection, int, Path]) -> None:
        cfg, conn, profil_id, verzeichnis = umgebung
        ws = Warteschlange(cfg, taktung = OHNE_TAKT, lauf_fabrik = lambda a: ErsatzLauf(  # type: ignore[arg-type,return-value]
            a, zeilen = [_ereignis("ERROR kaputt")], code = 2))
        job_id = await ws.einreihen(conn, profil_id, "publish", [], profil_verzeichnis = verzeichnis)
        await asyncio.gather(*list(ws._aufgaben))  # noqa: SLF001

        job = speicher.holen(conn, job_id)
        assert job is not None
        assert job.zustand is JobZustand.GESCHEITERT
        assert job.meldung is not None
        assert "2" in job.meldung

    @pytest.mark.asyncio
    async def test_wartepunkt_setzt_eigenen_zustand(
        self, umgebung:tuple[Settings, sqlite3.Connection, int, Path],
    ) -> None:
        cfg, conn, profil_id, verzeichnis = umgebung
        zustaende:list[JobZustand] = []

        def fabrik(auftrag:LaufAuftrag) -> ErsatzLauf:
            return ErsatzLauf(auftrag, zeilen = [
                _ereignis("Captcha detected, please solve"),
                _ereignis("INFO weiter"),
            ], verzoegerung = 0.02)

        ws = Warteschlange(cfg, taktung = OHNE_TAKT, lauf_fabrik = fabrik)  # type: ignore[arg-type]
        job_id = await ws.einreihen(conn, profil_id, "publish", [], profil_verzeichnis = verzeichnis)

        async def beobachten() -> None:
            pruef = db.connect(cfg.database_path)
            for _ in range(40):
                job = speicher.holen(pruef, job_id)
                if job is not None:
                    zustaende.append(job.zustand)
                await asyncio.sleep(0.01)
            pruef.close()

        await asyncio.gather(beobachten(), *list(ws._aufgaben))  # noqa: SLF001

        # BRAUCHT_EINGABE muss zwischendurch sichtbar gewesen sein, sonst
        # koennte die Oberflaeche den Wartepunkt nicht anzeigen.
        assert JobZustand.BRAUCHT_EINGABE in zustaende
        job = speicher.holen(conn, job_id)
        assert job is not None
        assert job.zustand is JobZustand.FERTIG
        # Nach dem Ende darf kein Wartepunkt mehr angezeigt werden.
        assert job.eingriff is None

    @pytest.mark.asyncio
    async def test_ein_lauf_je_profil(self, umgebung:tuple[Settings, sqlite3.Connection, int, Path]) -> None:
        cfg, conn, profil_id, verzeichnis = umgebung
        gleichzeitig = 0
        hoechststand = 0

        def fabrik(auftrag:LaufAuftrag) -> ErsatzLauf:
            class Zaehlend(ErsatzLauf):
                async def ereignisse(self) -> AsyncIterator[Ereignis]:
                    nonlocal gleichzeitig, hoechststand
                    gleichzeitig += 1
                    hoechststand = max(hoechststand, gleichzeitig)
                    await asyncio.sleep(0.05)
                    gleichzeitig -= 1
                    self.ergebnis.rueckgabecode = 0
                    # Erzeugt keine Ereignisse - der Test misst nur, wie viele
                    # Laeufe gleichzeitig in dieser Methode stehen. Das
                    # unerreichbare yield macht die Methode zum Generator.
                    leer:list[Ereignis] = []
                    for ereignis in leer:  # pragma: no cover
                        yield ereignis
            return Zaehlend(auftrag)

        ws = Warteschlange(cfg, taktung = OHNE_TAKT, lauf_fabrik = fabrik)  # type: ignore[arg-type]
        for _ in range(3):
            await ws.einreihen(conn, profil_id, "verify", [], profil_verzeichnis = verzeichnis)
        await asyncio.gather(*list(ws._aufgaben))  # noqa: SLF001

        # Chromium sperrt sein Profilverzeichnis, und zwei Sitzungen auf einem
        # Konto fallen der Plattform auf.
        assert hoechststand == 1

    @pytest.mark.asyncio
    async def test_abbruch_bei_schreibendem_befehl_meldet_ungewiss(
        self, umgebung:tuple[Settings, sqlite3.Connection, int, Path],
    ) -> None:
        """Ein Abbruch mitten im Veröffentlichen ist kein schlichtes 'abgebrochen'.

        Die Anzeige kann bereits online sein, während lokal nichts davon steht.
        Das als erledigt zu melden wäre der gefährlichste Fehler dieser Schicht.
        """
        cfg, conn, profil_id, verzeichnis = umgebung

        def fabrik(auftrag:LaufAuftrag) -> ErsatzLauf:
            lauf = ErsatzLauf(auftrag)
            lauf.ergebnis.abgebrochen = True
            lauf.ergebnis.rueckgabecode = -15
            return lauf

        ws = Warteschlange(cfg, taktung = OHNE_TAKT, lauf_fabrik = fabrik)  # type: ignore[arg-type]
        job_id = await ws.einreihen(conn, profil_id, "publish", [], profil_verzeichnis = verzeichnis)
        await asyncio.gather(*list(ws._aufgaben))  # noqa: SLF001

        job = speicher.holen(conn, job_id)
        assert job is not None
        assert job.zustand is JobZustand.PRUEFEN
        assert job.meldung is not None
        assert "kleinanzeigen.de" in job.meldung

    @pytest.mark.asyncio
    async def test_abbruch_bei_lesendem_befehl_ist_schlicht_abgebrochen(
        self, umgebung:tuple[Settings, sqlite3.Connection, int, Path],
    ) -> None:
        cfg, conn, profil_id, verzeichnis = umgebung

        def fabrik(auftrag:LaufAuftrag) -> ErsatzLauf:
            lauf = ErsatzLauf(auftrag)
            lauf.ergebnis.abgebrochen = True
            lauf.ergebnis.rueckgabecode = -15
            return lauf

        ws = Warteschlange(cfg, taktung = OHNE_TAKT, lauf_fabrik = fabrik)  # type: ignore[arg-type]
        # download liest nur - hier gibt es keinen ungewissen Zustand.
        job_id = await ws.einreihen(conn, profil_id, "download", [], profil_verzeichnis = verzeichnis)
        await asyncio.gather(*list(ws._aufgaben))  # noqa: SLF001

        job = speicher.holen(conn, job_id)
        assert job is not None
        assert job.zustand is JobZustand.ABGEBROCHEN

    @pytest.mark.asyncio
    async def test_ohne_zugangsdaten_scheitert_der_lauf(
        self, umgebung:tuple[Settings, sqlite3.Connection, int, Path], tmp_path:Path,
    ) -> None:
        cfg, conn, _, _ = umgebung
        ohne = profile_dienst.anlegen(conn, cfg.profiles_dir, "leer", "Ohne Zugang")
        ws = Warteschlange(cfg, taktung = OHNE_TAKT, lauf_fabrik = lambda a: ErsatzLauf(a))  # type: ignore[arg-type,return-value]
        job_id = await ws.einreihen(conn, ohne.id, "verify", [],
                              profil_verzeichnis = profile_dienst.pfade_fuer(cfg.profiles_dir, "leer").wurzel)
        await asyncio.gather(*list(ws._aufgaben))  # noqa: SLF001

        job = speicher.holen(conn, job_id)
        assert job is not None
        assert job.zustand is JobZustand.GESCHEITERT
