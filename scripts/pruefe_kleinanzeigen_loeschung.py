#!/usr/bin/env python3
# SPDX-FileCopyrightText: © Anzeigen-Studio contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# Read-only Gegenprobe nach dem Löschen einer Anzeige (AP-3.13).
#
# Das Skript ruft nur öffentliche Seiten mit GET auf. Es kennt weder
# Zugangsdaten noch Cookies und kann keine Anzeige löschen. Ein unbekannter
# Seiteninhalt wird bewusst nicht als Erfolg gewertet: Die sichere Antwort bei
# Captcha, Rate-Limit oder einer geänderten HTML-Struktur ist eine Rückfrage.
#
# ZWEI WEGE, UND SIE SIND NICHT GLEICHWERTIG (Befund 2026-09-04):
#
#   * ANBIETERLISTE (--anbieter/--nummer) ist der belastbare Weg. Steht die
#     Nummer nicht mehr in der öffentlichen Anzeigenliste des Anbieters, ist
#     die Anzeige weg.
#   * DETAILSEITE (--url) trägt nur in eine Richtung. kleinanzeigen.de liefert
#     die Detailseite einer GELÖSCHTEN Anzeige weiterhin mit HTTP 200 und
#     vollständigem Inhalt aus - Titel, Beschreibung und Anzeigen-ID inklusive.
#     Belegt an zwei nachweislich gelöschten Anzeigen (3503227963 unmittelbar
#     nach dem Löschlauf, 3461223245 nach mehreren Tagen). Eine erreichbare
#     Detailseite ist deshalb KEIN Beleg dafür, dass die Anzeige noch online
#     steht; sie beantwortet die Frage schlicht nicht. Nur ein 404/410 oder ein
#     ausdrücklicher Löschhinweis auf der Seite ist eine Aussage.

from __future__ import annotations

import argparse
import re
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Final, Literal
from urllib.parse import urlparse

Ergebnis = Literal["geloescht", "online", "unbekannt"]

_KLEINANZEIGEN_HOST: Final[str] = "kleinanzeigen.de"
_HTTP_OK: Final[int] = 200
_HTTP_NICHT_VERFUEGBAR: Final[tuple[int, int]] = (404, 410)
_MAX_TIMEOUT: Final[float] = 60.0
_MAX_ANTWORT_BYTES: Final[int] = 2 * 1024 * 1024
_STANDARD_TIMEOUT: Final[float] = 10.0
_ANBIETER_PFAD: Final[str] = "/s-bestandsliste.html"

#: Hinweise darauf, dass die Anbieterliste noch weitere Seiten hat. Wird die
#: gesuchte Nummer dann nicht gefunden, ist das kein Beleg fuer "geloescht" -
#: sie kann auf Seite zwei stehen.
_WEITERE_SEITEN: Final[tuple[str, ...]] = (
    "pagination-next",
    'rel="next"',
    "nächste seite",
)

# Die Formulierungen werden absichtlich als einzelne Textfragmente geprüft.
# Eine komplette DOM-Struktur wäre bei einer kleinen Layoutänderung sofort
# kaputt; die endgültige Aussage bleibt trotzdem konservativ.
_NICHT_VERFUEGBAR: Final[tuple[str, ...]] = (
    "anzeige wurde gelöscht",
    "diese anzeige wurde gelöscht",
    "anzeige ist nicht mehr verfügbar",
    "diese anzeige ist nicht mehr verfügbar",
    "gesuchte anzeige ist nicht mehr verfügbar",
    "anzeige nicht gefunden",
    "das inserat ist nicht mehr verfügbar",
)
_ANTI_BOT: Final[tuple[str, ...]] = (
    "captcha",
    "cloudflare",
    "access denied",
    "verify you are human",
    "bist du ein mensch",
)
_AKTIVE_ANZEIGE: Final[tuple[str, ...]] = (
    "aditem",
    "ad-detail",
    "ad-details",
    "m-anzeige",
    "kontakt aufnehmen",
    "nachricht senden",
)


@dataclass(frozen = True, slots = True)
class Pruefergebnis:
    status: Ergebnis
    meldung: str
    rueckgabecode: int


