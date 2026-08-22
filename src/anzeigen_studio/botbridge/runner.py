# SPDX-FileCopyrightText: © Anzeigen-Studio contributors
# SPDX-ArtifactOfProjectHomePage: https://github.com/TingelTangelBob/Kleinanzeigen.de-botUI/
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# Ruft den Bot als Unterprozess auf (AP-1.5).
#
# Warum Unterprozess und nicht Import: Der Upstream sagt Stabilitaet nur fuer
# CLI, Optionen, Exit-Verhalten und Dateiformate zu und behaelt sich vor,
# interne Importpfade jederzeit zu brechen. Dazu patcht ein blosser Import
# gettext prozessweit und setzt die Logger-Klasse um; 17 sys.exit-Stellen
# liegen im Bibliothekscode. Ein Unterprozess benutzt exakt die zugesagte
# Flaeche und kapselt alle Nebenwirkungen.
#
# Angenehmer Nebeneffekt: Der Bot fragt an sechs Stellen ueber die
# Standardeingabe nach einer Bestaetigung (Captcha, SMS, E-Mail). Im
# Unterprozessmodell gehoert uns diese Standardeingabe - die Uebernahme durch
# den Menschen (AP-1.8) braucht damit keinen Eingriff in den Upstream-Code.

from __future__ import annotations

import asyncio
import contextlib
import os
import signal
from dataclasses import dataclass
from typing import TYPE_CHECKING, Final

from anzeigen_studio.botbridge.events import Ereignis, LaufErgebnis, zeile_auswerten
from anzeigen_studio.core.errors import FachlicherFehler

if TYPE_CHECKING:
    from collections.abc import AsyncIterator
    from pathlib import Path

#: Befehle, die der Bot kennt. Abgeglichen mit app.py; `help` und `version`
#: fehlen bewusst - sie haben in der Oberflaeche keinen Zweck.
ERLAUBTE_BEFEHLE: Final[frozenset[str]] = frozenset({
    "publish", "verify", "delete", "update", "extend", "download",
    "status", "diagnose", "update-content-hash", "create-config",
})

#: Wie lange nach einem Abbruchsignal auf ein geordnetes Ende gewartet wird,
#: bevor hart beendet wird. Der Bot raeumt seinen Browser im finally auf -
#: diese Zeit soll er bekommen.
_ABBRUCH_FRIST_S: Final[float] = 20.0


@dataclass(frozen = True, slots = True)
class LaufAuftrag:
    befehl: str
    config_datei: Path
    argumente: tuple[str, ...] = ()
    #: Wird als Umgebung an den Unterprozess gegeben - enthaelt die
    #: Zugangsdaten im Klartext und darf NIE protokolliert werden.
    umgebung: dict[str, str] | None = None


class BotLauf:
    """Ein laufender Bot-Prozess.

    Die Ausgabe kommt als Strom von Ereignissen heraus; `abbrechen()` beendet
    den Lauf, `eingabe_senden()` beantwortet einen Wartepunkt.
    """

    def __init__(self, auftrag: LaufAuftrag, *, python: str = "python", modul: str = "kleinanzeigen_bot") -> None:
        if auftrag.befehl not in ERLAUBTE_BEFEHLE:
            # Weissliste statt Schwarzliste: was nicht ausdruecklich erlaubt
            # ist, wird nicht ausgefuehrt.
            raise FachlicherFehler(f"Unbekannter Bot-Befehl: {auftrag.befehl}", status = 400)
        self._auftrag = auftrag
        self._python = python
        self._modul = modul
        self._prozess: asyncio.subprocess.Process | None = None
        self._ergebnis = LaufErgebnis(befehl = auftrag.befehl, rueckgabecode = None)

    @property
    def ergebnis(self) -> LaufErgebnis:
        return self._ergebnis

    def _kommando(self) -> list[str]:
        return [
            self._python, "-m", self._modul,
            # --workspace-mode=portable IMMER ausdruecklich: ohne den Schalter
            # greift eine Erkennungsheuristik, die bei leerem Profilordner mit
            # "Detected neither portable nor XDG footprints" abbricht.
            "--workspace-mode=portable",
            f"--config={self._auftrag.config_datei}",
            self._auftrag.befehl,
            *self._auftrag.argumente,
        ]

    async def starten(self) -> None:
        umgebung = dict(os.environ)
        if self._auftrag.umgebung:
            umgebung.update(self._auftrag.umgebung)
        # Damit die Ausgabe zeilenweise ankommt statt blockweise gepuffert.
        umgebung["PYTHONUNBUFFERED"] = "1"

        self._prozess = await asyncio.create_subprocess_exec(
            *self._kommando(),
            stdin = asyncio.subprocess.PIPE,
            stdout = asyncio.subprocess.PIPE,
            stderr = asyncio.subprocess.STDOUT,
            env = umgebung,
            # Eigene Prozessgruppe: beim Abbruch laesst sich damit der ganze
            # Baum beenden, nicht nur der Elternprozess. Chromium haengt als
            # Kind darunter.
            start_new_session = True,
        )

    async def ereignisse(self) -> AsyncIterator[Ereignis]:
        """Liefert die Ausgabe Zeile fuer Zeile als Ereignisse."""
        if self._prozess is None or self._prozess.stdout is None:  # pragma: no cover
            raise FachlicherFehler("Der Lauf wurde nicht gestartet.", status = 500)

        async for rohzeile in self._prozess.stdout:
            ereignis = zeile_auswerten(rohzeile.decode("utf-8", errors = "replace"))
            if ereignis.aufmerksamkeit and ereignis.aufmerksamkeit not in self._ergebnis.aufmerksamkeit:
                self._ergebnis.aufmerksamkeit.append(ereignis.aufmerksamkeit)
            yield ereignis

        self._ergebnis.rueckgabecode = await self._prozess.wait()

    async def eingabe_senden(self, text: str = "") -> None:
        """Beantwortet einen Wartepunkt des Bots.

        Grundlage fuer AP-1.8: Der Bot wartet an Captcha- und
        Verifizierungsstellen auf eine Eingabe. Ein Zeilenumbruch genuegt.
        """
        if self._prozess is None or self._prozess.stdin is None:  # pragma: no cover
            raise FachlicherFehler("Der Lauf wurde nicht gestartet.", status = 409)
        self._prozess.stdin.write((text + "\n").encode("utf-8"))
        await self._prozess.stdin.drain()

    async def abbrechen(self) -> None:
        """Beendet den Lauf und raeumt den Prozessbaum ab."""
        if self._prozess is None or self._prozess.returncode is not None:
            return

        self._ergebnis.abgebrochen = True
        gruppe = os.getpgid(self._prozess.pid)

        # Erst geordnet: der Bot raeumt seinen Browser im finally auf.
        with contextlib.suppress(ProcessLookupError):
            os.killpg(gruppe, signal.SIGTERM)
        with contextlib.suppress(TimeoutError, asyncio.TimeoutError):
            await asyncio.wait_for(self._prozess.wait(), timeout = _ABBRUCH_FRIST_S)

        # Dann hart - inklusive verwaister Kinder.
        if self._prozess.returncode is None:
            with contextlib.suppress(ProcessLookupError):
                os.killpg(gruppe, signal.SIGKILL)
            with contextlib.suppress(TimeoutError, asyncio.TimeoutError):
                await asyncio.wait_for(self._prozess.wait(), timeout = 5.0)

        self._ergebnis.rueckgabecode = self._prozess.returncode
