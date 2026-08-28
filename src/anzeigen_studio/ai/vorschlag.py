# SPDX-FileCopyrightText: © Anzeigen-Studio contributors
# SPDX-ArtifactOfProjectHomePage: https://github.com/TingelTangelBob/Kleinanzeigen.de-botUI/
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# Kategorie- und Versandvorschlag (AP-4.5).
#
# Das Modell liefert Klartext: "Elektronik > Weitere Elektronik". Der Bot
# braucht einen Pfad: "161/168". Zwischen beidem liegt dieses Modul.
#
# WARUM NICHT DAS MODELL DEN PFAD NENNEN LASSEN: Es wuerde einen erfinden.
# Kategoriepfade sind willkuerliche Zahlen ohne Bedeutung; ein Modell, das sie
# nicht auswendig kennt, produziert plausibel aussehenden Unsinn. Ein falscher
# Pfad faellt nicht beim Erzeugen auf, sondern erst mitten im Lauf, wenn der
# Kategoriedialog nicht weitergeht.
#
# Deshalb der Umweg: Das Modell beschreibt in Worten, hier wird gegen die
# echte Liste des Bots abgeglichen, und heraus kommt entweder ein Pfad, den es
# wirklich gibt, oder gar keiner. Vorgeschlagen wird, entschieden wird vom
# Menschen (AP-4.6).

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Final

from anzeigen_studio.katalog import daten as katalog

#: Wie viele Kategorievorschlaege hoechstens angeboten werden. Drei ist die
#: Zahl, bei der eine Auswahl noch schneller ist als ein Suchfeld.
MAX_KATEGORIEN: Final[int] = 3

#: Ab welcher Uebereinstimmung ein Treffer ueberhaupt angeboten wird. Darunter
#: ist ein Vorschlag Raten, und Raten kostet den Nutzer mehr Zeit als eine
#: leere Liste.
_MINDESTGUETE: Final[float] = 0.34

#: Die Guete mittelt ueber zwei Richtungen, siehe `kategorie_treffer`.
_RICHTUNGEN: Final[int] = 2

#: Kuerzere Woerter unterscheiden nichts: "und", "fuer", "mit" stehen in
#: jedem zweiten Kategoriepfad.
_MINDESTLAENGE_WORT: Final[int] = 3

#: Woerter, die in fast jedem Kategoriepfad stehen und deshalb nichts
#: unterscheiden.
_FUELLWOERTER: Final[frozenset[str]] = frozenset({
    "und", "oder", "sonstige", "sonstiges", "weitere", "weiteres", "mehr",
    "zubehoer", "alles", "andere", "anderes",
})

#: Groessenstufen, wie das Modell sie schaetzen darf, und ihre Entsprechung in
#: der Paketliste des Bots ("Klein", "Mittel", "Groß").
GROESSE_ZU_GRUPPE: Final[dict[str, str]] = {
    "klein": "Klein",
    "mittel": "Mittel",
    "gross": "Groß",
}

#: Was das Modell antworten darf. `sperrgut` ist bewusst dabei: Ein Sofa in ein
#: Paket zu stecken ist kein Versandfehler, sondern ein Denkfehler - dafuer
#: gibt es dann eben keinen Vorschlag, sondern Abholung.
GROESSEN: Final[tuple[str, ...]] = ("klein", "mittel", "gross", "sperrgut")


@dataclass(frozen = True, slots = True)
class KategorieVorschlag:
    wert: str
    name: str
    guete: float


@dataclass(frozen = True, slots = True)
class VersandVorschlag:
    wert: str
    groesse: str
    preis: float | None


def _woerter(text: str) -> set[str]:
    """Zerlegt einen Kategorietext in vergleichbare Woerter.

    Umlaute werden ausgeschrieben, damit "Zubehör" und "Zubehoer" dasselbe
    Wort sind - das Modell schreibt mal so, mal so.
    """
    ersetzt = (text.lower()
               .replace("ä", "ae").replace("ö", "oe").replace("ü", "ue")
               .replace("ß", "ss"))
    ohne_zeichen = unicodedata.normalize("NFKD", ersetzt).encode("ascii", "ignore").decode("ascii")
    roh = {
        wort for wort in re.split(r"[^a-z0-9]+", ohne_zeichen)
        if len(wort) >= _MINDESTLAENGE_WORT
    }
    return roh - _FUELLWOERTER


def kategorie_treffer(vorschlag: str | None) -> list[KategorieVorschlag]:
    """Sucht die Kategorien, die zum Klartextvorschlag des Modells passen.

    Bewertet wird ueber gemeinsame Woerter, gewichtet nach dem Anteil an der
    Kategorie: "Elektronik > Weitere Elektronik" soll besser zu genau dieser
    Kategorie passen als zu "Elektronik > Handy & Telefon", obwohl beide das
    Wort "Elektronik" enthalten.

    Leere Liste ist ein gueltiges Ergebnis. Ein schwacher Vorschlag ist
    schlechter als keiner: Er verleitet zum Durchklicken.
    """
    if not vorschlag or not vorschlag.strip():
        return []

    gesucht = _woerter(vorschlag)
    if not gesucht:
        return []

    bewertet: list[KategorieVorschlag] = []
    for kategorie in katalog.kategorien():
        vorhanden = _woerter(kategorie.name)
        if not vorhanden:
            continue
        gemeinsam = gesucht & vorhanden
        if not gemeinsam:
            continue

        # Beide Richtungen zaehlen: Wie viel des Gesuchten steckt in der
        # Kategorie, und wie viel der Kategorie ist getroffen. Nur die erste
        # Haelfte wuerde jede sehr allgemeine Kategorie gewinnen lassen.
        guete = (len(gemeinsam) / len(gesucht) + len(gemeinsam) / len(vorhanden)) / _RICHTUNGEN
        if guete >= _MINDESTGUETE:
            bewertet.append(KategorieVorschlag(
                wert = kategorie.wert, name = kategorie.name, guete = round(guete, 3),
            ))

    bewertet.sort(key = lambda k: (-k.guete, k.name))
    return bewertet[:MAX_KATEGORIEN]


def versand_treffer(groesse: str | None) -> list[VersandVorschlag]:
    """Schlaegt Versandpakete zur geschaetzten Groesse vor.

    Nur Pakete EINER Groessengruppe: Kleinanzeigen laesst gemischte Groessen
    nicht zu, und der Lauf braeche sonst mitten im Versanddialog ab - dieselbe
    Regel, die `bestand/bearbeiten.versandgroessen_pruefen` durchsetzt.

    Fuer `sperrgut` gibt es bewusst keinen Vorschlag: Was nicht in ein Paket
    passt, wird abgeholt, und das ist eine Entscheidung und keine Schaetzung.
    """
    gruppe = GROESSE_ZU_GRUPPE.get((groesse or "").strip().lower())
    if gruppe is None:
        return []

    je_paket = katalog.groesse_je_paket()
    preise = {p.wert: p.preis for p in katalog.versandpakete()}

    treffer = [
        VersandVorschlag(wert = name, groesse = gruppe, preis = preise.get(name))
        for name, paketgruppe in je_paket.items()
        if paketgruppe == gruppe
    ]
    # Guenstigstes zuerst - das ist die Reihenfolge, in der man waehlt.
    treffer.sort(key = lambda v: (v.preis if v.preis is not None else 9999.0, v.wert))
    return treffer