def _gueltige_url(url: str) -> bool:
    parsed = urlparse(url)
    host = (parsed.hostname or "").rstrip(".").lower()
    return (
        parsed.scheme == "https"
        and (host == _KLEINANZEIGEN_HOST or host.endswith("." + _KLEINANZEIGEN_HOST))
        and parsed.path.lower().startswith("/s-anzeige/")
    )


def _text(antwort: bytes) -> str:
    # HTML von kleinanzeigen.de ist UTF-8. `errors=replace` macht die Prüfung
    # auch dann ungefährlich, wenn ein Fehlerdokument anders kodiert ist.
    return re.sub(r"\s+", " ", antwort.decode("utf-8", errors = "replace").lower())


def _enthaelt_eines(text: str, fragmente: tuple[str, ...]) -> bool:
    return any(fragment in text for fragment in fragmente)


def _http_fehler(fehler: urllib.error.HTTPError) -> Pruefergebnis:
    if fehler.code in _HTTP_NICHT_VERFUEGBAR:
        return Pruefergebnis(
            status = "geloescht",
            meldung = "Prüfung: Die öffentliche URL antwortet mit " + str(fehler.code) + " – Anzeige nicht verfügbar.",
            rueckgabecode = 0,
        )
    return Pruefergebnis(
        status = "unbekannt",
        meldung = "Prüfung nicht eindeutig: kleinanzeigen.de antwortet mit HTTP " + str(fehler.code) + ".",
        rueckgabecode = 2,
    )


def _antwort_auswerten(status: int, end_url: str, inhalt: bytes) -> Pruefergebnis:
    if status in _HTTP_NICHT_VERFUEGBAR:
        return Pruefergebnis(
            status = "geloescht",
            meldung = "Prüfung: Die öffentliche URL antwortet mit " + str(status) + " – Anzeige nicht verfügbar.",
            rueckgabecode = 0,
        )

    text = _text(inhalt)
    if _enthaelt_eines(text, _NICHT_VERFUEGBAR):
        return Pruefergebnis(
            status = "geloescht",
            meldung = "Prüfung: Die Seite meldet, dass die Anzeige nicht mehr verfügbar ist.",
            rueckgabecode = 0,
        )
    if _enthaelt_eines(text, _ANTI_BOT):
        return Pruefergebnis(
            status = "unbekannt",
            meldung = "Prüfung nicht eindeutig: Die Seite verlangt eine technische Prüfung.",
            rueckgabecode = 2,
        )
    if status == _HTTP_OK and _gueltige_url(end_url) and _enthaelt_eines(text, _AKTIVE_ANZEIGE):
        # Frueher stand hier "noch online", Rueckgabecode 1. Das war falsch:
        # Eine geloeschte Anzeige liefert dieselbe Seite. Der ehrliche Befund
        # ist, dass die Detailseite die Frage nicht beantwortet.
        return Pruefergebnis(
            status = "unbekannt",
            meldung = (
                "Prüfung nicht eindeutig: Die Detailseite ist erreichbar - das sagt bei "
                "kleinanzeigen.de nichts aus, gelöschte Anzeigen werden ebenso "
                "ausgeliefert. Bitte die Anbieterliste prüfen (--anbieter/--nummer)."
            ),
            rueckgabecode = 2,
        )

    return Pruefergebnis(
        status = "unbekannt",
        meldung = "Prüfung nicht eindeutig: Antwort und Seiteninhalt lassen keine sichere Aussage zu.",
        rueckgabecode = 2,
    )


