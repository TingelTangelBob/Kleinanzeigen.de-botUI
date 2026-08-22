# SPDX-FileCopyrightText: © Anzeigen-Studio contributors
# SPDX-ArtifactOfProjectHomePage: https://github.com/TingelTangelBob/Kleinanzeigen.de-botUI/
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# Ereignisse eines Bot-Laufs (AP-1.5).
#
# Der Bot wird als Unterprozess aufgerufen; seine Ausgabe ist Text. Diese
# Schicht macht daraus etwas, mit dem die Oberflaeche arbeiten kann - ohne zu
# behaupten, mehr zu wissen als im Text steht.

from __future__ import annotations

import enum
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Final


class Stufe(enum.StrEnum):
    """Protokollstufe einer Ausgabezeile."""

    DEBUG = "debug"
    INFO = "info"
    WARNUNG = "warnung"
    FEHLER = "fehler"


class Aufmerksamkeit(enum.StrEnum):
    """Warum ein Lauf einen Menschen braucht.

    Diese drei Faelle modelliert der Upstream ausdruecklich mit eigenen
    Ausnahmetypen - er hat sie im Feld erlebt. Sie als gewoehnliche Fehler zu
    behandeln waere der schlimmste Fehler dieser Schicht, weil sie genau die
    Faelle sind, in denen lokaler und entfernter Zustand auseinanderlaufen.
    """

    #: Anzeige ist online, lokal aber nicht gespeichert. Ohne Eingriff wird sie
    #: beim naechsten Lauf ein zweites Mal veroeffentlicht.
    VEROEFFENTLICHT_NICHT_GESPEICHERT = "veroeffentlicht_nicht_gespeichert"

    #: Absenden koennte durchgegangen sein oder nicht. Ein Wiederholversuch
    #: riskiert eine Doppelanzeige.
    ABSENDEN_UNGEWISS = "absenden_ungewiss"

    #: Kategorie liess sich nicht aufloesen - ein Konfigurationsfehler, kein
    #: Zeitueberschreitungsfall. Wiederholen hilft nicht.
    KATEGORIE_UNAUFLOESBAR = "kategorie_unaufloesbar"


class Eingriff(enum.StrEnum):
    """Wartet der Lauf auf eine Eingabe? Grundlage fuer AP-1.8."""

    CAPTCHA = "captcha"
    SMS_CODE = "sms_code"
    EMAIL_BESTAETIGUNG = "email_bestaetigung"
    UNBEKANNT = "unbekannt"


#: Ausnahmenamen des Upstreams, die auf einen Aufmerksamkeitsfall hinweisen.
#: Bewusst auf die Klassennamen abgestellt, nicht auf Meldungstexte - Namen
#: sind stabiler als Formulierungen.
_AUFMERKSAMKEIT_MUSTER: Final[dict[str, Aufmerksamkeit]] = {
    "PostPublishPersistenceError": Aufmerksamkeit.VEROEFFENTLICHT_NICHT_GESPEICHERT,
    "PublishSubmissionUncertainError": Aufmerksamkeit.ABSENDEN_UNGEWISS,
    "CategoryResolutionError": Aufmerksamkeit.KATEGORIE_UNAUFLOESBAR,
}

#: Wartepunkte. Der Bot ruft an sechs Stellen dieselbe Eingabefunktion; ihre
#: Aufforderungen sind englisch und stabil genug, um sie zu erkennen.
#:
#: ACHTUNG: Diese Muster sind der zerbrechlichste Teil des Adapters. Aendert
#: der Upstream einen dieser Texte, bleibt ein Lauf stehen, OHNE dass ein Test
#: fehlschlaegt. Deshalb steht dieser Punkt ausdruecklich in der Checkliste von
#: docs/UPSTREAM-SYNC.md.
_EINGRIFF_MUSTER: Final[list[tuple[re.Pattern[str], Eingriff]]] = [
    (re.compile(r"captcha", re.IGNORECASE), Eingriff.CAPTCHA),
    (re.compile(r"6-stelligen Code|6-digit code|Telefonnummer", re.IGNORECASE), Eingriff.SMS_CODE),
    (re.compile(r"E-Mail geschickt|sent you an e-?mail", re.IGNORECASE), Eingriff.EMAIL_BESTAETIGUNG),
    (re.compile(r"Press (a key|ENTER)", re.IGNORECASE), Eingriff.UNBEKANNT),
]

#: ANSI-Steuersequenzen. Der Bot faerbt seine Ausgabe ein; in einer
#: Weboberflaeche kaemen die Codes als Zeichensalat an. Sie werden entfernt,
#: bevor die Zeile ausgewertet oder gespeichert wird - auch damit die
#: Stufenerkennung nicht an eingefaerbten Schluesselwoertern scheitert.
_ANSI = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")

_STUFE_MUSTER: Final[list[tuple[re.Pattern[str], Stufe]]] = [
    (re.compile(r"\b(ERROR|CRITICAL|FATAL)\b"), Stufe.FEHLER),
    (re.compile(r"\b(WARN|WARNING)\b"), Stufe.WARNUNG),
    (re.compile(r"\bDEBUG\b"), Stufe.DEBUG),
]


@dataclass(frozen = True, slots = True)
class Ereignis:
    """Eine Zeile Bot-Ausgabe, angereichert um das, was sich sicher erkennen laesst."""

    zeitpunkt: str
    text: str
    stufe: Stufe = Stufe.INFO
    aufmerksamkeit: Aufmerksamkeit | None = None
    eingriff: Eingriff | None = None

    @property
    def braucht_menschen(self) -> bool:
        return self.eingriff is not None


@dataclass(slots = True)
class LaufErgebnis:
    """Was am Ende eines Laufs feststeht."""

    befehl: str
    rueckgabecode: int | None
    abgebrochen: bool = False
    aufmerksamkeit: list[Aufmerksamkeit] = field(default_factory = list)

    @property
    def erfolgreich(self) -> bool:
        # Ein Rueckgabecode von 0 allein genuegt nicht: die drei
        # Aufmerksamkeitsfaelle koennen auftreten, ohne dass der Prozess
        # scheitert. Sie stillschweigend als Erfolg zu melden waere falsch.
        return self.rueckgabecode == 0 and not self.abgebrochen and not self.aufmerksamkeit


def _jetzt() -> str:
    return datetime.now(UTC).isoformat(timespec = "milliseconds")


def zeile_auswerten(zeile: str) -> Ereignis:
    """Macht aus einer Ausgabezeile ein Ereignis.

    Bewusst zurueckhaltend: Was sich nicht sicher erkennen laesst, bleibt
    INFO ohne Zusatz. Lieber eine Zeile zu wenig markieren als eine falsch.
    """
    text = _ANSI.sub("", zeile).rstrip("\n").rstrip()

    stufe = Stufe.INFO
    for stufen_muster, stufen_kandidat in _STUFE_MUSTER:
        if stufen_muster.search(text):
            stufe = stufen_kandidat
            break

    aufmerksamkeit: Aufmerksamkeit | None = None
    for name, a_kandidat in _AUFMERKSAMKEIT_MUSTER.items():
        if name in text:
            aufmerksamkeit = a_kandidat
            break

    eingriff: Eingriff | None = None
    for eingriff_muster, e_kandidat in _EINGRIFF_MUSTER:
        if eingriff_muster.search(text):
            eingriff = e_kandidat
            break

    return Ereignis(
        zeitpunkt = _jetzt(),
        text = text,
        stufe = stufe,
        aufmerksamkeit = aufmerksamkeit,
        eingriff = eingriff,
    )
