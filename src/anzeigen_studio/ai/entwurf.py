# SPDX-FileCopyrightText: © Anzeigen-Studio contributors
# SPDX-ArtifactOfProjectHomePage: https://github.com/TingelTangelBob/Kleinanzeigen.de-botUI/
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# Aus Fotos wird ein Anzeigenentwurf (AP-4.4, AP-4.5).
#
# EIN Aufruf, nicht zwei. Das ist die bestimmende Entwurfsentscheidung und sie
# steckt im Schema: Der Anbieter liefert nicht nur die Felder, sondern auch
# seine offenen Fragen - jede mit fertigen Antwortmoeglichkeiten, und jede
# Moeglichkeit traegt den Wert, der beim Anklicken eingesetzt wird. Das
# Beantworten ist danach reines Zusammensetzen hier im Haus und kostet nichts
# mehr. Ein zweiter Aufruf "jetzt mit den Antworten" waere bequemer zu
# schreiben und wuerde die Kosten je Anzeige verdoppeln.
#
# Der Entwurf geht NIE von selbst online. Er landet als Datei im Bestand, und
# was damit geschieht, entscheidet der Mensch (AP-4.6).

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any, Final

from anzeigen_studio.core.errors import FachlicherFehler

LOG = logging.getLogger(__name__)

#: Zustandsstufen, wie der Bot sie versteht. Links, was der Anbieter liefern
#: darf; rechts, was in die Anzeigendatei geschrieben wird.
#:
#: Der Schluessel in der Datei heisst `condition_s`. Das `_s` streift der Bot
#: selbst ab (`publishing_form.set_special_attributes`), und fuer genau diesen
#: Schluessel gibt es dort einen Sonderweg: Bietet die gewaehlte Kategorie das
#: Merkmal nicht an, wird es mit einer Warnung uebersprungen statt den Lauf
#: abzubrechen. Deshalb ist es ungefaehrlich, den Zustand immer zu setzen.
ZUSTAND_ZU_API: Final[dict[str, str]] = {
    "neu": "new",
    "wie_neu": "like_new",
    "gut": "ok",
    "in_ordnung": "alright",
    "defekt": "defect",
}

#: Wie der Zustand in der Oberflaeche heisst.
ZUSTAND_BESCHRIFTUNG: Final[dict[str, str]] = {
    "neu": "Neu",
    "wie_neu": "Wie neu",
    "gut": "Gut",
    "in_ordnung": "In Ordnung",
    "defekt": "Defekt",
}

#: Kleinanzeigen begrenzt den Titel. Der Anbieter weiss das aus der Anweisung,
#: aber verlassen wird sich darauf nicht.
TITEL_MAX: Final[int] = 65

#: Und die Beschreibung.
BESCHREIBUNG_MAX: Final[int] = 4000

# Dieser Satz wird nicht dem Anbieter ueberlassen. So steht er auch dann unter
# jeder Anzeige, wenn das Modell ihn vergisst oder leicht anders formuliert.
PRIVATVERKAUF_HINWEIS: Final[str] = (
    "Privatverkauf, daher keine Garantie, Gewährleistung und Rücknahme."
)

#: Felder, auf die sich eine Rueckfrage beziehen darf.
_FELDER: Final[frozenset[str]] = frozenset({"titel", "beschreibung", "zustand", "preis"})