def pruefen(url: str, *, timeout: float = _STANDARD_TIMEOUT) -> Pruefergebnis:
    """Prüft eine öffentliche Anzeige-URL, ohne eine Änderung auszulösen."""
    if not _gueltige_url(url):
        return Pruefergebnis(
            status = "unbekannt",
            meldung = "Abgebrochen: Es wird nur eine https-Anzeige-URL von kleinanzeigen.de akzeptiert.",
            rueckgabecode = 2,
        )

    anfrage = urllib.request.Request(  # noqa: S310 - URL wurde oben auf kleinanzeigen.de begrenzt
        url,
        headers = {
            "Accept": "text/html,application/xhtml+xml",
            "User-Agent": "Anzeigen-Studio-Loeschpruefung/1.0 (read-only)",
        },
        method = "GET",
    )
    try:
        with urllib.request.urlopen(anfrage, timeout = timeout) as antwort:  # noqa: S310 - Host und Methode sind oben begrenzt
            status = int(antwort.status)
            end_url = antwort.geturl()
            inhalt = antwort.read(_MAX_ANTWORT_BYTES + 1)
    except urllib.error.HTTPError as fehler:
        return _http_fehler(fehler)
    except (TimeoutError, urllib.error.URLError) as fehler:
        return Pruefergebnis(
            status = "unbekannt",
            meldung = "Prüfung nicht möglich: " + type(fehler).__name__ + ".",
            rueckgabecode = 2,
        )
    return _antwort_auswerten(status, end_url, inhalt)


_ID_MUSTER: Final[re.Pattern[str]] = re.compile(
    r'data-adid="(\d+)"|/s-anzeige/[^"/]+/(\d{6,})',
)


def _nummern_der_liste(text: str) -> set[str]:
    """Alle Anzeigennummern, die in einer Anbieterliste vorkommen.

    Zwei Quellen, weil eine allein zerbrechlich waere: das Attribut
    `data-adid` der Trefferkacheln und die Nummer am Ende jedes
    Anzeigenlinks. Aendert sich das Markup einer der beiden, traegt die andere.
    """
    gefunden: set[str] = set()
    for treffer in _ID_MUSTER.finditer(text):
        gefunden.add(treffer.group(1) or treffer.group(2))
    return gefunden


def _listen_urteil(text: str, nummer: str) -> Pruefergebnis:
    """Das Urteil ueber eine bereits geladene Anbieterliste.

    Eigene Funktion, damit `anbieterliste_pruefen` das Holen macht und diese
    hier das Deuten - getrennt ist beides fuer sich lesbar und pruefbar.
    """
    if _enthaelt_eines(text, _ANTI_BOT):
        return Pruefergebnis(
            status = "unbekannt",
            meldung = "Prüfung nicht eindeutig: Die Anbieterliste verlangt eine technische Prüfung.",
            rueckgabecode = 2,
        )

    nummern = _nummern_der_liste(text)
    if nummer in nummern:
        return Pruefergebnis(
            status = "online",
            meldung = f"Prüfung: Die Anzeige {nummer} steht noch in der Liste des Anbieters "
                      f"({len(nummern)} Anzeigen).",
            rueckgabecode = 1,
        )
    if not nummern:
        return Pruefergebnis(
            status = "unbekannt",
            meldung = "Prüfung nicht eindeutig: In der Anbieterliste war keine einzige "
                      "Anzeigennummer zu finden - vermutlich hat sich die Seite geändert.",
            rueckgabecode = 2,
        )
    if _enthaelt_eines(text, _WEITERE_SEITEN):
        return Pruefergebnis(
            status = "unbekannt",
            meldung = "Prüfung nicht eindeutig: Die Anbieterliste hat mehrere Seiten; die "
                      "Anzeige kann auf einer weiteren stehen.",
            rueckgabecode = 2,
        )
    return Pruefergebnis(
        status = "geloescht",
        meldung = f"Prüfung: Die Anzeige {nummer} steht nicht mehr in der Liste des Anbieters "
                  f"({len(nummern)} andere Anzeigen sichtbar).",
        rueckgabecode = 0,
    )


