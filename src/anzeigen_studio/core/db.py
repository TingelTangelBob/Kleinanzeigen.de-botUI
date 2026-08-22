# SPDX-FileCopyrightText: © Anzeigen-Studio contributors
# SPDX-ArtifactOfProjectHomePage: https://github.com/TingelTangelBob/Kleinanzeigen.de-botUI/
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# SQLite-Zugriff und Migrationen.
#
# Bewusst ohne ORM: Das Datenmodell ist klein und die Anzeigeninhalte selbst
# liegen ohnehin als Dateien auf der Platte (siehe CONTEXT.md - die Platte ist
# die Wahrheit, die Datenbank nur Index). Ein ORM waere hier mehr Abhaengigkeit
# als Nutzen.
#
# Migrationen sind fortlaufend nummeriert, wie in SoloOffice. Sie laufen beim
# Start automatisch und sind idempotent.

from __future__ import annotations

import logging
import sqlite3
from contextlib import contextmanager
from datetime import UTC, datetime
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path

LOG = logging.getLogger(__name__)

#: Fortlaufende Migrationen. Neue kommen ans Ende und bekommen die naechste
#: Nummer. Bestehende werden NIE veraendert - eine bereits gelaufene Migration
#: nachtraeglich zu aendern, laesst bestehende und frische Datenbanken
#: auseinanderlaufen.
MIGRATIONS: list[tuple[int, str, str]] = [
    (
        1,
        "profile-grundgeruest",
        """
        CREATE TABLE profil (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            slug          TEXT    NOT NULL UNIQUE,
            anzeigename   TEXT    NOT NULL,
            angelegt_am   TEXT    NOT NULL,
            geaendert_am  TEXT    NOT NULL
        );

        -- Zugangsdaten getrennt von den Stammdaten: so laesst sich die
        -- Profiltabelle gefahrlos auslesen, ohne Geheimnisse mitzuziehen.
        -- Das Passwort liegt verschluesselt (AP-1.4), nie im Klartext.
        CREATE TABLE profil_zugang (
            profil_id        INTEGER PRIMARY KEY REFERENCES profil(id) ON DELETE CASCADE,
            benutzername     TEXT    NOT NULL,
            passwort_chiffre BLOB,
            geaendert_am     TEXT    NOT NULL
        );
        """,
    ),
]


def _now() -> str:
    """Zeitstempel in UTC, ISO-8601. Einheitlich, damit Sortierung funktioniert."""
    return datetime.now(UTC).isoformat(timespec = "seconds")


def connect(database_path: Path) -> sqlite3.Connection:
    """Oeffnet die Datenbank mit den Einstellungen, die wir ueberall brauchen."""
    database_path.parent.mkdir(parents = True, exist_ok = True)
    conn = sqlite3.connect(database_path, isolation_level = None)
    conn.row_factory = sqlite3.Row
    # WAL: erlaubt Lesen waehrend geschrieben wird. Bei einer Anwendung mit
    # laufenden Hintergrundjobs und gleichzeitiger Bedienung ist das kein Luxus.
    conn.execute("PRAGMA journal_mode = WAL")
    # Ohne dies ignoriert SQLite Fremdschluessel stillschweigend - dann liefe
    # das ON DELETE CASCADE oben ins Leere.
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA busy_timeout = 5000")
    return conn


@contextmanager
def transaction(conn: sqlite3.Connection) -> Iterator[sqlite3.Connection]:
    """Klammert Schreibvorgaenge. Bei einer Ausnahme wird zurueckgerollt."""
    conn.execute("BEGIN")
    try:
        yield conn
    except BaseException:
        conn.execute("ROLLBACK")
        raise
    conn.execute("COMMIT")


def _anweisungen(sql: str) -> Iterator[str]:
    """Zerlegt ein SQL-Skript in einzelne, vollstaendige Anweisungen.

    Notwendig, weil `executescript` eine offene Transaktion implizit
    abschliesst - ein anschliessendes COMMIT liefe dann ins Leere und die
    Migration waere nicht mehr atomar. `sqlite3.complete_statement` erkennt
    Anweisungsgrenzen zuverlaessiger als ein Aufteilen am Semikolon.
    """
    puffer = ""
    for zeile in sql.splitlines(keepends = True):
        puffer += zeile
        if sqlite3.complete_statement(puffer):
            anweisung = puffer.strip()
            if anweisung:
                yield anweisung
            puffer = ""
    rest = puffer.strip()
    if rest:
        yield rest


def migrate(conn: sqlite3.Connection) -> int:
    """Fuehrt ausstehende Migrationen aus. Gibt zurueck, wie viele es waren."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS schema_migration (
            nummer       INTEGER PRIMARY KEY,
            bezeichnung  TEXT NOT NULL,
            ausgefuehrt  TEXT NOT NULL
        )
    """)
    erledigt = {row["nummer"] for row in conn.execute("SELECT nummer FROM schema_migration")}

    angewandt = 0
    for nummer, bezeichnung, sql in MIGRATIONS:
        if nummer in erledigt:
            continue
        LOG.info("Migration %d (%s) wird ausgefuehrt", nummer, bezeichnung)
        with transaction(conn):
            for anweisung in _anweisungen(sql):
                conn.execute(anweisung)
            conn.execute(
                "INSERT INTO schema_migration (nummer, bezeichnung, ausgefuehrt) VALUES (?, ?, ?)",
                (nummer, bezeichnung, _now()),
            )
        angewandt += 1

    return angewandt