def schema() -> dict[str, Any]:
    """Das JSON-Schema, das mit der Anfrage hinausgeht.

    Streng (`strict: true`): Der Anbieter garantiert eine Antwort, die dazu
    passt. Alle Felder sind Pflicht - fuer "weiss ich nicht" gibt es `null`,
    nicht das Weglassen. Ein fehlendes Feld waere sonst nicht von einem
    unsicheren zu unterscheiden.
    """
    option = {
        "type": "object",
        "additionalProperties": False,
        "required": ["text", "wert"],
        "properties": {
            "text": {"type": "string", "description": "Beschriftung des Auswahlfeldes, kurz"},
            "wert": {
                "type": "string",
                "description": (
                    "Was eingesetzt wird, wenn der Mensch das waehlt. Bei feld=zustand einer der "
                    "Werte neu/wie_neu/gut/in_ordnung/defekt. Bei feld=preis eine Zahl in Euro. "
                    "Bei feld=titel der vollstaendige neue Titel. Bei feld=beschreibung ein "
                    "vollstaendiger Satz, der an die Beschreibung angehaengt wird."
                ),
            },
        },
    }

    frage = {
        "type": "object",
        "additionalProperties": False,
        "required": ["id", "frage", "feld", "optionen", "freitext_erlaubt"],
        "properties": {
            "id": {"type": "string", "description": "kurzer eindeutiger Bezeichner, klein, ohne Leerzeichen"},
            "frage": {"type": "string", "description": "die Frage an den Menschen, auf Deutsch, ein Satz"},
            "feld": {"type": "string", "enum": sorted(_FELDER)},
            "freitext_erlaubt": {
                "type": "boolean",
                "description": "true, wenn eine eigene Eingabe sinnvoller ist als die Auswahl",
            },
            "optionen": {"type": "array", "items": option},
        },
    }

    return {
        "type": "object",
        "additionalProperties": False,
        "required": [
            "titel", "beschreibung", "zustand", "kategorie",
            "preis_euro", "preis_begruendung", "sicherheit", "fragen",
        ],
        "properties": {
            "titel": {"type": "string", "description": f"hoechstens {TITEL_MAX} Zeichen"},
            "beschreibung": {"type": "string"},
            "zustand": {
                "type": ["string", "null"],
                "enum": [*sorted(ZUSTAND_ZU_API), None],
                "description": "null, wenn sich der Zustand auf den Fotos nicht beurteilen laesst",
            },
            "kategorie": {
                "type": ["string", "null"],
                "description": "Vorschlag im Klartext, z. B. 'Elektronik > Weitere Elektronik'",
            },
            "preis_euro": {
                "type": ["number", "null"],
                "description": "realistischer Gebrauchtpreis in Euro, null wenn nicht schaetzbar",
            },
            "preis_begruendung": {"type": ["string", "null"], "description": "ein Satz, woraus sich der Preis ergibt"},
            "sicherheit": {"type": "string", "enum": ["hoch", "mittel", "niedrig"]},
            "fragen": {"type": "array", "items": frage},
        },
    }


