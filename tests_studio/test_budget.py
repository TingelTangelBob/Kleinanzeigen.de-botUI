# SPDX-FileCopyrightText: © Anzeigen-Studio contributors
# SPDX-ArtifactOfProjectHomePage: https://github.com/TingelTangelBob/Kleinanzeigen.de-botUI/
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# Tests der Kostengrenze (AP-4.7).

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

import pytest

from anzeigen_studio.ai import budget
from anzeigen_studio.core import db
from anzeigen_studio.core.errors import FachlicherFehler

if TYPE_CHECKING:
    from pathlib import Path


@pytest.fixture
def conn(tmp_path: Path) -> sqlite3.Connection:
    verbindung = db.connect(tmp_path / "test.db")
    db.migrate(verbindung)
    return verbindung


def _buchen(verbindung: sqlite3.Connection, mikro_usd: int) -> None:
    budget.buchen(
        verbindung, profil_slug = "test", modell = "gpt-5.6-luna",
        token_eingabe = 1000, token_ausgabe = 500, mikro_usd = mikro_usd,
    )


def test_frisches_buch_ist_leer(conn: sqlite3.Connection) -> None:
    stand = budget.verbrauch(conn, grenze_usd = 5.0)
    assert stand.mikro_usd == 0
    assert stand.aufrufe == 0
    assert not stand.erschoepft
    assert stand.grenze_usd == 5.0


def test_verbrauch_summiert_sich(conn: sqlite3.Connection) -> None:
    _buchen(conn, 1400)
    _buchen(conn, 1600)

    stand = budget.verbrauch(conn, grenze_usd = 5.0)
    assert stand.mikro_usd == 3000
    assert stand.aufrufe == 2
    assert stand.usd == pytest.approx(0.003)


def test_unter_der_grenze_geht_es_weiter(conn: sqlite3.Connection) -> None:
    _buchen(conn, 4 * budget.MIKRO_JE_USD)
    assert budget.pruefen(conn, grenze_usd = 5.0).aufrufe == 1


def test_erreichte_grenze_weist_ab(conn: sqlite3.Connection) -> None:
    _buchen(conn, 5 * budget.MIKRO_JE_USD)

    with pytest.raises(FachlicherFehler) as fehler:
        budget.pruefen(conn, grenze_usd = 5.0)

    assert fehler.value.status == 429


def test_die_meldung_nennt_den_stand_statt_nur_zu_sperren(conn: sqlite3.Connection) -> None:
    """Ohne Zahlen weiß niemand, ob ein Cent oder zehn Dollar fehlen."""
    _buchen(conn, 6 * budget.MIKRO_JE_USD)

    with pytest.raises(FachlicherFehler) as fehler:
        budget.pruefen(conn, grenze_usd = 5.0)

    meldung = fehler.value.args[0]
    assert "6.00" in meldung
    assert "5.00" in meldung
    assert "ANZEIGEN_STUDIO_KI_BUDGET_USD" in meldung


def test_grenze_null_sperrt_vollstaendig(conn: sqlite3.Connection) -> None:
    """Wer 0 setzt, will das Modul aus - und nicht einen Aufruf durchlassen."""
    with pytest.raises(FachlicherFehler):
        budget.pruefen(conn, grenze_usd = 0.0)


def test_der_vormonat_zaehlt_nicht_mit(conn: sqlite3.Connection) -> None:
    """Gezählt wird der Kalendermonat, weil der Anbieter so abrechnet."""
    vormonat = (datetime.now(UTC).replace(day = 1) - timedelta(days = 1)).isoformat(timespec = "seconds")
    conn.execute(
        "INSERT INTO ki_verbrauch "
        "(zeitpunkt, profil_slug, modell, token_eingabe, token_ausgabe, mikro_usd) "
        "VALUES (?, 'test', 'gpt-5.6-luna', 1, 1, ?)",
        (vormonat, 9 * budget.MIKRO_JE_USD),
    )
    conn.commit()

    stand = budget.verbrauch(conn, grenze_usd = 5.0)
    assert stand.mikro_usd == 0
    assert not stand.erschoepft


def test_negative_kosten_werden_nicht_gebucht(conn: sqlite3.Connection) -> None:
    """Ein Rechenfehler darf kein Guthaben erzeugen."""
    _buchen(conn, -5000)
    assert budget.verbrauch(conn, grenze_usd = 5.0).mikro_usd == 0


def test_anteil_bleibt_zwischen_null_und_eins(conn: sqlite3.Connection) -> None:
    _buchen(conn, 10 * budget.MIKRO_JE_USD)
    assert budget.verbrauch(conn, grenze_usd = 5.0).anteil == 1.0
