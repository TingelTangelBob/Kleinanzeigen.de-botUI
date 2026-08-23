# SPDX-FileCopyrightText: © Anzeigen-Studio contributors
# SPDX-ArtifactOfProjectHomePage: https://github.com/TingelTangelBob/Kleinanzeigen.de-botUI/
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# Warteschlange und Worker (AP-1.6).
#
# Ein Lauf je Profil, mehrere Profile parallel. Die Grenze liegt nicht im Code
# - WebScrapingMixin ist instanzgebunden, es gibt keine Browser-Singletons -
# sondern im Chromium-Profilverzeichnis, das gesperrt wird, und darin, dass
# zwei gleichzeitige Sitzungen auf einem Konto der Plattform auffallen.

from __future__ import annotations

import asyncio
import contextlib
import logging
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Final

from anzeigen_studio.botbridge import konfiguration
from anzeigen_studio.botbridge.runner import BotLauf, LaufAuftrag
from anzeigen_studio.core import db, zugang
from anzeigen_studio.core.errors import FachlicherFehler
from anzeigen_studio.jobs import aufraeumen, speicher
from anzeigen_studio.jobs.modelle import JobZustand
from anzeigen_studio.jobs.taktung import Taktung

if TYPE_CHECKING:
    import sqlite3
    from collections.abc import Callable
    from pathlib import Path

    from anzeigen_studio.core.settings import Settings

LOG = logging.getLogger(__name__)

#: Obergrenze gleichzeitig laufender Profile. Chromium braucht 1-2 GB je
#: Instanz; ohne Grenze bringt ein Massenlauf den Container zum Auslagern.
#: Konservativ gewaehlt - lieber wartet ein Profil, als dass alle kriechen.
STANDARD_PARALLEL: Final[int] = 2

#: Befehle, die auf der Plattform etwas veraendern. Ein Abbruch waehrend eines
#: solchen Laufs hinterlaesst einen ungewissen Zustand (AP-1.9).
_SCHREIBENDE_BEFEHLE: Final[frozenset[str]] = frozenset({
    "publish", "update", "delete", "extend",
})


