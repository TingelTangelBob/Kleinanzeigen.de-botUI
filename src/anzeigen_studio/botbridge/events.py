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


class Phase(enum.StrEnum):
    """Woran ein Lauf gerade ist (AP-2.8).

    Nur zur Anzeige. Aus dem Ablauf wird hier NICHTS abgeleitet - eine
    verpasste oder falsch erkannte Phase darf hoechstens eine ungenaue
    Beschriftung erzeugen, niemals eine falsche Entscheidung.

    Anlass am 2026-08-27: Der Projektinhaber hat 40 Sekunden vor dem Ende
    nachgesehen, die Anzeige unveraendert vorgefunden und den Lauf fuer
    gescheitert gehalten. "Laeuft" allein sagt zu wenig, wenn ein Lauf
    anderthalb Minuten braucht.
    """

    EINLESEN = "einlesen"
    BROWSER = "browser"
    ANMELDEN = "anmelden"
    FORMULAR = "formular"
    BILDER = "bilder"
    ABSENDEN = "absenden"
    ABSCHLUSS = "abschluss"


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

#: Auch die deutschen Stufennamen, seit der Bot auf Deutsch laeuft.
#:
#: Aufgefallen am 2026-08-26 beim ersten echten Aktualisieren: Die Zeile
#: "[FEHLER] Alle 3 Versuche ... sind fehlgeschlagen" landete als "info" im
#: Protokoll. Die Sprache umzustellen war richtig - dabei zu vergessen, dass
#: die Stufenerkennung an englischen Woertern haengt, war der Fehler.
_STUFE_MUSTER: Final[list[tuple[re.Pattern[str], Stufe]]] = [
    (re.compile(r"\b(ERROR|CRITICAL|FATAL|FEHLER|KRITISCH)\b"), Stufe.FEHLER),
    (re.compile(r"\b(WARN|WARNING|WARNUNG)\b"), Stufe.WARNUNG),
    (re.compile(r"\bDEBUG\b"), Stufe.DEBUG),
]


#: Woran der Lauf gerade ist, erkannt an seinen eigenen Meldungen.
#:
#: Jeder Eintrag ist (Muster, Phase, Beschriftung). Die Beschriftung darf
#: `%s`-artige Platzhalter im Python-Format nutzen; gefuellt wird sie mit den
#: Fanggruppen des Musters. Passt keine, bleibt der Text ohne Zusatz.
#:
#: ZERBRECHLICH, wie die Eingriffsmuster daneben: Die Texte gehoeren dem
#: Upstream. Beide Sprachen stehen hier, weil die Sprache des Bots an `LANG`
#: haengt - ein Container ohne `LANG=de_DE.UTF-8` protokolliert englisch.
#: Deutsche Fassungen aus `resources/translations.de.yaml`, Stand 2026-08-27.
#: Aendert der Upstream einen Text, verliert die Anzeige ihre Genauigkeit -
#: mehr nicht. Siehe die Liste in docs/UPSTREAM-SYNC.md.
_PHASE_MUSTER: Final[list[tuple[re.Pattern[str], "Phase", str]]] = [
    # Bilder zuerst: Ihre Zeilen sind die einzigen mit einem echten Zaehler,
    # und sie sind die laengste Wartezeit im ganzen Lauf.
    (re.compile(r"uploading image (\d+)/(\d+)|Lade Bild (\d+)/(\d+)"),
     Phase.BILDER, "Bild {0}/{1} hochladen"),
    (re.compile(r"waiting for .* to be processed|Warte auf Verarbeitung"),
     Phase.BILDER, "Warte auf die Bildverarbeitung"),
    (re.compile(r"all images uploaded successfully|Alle Bilder erfolgreich hochgeladen"),
     Phase.BILDER, "Bilder sind hochgeladen"),
    (re.compile(r"removed \d+ existing image|vorhandene Bilder vor dem Hochladen entfernt"),
     Phase.BILDER, "Alte Bilder entfernen"),

    (re.compile(r"Searching for ad config files|Suche nach Anzeigendateien"),
     Phase.EINLESEN, "Anzeigen einlesen"),
    (re.compile(r"Creating Browser session|Erstelle Browser-Sitzung"),
     Phase.BROWSER, "Browser starten"),
    (re.compile(r"Checking if already logged in|Überprüfe, ob bereits eingeloggt"
                r"|Logging in\.\.\.|Anmeldung\.\.\."),
     Phase.ANMELDEN, "Anmelden"),

    # "Processing 2/5: 'Titel' from [...]" - die einzige Stelle, die sagt,
    # die wievielte von wie vielen Anzeigen gerade dran ist.
    (re.compile(r"Processing (\d+)/(\d+): .(.*?). (?:from|aus) \["),
     Phase.FORMULAR, "Anzeige {0}/{1}: {2}"),
    (re.compile(r"Publishing ad|Veröffentliche Anzeige|Updating ad|Aktualisiere Anzeige"),
     Phase.FORMULAR, "Formular ausfüllen"),

    (re.compile(r"Dismissing upsell dialog|Upsell-Dialog schließen"),
     Phase.ABSENDEN, "Absenden"),
    (re.compile(r"SUCCESS: ad (?:published|updated)|ERFOLG: Anzeige mit ID"),
     Phase.ABSCHLUSS, "Gespeichert, räume auf"),
]

