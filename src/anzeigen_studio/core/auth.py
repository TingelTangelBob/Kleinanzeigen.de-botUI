# SPDX-FileCopyrightText: © Anzeigen-Studio contributors
# SPDX-ArtifactOfProjectHomePage: https://github.com/TingelTangelBob/Kleinanzeigen.de-botUI/
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# Anmeldung an der Weboberflaeche (AP-1.10).
#
# Warum das kein Nebenschauplatz ist: Diese Anwendung haelt Zugangsdaten fremder
# Konten, LLM-Schluessel und - ab AP-1.8 - eine Fernsteuerung eines Browsers.
# Eine ungesicherte Oberflaeche gibt all das preis.
#
# Bewusst ohne Fremdbibliothek: scrypt und secrets stehen in der
# Standardbibliothek. Weniger Abhaengigkeiten, weniger Lizenzpruefung, weniger
# Angriffsflaeche.

from __future__ import annotations

import hashlib
import hmac
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Final

from anzeigen_studio.core.db import transaction
from anzeigen_studio.core.errors import FachlicherFehler

if TYPE_CHECKING:
    import sqlite3

#: scrypt-Parameter. n=2**15 braucht rund 32 MB und einige Zehntelsekunden -
#: fuer eine Anmeldung unmerklich, fuer Durchprobieren teuer.
_SCRYPT_N: Final = 2**15
_SCRYPT_R: Final = 8
_SCRYPT_P: Final = 1
_SCRYPT_LEN: Final = 32
_SALZ_LEN: Final = 16

#: OpenSSL begrenzt den Speicher fuer scrypt standardmaessig auf 32 MiB - genau
#: den Bedarf von n=2**15, r=8 (128 * n * r). Ohne ausdrueckliche Anhebung
#: scheitert der Aufruf mit "memory limit exceeded".
_SCRYPT_MAXMEM: Final = 128 * _SCRYPT_N * _SCRYPT_R * 2

#: Wie lange eine Sitzung ohne Zugriff gueltig bleibt.
SITZUNGSDAUER = timedelta(days = 14)

#: Rateversuche bremsen: mehr als so viele Fehlversuche in diesem Zeitraum
#: fuehren zur Sperre. Bewusst je Benutzername, nicht je IP - hinter einem
#: Reverse Proxy ist die IP oft wertlos.
MAX_FEHLVERSUCHE: Final = 5
FEHLVERSUCH_FENSTER = timedelta(minutes = 15)

#: Mindestlaenge. Kein Zwang zu Sonderzeichen - Laenge traegt mehr.
MIN_PASSWORTLAENGE: Final = 12

COOKIE_NAME: Final = "anzeigen_studio_sitzung"


def _jetzt() -> datetime:
    return datetime.now(UTC)


def _text(zeitpunkt: datetime) -> str:
    return zeitpunkt.isoformat(timespec = "seconds")


@dataclass(frozen = True, slots = True)
class Benutzer:
    id: int
    name: str


def passwort_hashen(passwort: str) -> str:
    salz = secrets.token_bytes(_SALZ_LEN)
    abgeleitet = hashlib.scrypt(
        passwort.encode("utf-8"), salt = salz,
        n = _SCRYPT_N, r = _SCRYPT_R, p = _SCRYPT_P, dklen = _SCRYPT_LEN,
        maxmem = _SCRYPT_MAXMEM,
    )
    # Parameter mitspeichern, damit sie sich spaeter erhoehen lassen, ohne
    # bestehende Hashes unlesbar zu machen.
    return f"scrypt${_SCRYPT_N}${_SCRYPT_R}${_SCRYPT_P}${salz.hex()}${abgeleitet.hex()}"


def passwort_pruefen(passwort: str, gespeichert: str) -> bool:
    try:
        verfahren, n, r, p, salz_hex, hash_hex = gespeichert.split("$")
        if verfahren != "scrypt":
            return False
        abgeleitet = hashlib.scrypt(
            passwort.encode("utf-8"), salt = bytes.fromhex(salz_hex),
            n = int(n), r = int(r), p = int(p), dklen = len(bytes.fromhex(hash_hex)),
            maxmem = 128 * int(n) * int(r) * 2,
        )
    except (ValueError, TypeError):
        return False
    # Zeitkonstanter Vergleich: ein frueher Abbruch verriete sonst, wie viele
    # Bytes stimmen.
    return hmac.compare_digest(abgeleitet.hex(), hash_hex)


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def gibt_es_benutzer(conn: sqlite3.Connection) -> bool:
    anzahl: int = conn.execute("SELECT COUNT(*) AS n FROM benutzer").fetchone()["n"]
    return anzahl > 0


def ersten_benutzer_anlegen(conn: sqlite3.Connection, name: str, passwort: str) -> Benutzer:
    """Legt das erste Konto an.

    Nur solange es noch keines gibt - danach gibt es KEINE Selbstregistrierung.
    Eine offene Registrierung waere bei einer Anwendung, die fremde
    Zugangsdaten haelt, ein Einfallstor.
    """
    if gibt_es_benutzer(conn):
        raise FachlicherFehler("Es gibt bereits ein Konto.", status = 409)
    return _anlegen(conn, name, passwort)


