# SPDX-FileCopyrightText: © Anzeigen-Studio contributors
# SPDX-ArtifactOfProjectHomePage: https://github.com/TingelTangelBob/Kleinanzeigen.de-botUI/
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# Taeglicher Abgleich der eigenen Anzeigen (AP-3.12) - Zustand und Vergleich.
#
# Hier liegt, WAS verglichen wird und was daraus in der Glocke steht. WANN
# etwas laeuft, liegt in `jobs/zeitgeber.py`; die Trennung haelt den Vergleich
# ohne Ereignisschleife und ohne Warteschlange testbar.
#
# Der Anlass: Eine Anzeige, die auf der Plattform geloescht wurde, gilt lokal
# bis zum naechsten Download weiter als aktiv. Der Bestand behauptet dann
# etwas, was nicht mehr stimmt - und niemand sieht es, weil niemand ohne Anlass
# herunterlaedt.
#
# WAS HIER NICHT PASSIERT: Es wird nichts geschrieben, was der Bot nicht selbst
# geschrieben hat. Der Abgleich vergleicht zwei Staende derselben Dateien; die
# Dateien selbst fasst allein der `download`-Lauf an. Ein Abgleich, der von
# sich aus `active: false` in eine YAML schriebe, wuerde eine Auskunft der
# Plattform erfinden, die er nicht hat.

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any, Final

from anzeigen_studio.bestand.lesen import bestand_lesen

if TYPE_CHECKING:
    import sqlite3
    from pathlib import Path

LOG = logging.getLogger(__name__)

#: Wie lange eine Meldung in der Glocke angeboten wird. Aelteres ist kein
#: Befund mehr, sondern Archiv - und die Glocke ist kein Archiv.
MELDUNG_TAGE: Final[int] = 14

#: Wie viele Anzeigen eine Meldung namentlich nennt. Darueber wird gezaehlt:
#: Eine Glockenzeile mit vierzig Titeln liest niemand.
_NAMEN_GRENZE: Final[int] = 3


@dataclass(frozen = True, slots = True)
class Zustand:
    """Der gespeicherte Stand des Abgleichs fuer ein Profil."""

    eingeschaltet: bool = False
    letzter_tag: str | None = None
    """Lokaler Kalendertag des letzten Einreihens (YYYY-MM-DD)."""

    letzter_lauf_am: str | None = None
    letztes_ergebnis: str | None = None
    job_id: int | None = None
    """Der eingereihte Lauf, solange er noch nicht ausgewertet ist."""

    vorher: dict[str, dict[str, Any]] = field(default_factory = dict)
    reihenfolge_job_id: int | None = None
    reihenfolge_letzter_lauf_am: str | None = None


@dataclass(frozen = True, slots = True)
class Aenderungen:
    """Was sich zwischen zwei Staenden an den eigenen Anzeigen getan hat.

    Bewusst nur Statusaenderungen. Ob sich ein Text geaendert hat, beantwortet
    der Vergleich aus AP-3.5 (`bestand/stand.py`) - und zwar auf Nachfrage im
    Hochladen-Dialog, nicht ungefragt in der Glocke.
    """

    nicht_mehr_online: list[str] = field(default_factory = list)
    wieder_online: list[str] = field(default_factory = list)
    neu_dazu: list[str] = field(default_factory = list)
    verschwunden: list[str] = field(default_factory = list)

    @property
    def leer(self) -> bool:
        return not (
            self.nicht_mehr_online or self.wieder_online or self.neu_dazu or self.verschwunden
        )


def _jetzt() -> str:
    return datetime.now(UTC).isoformat(timespec = "seconds")


def heutiger_tag() -> str:
    """Der lokale Kalendertag als YYYY-MM-DD.

    Bewusst lokal und nicht UTC: "einmal am Tag" meint den Tag, den der
    Betreiber im Kalender hat. Der Container bekommt `TZ=Europe/Berlin`
    (docker-compose.yml); ohne die Variable ist es UTC, und dann ist der
    Tageswechsel eben um Mitternacht UTC - falsch waere daran nichts, nur
    ueberraschend.
    """
    return datetime.now().astimezone().strftime("%Y-%m-%d")


# -- Zustand lesen und schreiben --------------------------------------------

