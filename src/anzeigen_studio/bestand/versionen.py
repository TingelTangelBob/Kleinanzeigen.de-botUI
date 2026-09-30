# SPDX-FileCopyrightText: © Anzeigen-Studio contributors
# SPDX-ArtifactOfProjectHomePage: https://github.com/TingelTangelBob/Kleinanzeigen.de-botUI/
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# Fruehere Fassungen einer Anzeigendatei (AP-3.5, MVP).
#
# Beim Speichern liegt die bisherige YAML hier, bevor die neue geschrieben
# wird. Damit laesst sich zuruecksetzen, ohne den Bot oder die Plattform zu
# fragen. Der Vergleich gegen "zuletzt veroeffentlicht" bleibt bei
# `bestand/stand.py` - dort steht der Schnappschuss nach Download/Upload.
#
# Warum in der Datenbank und nicht als Datei neben der Anzeige: Der Bot sucht
# mit `ad_*.{yaml,yml,json}`. Eine Begleitdatei waere von diesem Muster
# erfasst worden (derselbe Grund wie bei `anzeige_stand`). Die Anzeige selbst
# bleibt die Wahrheit auf der Platte; die Historie ist Meta und deshalb hier.
#
# Bilder werden nicht verdoppelt - nur der YAML-Text. Eine wiederhergestellte
# Fassung kann Bildnamen nennen, die inzwischen fehlen; das ist denselbe
# Zustand wie eine von Hand editierte Datei und wird in der Liste als Hinweis
# sichtbar, nicht als stiller Datenverlust der Historie.

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Final

from anzeigen_studio.core.errors import FachlicherFehler

if TYPE_CHECKING:
    import sqlite3
    from pathlib import Path

#: Obere Grenze je Anzeige. Ohne Deckel wuerde jedes Speichern den Bestand
#: unbegrenzt fuellen - genau das, was der Projektplan fuer AP-3.5 verbietet.
MAX_VERSIONEN: Final[int] = 20


@dataclass(frozen = True, slots = True)
class Version:
    """Eine abgelegte Fassung. `inhalt` nur, wenn ausdruecklich mitgelesen."""

    id: int
    datei: str
    angelegt_am: str
    groesse: int
    inhalt: str | None = None


def _jetzt() -> str:
    return datetime.now(UTC).isoformat(timespec = "seconds")


def ablegen(conn: sqlite3.Connection, profil_id: int, datei: str, inhalt: str) -> int:
    """Legt die bisherige Fassung ab und kuerzt auf MAX_VERSIONEN.

    Gibt die neue Versions-ID zurueck. Identischer Inhalt wie die juengste
    Fassung wird nicht noch einmal gespeichert - sonst wuerde ein Speichern
    ohne echte Aenderung die Historie mit Dubletten fuellen.
    """
    if not inhalt:
        raise FachlicherFehler("Leere Fassung laesst sich nicht ablegen.", status = 400)

    jungste = conn.execute(
        "SELECT id, inhalt FROM anzeige_version "
        "WHERE profil_id = ? AND datei = ? ORDER BY id DESC LIMIT 1",
        (profil_id, datei),
    ).fetchone()
    if jungste is not None and jungste["inhalt"] == inhalt:
        return int(jungste["id"])

    cur = conn.execute(
        "INSERT INTO anzeige_version (profil_id, datei, inhalt, angelegt_am) "
        "VALUES (?, ?, ?, ?)",
        (profil_id, datei, inhalt, _jetzt()),
    )
    if cur.lastrowid is None:
        raise RuntimeError("Versions-ID fehlt nach dem Einfügen.")
    neue_id = int(cur.lastrowid)

    ueberzaehlige = conn.execute(
        "SELECT id FROM anzeige_version WHERE profil_id = ? AND datei = ? "
        "ORDER BY id DESC LIMIT -1 OFFSET ?",
        (profil_id, datei, MAX_VERSIONEN),
    ).fetchall()
    if ueberzaehlige:
        ids = [int(z["id"]) for z in ueberzaehlige]
        # Platzhalter nur aus festen "?" - die IDs bleiben Parameter.
        platzhalter = ",".join("?" for _ in ids)
        conn.execute(
            f"DELETE FROM anzeige_version WHERE id IN ({platzhalter})",  # noqa: S608
            ids,
        )
    return neue_id


def liste(conn: sqlite3.Connection, profil_id: int, datei: str) -> list[Version]:
    """Alle Fassungen einer Anzeige, neueste zuerst. Ohne YAML-Text."""
    zeilen = conn.execute(
        "SELECT id, datei, angelegt_am, length(inhalt) AS bytes "
        "FROM anzeige_version WHERE profil_id = ? AND datei = ? "
        "ORDER BY id DESC",
        (profil_id, datei),
    ).fetchall()
    return [
        Version(
            id = int(z["id"]),
            datei = z["datei"],
            angelegt_am = z["angelegt_am"],
            groesse = int(z["bytes"]),
        )
        for z in zeilen
    ]


def lesen(conn: sqlite3.Connection, profil_id: int, datei: str, version_id: int) -> Version:
    """Eine Fassung inklusive YAML-Text."""
    z = conn.execute(
        "SELECT id, datei, angelegt_am, inhalt, length(inhalt) AS bytes "
        "FROM anzeige_version WHERE id = ? AND profil_id = ? AND datei = ?",
        (version_id, profil_id, datei),
    ).fetchone()
    if z is None:
        raise FachlicherFehler("Version nicht gefunden.", status = 404)
    return Version(
        id = int(z["id"]),
        datei = z["datei"],
        angelegt_am = z["angelegt_am"],
        groesse = int(z["bytes"]),
        inhalt = z["inhalt"],
    )


def vergessen(conn: sqlite3.Connection, profil_id: int, datei: str) -> int:
    """Loescht die Historie einer Anzeige. Gibt die Anzahl geloeschter Zeilen."""
    cur = conn.execute(
        "DELETE FROM anzeige_version WHERE profil_id = ? AND datei = ?",
        (profil_id, datei),
    )
    return int(cur.rowcount)


def zuruecksetzen(
    conn: sqlite3.Connection,
    profil_wurzel: Path,
    profil_id: int,
    datei: str,
    version_id: int,
) -> Version:
    """Schreibt eine fruehere Fassung zurueck auf die Platte.

    Vor dem Ueberschreiben wird der aktuelle Stand selbst als Version abgelegt,
    damit ein versehentliches Zuruecksetzen nicht die juengste Arbeit kostet.
    Die Wiederherstellung ist der volle YAML-Text von damals - inklusive der
    Bot-Stempel, die damals in der Datei standen. Das ist Absicht: Wer
    zuruecksetzt, will genau diesen Zustand, nicht eine Mischung.
    """
    from anzeigen_studio.bestand import bearbeiten  # noqa: PLC0415 - Pfadregeln teilen

    fassung = lesen(conn, profil_id, datei, version_id)
    if fassung.inhalt is None:  # pragma: no cover - lesen liefert inhalt immer
        raise FachlicherFehler("Version nicht gefunden.", status = 404)

    aktuell = bearbeiten.rohtext_lesen(profil_wurzel, datei)
    if aktuell != fassung.inhalt:
        ablegen(conn, profil_id, datei, aktuell)

    bearbeiten.rohtext_schreiben(profil_wurzel, datei, fassung.inhalt)
    return fassung