def _anlegen(conn: sqlite3.Connection, name: str, passwort: str) -> Benutzer:
    name = name.strip()
    if not name:
        raise FachlicherFehler("Der Benutzername darf nicht leer sein.", feld = "name")
    if len(passwort) < MIN_PASSWORTLAENGE:
        raise FachlicherFehler(
            f"Das Passwort muss mindestens {MIN_PASSWORTLAENGE} Zeichen lang sein.",
            feld = "passwort",
        )

    jetzt = _text(_jetzt())
    with transaction(conn):
        cursor = conn.execute(
            "INSERT INTO benutzer (name, passwort_hash, angelegt_am, geaendert_am) VALUES (?, ?, ?, ?)",
            (name, passwort_hashen(passwort), jetzt, jetzt),
        )
    return Benutzer(id = int(cursor.lastrowid or 0), name = name)


def _fehlversuche_zaehlen(conn: sqlite3.Connection, name: str) -> int:
    grenze = _text(_jetzt() - FEHLVERSUCH_FENSTER)
    row = conn.execute(
        "SELECT COUNT(*) AS n FROM anmeldeversuch WHERE name = ? AND zeitpunkt > ?",
        (name, grenze),
    ).fetchone()
    return int(row["n"])


def anmelden(conn: sqlite3.Connection, name: str, passwort: str) -> str:
    """Prueft die Anmeldedaten und gibt ein Sitzungstoken zurueck."""
    name = name.strip()

    if _fehlversuche_zaehlen(conn, name) >= MAX_FEHLVERSUCHE:
        raise FachlicherFehler(
            "Zu viele Fehlversuche. Bitte in einigen Minuten erneut versuchen.",
            status = 429,
        )

    row = conn.execute("SELECT id, name, passwort_hash FROM benutzer WHERE name = ?", (name,)).fetchone()

    # Auch bei unbekanntem Namen ein Hashing durchfuehren, damit die Antwortzeit
    # nicht verraet, ob es den Benutzer gibt.
    gespeichert = row["passwort_hash"] if row else passwort_hashen("dummy")
    stimmt = passwort_pruefen(passwort, gespeichert) if row else False

    if not stimmt:
        with transaction(conn):
            conn.execute(
                "INSERT INTO anmeldeversuch (name, zeitpunkt) VALUES (?, ?)",
                (name, _text(_jetzt())),
            )
        # Bewusst dieselbe Meldung fuer falschen Namen und falsches Passwort.
        raise FachlicherFehler("Benutzername oder Passwort ist falsch.", status = 401)

    token = secrets.token_urlsafe(32)
    jetzt = _jetzt()
    with transaction(conn):
        conn.execute("DELETE FROM anmeldeversuch WHERE name = ?", (name,))
        conn.execute(
            "INSERT INTO sitzung (token_hash, benutzer_id, angelegt_am, gueltig_bis, letzter_zugriff) "
            "VALUES (?, ?, ?, ?, ?)",
            (_token_hash(token), row["id"], _text(jetzt),
             _text(jetzt + SITZUNGSDAUER), _text(jetzt)),
        )
    return token


def sitzung_pruefen(conn: sqlite3.Connection, token: str | None) -> Benutzer | None:
    """Loest ein Sitzungstoken auf. Verlaengert dabei die Gueltigkeit."""
    if not token:
        return None

    row = conn.execute(
        "SELECT s.token_hash, s.gueltig_bis, b.id, b.name FROM sitzung s "
        "JOIN benutzer b ON b.id = s.benutzer_id WHERE s.token_hash = ?",
        (_token_hash(token),),
    ).fetchone()
    if row is None:
        return None

    jetzt = _jetzt()
    if datetime.fromisoformat(row["gueltig_bis"]) < jetzt:
        with transaction(conn):
            conn.execute("DELETE FROM sitzung WHERE token_hash = ?", (row["token_hash"],))
        return None

    with transaction(conn):
        conn.execute(
            "UPDATE sitzung SET letzter_zugriff = ?, gueltig_bis = ? WHERE token_hash = ?",
            (_text(jetzt), _text(jetzt + SITZUNGSDAUER), row["token_hash"]),
        )
    return Benutzer(id = row["id"], name = row["name"])


def abmelden(conn: sqlite3.Connection, token: str | None) -> None:
    if not token:
        return
    with transaction(conn):
        conn.execute("DELETE FROM sitzung WHERE token_hash = ?", (_token_hash(token),))


def passwort_aendern(conn: sqlite3.Connection, benutzer_id: int, alt: str, neu: str) -> None:
    row = conn.execute("SELECT passwort_hash FROM benutzer WHERE id = ?", (benutzer_id,)).fetchone()
    if row is None or not passwort_pruefen(alt, row["passwort_hash"]):
        raise FachlicherFehler("Das bisherige Passwort ist falsch.", status = 401, feld = "alt")
    if len(neu) < MIN_PASSWORTLAENGE:
        raise FachlicherFehler(
            f"Das Passwort muss mindestens {MIN_PASSWORTLAENGE} Zeichen lang sein.", feld = "neu",
        )
    with transaction(conn):
        conn.execute(
            "UPDATE benutzer SET passwort_hash = ?, geaendert_am = ? WHERE id = ?",
            (passwort_hashen(neu), _text(_jetzt()), benutzer_id),
        )
        # Alle anderen Sitzungen beenden: Wer sein Passwort aendert, will
        # ueblicherweise genau das erreichen.
        conn.execute("DELETE FROM sitzung WHERE benutzer_id = ?", (benutzer_id,))