#: Wie lang die Beschriftung hoechstens wird. Ein Anzeigentitel kann beliebig
#: lang sein; die Zeile soll in der Oberflaeche nicht umbrechen.
_PHASE_TEXT_MAX: Final[int] = 70


def _phase_erkennen(text: str) -> tuple[Phase, str] | None:
    """Liest aus einer Ausgabezeile, woran der Lauf gerade ist.

    Gibt None zurueck, wenn die Zeile nichts darueber sagt - das ist der
    Normalfall und ausdruecklich kein Mangel.
    """
    for muster, phase, vorlage in _PHASE_MUSTER:
        treffer = muster.search(text)
        if treffer is None:
            continue
        # Nur die Gruppen, die wirklich gefangen haben: Die Bildmuster halten
        # je Sprache ein eigenes Klammerpaar, von denen immer eines leer bleibt.
        gefangen = [g for g in treffer.groups() if g is not None]
        try:
            beschriftung = vorlage.format(*gefangen) if gefangen else vorlage
        except (IndexError, KeyError):
            # Die Vorlage erwartet mehr, als das Muster gefangen hat. Lieber
            # die nackte Vorlage zeigen als den Lauf mit einem Formatfehler
            # abbrechen - diese Schicht darf nichts kaputtmachen.
            beschriftung = vorlage
        return phase, beschriftung.strip()[:_PHASE_TEXT_MAX]
    return None


@dataclass(frozen = True, slots = True)
class Ereignis:
    """Eine Zeile Bot-Ausgabe, angereichert um das, was sich sicher erkennen laesst."""

    zeitpunkt: str
    text: str
    stufe: Stufe = Stufe.INFO
    aufmerksamkeit: Aufmerksamkeit | None = None
    eingriff: Eingriff | None = None

    #: Woran der Lauf laut dieser Zeile gerade ist. None heisst nur: Die Zeile
    #: sagt nichts darueber - die zuletzt erkannte Phase gilt weiter.
    phase: Phase | None = None
    phase_text: str | None = None

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

    #: Wie viele Fehlerzeilen im Protokoll standen.
    #:
    #: Der Bot endet auch dann mit 0, wenn keine einzige Anzeige durchging -
    #: beobachtet am 2026-08-26: "FERTIG: 0 Anzeigen aktualisiert (1 nach
    #: Wiederholungen fehlgeschlagen)", Rueckgabecode 0. Ein Lauf, in dem
    #: Fehler standen, darf nicht als erledigt in der Oberflaeche stehen.
    fehlerzeilen: int = 0

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

    phase_treffer = _phase_erkennen(text)

    return Ereignis(
        zeitpunkt = _jetzt(),
        text = text,
        stufe = stufe,
        aufmerksamkeit = aufmerksamkeit,
        eingriff = eingriff,
        phase = phase_treffer[0] if phase_treffer else None,
        phase_text = phase_treffer[1] if phase_treffer else None,
    )
