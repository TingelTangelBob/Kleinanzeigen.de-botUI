# SPDX-FileCopyrightText: © Anzeigen-Studio contributors
# SPDX-ArtifactOfProjectHomePage: https://github.com/TingelTangelBob/Kleinanzeigen.de-botUI/
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# Profilverwaltung (AP-1.3).
#
# Ein Profil ist ein Kleinanzeigen-Konto mit eigenem Verzeichnisbaum. Die
# Trennung selbst uebernimmt der Bot: `Workspace.for_config()` leitet aus EINEM
# Konfigurationspfad alle abgeleiteten Pfade ab - Downloads, Logs, Browserprofil,
# Diagnose. Wir muessen also nur je Profil eine config.yaml an der richtigen
# Stelle anlegen und dem Bot beim Aufruf
#     --workspace-mode=portable --config=<pfad>
# mitgeben. Der Schalter ist Pflicht: ohne ihn greift eine Erkennungsheuristik,
# die bei einem leeren Profilordner abbricht (siehe Upstream-Codepruefung, B.4).

from __future__ import annotations

import re
import shutil
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import sqlite3
    from pathlib import Path

from anzeigen_studio.core.db import transaction
from anzeigen_studio.core.errors import FachlicherFehler

#: Erlaubt sind Kleinbuchstaben, Ziffern und Bindestrich. Bewusst eng:
#: Das Kuerzel wird zu einem Verzeichnisnamen, und alles, was Pfadanteile
#: bilden koennte, ist damit ausgeschlossen - nicht durch Filtern, sondern
#: durch Nichtzulassen.
_SLUG_MUSTER = re.compile(r"^[a-z0-9]([a-z0-9-]{0,30}[a-z0-9])?$")

#: Namen, die auf Dateisystemebene Aerger machen.
_VERBOTENE_SLUGS = frozenset({"con", "prn", "aux", "nul", "com1", "lpt1"})


def _jetzt() -> str:
    return datetime.now(UTC).isoformat(timespec = "seconds")


@dataclass(frozen = True, slots = True)
class Profil:
    id: int
    slug: str
    anzeigename: str
    angelegt_am: str
    geaendert_am: str


@dataclass(frozen = True, slots = True)
class ProfilPfade:
    """Die Verzeichnisse eines Profils.

    Spiegelt bewusst das Schema, das der Bot im portablen Modus selbst anlegt,
    statt ein eigenes danebenzustellen.
    """

    wurzel: Path

    @property
    def config_datei(self) -> Path:
        return self.wurzel / "config.yaml"

    @property
    def anzeigen_verzeichnis(self) -> Path:
        return self.wurzel / "ads"

    @property
    def browser_profil(self) -> Path:
        # Der Bot legt es im portablen Modus unter <config_dir>/.temp/ an.
        return self.wurzel / ".temp" / "browser-profile"

    @property
    def diagnose_verzeichnis(self) -> Path:
        return self.wurzel / ".temp" / "diagnostics"


def slug_pruefen(slug: str) -> str:
    """Prueft ein Kuerzel und gibt es zurueck. Wirft bei Verstoessen."""
    if not _SLUG_MUSTER.match(slug):
        raise FachlicherFehler(
            "Das Kürzel darf nur Kleinbuchstaben, Ziffern und Bindestriche enthalten, "
            "muss mit einem Buchstaben oder einer Ziffer beginnen und enden "
            "und höchstens 32 Zeichen lang sein.",
            feld = "slug",
        )
    if slug in _VERBOTENE_SLUGS:
        raise FachlicherFehler(f"Das Kürzel „{slug}“ ist reserviert.", feld = "slug")
    return slug


def pfade_fuer(profiles_dir: Path, slug: str) -> ProfilPfade:
    """Baut die Pfade eines Profils - mit Gegenprobe gegen Ausbruch.

    Das Kuerzel ist zwar bereits geprueft, aber diese Funktion wird auch mit
    Werten aus der Datenbank aufgerufen. Eine zweite Pruefung an der Stelle, wo
    aus einem Namen ein Pfad wird, kostet nichts und faengt ab, was auf anderem
    Weg hineingekommen ist.
    """
    wurzel = (profiles_dir / slug).resolve()
    basis = profiles_dir.resolve()
    if not wurzel.is_relative_to(basis):
        raise FachlicherFehler("Ungültiges Profilkürzel.", status = 400, feld = "slug")
    return ProfilPfade(wurzel = wurzel)