_ANWEISUNG_GRUNDLAGE: Final[str] = f"""\
Du hilfst beim Erstellen einer privaten Kleinanzeige auf kleinanzeigen.de.
Du siehst nur die beigefügten Fotos eines Gegenstands.

Erzeuge daraus einen Anzeigenentwurf auf Deutsch:

- Titel: sachlich, suchbar, höchstens {TITEL_MAX} Zeichen. Marke und Modell
  gehören hinein, wenn sie erkennbar sind. Keine Werbesprache, keine
  Ausrufezeichen, kein "TOP" und kein "RAR".
- Beschreibung: Schreibe für potentielle Käufer in der einfachen Sprache einer
  privaten Anzeige. Beginne direkt mit dem Gegenstand und dem Angebot, nicht mit
  "Auf dem Foto ..." oder "Anhand des Fotos ...". Schreibe 3 bis 8 kurze,
  natürliche Sätze: Was wird angeboten, was gehört dazu, wie ist der Zustand und
  welche sichtbaren Gebrauchsspuren oder Mängel gibt es? Kein Werbetext, keine
  Bildanalyse und keine Hinweise darauf, was die Fotos nicht zeigen.
- Beende die Beschreibung mit genau diesem Satz: "{PRIVATVERKAUF_HINWEIS}"
- Zustand: eine der Stufen neu, wie_neu, gut, in_ordnung, defekt.
- Kategorie: ein Vorschlag im Klartext.
- Preis: ein realistischer Gebrauchtpreis in Euro für einen Privatverkauf.

Wichtige Regeln:

1. ERFINDE NICHTS. Was du nicht siehst, behauptest du nicht. Technische Daten,
   Baujahr, Herkunft oder Zubehör nur, wenn sie auf den Fotos lesbar sind.
2. Was du für die Anzeige brauchst, aber nicht sehen kannst, wird eine FRAGE.
   Jede Frage bekommt 2 bis 5 Antwortmöglichkeiten, die den häufigsten Fällen
   entsprechen. Der Wert jeder Möglichkeit ist das, was eingesetzt wird - bei
   feld=beschreibung also ein fertiger Satz, nicht ein Stichwort.
   Setze freitext_erlaubt auf true, wenn eine eigene Eingabe sinnvoller ist
   (z. B. bei einer Modellnummer, die man ablesen muss).
3. Bei Möbeln und anderen Gegenständen, bei denen die Größe für Käufer wichtig
   ist, frage nach den Maßen, wenn sie nicht auf dem Foto stehen: feld muss
   "beschreibung" sein, freitext_erlaubt muss true sein und die Frage muss um
   Länge × Breite × Höhe in Zentimetern bitten. Dafür keine Platzhalter und
   keine Antwort wie "[Länge x Breite x Höhe]" in titel oder beschreibung
   ausgeben.
4. Stelle höchstens 5 Fragen und nur solche, die den Verkauf wirklich ändern:
   Funktioniert es? Ist Zubehör dabei? Wie alt ist es? Gibt es Mängel, die man
   nicht sieht? Frage nicht nach Dingen, die auf den Fotos stehen.
5. Verwende niemals Vorlagenvariablen oder Platzhalter wie [...] , {{...}},
   <...> oder "Länge x Breite x Höhe". Wenn eine Angabe fehlt, wird sie eine
   Rückfrage oder bleibt weg.
6. Wenn du gar nicht erkennst, was der Gegenstand ist, setze sicherheit auf
   "niedrig", schreibe einen ehrlichen, allgemeinen Titel und stelle eine
   Frage mit feld=titel, deren Möglichkeiten plausible Deutungen anbieten.
7. Keine Preisverhandlungsfloskeln, kein "VB" im Titel, keine Angaben zu
   Versand oder Zahlungsart - das setzt die Anwendung selbst.
"""


def anweisung(stilteil: str | None = None) -> str:
    """Ergaenzt die Grundanweisung um wenige eigene Beschreibungstexte.

    Ohne Stilteil bleibt die Anweisung unveraendert - ein leeres Profil darf
    keinen leeren Absatz an den Anbieter schicken.
    """
    if not stilteil or not stilteil.strip():
        return _ANWEISUNG_GRUNDLAGE
    return f"{_ANWEISUNG_GRUNDLAGE}\n\n{stilteil.strip()}"


@dataclass(frozen = True, slots = True)
class Option:
    text: str
    wert: str


@dataclass(frozen = True, slots = True)
class Frage:
    id: str
    frage: str
    feld: str
    freitext_erlaubt: bool
    optionen: list[Option] = field(default_factory = list)


@dataclass(frozen = True, slots = True)
class Entwurf:
    """Der Vorschlag des Anbieters, geprueft und in Form gebracht."""

    titel: str
    beschreibung: str
    zustand: str | None
    kategorie: str | None
    preis_euro: float | None
    preis_begruendung: str | None
    sicherheit: str
    fragen: list[Frage] = field(default_factory = list)


def _text(daten: dict[str, Any], schluessel: str, *, hoechstens: int) -> str:
    wert = daten.get(schluessel)
    if not isinstance(wert, str) or not wert.strip():
        raise FachlicherFehler(
            f"Die Antwort des KI-Anbieters hatte kein Feld „{schluessel}“.", status = 502,
        )
    return wert.strip()[:hoechstens]


