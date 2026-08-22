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
from typing import TYPE_CHECKING, Final

from anzeigen_studio.botbridge import konfiguration
from anzeigen_studio.botbridge.runner import BotLauf, LaufAuftrag
from anzeigen_studio.core import db, zugang
from anzeigen_studio.core.errors import FachlicherFehler
from anzeigen_studio.jobs import speicher
from anzeigen_studio.jobs.modelle import JobZustand

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
    ) -> None:
        self._settings = settings
        self._semaphor = asyncio.Semaphore(parallel)
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

    def _sperre(self, profil_id: int) -> asyncio.Lock:
        if profil_id not in self._profil_sperren:
            self._profil_sperren[profil_id] = asyncio.Lock()
        return self._profil_sperren[profil_id]

    async def _abarbeiten(self, job_id: int, profil_id: int, profil_verzeichnis: Path) -> None:
        # Zwei Stufen: die Profilsperre serialisiert je Konto, das Semaphor
        # begrenzt, wie viele Profile insgesamt gleichzeitig laufen.
        async with self._sperre(profil_id), self._semaphor:
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
