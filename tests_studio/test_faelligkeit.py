# SPDX-FileCopyrightText: © Anzeigen-Studio contributors
# SPDX-ArtifactOfProjectHomePage: https://github.com/TingelTangelBob/Kleinanzeigen.de-botUI/
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# AP-3.9: Eine neu angelegte Anzeige darf nicht als "schon veroeffentlicht"
# gelten.
#
# Der Bot liest `updated_on or created_on` als "zuletzt (erneut) eingestellt"
# und ueberspringt bei `publish --ads=due` (Standard) alles, was juenger als
# `republication_interval` (Standard 7 Tage) ist. Schrieb das Studio schon beim
# Anlegen ein `created_on`, war eine nie online gewesene Anzeige "nicht faellig"
# und wurde stillschweigend nicht eingestellt - der Samsung-SSD-Fall.

from __future__ import annotations

from typing import TYPE_CHECKING

from anzeigen_studio.bestand import bestand_lesen, rohdaten_lesen
from anzeigen_studio.bestand import anlegen as anlegen_dienst
from anzeigen_studio.bestand import vorlagen as vorlagen_dienst

if TYPE_CHECKING:
    from pathlib import Path

_FELDER = {
    "title": "Samsung SSD 980 1TB NVMe",
    "description": "Wenig genutzt, aus einem Aufruestprojekt uebrig geblieben.",
    "price": 45,
    "price_type": "FIXED",
}


def test_anlegen_schreibt_kein_created_on(tmp_path: Path) -> None:
    angelegt = anlegen_dienst.anlegen(tmp_path, dict(_FELDER), [])

    roh = rohdaten_lesen(tmp_path, angelegt.datei)
    assert "created_on" not in roh
    assert "updated_on" not in roh
    assert angelegt.id is None


def test_frisch_angelegte_anzeige_ist_faellig(tmp_path: Path) -> None:
    """Ohne Datum greift der Sofort-Zweig: der Bot wuerde sie einstellen."""
    angelegt = anlegen_dienst.anlegen(tmp_path, dict(_FELDER), [])

    gelesen = next(a for a in bestand_lesen(tmp_path) if a.datei == angelegt.datei)
    assert gelesen.faellig is True
    assert gelesen.erstellt_am is None
    assert gelesen.neueinstellung_am is None


def test_duplikat_streift_alle_plattform_stempel_ab(tmp_path: Path) -> None:
    """AP-3.11: Kein `created_on`/`updated_on`/`id`/`content_hash` an der Kopie -
    jeder davon liesse den Bot die Kopie fuer schon online halten oder still
    ueberspringen."""
    original = anlegen_dienst.anlegen(tmp_path, dict(_FELDER), [])

    kopie = anlegen_dienst.duplizieren(tmp_path, original.datei)

    roh = rohdaten_lesen(tmp_path, kopie.datei)
    for stempel in ("created_on", "updated_on", "id", "content_hash"):
        assert stempel not in roh
    assert kopie.id is None
    assert kopie.faellig is True


def test_schreiben_verwirft_durchgereichte_stempel(tmp_path: Path) -> None:
    """AP-3.11: `schreiben` schreibt die Skip-Stempel selbst dann nicht, wenn ein
    Aufrufer sie versehentlich in `felder` mitgibt - die Zusicherung haengt nicht
    an `kopierbares_lesen`."""
    felder = dict(_FELDER)
    felder.update(
        id = 4711,
        created_on = "2026-09-01T00:00:00+00:00",
        updated_on = "2026-09-02T00:00:00+00:00",
        content_hash = "deadbeef",
    )

    relativ = anlegen_dienst.schreiben(tmp_path, felder, [])

    roh = rohdaten_lesen(tmp_path, relativ)
    for stempel in ("id", "created_on", "updated_on", "content_hash"):
        assert stempel not in roh
    gelesen = next(a for a in bestand_lesen(tmp_path) if a.datei == relativ)
    assert gelesen.faellig is True


def test_vorlage_anwenden_ergibt_anzeige_ohne_created_on(tmp_path: Path) -> None:
    """Die Vorlage traegt ein `created_on` fuer ihre Liste - die daraus
    angewendete Anzeige darf es nicht erben (AP-3.9/AP-3.11)."""
    original = anlegen_dienst.anlegen(tmp_path, dict(_FELDER), [])
    vorlage = vorlagen_dienst.aus_anzeige(tmp_path, original.datei)

    angewendet = vorlagen_dienst.anwenden(tmp_path, vorlage.datei)

    roh = rohdaten_lesen(tmp_path, angewendet.datei)
    assert "created_on" not in roh
    assert "updated_on" not in roh
    assert angewendet.id is None
    assert angewendet.faellig is True


def test_vorlage_behaelt_ein_angelegt_am(tmp_path: Path) -> None:
    """Vorlagen sehen die Faelligkeitslogik nie - ihr `created_on` bleibt, fuer die Liste."""
    original = anlegen_dienst.anlegen(tmp_path, dict(_FELDER), [])

    vorlage = vorlagen_dienst.aus_anzeige(tmp_path, original.datei)

    assert vorlage.erstellt_am is not None
    assert "created_on" in rohdaten_lesen(tmp_path, vorlage.datei)