def aus_antwort(daten: dict[str, Any]) -> Entwurf:
    """Macht aus der Anbieterantwort einen geprueften Entwurf.

    Trotz striktem Schema wird hier noch einmal nachgesehen. Das Schema ist eine
    Zusage des Anbieters, keine Eigenschaft unseres Programms - und diese
    Schicht ist die letzte, bevor fremde Daten in eine Datei wandern.
    """
    zustand = daten.get("zustand")
    if zustand is not None and zustand not in ZUSTAND_ZU_API:
        LOG.info("Unbekannte Zustandsstufe vom Anbieter verworfen: %r", zustand)
        zustand = None

    # `isinstance(True, int)` ist wahr - ohne die bool-Abfrage waere `true`
    # ein Preis von 1,00 Euro.
    roh_preis = daten.get("preis_euro")
    preis: float | None = None
    if not isinstance(roh_preis, bool) and isinstance(roh_preis, (int, float)) and roh_preis > 0:
        preis = round(float(roh_preis), 2)

    sicherheit = daten.get("sicherheit")
    if sicherheit not in {"hoch", "mittel", "niedrig"}:
        sicherheit = "niedrig"

    roh_beschreibung = _text(daten, "beschreibung", hoechstens = BESCHREIBUNG_MAX)
    beschreibung, platzhalter_entfernt = _platzhalter_bereinigen(roh_beschreibung)
    fragen = _fragen_lesen(daten.get("fragen"))
    if platzhalter_entfernt:
        fragen = _massefrage_ergaenzen(fragen)

    return Entwurf(
        titel = _text(daten, "titel", hoechstens = TITEL_MAX),
        beschreibung = _mit_privatverkauf_hinweis(beschreibung),
        zustand = zustand,
        kategorie = (daten.get("kategorie") or None),
        preis_euro = preis,
        preis_begruendung = (daten.get("preis_begruendung") or None),
        sicherheit = sicherheit,
        fragen = fragen,
    )


_MASS_BEGRIFFE: Final[re.Pattern[str]] = re.compile(
    r"(?:maße|masse|länge|laenge|breite|höhe|hoehe|nachmessen|zentimeter|\bcm\b)",
    re.IGNORECASE,
)
_MASS_NENNUNG: Final[re.Pattern[str]] = re.compile(
    r"(?:maße|masse|länge|laenge|breite|höhe|hoehe)",
    re.IGNORECASE,
)
_MASS_PLATZHALTER: Final[re.Pattern[str]] = re.compile(
    r"(?:"
    r"\[[^\]\n]*(?:maße|masse|länge|laenge|breite|höhe|hoehe)[^\]\n]*\]"
    r"|\{[^}\n]*(?:maße|masse|länge|laenge|breite|höhe|hoehe)[^}\n]*\}"
    r"|<[^>\n]*(?:maße|masse|länge|laenge|breite|höhe|hoehe)[^>\n]*>"
    r"|\b(?:länge|laenge)\s*[x×]\s*(?:breite)\s*[x×]\s*(?:höhe|hoehe)\b"
    r")",
    re.IGNORECASE,
)


def _platzhalter_satz_entfernen(text: str, start: int, ende: int) -> str:
    """Entfernt den ganzen Satz um einen gefundenen Platzhalter."""
    links = max((text.rfind(zeichen, 0, start) for zeichen in ".!?\n"), default = -1)
    rechts = min(
        (position for zeichen in ".!?" if (position := text.find(zeichen, ende)) >= 0),
        default = len(text),
    )
    return text[:links + 1] + text[rechts + 1:]


def _platzhalter_bereinigen(text: str) -> tuple[str, bool]:
    """Entfernt Modell-Platzhalter und meldet, ob daraus eine Frage noetig ist."""
    bereinigt = text
    gefunden = False
    while (treffer := _MASS_PLATZHALTER.search(bereinigt)) is not None:
        gefunden = True
        bereinigt = _platzhalter_satz_entfernen(
            bereinigt, treffer.start(), treffer.end(),
        )

    bereinigt = re.sub(r"[ \t]+", " ", bereinigt)
    bereinigt = re.sub(r"\n\s*\n(?:\s*\n)+", "\n\n", bereinigt)
    return bereinigt.strip(), gefunden