def lesen(conn: sqlite3.Connection, profil_id: int) -> Zustand:
    """Der Stand eines Profils. Ohne Zeile gilt: aus, nie gelaufen."""
    row = conn.execute(
        "SELECT eingeschaltet, letzter_tag, letzter_lauf_am, letztes_ergebnis, job_id, vorher, "
        "reihenfolge_job_id, reihenfolge_letzter_lauf_am "
        "FROM abgleich WHERE profil_id = ?",
        (profil_id,),
    ).fetchone()
    if row is None:
        return Zustand()
    vorher: dict[str, dict[str, Any]] = {}
    if row["vorher"]:
        try:
            geladen = json.loads(row["vorher"])
        except (ValueError, TypeError):
            # Ein unlesbarer Schnappschuss ist wie keiner: Dann meldet der
            # naechste Lauf nichts, statt Unterschiede zu erfinden.
            LOG.warning("Abgleich-Schnappschuss von Profil %d ist unlesbar", profil_id)
            geladen = None
        if isinstance(geladen, dict):
            vorher = {str(k): v for k, v in geladen.items() if isinstance(v, dict)}
    return Zustand(
        eingeschaltet = bool(row["eingeschaltet"]),
        letzter_tag = row["letzter_tag"],
        letzter_lauf_am = row["letzter_lauf_am"],
        letztes_ergebnis = row["letztes_ergebnis"],
        job_id = row["job_id"],
        vorher = vorher,
        reihenfolge_job_id = row["reihenfolge_job_id"],
        reihenfolge_letzter_lauf_am = row["reihenfolge_letzter_lauf_am"],
    )


def _sicherstellen(conn: sqlite3.Connection, profil_id: int) -> None:
    conn.execute(
        "INSERT INTO abgleich (profil_id) VALUES (?) ON CONFLICT(profil_id) DO NOTHING",
        (profil_id,),
    )


def einschalten(conn: sqlite3.Connection, profil_id: int, *, an: bool) -> Zustand:
    """Schaltet den taeglichen Abgleich fuer ein Profil ein oder aus.

    Der einzige Weg, aus dem Studio heraus einen wiederkehrenden Lauf gegen das
    echte Konto zu erlauben. Ausschalten loescht die Vorgeschichte nicht - wer
    wieder einschaltet, soll sehen, wann zuletzt etwas lief.
    """
    _sicherstellen(conn, profil_id)
    conn.execute(
        "UPDATE abgleich SET eingeschaltet = ? WHERE profil_id = ?",
        (1 if an else 0, profil_id),
    )
    return lesen(conn, profil_id)


def lauf_vermerken(
    conn: sqlite3.Connection, profil_id: int, *,
    tag: str, job_id: int, vorher: dict[str, dict[str, Any]],
) -> None:
    """Haelt fest, dass fuer diesen Tag eingereiht wurde - vor dem Lauf.

    Der Tag wird beim EINREIHEN gesetzt, nicht beim Auswerten. Sonst wuerde ein
    Lauf, der scheitert oder abgebrochen wird, denselben Tag noch einmal
    ausloesen - und aus "ein Lauf je Tag" wuerde "ein Lauf je Stunde, solange
    es nicht klappt".
    """
    _sicherstellen(conn, profil_id)
    conn.execute(
        "UPDATE abgleich SET letzter_tag = ?, letzter_lauf_am = ?, job_id = ?, vorher = ? "
        "WHERE profil_id = ?",
        (tag, _jetzt(), job_id, json.dumps(vorher, sort_keys = True), profil_id),
    )


def ergebnis_vermerken(conn: sqlite3.Connection, profil_id: int, ergebnis: str) -> None:
    """Schliesst den offenen Lauf ab und schreibt, was dabei herauskam."""
    _sicherstellen(conn, profil_id)
    conn.execute(
        "UPDATE abgleich SET letztes_ergebnis = ?, job_id = NULL, vorher = NULL "
        "WHERE profil_id = ?",
        (ergebnis, profil_id),
    )


def reihenfolge_lauf_vermerken(conn: sqlite3.Connection, profil_id: int, *, job_id: int) -> None:
    """Mark a lightweight order check as queued before it starts."""
    _sicherstellen(conn, profil_id)
    conn.execute(
        "UPDATE abgleich SET reihenfolge_letzter_lauf_am = ?, reihenfolge_job_id = ? "
        "WHERE profil_id = ?",
        (_jetzt(), job_id, profil_id),
    )


def reihenfolge_ergebnis_vermerken(conn: sqlite3.Connection, profil_id: int, ergebnis: str) -> None:
    """Close a lightweight order check without touching the daily snapshot."""
    _sicherstellen(conn, profil_id)
    conn.execute(
        "UPDATE abgleich SET letztes_ergebnis = ?, reihenfolge_job_id = NULL WHERE profil_id = ?",
        (ergebnis, profil_id),
    )


