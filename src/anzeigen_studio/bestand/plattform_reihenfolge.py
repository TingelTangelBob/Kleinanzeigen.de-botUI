# SPDX-FileCopyrightText: © Anzeigen-Studio contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
# SPDX-ArtifactOfProjectHomePage: https://github.com/TingelTangelBob/Kleinanzeigen.de-botUI/
"""Persisted index of the order returned by Kleinanzeigen."""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import sqlite3
    from pathlib import Path

LOG = logging.getLogger(__name__)
DATEINAME = ".anzeigen-studio-plattform-reihenfolge.json"


def aus_sidecar(datei: Path) -> tuple[list[int], str] | None:
    """Read a bot-produced sidecar, rejecting incomplete or malformed data."""
    try:
        daten = json.loads(datei.read_text(encoding = "utf-8"))
    except (OSError, ValueError, TypeError):
        return None
    if not isinstance(daten, dict) or daten.get("version") != 1:
        return None
    roh_ids = daten.get("ids")
    geprueft = daten.get("geprueft_am")
    if not isinstance(roh_ids, list) or not isinstance(geprueft, str):
        return None
    ids: list[int] = []
    gesehen: set[int] = set()
    for wert in roh_ids:
        try:
            ad_id = int(wert)
        except (TypeError, ValueError):
            return None
        if ad_id <= 0 or ad_id in gesehen:
            return None
        ids.append(ad_id)
        gesehen.add(ad_id)
    return ids, geprueft


def uebernehmen(conn: sqlite3.Connection, profil_id: int, datei: Path) -> bool | None:
    """Import a complete sidecar and return whether the order changed.

    ``None`` means there was no valid sidecar. The file is deliberately kept
    in that case so a later successful job can retry the import.
    """
    gelesen = aus_sidecar(datei)
    if gelesen is None:
        return None
    ids, geprueft = gelesen
    reihenfolge = json.dumps(ids, separators = (",", ":"))
    alt = conn.execute(
        "SELECT reihenfolge FROM plattform_reihenfolge WHERE profil_id = ?",
        (profil_id,),
    ).fetchone()
    geaendert = alt is None or alt["reihenfolge"] != reihenfolge
    conn.execute(
        "INSERT INTO plattform_reihenfolge "
        "(profil_id, reihenfolge, geprueft_am, geaendert_am) VALUES (?, ?, ?, ?) "
        "ON CONFLICT(profil_id) DO UPDATE SET reihenfolge = excluded.reihenfolge, "
        "geprueft_am = excluded.geprueft_am, "
        "geaendert_am = CASE WHEN plattform_reihenfolge.reihenfolge <> excluded.reihenfolge "
        "THEN excluded.geprueft_am ELSE plattform_reihenfolge.geaendert_am END",
        (profil_id, reihenfolge, geprueft, geprueft if geaendert else None),
    )
    try:
        datei.unlink()
    except OSError:
        LOG.warning("Plattform-Reihenfolge gespeichert, Sidecar konnte nicht entfernt werden: %s", datei)
    return geaendert


def laden(conn: sqlite3.Connection, profil_id: int) -> tuple[dict[int, int], str | None, str | None]:
    """Return ``id -> rank`` and the two cache timestamps."""
    row = conn.execute(
        "SELECT reihenfolge, geprueft_am, geaendert_am FROM plattform_reihenfolge "
        "WHERE profil_id = ?",
        (profil_id,),
    ).fetchone()
    if row is None:
        return {}, None, None
    try:
        ids = json.loads(row["reihenfolge"])
        if not isinstance(ids, list):
            return {}, row["geprueft_am"], row["geaendert_am"]
        rang = {int(ad_id): index for index, ad_id in enumerate(ids)}
    except (TypeError, ValueError, KeyError):
        return {}, row["geprueft_am"], row["geaendert_am"]
    return rang, row["geprueft_am"], row["geaendert_am"]


def faellig(geprueft_am: str | None, *, jetzt: datetime | None = None, intervall_s: int = 3600) -> bool:
    """Whether the cheap order check is due."""
    if geprueft_am is None:
        return True
    try:
        zeitpunkt = datetime.fromisoformat(geprueft_am)
    except ValueError:
        return True
    if zeitpunkt.tzinfo is None:
        zeitpunkt = zeitpunkt.replace(tzinfo = UTC)
    return (jetzt or datetime.now(UTC)).timestamp() - zeitpunkt.timestamp() >= intervall_s