def anbieterliste_pruefen(
    anbieter: str, nummer: str, *, timeout: float = _STANDARD_TIMEOUT,
) -> Pruefergebnis:
    """Steht die Nummer noch in der oeffentlichen Anzeigenliste des Anbieters?

    Das ist die belastbare Gegenprobe. Sie beantwortet genau die Frage, die
    nach einem Loeschlauf offen ist - "ist die Anzeige noch im Konto sichtbar" -
    und braucht dafuer weder Anmeldung noch Cookies.

    Konservativ in beide Richtungen: Nennt die Seite ueberhaupt keine Nummern
    oder deutet sie auf weitere Seiten hin, lautet die Antwort "unbekannt".
    Eine leere Liste koennte auch ein geaendertes Markup sein, und eine zweite
    Seite koennte die gesuchte Anzeige tragen.
    """
    if not anbieter.isdigit() or not nummer.isdigit():
        return Pruefergebnis(
            status = "unbekannt",
            meldung = "Abgebrochen: Anbieternummer und Anzeigennummer müssen Ziffern sein.",
            rueckgabecode = 2,
        )

    url = f"https://www.kleinanzeigen.de{_ANBIETER_PFAD}?userId={anbieter}"
    anfrage = urllib.request.Request(  # noqa: S310 - Host ist oben fest verdrahtet
        url,
        headers = {
            "Accept": "text/html,application/xhtml+xml",
            "User-Agent": "Anzeigen-Studio-Loeschpruefung/1.0 (read-only)",
        },
        method = "GET",
    )
    try:
        with urllib.request.urlopen(anfrage, timeout = timeout) as antwort:  # noqa: S310 - Host und Methode sind begrenzt
            status = int(antwort.status)
            inhalt = antwort.read(_MAX_ANTWORT_BYTES + 1)
    except urllib.error.HTTPError as fehler:
        return Pruefergebnis(
            status = "unbekannt",
            meldung = "Prüfung nicht eindeutig: Die Anbieterliste antwortet mit HTTP "
                      + str(fehler.code) + ".",
            rueckgabecode = 2,
        )
    except (TimeoutError, urllib.error.URLError) as fehler:
        return Pruefergebnis(
            status = "unbekannt",
            meldung = "Prüfung nicht möglich: " + type(fehler).__name__ + ".",
            rueckgabecode = 2,
        )

    if status != _HTTP_OK:
        return Pruefergebnis(
            status = "unbekannt",
            meldung = "Prüfung nicht eindeutig: Die Anbieterliste antwortet mit HTTP "
                      + str(status) + ".",
            rueckgabecode = 2,
        )

    return _listen_urteil(_text(inhalt), nummer)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description = "Read-only prüfen, ob eine Kleinanzeigen-Anzeige noch im Konto steht.",
        epilog = (
            "Belastbar ist --anbieter/--nummer über die öffentliche Anbieterliste. "
            "--url prüft die Detailseite; die beantwortet die Frage nur, wenn sie mit "
            "404/410 oder einem Löschhinweis antwortet."
        ),
    )
    parser.add_argument("--url", help = "Öffentliche URL der Anzeige (schwächerer Weg)")
    parser.add_argument(
        "--anbieter",
        help = "Anbieternummer (userId aus dem Link „Alle Anzeigen dieses Anbieters“)",
    )
    parser.add_argument("--nummer", help = "Anzeigennummer, die geprüft werden soll")
    parser.add_argument(
        "--timeout", type = float, default = _STANDARD_TIMEOUT,
        help = "Zeitlimit in Sekunden (Standard: 10)",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.timeout <= 0 or args.timeout > _MAX_TIMEOUT:
        _parser().error("--timeout muss größer als 0 und höchstens 60 sein.")

    # Entweder der belastbare Weg über die Anbieterliste oder der schwächere
    # über die Detailseite - aber einer von beiden muss angegeben sein.
    hat_liste = bool(args.anbieter) and bool(args.nummer)
    if bool(args.anbieter) != bool(args.nummer):
        _parser().error("--anbieter und --nummer gehören zusammen.")
    if not hat_liste and not args.url:
        _parser().error("Entweder --anbieter mit --nummer oder --url angeben.")

    ergebnis = (
        anbieterliste_pruefen(args.anbieter, args.nummer, timeout = args.timeout) if hat_liste
        else pruefen(args.url, timeout = args.timeout)
    )

    print(ergebnis.meldung)
    if ergebnis.status == "geloescht":
        print("Ergebnis: gelöscht / nicht mehr im Konto sichtbar.")
    elif ergebnis.status == "online":
        print("Ergebnis: steht noch online – bitte den Löschlauf prüfen.")
    else:
        print("Ergebnis: unbekannt – bitte im Browser nachsehen.")
    return ergebnis.rueckgabecode


if __name__ == "__main__":
    sys.exit(main())
