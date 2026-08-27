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
    (
        2,
        "jobs",
        """
        CREATE TABLE job (
            id             INTEGER PRIMARY KEY AUTOINCREMENT,
            profil_id      INTEGER NOT NULL REFERENCES profil(id) ON DELETE CASCADE,
            befehl         TEXT    NOT NULL,
            argumente      TEXT    NOT NULL DEFAULT '',
            zustand        TEXT    NOT NULL,
            eingereicht_am TEXT    NOT NULL,
            gestartet_am   TEXT,
            beendet_am     TEXT,
            rueckgabecode  INTEGER,
            aufmerksamkeit TEXT    NOT NULL DEFAULT '',
            eingriff       TEXT,
            meldung        TEXT
        );

        -- Die Warteschlange fragt staendig nach dem naechsten wartenden Job
        -- eines Profils; ohne Index waere das ein voller Tabellendurchlauf.
        CREATE INDEX idx_job_profil_zustand ON job(profil_id, zustand, id);

        CREATE TABLE job_log (
            id        INTEGER PRIMARY KEY AUTOINCREMENT,
            job_id    INTEGER NOT NULL REFERENCES job(id) ON DELETE CASCADE,
            zeitpunkt TEXT    NOT NULL,
            stufe     TEXT    NOT NULL,
            text      TEXT    NOT NULL
        );

        CREATE INDEX idx_job_log_job ON job_log(job_id, id);
        """,
    ),
    (
        3,
        "anmeldung",
        """
        CREATE TABLE benutzer (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            name          TEXT    NOT NULL UNIQUE,
            passwort_hash TEXT    NOT NULL,
            angelegt_am   TEXT    NOT NULL,
            geaendert_am  TEXT    NOT NULL
        );

        -- Sitzungen serverseitig. Der Browser bekommt nur ein Zufallstoken;
        -- gespeichert wird ausschliesslich dessen Hash, damit ein Blick in die
        -- Datenbank keine gueltigen Sitzungen verschafft.
        CREATE TABLE sitzung (
            token_hash    TEXT    PRIMARY KEY,
            benutzer_id   INTEGER NOT NULL REFERENCES benutzer(id) ON DELETE CASCADE,
            angelegt_am   TEXT    NOT NULL,
            gueltig_bis   TEXT    NOT NULL,
            letzter_zugriff TEXT  NOT NULL
        );

        CREATE INDEX idx_sitzung_benutzer ON sitzung(benutzer_id);

        -- Fehlversuche, um Rateversuche zu bremsen.
        CREATE TABLE anmeldeversuch (
            id        INTEGER PRIMARY KEY AUTOINCREMENT,
            name      TEXT NOT NULL,
            zeitpunkt TEXT NOT NULL
        );

        CREATE INDEX idx_anmeldeversuch ON anmeldeversuch(name, zeitpunkt);
        """,
    ),
    (
        4,
        "wartegrund",
        """
        -- Warum ein Job noch nicht laeuft und bis wann. Ohne das steht er auf
        -- "wartet", ohne Grund und ohne Restzeit - und wer mehrere Laeufe
        -- einreiht, haelt die Taktung fuer ein Haengen.
        ALTER TABLE job ADD COLUMN wartet_bis TEXT;
        ALTER TABLE job ADD COLUMN wartegrund TEXT;
        """,
    ),
    (
        5,
        "anzeigen-glob-je-job",
        """
        -- Auf welche Anzeigendateien ein Lauf schauen darf (AP-3.3).
        --
        -- Ohne das gilt fuer jeden Lauf derselbe weite Ausschnitt. Fuer einen
        -- Lauf, der genau eine Anzeige hochladen soll, ist das zu viel: Ein
        -- falscher Schalter traefe dann den ganzen Bestand. Steht hier ein
        -- Wert, sieht der Bot ausschliesslich diese eine Datei - die Grenze
        -- liegt damit in der Konfiguration und nicht nur in einem Argument.
        ALTER TABLE job ADD COLUMN anzeigen_glob TEXT;
        """,
    ),
    (
        6,
        "laufphase",
        """
        -- Woran ein Lauf gerade ist (AP-2.8).
        --
        -- "laeuft" allein sagt zu wenig: Ein Bearbeiten-Lauf braucht gut
        -- anderthalb Minuten, und wer waehrenddessen auf kleinanzeigen.de
        -- nachsieht, findet die Anzeige unveraendert und haelt den Lauf fuer
        -- gescheitert. Genau so geschehen am 2026-08-27.
        --
        -- `phase_seit` steht daneben, weil die Dauer die eigentliche Auskunft
        -- ist: "Bild 2/3 hochladen" ist beruhigend, dieselbe Zeile seit vier
        -- Minuten ist es nicht.
        ALTER TABLE job ADD COLUMN phase TEXT;
        ALTER TABLE job ADD COLUMN phase_text TEXT;
        ALTER TABLE job ADD COLUMN phase_seit TEXT;
        """,
    ),
    (
        7,
        "anzeigenstand",
        """
        -- Die Fassung, die zuletzt mit der Plattform uebereinstimmte (AP-3.5).
        --
        -- Festgehalten wird sie, wenn der Bot die Datei geschrieben hat: beim
        -- Herunterladen und nach dem Hochladen. Danach gilt Datei == Plattform.
        --
        -- In der Datenbank und nicht als Datei neben der Anzeige: Der Bot
        -- sucht seine Anzeigen mit `ad_*.{yaml,yml,json}`, eine Begleitdatei
        -- waere von diesem Muster erfasst worden.
        CREATE TABLE anzeige_stand (
            profil_id  INTEGER NOT NULL REFERENCES profil(id) ON DELETE CASCADE,
            datei      TEXT    NOT NULL,
            stand      TEXT    NOT NULL,
            quelle     TEXT    NOT NULL,
            zeitpunkt  TEXT    NOT NULL,
            PRIMARY KEY (profil_id, datei)
        );
        """,
    ),
    (
        8,
        "geheime-einstellungen",
        """
        -- Geheimnisse, die der ganzen Installation gehoeren und nicht einem
        -- Profil (AP-4.1). Erster Bewohner: der OpenAI-Schluessel.
        --
        -- Warum nicht in einer Umgebungsvariable, wie es Roomverse macht: Dort
        -- gibt es einen Betreiber und keine Oberflaeche. Hier liegen die
        -- Kleinanzeigen-Zugangsdaten bereits verschluesselt in dieser
        -- Datenbank (AP-1.4). Ein zweiter Geheimnisweg daneben waere eine
        -- zweite Stelle, die abgesichert, gesichert und beim Umzug bedacht
        -- werden muss.
        --
        -- Verschluesselt wie alles andere mit AES-256-GCM aus core/crypto.py.
        -- Der Klartext steht nie in dieser Tabelle.
        CREATE TABLE einstellung_geheim (
            schluessel   TEXT PRIMARY KEY,
            chiffre      BLOB NOT NULL,
            geaendert_am TEXT NOT NULL
        );
        """,
    ),
    (
        9,
        "ki-verbrauch",
        """
        -- Was jeder KI-Aufruf gekostet hat (AP-4.7).
        --
        -- Kosten, die niemand zaehlt, faellt erst die Kreditkartenabrechnung
        -- auf. Ein Entwurf kostet Bruchteile eines Cents; ein Fehler in einer
        -- Schleife kostet das Tausendfache, und zwar bevor jemand hinsieht.
        --
        -- Gespeichert wird in MIKRO-DOLLAR als ganze Zahl, nicht als
        -- Fliesskommazahl: Ueber viele kleine Summanden driftet Fliesskomma,
        -- und ausgerechnet die Summe ist hier die Zahl, auf die es ankommt.
        -- Dasselbe Verfahren wie in Roomverse (`costTrackingService`).
        CREATE TABLE ki_verbrauch (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            zeitpunkt     TEXT    NOT NULL,
            profil_slug   TEXT,
            modell        TEXT    NOT NULL,
            token_eingabe INTEGER NOT NULL,
            token_ausgabe INTEGER NOT NULL,
            mikro_usd     INTEGER NOT NULL
        );

        -- Abgefragt wird immer "was lief in diesem Monat".
        CREATE INDEX idx_ki_verbrauch_zeit ON ki_verbrauch(zeitpunkt);
        """,
    ),
]


