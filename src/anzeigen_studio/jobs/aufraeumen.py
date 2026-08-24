# SPDX-FileCopyrightText: © Anzeigen-Studio contributors
# SPDX-ArtifactOfProjectHomePage: https://github.com/TingelTangelBob/Kleinanzeigen.de-botUI/
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# Aufraeumen nach einem Lauf (AP-1.9).
#
# Der Bot raeumt seinen Browser selbst auf, und zwar gruendlich - die
# Codepruefung nennt das Produktionsniveau. Diese Schicht ist die zweite
# Verteidigungslinie fuer den Fall, dass der Bot dazu nicht mehr kam: hartes
# Beenden, Absturz, oder ein Chromium, das sich vom Elternprozess geloest hat.
#
# Warum das noetig ist: Ein zurueckgebliebenes Chromium haelt die Sperre auf
# dem Profilverzeichnis. Der naechste Lauf desselben Profils scheitert dann mit
# einer Meldung, die nichts mit der eigentlichen Ursache zu tun hat.

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import psutil

if TYPE_CHECKING:
    from pathlib import Path

LOG = logging.getLogger(__name__)

#: Wie lange ein Prozess nach dem Beenden-Signal Zeit bekommt.
_FRIST_S = 5.0


def verwaiste_browser_beenden(browser_profil: Path) -> int:
    """Beendet Chromium-Prozesse, die noch auf dieses Profilverzeichnis zeigen.

    Gibt zurueck, wie viele beendet wurden. Bewusst eng: Es werden nur
    Prozesse angefasst, deren Befehlszeile genau dieses Verzeichnis nennt -
    nicht alles, was nach Chromium aussieht. Ein Lauf eines anderen Profils
    darf hier nicht mitgerissen werden.
    """
    marke = f"--user-data-dir={browser_profil}"
    kandidaten: list[psutil.Process] = []

    for prozess in psutil.process_iter(["cmdline", "status"]):
        try:
            # Zombies sind bereits beendet und lassen sich nicht noch einmal
            # beenden. Sie werden vom init-Prozess des Containers eingesammelt
            # (init: true in docker-compose.yml).
            if prozess.info["status"] == psutil.STATUS_ZOMBIE:
                continue
            zeile = prozess.info["cmdline"] or []
            if any(teil.startswith(marke) for teil in zeile):
                kandidaten.append(prozess)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            # Prozess ist zwischenzeitlich verschwunden oder gehoert jemand
            # anderem - beides kein Grund, das Aufraeumen abzubrechen.
            continue

    if not kandidaten:
        return 0

    LOG.warning("%d verwaiste Browserprozesse werden beendet (%s)", len(kandidaten), browser_profil)

    for prozess in kandidaten:
        try:
            prozess.terminate()
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue

    _, uebrig = psutil.wait_procs(kandidaten, timeout = _FRIST_S)
    for prozess in uebrig:
        try:
            prozess.kill()
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    psutil.wait_procs(uebrig, timeout = _FRIST_S)

    return len(kandidaten)


def sperren_entfernen(browser_profil: Path) -> list[str]:
    """Entfernt Chromium-Sperrdateien aus einem Profilverzeichnis.

    Nach einem harten Abbruch bleiben SingletonLock und Verwandte liegen.
    Chromium weigert sich dann zu starten, obwohl kein Prozess mehr laeuft.

    Wird NUR aufgerufen, nachdem verwaiste_browser_beenden() gelaufen ist -
    eine Sperre zu entfernen, waehrend der Inhaber noch lebt, waere schlimmer
    als das Problem.
    """
    entfernt: list[str] = []
    if not browser_profil.is_dir():
        return entfernt

    for name in ("SingletonLock", "SingletonCookie", "SingletonSocket"):
        pfad = browser_profil / name
        # is_symlink() zuerst: SingletonLock IST eine symbolische Verknuepfung,
        # exists() folgt ihr und meldet False, wenn das Ziel fehlt.
        if pfad.is_symlink() or pfad.exists():
            try:
                pfad.unlink()
                entfernt.append(name)
            except OSError as fehler:
                LOG.warning("Sperrdatei %s liess sich nicht entfernen: %s", pfad, fehler)
    return entfernt


def _aufraeumen(browser_profil: Path) -> None:
    """Beendet verwaiste Prozesse und entfernt danach die Sperrdateien.

    Die Reihenfolge ist die Bedingung dafuer, dass das Entfernen sicher ist:
    Erst wird alles beendet, was noch auf dem Profil sitzt, dann sind die
    Sperren nachweislich herrenlos.

    Die Sperren werden auch dann entfernt, wenn kein Prozess zu beenden war.
    Genau das ist der haeufige Fall - und er war bis zum 2026-08-23 nicht
    abgedeckt: Beim Beenden des Containers stirbt Chromium mit ihm, ein
    verwaister Prozess bleibt also gar nicht uebrig. Die Sperrdateien liegen
    aber im Datenverzeichnis und ueberleben den Neustart. Jeder folgende Lauf
    scheiterte daraufhin mit "Failed to start browser" - einer Meldung, die auf
    Rechte oder das Browser-Binary zeigt und nicht auf die wahre Ursache.
    """
    beendet = verwaiste_browser_beenden(browser_profil)
    entfernt = sperren_entfernen(browser_profil)
    if beendet or entfernt:
        LOG.info(
            "Aufgeraeumt: %d verwaiste Prozess(e), Sperrdateien: %s",
            beendet, ", ".join(entfernt) if entfernt else "keine",
        )


def vor_lauf(browser_profil: Path) -> None:
    """Aufraeumen vor dem Start eines Laufs.

    Notwendig, weil `nach_lauf` nur laeuft, wenn es ein Ende gab. Ein
    Container-Neustart oder ein harter Absturz lassen Sperren zurueck, die
    sonst niemand mehr anfasst - und blockieren damit dauerhaft jeden weiteren
    Lauf des Profils.
    """
    _aufraeumen(browser_profil)


def nach_lauf(browser_profil: Path) -> None:
    """Vollstaendiges Aufraeumen nach einem Lauf."""
    _aufraeumen(browser_profil)
