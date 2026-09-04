# SPDX-FileCopyrightText: © Anzeigen-Studio contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# Tests for the cheap, read-only account-order index (AP-3.14).

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from anzeigen_studio.bestand import plattform_reihenfolge
from kleinanzeigen_bot import order_flow


def test_ids_aus_ads_erhaelt_reihenfolge_und_entfernt_doppelte() -> None:
    ads: list[dict[str, Any]] = [{"id": "22"}, {"id": 11}, {"id": "22"}, {"id": "kaputt"}]
    assert order_flow.ids_aus_ads(ads) == [22, 11]


def test_sidecar_wird_atomar_geschrieben_und_gelesen(tmp_path: Path) -> None:
    datei = tmp_path / order_flow.DATEINAME
    order_flow.speichern(datei, [{"id": 22}, {"id": 11}])
    gelesen = plattform_reihenfolge.aus_sidecar(datei)
    assert gelesen is not None
    assert gelesen[0] == [22, 11]
    assert gelesen[1].endswith("+00:00")


def test_uebernehmen_speichert_rang_und_entfernt_sidecar(tmp_path: Path) -> None:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute(
        "CREATE TABLE plattform_reihenfolge (profil_id INTEGER PRIMARY KEY, "
        "reihenfolge TEXT NOT NULL, geprueft_am TEXT NOT NULL, geaendert_am TEXT)"
    )
    datei = tmp_path / order_flow.DATEINAME
    order_flow.speichern(datei, [{"id": 22}, {"id": 11}])
    assert plattform_reihenfolge.uebernehmen(conn, 7, datei) is True
    assert not datei.exists()
    rang, _, _ = plattform_reihenfolge.laden(conn, 7)
    assert rang == {22: 0, 11: 1}


def test_uebernehmen_meldet_unveraendert() -> None:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute(
        "CREATE TABLE plattform_reihenfolge (profil_id INTEGER PRIMARY KEY, "
        "reihenfolge TEXT NOT NULL, geprueft_am TEXT NOT NULL, geaendert_am TEXT)"
    )
    conn.execute(
        "INSERT INTO plattform_reihenfolge VALUES (7, '[22,11]', '2026-09-04T10:00:00+00:00', "
        "'2026-09-03T10:00:00+00:00')"
    )
    datei = Path("/tmp/nicht-vorhanden-order-sidecar.json")
    assert plattform_reihenfolge.uebernehmen(conn, 7, datei) is None


def test_faellig_erst_nach_einer_stunde() -> None:
    jetzt = datetime(2026, 9, 4, 12, 0, tzinfo = UTC)
    pruefung = (jetzt - timedelta(minutes = 59)).isoformat()
    assert not plattform_reihenfolge.faellig(pruefung, jetzt = jetzt)
    assert plattform_reihenfolge.faellig(
        (jetzt - timedelta(hours = 1)).isoformat(), jetzt = jetzt,
    )