def _massefrage_ergaenzen(fragen: list[Frage]) -> list[Frage]:
    """Sichert bei einem entfernten Mass-Platzhalter eine echte Eingabefrage."""
    for nummer, frage in enumerate(fragen):
        if not _MASS_BEGRIFFE.search(f"{frage.id} {frage.frage}"):
            continue
        frage_text = frage.frage
        if not re.search(r"nachmessen|zentimeter|\bcm\b", frage_text, re.IGNORECASE):
            frage_text += " Bitte Länge × Breite × Höhe in Zentimetern nachmessen."
        fragen[nummer] = Frage(
            id = frage.id,
            frage = frage_text[:200],
            feld = "beschreibung",
            freitext_erlaubt = True,
            optionen = [],
        )
        return fragen

    massefrage = Frage(
        id = "masse",
        frage = "Welche Maße hat der Gegenstand? Bitte Länge × Breite × Höhe in Zentimetern nachmessen.",
        feld = "beschreibung",
        freitext_erlaubt = True,
    )
    # Die Maße sind für die konkrete Beanstandung wichtiger als die letzte
    # beliebige Modellfrage. Die Obergrenze von fünf bleibt erhalten.
    return [*fragen[:4], massefrage]


def _ohne_privatverkauf_hinweis(text: str) -> str:
    """Entfernt den festen Hinweis, damit er beim Zusammensetzen nicht doppelt steht."""
    return re.sub(re.escape(PRIVATVERKAUF_HINWEIS), "", text, flags = re.IGNORECASE).strip()


def _mit_privatverkauf_hinweis(text: str) -> str:
    """Setzt den festen Hinweis genau einmal ans Ende der Beschreibung."""
    basis = _ohne_privatverkauf_hinweis(text)
    max_basis = max(0, BESCHREIBUNG_MAX - len(PRIVATVERKAUF_HINWEIS) - 2)
    basis = basis[:max_basis].rstrip()
    if not basis:
        return PRIVATVERKAUF_HINWEIS
    return f"{basis}\n\n{PRIVATVERKAUF_HINWEIS}"


def _masseantwort_als_satz(wert: str) -> str:
    """Macht eine freie Massangabe zu einem lesbaren Satz fuer die Anzeige."""
    sauber = " ".join(wert.split())
    sauber = re.sub(r"(?<=\d)\s*[xX×]\s*(?=\d)", " × ", sauber)
    satz = sauber if _MASS_NENNUNG.search(sauber) else f"Maße (Länge × Breite × Höhe): {sauber}"
    return satz if satz.endswith((".", "!", "?")) else f"{satz}."


def _fragen_lesen(roh: Any) -> list[Frage]:
    """Liest die Rueckfragen. Was nicht passt, faellt weg statt zu stoeren.

    Eine unbrauchbare Frage soll den ganzen Entwurf nicht wertlos machen - der
    Mensch kann jedes Feld ohnehin von Hand aendern.
    """
    if not isinstance(roh, list):
        return []

    fragen: list[Frage] = []
    for eintrag in roh[:5]:
        if not isinstance(eintrag, dict):
            continue
        feld = eintrag.get("feld")
        frage_text = eintrag.get("frage")
        kennung = eintrag.get("id")
        if feld not in _FELDER or not isinstance(frage_text, str) or not isinstance(kennung, str):
            continue

        optionen = [
            Option(text = o["text"].strip()[:80], wert = o["wert"].strip()[:400])
            for o in (eintrag.get("optionen") or [])
            if isinstance(o, dict)
            and isinstance(o.get("text"), str) and o["text"].strip()
            and isinstance(o.get("wert"), str) and o["wert"].strip()
        ][:5]

        freitext = bool(eintrag.get("freitext_erlaubt"))
        if not optionen and not freitext:
            # Eine Frage ohne Auswahl und ohne Eingabefeld ist unbeantwortbar.
            continue

        fragen.append(Frage(
            id = kennung.strip()[:40],
            frage = frage_text.strip()[:200],
            feld = feld,
            freitext_erlaubt = freitext,
            optionen = optionen,
        ))
    return fragen