class Warteschlange:
    """Nimmt Jobs entgegen und arbeitet sie ab.

    Bewusst schlicht gehalten: keine externe Aufgabenverwaltung, kein Redis.
    Fuer eine Anwendung mit einem Betreiber und wenigen Profilen waere das
    Betriebsaufwand ohne Gegenwert.
    """

    def __init__(
        self,
        settings: Settings,
        *,
        parallel: int = STANDARD_PARALLEL,
        lauf_fabrik: Callable[[LaufAuftrag], BotLauf] | None = None,
        taktung: Taktung | None = None,
    ) -> None:
        self._settings = settings
        self._semaphor = asyncio.Semaphore(parallel)
        self._taktung = taktung or Taktung()
        #: Wann das Profil zuletzt einen Lauf beendet hat - Grundlage der
        #: Mindestpause aus AP-1.12.
        self._letztes_ende: dict[int, float] = {}
        # Erlaubt Tests, einen Ersatz-Bot einzusetzen, ohne die Warteschlange
        # nachzubauen.
        self._lauf_fabrik = lauf_fabrik or BotLauf
        self._laeuft: dict[int, BotLauf] = {}
        self._aufgaben: set[asyncio.Task[None]] = set()
        self._profil_sperren: dict[int, asyncio.Lock] = {}

    # -- oeffentlich ---------------------------------------------------------

    async def einreihen(self, conn: sqlite3.Connection, profil_id: int, befehl: str,
                        argumente: list[str], *, profil_verzeichnis: Path) -> int:
        # Bewusst async: asyncio.create_task braucht eine laufende
        # Ereignisschleife. Ein synchroner FastAPI-Endpunkt laeuft im
        # Threadpool, dort gibt es keine - genau daran ist der erste Lauf
        # gescheitert.
        with db.transaction(conn):
            job_id = speicher.einreihen(conn, profil_id, befehl, argumente)
        aufgabe = asyncio.create_task(self._abarbeiten(job_id, profil_id, profil_verzeichnis))
        # Referenz halten, sonst kann der Garbage Collector die Aufgabe
        # einsammeln, bevor sie fertig ist.
        self._aufgaben.add(aufgabe)
        aufgabe.add_done_callback(self._aufgaben.discard)
        return job_id

    async def abbrechen(self, job_id: int) -> None:
        lauf = self._laeuft.get(job_id)
        if lauf is None:
            raise FachlicherFehler("Dieser Lauf läuft nicht mehr.", status = 409)
        await lauf.abbrechen()

    async def eingabe_senden(self, job_id: int, text: str = "") -> None:
        lauf = self._laeuft.get(job_id)
        if lauf is None:
            raise FachlicherFehler("Dieser Lauf wartet nicht auf eine Eingabe.", status = 409)
        await lauf.eingabe_senden(text)

    async def stillegen(self) -> None:
        """Beendet alle laufenden Jobs - fuer das geordnete Herunterfahren."""
        for lauf in list(self._laeuft.values()):
            with contextlib.suppress(Exception):
                await lauf.abbrechen()
        for aufgabe in list(self._aufgaben):
            aufgabe.cancel()
        if self._aufgaben:
            await asyncio.gather(*self._aufgaben, return_exceptions = True)

    # -- intern --------------------------------------------------------------

    def _nutzer_konfiguration(self, _profil_id: int) -> dict[str, object]:
        """Der nutzereditierbare Teil der Bot-Konfiguration.

        Noch leer: Die Einstellungsoberflaeche ist AP-2.9. Bis dahin laeuft der
        Bot mit seinen Vorgaben plus der festen Basis.
        """
        return {}

    async def _takt_abwarten(self, job_id: int, profil_id: int) -> None:
        """Haelt Mindestpause und Zeitfenster ein (AP-1.12).

        Laeuft INNERHALB der Profilsperre: Waehrend gewartet wird, startet kein
        anderer Lauf desselben Profils. Ein Abbruch waehrend der Wartezeit
        wirkt sofort, weil asyncio.sleep abbrechbar ist.

        Der Grund und das Ende der Wartezeit werden in der Datenbank vermerkt.
        Ohne das steht der Job auf "wartet", ohne Erklaerung - und wer mehrere
        Laeufe einreiht, haelt die absichtliche Bremse fuer ein Haengen. Genau
        das ist im ersten Test mit einem echten Konto passiert.
        """
        bis_fenster = self._taktung.wartezeit_bis_fenster()
        if bis_fenster > 0:
            LOG.info("Job %d wartet %.0f Minuten auf das Zeitfenster", job_id, bis_fenster / 60)
            await self._warten_mit_vermerk(
                job_id, bis_fenster,
                f"Wartet auf das erlaubte Zeitfenster ab "
                f"{self._taktung.fenster_von.strftime('%H:%M')} Uhr.",
            )

        letztes = self._letztes_ende.get(profil_id)
        if letztes is None:
            return
        pause = self._taktung.pause_nach_lauf()
        verstrichen = asyncio.get_running_loop().time() - letztes
        rest = pause - verstrichen
        if rest > 0:
            LOG.info("Job %d wartet %.0f s Mindestpause", job_id, rest)
            await self._warten_mit_vermerk(
                job_id, rest,
                "Mindestabstand zwischen zwei Läufen desselben Profils. "
                "Schützt davor, dass viele Aktionen kurz hintereinander auffallen.",
            )

    async def _warten_mit_vermerk(self, job_id: int, sekunden: float, grund: str) -> None:
        """Wartet und haelt dabei fest, warum und bis wann."""
        bis = (datetime.now(UTC) + timedelta(seconds = sekunden)).isoformat(timespec = "seconds")
        conn = db.connect(self._settings.database_path)
        try:
            with db.transaction(conn):
                speicher.warten_setzen(conn, job_id, bis = bis, grund = grund)
        finally:
            conn.close()
        try:
            await asyncio.sleep(sekunden)
        finally:
            # Auch bei Abbruch aufraeumen, sonst zeigt die Oberflaeche eine
            # Wartezeit an, die es nicht mehr gibt.
            conn = db.connect(self._settings.database_path)
            try:
                with db.transaction(conn):
                    speicher.warten_setzen(conn, job_id, bis = None, grund = None)
            finally:
                conn.close()

    def _sperre(self, profil_id: int) -> asyncio.Lock:
        if profil_id not in self._profil_sperren:
            self._profil_sperren[profil_id] = asyncio.Lock()
        return self._profil_sperren[profil_id]

    async def _abarbeiten(self, job_id: int, profil_id: int, profil_verzeichnis: Path) -> None:
        # Zwei Stufen: die Profilsperre serialisiert je Konto, das Semaphor
        # begrenzt, wie viele Profile insgesamt gleichzeitig laufen.
        async with self._sperre(profil_id), self._semaphor:
            await self._takt_abwarten(job_id, profil_id)
            conn = db.connect(self._settings.database_path)
            try:
                await self._lauf_durchfuehren(conn, job_id, profil_id, profil_verzeichnis)
            except asyncio.CancelledError:
                with db.transaction(conn):
                    speicher.zustand_setzen(conn, job_id, JobZustand.ABGEBROCHEN,
                                            meldung = "Abgebrochen.")
                raise
            except Exception as fehler:  # noqa: BLE001 - der Worker darf nie sterben
                LOG.exception("Job %d ist unerwartet gescheitert", job_id)
                with db.transaction(conn):
                    speicher.zustand_setzen(conn, job_id, JobZustand.GESCHEITERT,
                                            meldung = f"Unerwarteter Fehler: {type(fehler).__name__}")
            finally:
                self._laeuft.pop(job_id, None)
                self._letztes_ende[profil_id] = asyncio.get_running_loop().time()
                # Zweite Verteidigungslinie (AP-1.9). Laeuft in jedem Fall -
                # gerade der harte Abbruch ist der Fall, in dem der Bot nicht
                # mehr selbst aufraeumen konnte.
                try:
                    aufraeumen.nach_lauf(profil_verzeichnis / ".temp" / "browser-profile")
                except Exception:  # noqa: BLE001 - Aufraeumen darf nie den Job ueberschatten
                    LOG.exception("Aufraeumen nach Job %d ist gescheitert", job_id)
                conn.close()

    async def _lauf_durchfuehren(self, conn: sqlite3.Connection, job_id: int,
                                 profil_id: int, profil_verzeichnis: Path) -> None:
        job = speicher.holen(conn, job_id)
        if job is None or job.zustand is not JobZustand.WARTET:
            return

        # Zugangsdaten erst hier entschluesseln - so kurz wie moeglich im
        # Speicher, und nur fuer diesen einen Unterprozess.
        umgebung = zugang.umgebung_fuer_lauf(conn, profil_id, schluessel = self._settings.secret_key)

        # config.yaml vor jedem Lauf neu schreiben. So koennen Aenderungen von
        # Hand an der Datei nichts umgehen, was die Oberflaeche verbietet - die
        # gesperrten Felder aus AP-1.11 werden dabei erneut gesetzt.
        verworfen = konfiguration.schreiben(
            profil_verzeichnis / "config.yaml",
            self._nutzer_konfiguration(profil_id),
            anzeigen_glob = "./ads/**/ad_*.{yaml,yml,json}",
            chromium = self._settings.chromium,
        )
        if verworfen:
            LOG.warning("Gesperrte Konfigurationsfelder verworfen: %s", ", ".join(verworfen))

        lauf = self._lauf_fabrik(LaufAuftrag(
            befehl = job.befehl,
            config_datei = profil_verzeichnis / "config.yaml",
            argumente = tuple(job.argumente),
            umgebung = umgebung,
        ))
        self._laeuft[job_id] = lauf

        with db.transaction(conn):
            speicher.zustand_setzen(conn, job_id, JobZustand.LAEUFT)

        await lauf.starten()
        async for ereignis in lauf.ereignisse():
            with db.transaction(conn):
                speicher.log_anhaengen(conn, job_id, ereignis)
                if ereignis.braucht_menschen:
                    speicher.zustand_setzen(conn, job_id, JobZustand.BRAUCHT_EINGABE,
                                            eingriff = str(ereignis.eingriff))
                    LOG.info("Job %d wartet auf eine Eingabe (%s)", job_id, ereignis.eingriff)

        ergebnis = lauf.ergebnis
        if ergebnis.abgebrochen:
            if job.befehl in _SCHREIBENDE_BEFEHLE:
                # Ein Abbruch mitten im Veroeffentlichen hinterlaesst einen
                # ungewissen Zustand: Die Anzeige kann bereits online sein,
                # waehrend lokal nichts davon steht. Das als schlichtes
                # "abgebrochen" zu melden waere irrefuehrend.
                zustand = JobZustand.PRUEFEN
                meldung = (
                    "Abgebrochen, während der Bot Änderungen vornahm. "
                    "Bitte auf kleinanzeigen.de nachsehen, was tatsächlich passiert ist - "
                    "eine Anzeige kann online sein, ohne lokal gespeichert zu sein."
                )
            else:
                zustand = JobZustand.ABGEBROCHEN
                meldung = "Abgebrochen."
        elif ergebnis.aufmerksamkeit:
            # Ausdruecklich weder Erfolg noch Fehlschlag: lokaler und
            # entfernter Zustand koennen auseinanderlaufen.
            zustand = JobZustand.PRUEFEN
            meldung = "Der Lauf braucht eine Prüfung von Hand."
        elif ergebnis.rueckgabecode == 0:
            zustand = JobZustand.FERTIG
            meldung = None
        else:
            zustand = JobZustand.GESCHEITERT
            meldung = f"Der Bot endete mit Rückgabecode {ergebnis.rueckgabecode}."

        with db.transaction(conn):
            speicher.zustand_setzen(
                conn, job_id, zustand,
                rueckgabecode = ergebnis.rueckgabecode,
                aufmerksamkeit = [str(a) for a in ergebnis.aufmerksamkeit],
                eingriff = None,
                meldung = meldung,
            )
