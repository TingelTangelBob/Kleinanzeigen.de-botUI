# SPDX-FileCopyrightText: © Anzeigen-Studio contributors
# SPDX-ArtifactOfProjectHomePage: https://github.com/TingelTangelBob/Kleinanzeigen.de-botUI/
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# Anzeigennummern aus eingefügtem Text lesen (AP-3.7).
#
# Der Weg dahin ist Kopieren und Einfügen aus einem alten Nachrichtenverlauf.
# Was dabei mitkommt, ist selten sauber: mal die volle Adresse, mal nur die
# Nummer, mal beides mit Text drumherum. Deshalb wird hier gelesen und nicht
# geparst - alles, was wie eine Anzeigennummer aussieht, zaehlt.

from __future__ import annotations

import re
from dataclasses import dataclass

#: Adresse einer Anzeige: .../s-anzeige/<titel>/<nummer>-<kategorie>-<...>
#:
#: Die Nummer steht vor dem ersten Bindestrich. Die Zahlen danach sind die
#: Kategorie - wer die mitnimmt, laedt Unsinn herunter.
_AUS_ADRESSE = re.compile(r"/s-anzeige/[^/\s]+/(\d{6,})")

#: Eine allein stehende Nummer. Anzeigennummern liegen bei zehn Stellen; die
#: Untergrenze ist bewusst niedriger, weil aeltere kuerzer sein koennen.
_ALLEIN = re.compile(r"(?<!\d)(\d{8,12})(?!\d)")


@dataclass(frozen = True, slots = True)
class Fund:
    nummern: list[int]
    """Gefundene Anzeigennummern, in der Reihenfolge des Textes, ohne Doppelte."""

    unlesbare_zeilen: list[str]
    """Zeilen mit Inhalt, in denen keine Nummer steckt - fuer die Rueckmeldung."""


def nummern_lesen(text: str) -> Fund:
    """Liest Anzeigennummern aus beliebigem eingefügtem Text."""
    gefunden: list[int] = []
    gesehen: set[int] = set()
    unlesbar: list[str] = []

    for rohzeile in text.splitlines():
        zeile = rohzeile.strip()
        if not zeile:
            continue

        treffer = [*_AUS_ADRESSE.findall(zeile)]
        if not treffer:
            # Erst die Adresse, dann die nackte Zahl: In einer Adresse stehen
            # hinter der Nummer weitere Zahlen, die sonst mitgelesen wuerden.
            treffer = [*_ALLEIN.findall(zeile)]

        if not treffer:
            unlesbar.append(zeile[:120])
            continue

        for roh in treffer:
            nummer = int(roh)
            if nummer not in gesehen:
                gesehen.add(nummer)
                gefunden.append(nummer)

    return Fund(nummern = gefunden, unlesbare_zeilen = unlesbar)
