# SPDX-FileCopyrightText: © Anzeigen-Studio contributors
# SPDX-ArtifactOfProjectHomePage: https://github.com/TingelTangelBob/Kleinanzeigen.de-botUI/
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# Zugangsdaten eines Profils (AP-1.4).
#
# Kernregel: Das Passwort verlaesst dieses Modul nur in zwei Richtungen -
# verschluesselt in die Datenbank, und als Umgebungsvariable an den
# Bot-Unterprozess. Es geht NIE in eine HTTP-Antwort, in eine Konfigurationsdatei
# oder in ein Log.
#
# Der Bot ersetzt in genau zwei Feldern - login.username und login.password -
# Platzhalter der Form ${VAR} durch Umgebungsvariablen. In der config.yaml auf
# der Platte steht deshalb dauerhaft nur der Platzhalter.

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from anzeigen_studio.core.crypto import tresor_oder_fehler
from anzeigen_studio.core.db import transaction
from anzeigen_studio.core.errors import FachlicherFehler

if TYPE_CHECKING:
    import sqlite3

#: Namen der Umgebungsvariablen, die der Bot-Unterprozess bekommt.
#: Muessen zu den Platzhaltern in der erzeugten config.yaml passen.
ENV_BENUTZER = "KLEINANZEIGEN_BOT_USERNAME"
ENV_PASSWORT = "KLEINANZEIGEN_BOT_PASSWORD"

#: Was in der config.yaml steht - niemals der Wert selbst.
PLATZHALTER_BENUTZER = f"${{{ENV_BENUTZER}}}"
PLATZHALTER_PASSWORT = f"${{{ENV_PASSWORT}}}"


def _jetzt() -> str:
    return datetime.now(UTC).isoformat(timespec = "seconds")


@dataclass(frozen = True, slots = True)
class ZugangStatus:
    """Was die Oberflaeche ueber die Zugangsdaten erfahren darf.

    Bewusst ohne Passwort und ohne dessen Laenge - auch eine Laengenangabe ist
    eine Information, die niemand braucht.
    """

    benutzername: str
    passwort_hinterlegt: bool
    geaendert_am: str


def status(conn: sqlite3.Connection, profil_id: int) -> ZugangStatus | None:
    row = conn.execute(
        "SELECT benutzername, passwort_chiffre, geaendert_am FROM profil_zugang WHERE profil_id = ?",
        (profil_id,),
    ).fetchone()
    if row is None:
        return None
    return ZugangStatus(
        benutzername = row["benutzername"],
        passwort_hinterlegt = row["passwort_chiffre"] is not None,
        geaendert_am = row["geaendert_am"],
    )


def setzen(
    conn: sqlite3.Connection,
    profil_id: int,
    *,
    benutzername: str,
    passwort: str | None,
    schluessel: str | None,
) -> ZugangStatus:
    """Legt Zugangsdaten ab.

    `passwort=None` laesst ein bereits gespeichertes Passwort unveraendert -
    damit kann die Oberflaeche den Benutzernamen korrigieren, ohne dass der
    Nutzer das Passwort erneut eingeben muss. Ein leerer String ist etwas
    anderes und wird abgewiesen.
    """
    benutzername = benutzername.strip()
    if not benutzername:
        raise FachlicherFehler("Der Benutzername darf nicht leer sein.", feld = "benutzername")

    vorher = status(conn, profil_id)

    if passwort is None:
        if vorher is None or not vorher.passwort_hinterlegt:
            raise FachlicherFehler(
                "Für dieses Profil ist noch kein Passwort hinterlegt.", feld = "passwort",
            )
        chiffre = None  # bestehendes Chiffrat behalten
    else:
        if not passwort:
            raise FachlicherFehler("Das Passwort darf nicht leer sein.", feld = "passwort")
        # Erst hier wird der Schluessel gebraucht - und ohne ihn geht es nicht
        # weiter. Klartext ist keine Rueckfalloption.
        chiffre = tresor_oder_fehler(schluessel).verschluesseln(passwort)

    jetzt = _jetzt()
    with transaction(conn):
        if vorher is None:
            conn.execute(
                "INSERT INTO profil_zugang (profil_id, benutzername, passwort_chiffre, geaendert_am) "
                "VALUES (?, ?, ?, ?)",
                (profil_id, benutzername, chiffre, jetzt),
            )
        elif chiffre is None:
            conn.execute(
                "UPDATE profil_zugang SET benutzername = ?, geaendert_am = ? WHERE profil_id = ?",
                (benutzername, jetzt, profil_id),
            )
        else:
            conn.execute(
                "UPDATE profil_zugang SET benutzername = ?, passwort_chiffre = ?, geaendert_am = ? "
                "WHERE profil_id = ?",
                (benutzername, chiffre, jetzt, profil_id),
            )

    ergebnis = status(conn, profil_id)
    if ergebnis is None:  # pragma: no cover - kann nach dem Schreiben nicht eintreten
        raise FachlicherFehler("Die Zugangsdaten konnten nicht gespeichert werden.", status = 500)
    return ergebnis


def entfernen(conn: sqlite3.Connection, profil_id: int) -> None:
    with transaction(conn):
        conn.execute("DELETE FROM profil_zugang WHERE profil_id = ?", (profil_id,))


def umgebung_fuer_lauf(
    conn: sqlite3.Connection,
    profil_id: int,
    *,
    schluessel: str | None,
) -> dict[str, str]:
    """Baut die Umgebungsvariablen fuer den Bot-Unterprozess.

    Das Ergebnis enthaelt das Passwort im Klartext und darf ausschliesslich an
    `subprocess` uebergeben werden - nicht protokolliert, nicht zurueckgegeben,
    nicht in die Umgebung des Backends geschrieben.
    """
    row = conn.execute(
        "SELECT benutzername, passwort_chiffre FROM profil_zugang WHERE profil_id = ?",
        (profil_id,),
    ).fetchone()
    if row is None or row["passwort_chiffre"] is None:
        raise FachlicherFehler(
            "Für dieses Profil sind keine Zugangsdaten hinterlegt.", status = 409,
        )

    passwort = tresor_oder_fehler(schluessel).entschluesseln(bytes(row["passwort_chiffre"]))
    return {ENV_BENUTZER: row["benutzername"], ENV_PASSWORT: passwort}
