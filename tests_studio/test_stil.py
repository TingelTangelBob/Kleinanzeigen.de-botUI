# SPDX-FileCopyrightText: © Anzeigen-Studio contributors
# SPDX-ArtifactOfProjectHomePage: https://github.com/TingelTangelBob/Kleinanzeigen.de-botUI/
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# Tests fuer die begrenzte lokale Stilreferenz (AP-4.2).

from __future__ import annotations

import textwrap
from pathlib import Path

from anzeigen_studio.ai import stil


def _anzeige_schreiben(wurzel: Path, nummer: int, beschreibung: str) -> None:
    ordner = wurzel / "ads" / f"anzeige-{nummer}"
    ordner.mkdir(parents = True)
    text = "description: |\n" + textwrap.indent(beschreibung, "  ") + "\n"
    (ordner / f"anzeige-{nummer}.yaml").write_text(text, encoding = "utf-8")


def test_liest_nur_wenige_beschreibungen_und_entfernt_kontakte(tmp_path: Path) -> None:
    _anzeige_schreiben(
        tmp_path, 1,
        "Gut erhalten und voll funktionsfähig.\n"
        "Kontakt: 0176 12345678 oder privat@example.de",
    )
    for nummer in range(2, stil.MAX_BEISPIELE + 3):
        _anzeige_schreiben(tmp_path, nummer, f"Eigener Beschreibungstext Nummer {nummer}.")

    profil = stil.aus_bestand(tmp_path)

    assert len(profil.beispiele) == stil.MAX_BEISPIELE
    assert "Gut erhalten" in profil.beispiele[0]
    assert "0176 12345678" not in profil.beispiele[0]
    assert "privat@example.de" not in profil.beispiele[0]
    assert "[Telefonnummer entfernt]" in profil.beispiele[0]
    assert "[E-Mail entfernt]" in profil.beispiele[0]
    assert sum(map(len, profil.beispiele)) <= stil.MAX_ZEICHEN_GESAMT


def test_stilbeispiele_werden_als_stil_und_nicht_als_sachangabe_markiert(tmp_path: Path) -> None:
    _anzeige_schreiben(tmp_path, 1, "Schlicht geschrieben und mit Gebrauchsspuren.")

    anweisungsteil = stil.aus_bestand(tmp_path).anweisungsteil()

    assert "ausschließlich als Stilreferenz" in anweisungsteil
    assert "niemals Sachangaben" in anweisungsteil
    assert "Schlicht geschrieben" in anweisungsteil