def _zeile_zu_profil(row: sqlite3.Row) -> Profil:
    return Profil(
        id = row["id"],
        slug = row["slug"],
        anzeigename = row["anzeigename"],
        angelegt_am = row["angelegt_am"],
        geaendert_am = row["geaendert_am"],
    )


def alle(conn: sqlite3.Connection) -> list[Profil]:
    rows = conn.execute("SELECT * FROM profil ORDER BY anzeigename COLLATE NOCASE")
    return [_zeile_zu_profil(row) for row in rows]


def nach_slug(conn: sqlite3.Connection, slug: str) -> Profil | None:
    row = conn.execute("SELECT * FROM profil WHERE slug = ?", (slug,)).fetchone()
    return _zeile_zu_profil(row) if row else None


def nach_id(conn: sqlite3.Connection, profil_id: int) -> Profil | None:
    row = conn.execute("SELECT * FROM profil WHERE id = ?", (profil_id,)).fetchone()
    return _zeile_zu_profil(row) if row else None


def anlegen(conn: sqlite3.Connection, profiles_dir: Path, slug: str, anzeigename: str) -> Profil:
    slug_pruefen(slug)
    anzeigename = anzeigename.strip()
    if not anzeigename:
        raise FachlicherFehler("Der Anzeigename darf nicht leer sein.", feld = "anzeigename")

    if nach_slug(conn, slug) is not None:
        raise FachlicherFehler(f"Ein Profil mit dem Kürzel „{slug}“ gibt es bereits.", status = 409, feld = "slug")

    pfade = pfade_fuer(profiles_dir, slug)
    jetzt = _jetzt()

    with transaction(conn):
        cursor = conn.execute(
            "INSERT INTO profil (slug, anzeigename, angelegt_am, geaendert_am) VALUES (?, ?, ?, ?)",
            (slug, anzeigename, jetzt, jetzt),
        )
        # Verzeichnisse erst innerhalb der Transaktion anlegen: schlaegt die
        # Datenbank fehl, bleibt kein verwaister Ordner zurueck.
        pfade.anzeigen_verzeichnis.mkdir(parents = True, exist_ok = True)
        profil_id = int(cursor.lastrowid or 0)

    return Profil(id = profil_id, slug = slug, anzeigename = anzeigename, angelegt_am = jetzt, geaendert_am = jetzt)


def umbenennen(conn: sqlite3.Connection, slug: str, anzeigename: str) -> Profil:
    """Aendert nur den Anzeigenamen.

    Das Kuerzel bleibt unveraenderlich - es steckt im Verzeichnispfad und in der
    config.yaml des Bots. Es zu aendern hiesse, Verzeichnisse zu verschieben
    waehrend moeglicherweise ein Lauf darauf zugreift. Wer ein anderes Kuerzel
    will, legt ein neues Profil an.
    """
    profil = nach_slug(conn, slug)
    if profil is None:
        raise FachlicherFehler("Profil nicht gefunden.", status = 404)

    anzeigename = anzeigename.strip()
    if not anzeigename:
        raise FachlicherFehler("Der Anzeigename darf nicht leer sein.", feld = "anzeigename")

    jetzt = _jetzt()
    with transaction(conn):
        conn.execute("UPDATE profil SET anzeigename = ?, geaendert_am = ? WHERE id = ?", (anzeigename, jetzt, profil.id))

    return Profil(id = profil.id, slug = profil.slug, anzeigename = anzeigename,
                  angelegt_am = profil.angelegt_am, geaendert_am = jetzt)


def loeschen(conn: sqlite3.Connection, profiles_dir: Path, slug: str, *, mit_daten: bool) -> None:
    """Loescht ein Profil.

    `mit_daten` muss vom Aufrufer ausdruecklich gesetzt werden - die Oberflaeche
    fragt vorher nach und weist darauf hin, dass der Anzeigenbestand mitgeht.
    Ohne das Kennzeichen bleiben die Dateien liegen und koennen von Hand
    gesichert werden.
    """
    profil = nach_slug(conn, slug)
    if profil is None:
        raise FachlicherFehler("Profil nicht gefunden.", status = 404)

    pfade = pfade_fuer(profiles_dir, slug)

    with transaction(conn):
        # profil_zugang haengt per ON DELETE CASCADE daran.
        conn.execute("DELETE FROM profil WHERE id = ?", (profil.id,))

    if mit_daten and pfade.wurzel.exists():
        # Nach der Transaktion: Dateien loeschen laesst sich nicht zurueckrollen,
        # also erst dann, wenn die Datenbank sicher geschrieben ist.
        shutil.rmtree(pfade.wurzel)
