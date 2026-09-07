# SPDX-FileCopyrightText: © Anzeigen-Studio contributors
# SPDX-ArtifactOfProjectHomePage: https://github.com/TingelTangelBob/Kleinanzeigen.de-botUI/
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# Automatisches kostenloses Verlaengern (AP-3.15) - Zustand je Profil.
#
# Spiegelbild zum taeglichen Abgleich (AP-3.12), aber schmaler: Hier wird kein
# Dateivergleich gefuehrt. `extend` holt `endDate` live aus der Plattform-API
# und klickt nur Free-„Verlaengern" (Dialog schliessen = kein Paid-Boost).
# WANN eingereiht wird, liegt im Zeitgeber; WAS gespeichert wird, liegt hier.

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from anzeigen_studio.bestand.tagesabgleich import heutiger_tag

if TYPE_CHECKING:
    import sqlite3

# heutiger_tag bewusst wiederverwendet: derselbe lokale Kalendertag wie beim
# Abgleich, damit „ein Lauf je Tag" fuer beide Schalter dieselbe Mitternacht meint.


@dataclass(frozen = True, slots = True)
class Zustand:
    """Der gespeicherte Stand des Auto-Verlaengerns fuer ein Profil."""

    eingeschaltet: bool = False
    letzter_tag: str | None = None
    """Lokaler Kalendertag des letzten Einreihens (YYYY-MM-DD)."""

    letzter_lauf_am: str | None = None
    letztes_ergebnis: str | None = None
    job_id: int | None = None
    """Der eingereihte Lauf, solange er noch nicht ausgewertet ist."""


def _jetzt() -> str:
    return datetime.now(UTC).isoformat(timespec = "seconds")


def lesen(conn: sqlite3.Connection, profil_id: int) -> Zustand:
    """Der Stand eines Profils. Ohne Zeile gilt: aus, nie gelaufen."""
    row = conn.execute(
        "SELECT eingeschaltet, letzter_tag, letzter_lauf_am, letztes_ergebnis, job_id "
        "FROM verlaengern WHERE profil_id = ?",
        (profil_id,),
    ).fetchone()
    if row is None:
        return Zustand()
    return Zustand(
        eingeschaltet = bool(row["eingeschaltet"]),
        letzter_tag = row["letzter_tag"],
        letzter_lauf_am = row["letzter_lauf_am"],
        letztes_ergebnis = row["letztes_ergebnis"],
        job_id = row["job_id"],
    )


def _sicherstellen(conn: sqlite3.Connection, profil_id: int) -> None:
    conn.execute(
        "INSERT INTO verlaengern (profil_id) VALUES (?) ON CONFLICT(profil_id) DO NOTHING",
        (profil_id,),
    )


def einschalten(conn: sqlite3.Connection, profil_id: int, *, an: bool) -> Zustand:
    """Schaltet das taegliche kostenlose Verlaengern fuer ein Profil ein oder aus.

    Vorgabe aus - ohne diesen Schalter reiht der Zeitgeber keinen `extend` ein.
    """
    _sicherstellen(conn, profil_id)
    conn.execute(
        "UPDATE verlaengern SET eingeschaltet = ? WHERE profil_id = ?",
        (1 if an else 0, profil_id),
    )
    return lesen(conn, profil_id)


def lauf_vermerken(conn: sqlite3.Connection, profil_id: int, *, tag: str, job_id: int) -> None:
    """Haelt fest, dass fuer diesen Tag eingereiht wurde - vor dem Lauf."""
    _sicherstellen(conn, profil_id)
    conn.execute(
        "UPDATE verlaengern SET letzter_tag = ?, letzter_lauf_am = ?, job_id = ? "
        "WHERE profil_id = ?",
        (tag, _jetzt(), job_id, profil_id),
    )


def ergebnis_vermerken(conn: sqlite3.Connection, profil_id: int, ergebnis: str) -> None:
    """Schliesst den offenen Lauf ab und schreibt, was dabei herauskam."""
    _sicherstellen(conn, profil_id)
    conn.execute(
        "UPDATE verlaengern SET letztes_ergebnis = ?, job_id = NULL WHERE profil_id = ?",
        (ergebnis, profil_id),
    )


def hinweis_vermerken(conn: sqlite3.Connection, profil_id: int, text: str) -> None:
    """Vermerkt einen Grund, aus dem gar nicht erst eingereiht wurde."""
    _sicherstellen(conn, profil_id)
    conn.execute(
        "UPDATE verlaengern SET letztes_ergebnis = ? WHERE profil_id = ? "
        "AND (letztes_ergebnis IS NULL OR letztes_ergebnis <> ?)",
        (text, profil_id, text),
    )


__all__ = [
    "Zustand",
    "einschalten",
    "ergebnis_vermerken",
    "heutiger_tag",
    "hinweis_vermerken",
    "lauf_vermerken",
    "lesen",
]
