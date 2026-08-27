# SPDX-FileCopyrightText: © Anzeigen-Studio contributors
# SPDX-ArtifactOfProjectHomePage: https://github.com/TingelTangelBob/Kleinanzeigen.de-botUI/
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# Der Schluessel zum KI-Anbieter (AP-4.1).
#
# Gleiches Verfahren wie bei den Kleinanzeigen-Zugangsdaten (core/zugang.py),
# nur ohne Profilbezug: Der Anbieterschluessel gehoert dem Betreiber der
# Installation, nicht einem einzelnen Kleinanzeigen-Konto.
#
# Was die Oberflaeche ueber den Schluessel erfaehrt, ist bewusst duenn: ob einer
# hinterlegt ist, wann zuletzt, und die letzten vier Zeichen zum Wiedererkennen.
# Wer zwei Schluessel hat, muss unterscheiden koennen, welcher gerade liegt -
# mehr Auskunft braucht es dafuer nicht.

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Final

from anzeigen_studio.core.crypto import tresor_oder_fehler
from anzeigen_studio.core.db import transaction
from anzeigen_studio.core.errors import FachlicherFehler

if TYPE_CHECKING:
    import sqlite3

#: Unter diesem Namen liegt der Schluessel in `einstellung_geheim`.
SCHLUESSEL_OPENAI: Final[str] = "openai_api_key"

#: Wie viele Zeichen am Ende die Oberflaeche sehen darf. Vier genuegen zum
#: Wiedererkennen und verraten nichts Brauchbares.
_ENDE_SICHTBAR: Final[int] = 4

#: Kuerzeste Laenge, die noch plausibel ist. Nicht als Formatpruefung gedacht -
#: Anbieter aendern ihre Praefixe - sondern um ein versehentlich leeres oder
#: abgeschnittenes Einfuegen abzufangen.
_MINDESTLAENGE: Final[int] = 20


@dataclass(frozen = True, slots = True)
class KiZugangStatus:
    """Was die Oberflaeche ueber den hinterlegten Schluessel erfahren darf."""

    hinterlegt: bool
    endet_auf: str | None
    geaendert_am: str | None


def _jetzt() -> str:
    return datetime.now(UTC).isoformat(timespec = "seconds")


def status(conn: sqlite3.Connection, *, schluessel: str | None) -> KiZugangStatus:
    """Ob ein Schluessel hinterlegt ist - ohne ihn preiszugeben.

    Braucht den Verschluesselungsschluessel, weil die letzten vier Zeichen nur
    aus dem entschluesselten Wert zu holen sind. Fehlt er oder laesst sich das
    Chiffrat nicht lesen, gilt der Schluessel als hinterlegt, aber ohne Endung -
    das ist ehrlicher, als ihn zu verschweigen.
    """
    row = conn.execute(
        "SELECT chiffre, geaendert_am FROM einstellung_geheim WHERE schluessel = ?",
        (SCHLUESSEL_OPENAI,),
    ).fetchone()
    if row is None:
        return KiZugangStatus(hinterlegt = False, endet_auf = None, geaendert_am = None)

    endet_auf: str | None = None
    if schluessel:
        try:
            klartext = tresor_oder_fehler(schluessel).entschluesseln(row["chiffre"])
            endet_auf = klartext[-_ENDE_SICHTBAR:] if len(klartext) > _ENDE_SICHTBAR else None
        except FachlicherFehler:
            endet_auf = None

    return KiZugangStatus(
        hinterlegt = True,
        endet_auf = endet_auf,
        geaendert_am = row["geaendert_am"],
    )


def setzen(conn: sqlite3.Connection, api_schluessel: str, *, schluessel: str | None) -> KiZugangStatus:
    """Legt den Anbieterschluessel verschluesselt ab."""
    api_schluessel = api_schluessel.strip()
    if not api_schluessel:
        raise FachlicherFehler("Der Schlüssel darf nicht leer sein.", feld = "api_schluessel")
    if len(api_schluessel) < _MINDESTLAENGE:
        raise FachlicherFehler(
            "Der Schlüssel ist zu kurz – wurde beim Einfügen etwas abgeschnitten?",
            feld = "api_schluessel",
        )
    if any(zeichen.isspace() for zeichen in api_schluessel):
        # Ein Zeilenumbruch mitten im Schluessel bricht spaeter den HTTP-Kopf,
        # und die Meldung des Anbieters wuerde nicht darauf hinweisen.
        raise FachlicherFehler(
            "Der Schlüssel enthält Leerzeichen oder Zeilenumbrüche.", feld = "api_schluessel",
        )

    chiffre = tresor_oder_fehler(schluessel).verschluesseln(api_schluessel)
    with transaction(conn):
        conn.execute(
            "INSERT INTO einstellung_geheim (schluessel, chiffre, geaendert_am) "
            "VALUES (?, ?, ?) "
            "ON CONFLICT(schluessel) DO UPDATE SET "
            "chiffre = excluded.chiffre, geaendert_am = excluded.geaendert_am",
            (SCHLUESSEL_OPENAI, chiffre, _jetzt()),
        )
    return status(conn, schluessel = schluessel)


def entfernen(conn: sqlite3.Connection) -> None:
    """Loescht den Schluessel. Danach ist das KI-Modul aus."""
    with transaction(conn):
        conn.execute("DELETE FROM einstellung_geheim WHERE schluessel = ?", (SCHLUESSEL_OPENAI,))


def lesen(conn: sqlite3.Connection, *, schluessel: str | None) -> str:
    """Holt den Klartext-Schluessel fuer einen Aufruf beim Anbieter.

    Nur von der Anbieterschicht zu rufen, unmittelbar vor der Anfrage. Der
    Rueckgabewert darf nirgends protokolliert, in eine Antwort geschrieben oder
    in eine Ausnahme aufgenommen werden.
    """
    row = conn.execute(
        "SELECT chiffre FROM einstellung_geheim WHERE schluessel = ?",
        (SCHLUESSEL_OPENAI,),
    ).fetchone()
    if row is None:
        raise FachlicherFehler(
            "Es ist kein OpenAI-Schlüssel hinterlegt. Er lässt sich unter „Profil“ eintragen.",
            status = 409,
        )
    return tresor_oder_fehler(schluessel).entschluesseln(row["chiffre"])
