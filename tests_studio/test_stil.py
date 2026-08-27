# SPDX-FileCopyrightText: © Anzeigen-Studio contributors
# SPDX-ArtifactOfProjectHomePage: https://github.com/TingelTangelBob/Kleinanzeigen.de-botUI/
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# Tests fuer die begrenzte lokale Stilreferenz (AP-4.2).

from __future__ import annotations

import textwrap
from pathlib import Path

from anzeigen_studio.ai import stil


def _anzeige_schreiben(
    wurzel: Path, nummer: int, beschreibung: str, *, veroeffentlicht: bool = True,
) -> None:
    """Legt eine Anzeigendatei an.

    `veroeffentlicht` steuert, ob sie eine Anzeigennummer traegt - das ist das
    Merkmal, an dem das Stilprofil eigene Texte von eigenen Entwuerfen
    unterscheidet.
    """
    ordner = wurzel / "ads" / f"anzeige-{nummer}"
    ordner.mkdir(parents = True)
    kopf = f"id: {1000 + nummer}\n" if veroeffentlicht else ""
    text = kopf + "description: |\n" + textwrap.indent(beschreibung, "  ") + "\n"
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


def test_eigene_entwuerfe_dienen_nicht_als_stilvorlage(tmp_path: Path) -> None:
    """Sonst imitiert das Modell nach wenigen Entwuerfen sich selbst.

    Entwuerfe aus dem KI-Modul liegen im selben Bestand, tragen aber keine
    Anzeigennummer - sie waren nie online. Wuerden sie mitgelesen, waere das
    Stilprofil nach kurzer Zeit eine Kopie der Modellsprache statt der eigenen.
    """
    _anzeige_schreiben(tmp_path, 1, "Selbst geschriebener Text.", veroeffentlicht = True)
    _anzeige_schreiben(tmp_path, 2, "Vom Modell entworfener Text.", veroeffentlicht = False)

    beispiele = stil.aus_bestand(tmp_path).beispiele

    assert any("Selbst geschriebener" in b for b in beispiele)
    assert not any("Vom Modell entworfener" in b for b in beispiele)


def test_ohne_veroeffentlichte_anzeigen_greift_der_standardstil(tmp_path: Path) -> None:
    """AP-4.3: Wer noch nichts veroeffentlicht hat, bekommt trotzdem eine Vorgabe.

    Ohne sie schreibt das Modell in seinem eigenen Ton - fuer eine private
    Kleinanzeige regelmaessig zu glatt und zu lang.
    """
    _anzeige_schreiben(tmp_path, 1, "Nur ein Entwurf.", veroeffentlicht = False)

    profil = stil.aus_bestand(tmp_path)

    assert profil.beispiele == ()
    assert not profil.aus_eigenen_texten
    assert profil.anweisungsteil() == stil.STANDARDSTIL


def test_leeres_verzeichnis_bekommt_ebenfalls_den_standardstil(tmp_path: Path) -> None:
    profil = stil.aus_bestand(tmp_path)

    assert not profil.aus_eigenen_texten
    assert "Privatmensch" in profil.anweisungsteil()


def test_eigene_texte_verdraengen_den_standardstil(tmp_path: Path) -> None:
    _anzeige_schreiben(tmp_path, 1, "Schlicht geschrieben und mit Gebrauchsspuren.")

    profil = stil.aus_bestand(tmp_path)

    assert profil.aus_eigenen_texten
    assert stil.STANDARDSTIL not in profil.anweisungsteil()
    assert "Schlicht geschrieben" in profil.anweisungsteil()