def anwenden(entwurf: Entwurf, antworten: dict[str, str]) -> Entwurf:
    """Setzt die Antworten des Menschen in den Entwurf ein. Ohne neuen Aufruf.

    `antworten` bildet Frage-Kennung auf den gewaehlten Wert ab - entweder den
    `wert` einer Moeglichkeit oder eine eigene Eingabe. Unbekannte Kennungen
    werden uebergangen.
    """
    titel = entwurf.titel
    beschreibung = _ohne_privatverkauf_hinweis(entwurf.beschreibung)
    zustand = entwurf.zustand
    preis = entwurf.preis_euro
    zusaetze: list[str] = []

    nach_id = {frage.id: frage for frage in entwurf.fragen}
    for kennung, wert in antworten.items():
        frage = nach_id.get(kennung)
        if frage is None or not wert.strip():
            continue
        antwort = wert.strip()

        if frage.feld == "titel":
            titel = antwort[:TITEL_MAX]
        elif frage.feld == "zustand":
            # Auch eine Freitextantwort kann hier landen; nur bekannte Stufen
            # werden uebernommen.
            if antwort in ZUSTAND_ZU_API:
                zustand = antwort
        elif frage.feld == "preis":
            zahl = _zahl_lesen(antwort)
            if zahl is not None:
                preis = zahl
        else:
            zusaetze.append(
                _masseantwort_als_satz(antwort) if _MASS_BEGRIFFE.search(
                    f"{frage.id} {frage.frage}"
                ) else antwort
            )

    if zusaetze:
        beschreibung = f"{beschreibung.rstrip()}\n\n{' '.join(zusaetze)}"
    beschreibung = _mit_privatverkauf_hinweis(beschreibung)

    return Entwurf(
        titel = titel,
        beschreibung = beschreibung,
        zustand = zustand,
        kategorie = entwurf.kategorie,
        preis_euro = preis,
        preis_begruendung = entwurf.preis_begruendung,
        sicherheit = entwurf.sicherheit,
        fragen = entwurf.fragen,
    )


def _zahl_lesen(wert: str) -> float | None:
    """Liest eine Euro-Angabe aus freiem Text. '12,50 €' und '12.50' gleichermassen."""
    treffer = re.search(r"\d+(?:[.,]\d+)?", wert)
    if treffer is None:
        return None
    try:
        zahl = float(treffer.group(0).replace(",", "."))
    except ValueError:
        return None
    return round(zahl, 2) if zahl > 0 else None


def als_anzeigenfelder(entwurf: Entwurf) -> dict[str, Any]:
    """Uebersetzt den Entwurf in die Felder einer Anzeigendatei.

    Bewusst nicht gesetzt: Kategorie, Versand und "Direkt kaufen". Die Kategorie
    braucht einen Pfad aus dem Katalog, nicht den Klartextvorschlag des
    Anbieters - ein geratener Pfad liesse den Lauf spaeter im Kategoriedialog
    stehenbleiben. Der Vorschlag wandert stattdessen sichtbar in die Oberflaeche.
    """
    felder: dict[str, Any] = {
        "title": entwurf.titel,
        "description": _mit_privatverkauf_hinweis(entwurf.beschreibung),
        "special_attributes": {},
    }
    if entwurf.zustand:
        felder["special_attributes"] = {"condition_s": ZUSTAND_ZU_API[entwurf.zustand]}
    if entwurf.preis_euro is not None:
        felder["price"] = entwurf.preis_euro
        felder["price_type"] = "NEGOTIABLE"
    return felder