def _now() -> str:
    """Zeitstempel in UTC, ISO-8601. Einheitlich, damit Sortierung funktioniert."""
    return datetime.now(UTC).isoformat(timespec = "seconds")


def connect(database_path: Path) -> sqlite3.Connection:
    """Oeffnet die Datenbank mit den Einstellungen, die wir ueberall brauchen."""
    database_path.parent.mkdir(parents = True, exist_ok = True)
    # check_same_thread = False ist hier notwendig und sicher:
    #
    # NOTWENDIG, weil FastAPI synchrone Abhaengigkeiten im Threadpool ausfuehrt,
    # asynchrone Endpunkte aber in der Ereignisschleife. Die Verbindung entsteht
    # damit in einem anderen Thread als sie benutzt wird - SQLite verbietet das
    # standardmaessig.
    #
    # SICHER, weil jede Anfrage ihre EIGENE Verbindung bekommt und sie nicht an
    # nebenlaeufige Aufgaben weiterreicht. Der Hintergrund-Worker oeffnet
    # ebenfalls eine eigene. Es gibt also nie zwei Zugriffe gleichzeitig auf
    # dieselbe Verbindung - nur nacheinander aus verschiedenen Threads.
    conn = sqlite3.connect(database_path, isolation_level = None, check_same_thread = False)
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