def hinweis_vermerken(conn: sqlite3.Connection, profil_id: int, text: str) -> None:
    """Vermerkt einen Grund, aus dem gar nicht erst eingereiht wurde.

    Anders als `ergebnis_vermerken` ruehrt das weder `job_id` noch `vorher` an -
    es gab keinen Lauf. Geschrieben wird nur, wenn sich der Text aendert, sonst
    schriebe der Zeitgeber im Minutentakt dasselbe in die Datenbank.
    """
    _sicherstellen(conn, profil_id)
    conn.execute(
        "UPDATE abgleich SET letztes_ergebnis = ? WHERE profil_id = ? "
        "AND (letztes_ergebnis IS NULL OR letztes_ergebnis <> ?)",
        (text, profil_id, text),
    )


# -- Vergleich ---------------------------------------------------------------

def stand_aufnehmen(profil_wurzel: Path) -> dict[str, dict[str, Any]]:
    """Der Status der eigenen Anzeigen, wie er gerade auf der Platte steht.

    Schluessel ist die Anzeigennummer und nicht der Dateipfad: Der Bot benennt
    beim Herunterladen Ordner nach dem Titel um (`download.rename_existing_folders`),
    ein Pfadvergleich wuerde daraus "verschwunden und neu dazu" machen.

    Anzeigen ohne Nummer bleiben draussen. Sie waren nie online; ueber ihren
    Status auf der Plattform gibt es nichts abzugleichen.
    """
    stand: dict[str, dict[str, Any]] = {}
    for anzeige in bestand_lesen(profil_wurzel):
        if anzeige.herkunft != "eigene" or anzeige.id is None:
            continue
        stand[str(anzeige.id)] = {"titel": anzeige.titel, "online": not anzeige.geloescht}
    return stand


def _titel(eintrag: dict[str, Any] | None, nummer: str) -> str:
    if not isinstance(eintrag, dict):
        return nummer
    titel = str(eintrag.get("titel") or "").strip()
    return titel or nummer


def vergleichen(
    vorher: dict[str, dict[str, Any]], nachher: dict[str, dict[str, Any]],
    *, plattform_ids: set[str] | None = None,
) -> Aenderungen:
    """Was hat sich am Status der eigenen Anzeigen geaendert?

    Ohne einen Stand von vorher gibt es nichts zu vergleichen - der erste Lauf
    meldet deshalb nichts. Das ist Absicht: Beim ersten Mal waere jede Anzeige
    des Kontos "neu dazu", und die Glocke haette dreissig Zeilen.

    **`plattform_ids` schliesst die Luecke, die der Dateivergleich allein
    laesst** (Befund 2026-09-05). Der Bot laeuft beim Konto-Download ueber die
    Anzeigen, die auf der Uebersichtsseite STEHEN: `_download_all_ads` in
    `download_flow.py` besucht `own_ad_urls`. Eine Anzeige, die ganz aus dem
    Konto verschwunden ist, steht dort nicht mehr - ihre lokale Datei wird also
    gar nicht angefasst und behaelt `active: true`. Vorher und nachher sind
    identisch, und der Abgleich haette geschwiegen, waehrend der Bestand
    weiterhin behauptet, die Anzeige sei online.

    Die geordnete Kontoliste aus AP-3.14 beantwortet genau diese Frage: Sie
    ist die Liste der Nummern, die das Konto JETZT fuehrt. Wer lokal eine
    eigene Anzeige mit Nummer hat, die dort fehlt, hat sie nicht mehr online.

    `None` heisst "keine belastbare Liste" - dann bleibt es beim reinen
    Dateivergleich. Eine veraltete Liste waere schlimmer als keine: Sie wuerde
    jede seither eingestellte Anzeige als verschwunden melden.
    """
    if not vorher:
        return Aenderungen()

    nicht_mehr, wieder, neu, weg = [], [], [], []
    for nummer, jetzt in nachher.items():
        alt = vorher.get(nummer)
        # Die Kontoliste sticht die Datei: Sie kommt von der Plattform, die
        # Datei nur von unserem letzten Wissensstand.
        fehlt_im_konto = plattform_ids is not None and nummer not in plattform_ids
        ist_online = bool(jetzt.get("online")) and not fehlt_im_konto
        if alt is None:
            # Neu ist neu, unabhaengig von der Kontoliste. Die korrigiert nur
            # den Online-Status von Anzeigen, die wir vorher schon kannten.
            neu.append(_titel(jetzt, nummer))
            continue
        war_online = bool(alt.get("online"))
        if war_online and not ist_online:
            nicht_mehr.append(_titel(jetzt, nummer))
        elif not war_online and ist_online:
            wieder.append(_titel(jetzt, nummer))
    for nummer, alt in vorher.items():
        if nummer not in nachher:
            weg.append(_titel(alt, nummer))

    return Aenderungen(
        nicht_mehr_online = sorted(nicht_mehr),
        wieder_online = sorted(wieder),
        neu_dazu = sorted(neu),
        verschwunden = sorted(weg),
    )


def _aufzaehlen(titel: list[str]) -> str:
    if len(titel) <= _NAMEN_GRENZE:
        return ", ".join(f"„{t}“" for t in titel)
    sichtbar = ", ".join(f"„{t}“" for t in titel[:_NAMEN_GRENZE])
    return f"{sichtbar} und {len(titel) - _NAMEN_GRENZE} weitere"


def meldungstext(aenderungen: Aenderungen) -> tuple[str, str] | None:
    """Titel und Text fuer die Glocke. `None` heisst: nichts zu melden.

    Die Formulierung sagt bewusst "nicht mehr online" und nicht "gelöscht":
    Die Plattform wirft Löschen, Pausieren und "in Prüfung" auf denselben
    Status - dieselbe Vorsicht wie in `BestandsAnzeige.geloescht` (AP-3.10).
    """
    if aenderungen.leer:
        return None

    saetze: list[str] = []
    if aenderungen.nicht_mehr_online:
        saetze.append(
            f"Nicht mehr online: {_aufzaehlen(aenderungen.nicht_mehr_online)}.",
        )
    if aenderungen.wieder_online:
        saetze.append(f"Wieder online: {_aufzaehlen(aenderungen.wieder_online)}.")
    if aenderungen.neu_dazu:
        saetze.append(f"Neu im Konto: {_aufzaehlen(aenderungen.neu_dazu)}.")
    if aenderungen.verschwunden:
        saetze.append(
            f"Lokal nicht mehr vorhanden: {_aufzaehlen(aenderungen.verschwunden)}.",
        )

    anzahl = (
        len(aenderungen.nicht_mehr_online) + len(aenderungen.wieder_online)
        + len(aenderungen.neu_dazu) + len(aenderungen.verschwunden)
    )
    titel = (
        "Täglicher Abgleich: 1 Änderung" if anzahl == 1
        else f"Täglicher Abgleich: {anzahl} Änderungen"
    )
    return titel, " ".join(saetze)


# -- Meldungen ---------------------------------------------------------------

def meldung_anlegen(
    conn: sqlite3.Connection, profil_id: int, *, art: str, titel: str, text: str,
) -> int:
    cursor = conn.execute(
        "INSERT INTO abgleich_meldung (profil_id, zeitpunkt, art, titel, text) "
        "VALUES (?, ?, ?, ?, ?)",
        (profil_id, _jetzt(), art, titel, text),
    )
    return int(cursor.lastrowid or 0)


def fehlschlaege_loeschen(conn: sqlite3.Connection, profil_id: int) -> int:
    """Nimmt die Fehlschlag-Warnungen eines Profils zurueck.

    Aufgerufen, sobald ein Abgleich wieder durchlaeuft. Die Warnung sagt „der
    Bestand kann veraltet sein" - und genau das stimmt ab diesem Moment nicht
    mehr. Eine Warnung, die nach der Behebung stehen bleibt, bringt Menschen
    dazu, Warnungen zu ueberlesen.
    """
    cursor = conn.execute(
        "DELETE FROM abgleich_meldung WHERE profil_id = ? AND art = 'fehlschlag'",
        (profil_id,),
    )
    return cursor.rowcount or 0


def meldungen(conn: sqlite3.Connection, *, tage: int = MELDUNG_TAGE) -> list[dict[str, Any]]:
    """Die juengsten Befunde aller Profile, neueste zuerst."""
    grenze = (datetime.now(UTC) - timedelta(days = tage)).isoformat(timespec = "seconds")
    rows = conn.execute(
        "SELECT m.id, m.profil_id, p.slug, p.anzeigename, m.zeitpunkt, m.art, m.titel, m.text "
        "FROM abgleich_meldung m JOIN profil p ON p.id = m.profil_id "
        "WHERE m.zeitpunkt >= ? ORDER BY m.id DESC",
        (grenze,),
    ).fetchall()
    return [dict(row) for row in rows]


def aufraeumen(conn: sqlite3.Connection, *, tage: int = MELDUNG_TAGE) -> int:
    """Wirft Meldungen weg, die aelter sind als das Fenster der Glocke."""
    grenze = (datetime.now(UTC) - timedelta(days = tage)).isoformat(timespec = "seconds")
    cursor = conn.execute("DELETE FROM abgleich_meldung WHERE zeitpunkt < ?", (grenze,))
    return cursor.rowcount or 0
