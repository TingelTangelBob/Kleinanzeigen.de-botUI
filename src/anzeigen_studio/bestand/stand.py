# SPDX-FileCopyrightText: © Anzeigen-Studio contributors
# SPDX-ArtifactOfProjectHomePage: https://github.com/TingelTangelBob/Kleinanzeigen.de-botUI/
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# Was zuletzt auf der Plattform stand - und was sich seither geaendert hat (AP-3.5).
#
# Der Hochladen-Dialog musste bisher zugeben, dass er den Unterschied nicht
# kennt: "Was gerade auf der Plattform steht, weiss hier niemand." Das war
# ehrlich, aber unbefriedigend - wer eine Anzeige aendert, will vor dem
# Absenden sehen, WAS er aendert.
#
# Die Fassung, die zuletzt mit der Plattform uebereinstimmte, ist bekannt: Es
# ist die Datei genau in dem Moment, in dem der Bot sie geschrieben hat. Das
# tut er in beiden Richtungen - beim Herunterladen (er uebernimmt den Stand der
# Plattform) und nach dem Hochladen (`publishing_persistence.persist_published_ad`
# schreibt Kennung, Pruefsumme und Zeitstempel zurueck). Beide Male gilt danach:
# Datei == Plattform.
#
# Diese Schicht haelt genau diesen Moment fest und vergleicht ihn spaeter mit
# dem, was jetzt in der Datei steht.
#
# WICHTIG, warum der Schnappschuss in der Datenbank liegt und nicht als Datei
# daneben: Der Bot sucht seine Anzeigen mit `ad_*.{yaml,yml,json}`. Eine
# Begleitdatei `ad_123.stand.json` neben der Anzeige waere von diesem Muster
# erfasst worden - der Bot haette versucht, den Schnappschuss als Anzeige zu
# laden. Ein Index gehoert ohnehin in die Datenbank (siehe CONTEXT.md: die
# Platte ist die Wahrheit, die Datenbank nur Index). Geht der Schnappschuss
# verloren, fehlt der Vergleich - mehr nicht.

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import UTC
from typing import TYPE_CHECKING, Any, Final

from anzeigen_studio.bestand.bearbeiten import AENDERBAR

if TYPE_CHECKING:
    import sqlite3
    from pathlib import Path

LOG = logging.getLogger(__name__)

#: Welche Felder verglichen werden, und wie sie in der Oberflaeche heissen.
#:
#: Genau die Felder aus `AENDERBAR` - was sich hier nicht aendern laesst, kann
#: auch nicht Gegenstand eines Vergleichs sein. Die Reihenfolge ist die des
#: Editors, damit der Vergleich sich liest wie das Formular.
BESCHRIFTUNGEN: Final[dict[str, str]] = {
    "title": "Titel",
    "description": "Beschreibung",
    "category": "Kategorie",
    "price": "Preis",
    "price_type": "Preistyp",
    "shipping_type": "Versandart",
    "shipping_options": "Versandpakete",
    "shipping_costs": "Versandkosten",
    "sell_directly": "Direkt kaufen",
    "images": "Bilder",
    "special_attributes": "Weitere Angaben",
    "contact": "Kontakt",
    "type": "Gebot / Gesuch",
    "active": "Aktiv",
    "republication_interval": "Abstand zur Neueinstellung",
}

#: Ab dieser Laenge wird ein Textfeld nicht mehr ausgeschrieben, sondern nur
#: als geaendert gemeldet. Eine Beschreibung darf 4000 Zeichen haben; die in
#: einen Dialog zu schuetten hilft niemandem.
_TEXT_GRENZE: Final[int] = 60

# Gegenprobe beim Import: Faellt ein Feld aus AENDERBAR heraus oder kommt eines
# hinzu, soll das hier auffallen und nicht als stiller Luecke im Vergleich
# enden. Bewusst eine Zusicherung und keine Ausnahme - ein fehlendes Label
# darf das Backend nicht am Starten hindern.
FEHLENDE_BESCHRIFTUNGEN: Final[frozenset[str]] = frozenset(AENDERBAR) - frozenset(BESCHRIFTUNGEN)


@dataclass(frozen = True, slots = True)
class Unterschied:
    """Ein Feld, das sich seit dem letzten Abgleich geaendert hat."""

    feld: str
    beschriftung: str
    vorher: str
    jetzt: str


def schnappschuss(daten: dict[str, Any]) -> dict[str, Any]:
    """Reduziert eine Anzeige auf das, was verglichen wird.

    Alles andere - Kennung, Pruefsumme, Zeitstempel, Zaehler - gehoert dem Bot
    und aendert sich bei jedem Lauf. Es mitzunehmen hiesse, bei jedem Vergleich
    Unterschiede zu melden, die niemanden interessieren.
    """
    return {feld: daten.get(feld) for feld in BESCHRIFTUNGEN if feld in daten}


def merken(
    conn: sqlite3.Connection,
    profil_id: int,
    datei: str,
    daten: dict[str, Any],
    *,
    quelle: str,
    zeitpunkt: str,
) -> None:
    """Haelt fest, dass die Datei in dieser Fassung mit der Plattform uebereinstimmte."""
    conn.execute(
        "INSERT INTO anzeige_stand (profil_id, datei, stand, quelle, zeitpunkt) "
        "VALUES (?, ?, ?, ?, ?) "
        "ON CONFLICT(profil_id, datei) DO UPDATE SET "
        "stand = excluded.stand, quelle = excluded.quelle, zeitpunkt = excluded.zeitpunkt",
        (profil_id, datei, json.dumps(schnappschuss(daten), sort_keys = True), quelle, zeitpunkt),
    )


def gemerkt(conn: sqlite3.Connection, profil_id: int, datei: str) -> tuple[dict[str, Any], str, str] | None:
    """Liest den letzten Abgleich. None heisst: Es gab noch keinen."""
    row = conn.execute(
        "SELECT stand, quelle, zeitpunkt FROM anzeige_stand WHERE profil_id = ? AND datei = ?",
        (profil_id, datei),
    ).fetchone()
    if row is None:
        return None
    try:
        stand = json.loads(row["stand"])
    except (ValueError, TypeError):
        # Unlesbarer Schnappschuss ist wie keiner. Der Dialog sagt dann, dass
        # er nichts vergleichen kann - das ist besser als ein Fehler an einer
        # Stelle, die nur zusaetzliche Auskunft geben soll.
        return None
    if not isinstance(stand, dict):
        return None
    return stand, row["quelle"], row["zeitpunkt"]


def vergessen(conn: sqlite3.Connection, profil_id: int, datei: str) -> None:
    """Entfernt den Schnappschuss - fuer geloeschte oder umbenannte Anzeigen."""
    conn.execute("DELETE FROM anzeige_stand WHERE profil_id = ? AND datei = ?", (profil_id, datei))


def _liste_als_text(feld: str, wert: list[Any]) -> str:
    """Listen kurz fassen. Eigene Funktion, damit `_als_text` lesbar bleibt."""
    if not wert:
        return "keine"
    if feld == "images":
        return "1 Bild" if len(wert) == 1 else f"{len(wert)} Bilder"
    text = ", ".join(str(eintrag) for eintrag in wert)
    return text if len(text) <= _TEXT_GRENZE else f"{len(wert)} Einträge"


def _als_text(feld: str, wert: Any) -> str:
    """Macht einen Feldwert lesbar. Bewusst kurz - der Dialog ist kein Editor."""
    if wert is None or wert == "":
        return "leer"
    if isinstance(wert, bool):
        return "ja" if wert else "nein"
    if isinstance(wert, list):
        return _liste_als_text(feld, wert)
    if isinstance(wert, dict):
        if not wert:
            return "leer"
        return "1 Angabe" if len(wert) == 1 else f"{len(wert)} Angaben"
    if isinstance(wert, int | float) and feld == "price":
        return f"{wert:.2f} €".replace(".", ",")
    text = str(wert)
    # Lange Texte nicht ausschreiben, aber die Laenge nennen: Sie ist der
    # einzige Hinweis, ob viel oder wenig passiert ist.
    return f"{len(text)} Zeichen" if len(text) > _TEXT_GRENZE else text


def vergleichen(vorher: dict[str, Any] | None, jetzt: dict[str, Any]) -> list[Unterschied]:
    """Was hat sich seit dem letzten Abgleich geaendert?

    Ohne Schnappschuss gibt es nichts zu vergleichen - dann eine leere Liste
    und keine erfundenen Unterschiede. Der Aufrufer muss diesen Fall von "es
    hat sich nichts geaendert" unterscheiden koennen; dafuer steht neben der
    Liste, ob ueberhaupt ein Stand bekannt ist.
    """
    if vorher is None:
        return []

    jetzt_kurz = schnappschuss(jetzt)
    unterschiede: list[Unterschied] = []
    for feld, beschriftung in BESCHRIFTUNGEN.items():
        alt = vorher.get(feld)
        neu = jetzt_kurz.get(feld)
        if alt == neu:
            continue
        # Leer und nicht vorhanden sind dasselbe - sonst meldet jede Datei,
        # die ein Feld gar nicht kennt, einen Unterschied gegen `None`.
        if _leer(alt) and _leer(neu):
            continue
        unterschiede.append(Unterschied(
            feld = feld,
            beschriftung = beschriftung,
            vorher = _als_text(feld, alt),
            jetzt = _als_text(feld, neu),
        ))
    return unterschiede


def _leer(wert: Any) -> bool:
    # Kein `set`: Die Vergleichswerte sind Liste und Wörterbuch und damit
    # nicht hashbar.
    return wert is None or wert in ("", [], {})


def abgleich_nach_lauf(
    conn: sqlite3.Connection,
    profil_id: int,
    profil_wurzel: Path,
    *,
    seit: str,
    quelle: str,
) -> int:
    """Merkt sich jede Anzeigendatei, die der Lauf geschrieben hat.

    `seit` ist der Start des Laufs (ISO-8601, UTC). Verglichen wird ueber die
    Aenderungszeit der Datei: Hat der Bot sie waehrend des Laufs geschrieben,
    steht darin jetzt der Stand der Plattform - beim Herunterladen, weil er
    ihn uebernommen hat, nach dem Hochladen, weil er ihn hingeschrieben hat.

    Bewusst ueber die Aenderungszeit und nicht ueber die Argumente des Laufs:
    Welche Anzeigen ein Lauf tatsaechlich angefasst hat, steht nur in seiner
    Ausgabe, und die zu deuten hiesse raten. Die Datei weiss es genau.

    Wer waehrend eines Laufs von Hand an derselben Datei arbeitet, bekommt
    seine Aenderung als "auf der Plattform" gemerkt. Das ist der bekannte
    Preis dieser Vereinfachung; die Oberflaeche laesst waehrend eines Laufs
    ohnehin keinen zweiten Lauf auf dasselbe Profil zu.

    Gibt zurueck, wie viele Dateien gemerkt wurden. Fehler beim Lesen einzelner
    Dateien werden uebergangen - ein Vergleich ist Zusatzauskunft und darf
    einen erfolgreichen Lauf nicht nachtraeglich zum Fehlschlag machen.
    """
    from datetime import datetime  # noqa: PLC0415 - nur hier gebraucht

    from ruamel.yaml import YAML  # noqa: PLC0415 - nur hier gebraucht

    from anzeigen_studio.bestand import lesen  # noqa: PLC0415 - sonst Ringschluss

    try:
        grenze = datetime.fromisoformat(seit).timestamp()
    except ValueError:
        return 0

    yaml = YAML(typ = "safe")
    gemerkte = 0
    for pfad in lesen.anzeigendateien(profil_wurzel):
        try:
            if pfad.stat().st_mtime < grenze:
                continue
            daten = yaml.load(pfad.read_text(encoding = "utf-8"))
        except Exception:  # noqa: BLE001 - siehe Beschreibung oben
            LOG.debug("Schnappschuss uebersprungen: %s", pfad, exc_info = True)
            continue
        if not isinstance(daten, dict):
            continue
        merken(
            conn, profil_id, pfad.relative_to(profil_wurzel).as_posix(), daten,
            quelle = quelle,
            zeitpunkt = datetime.fromtimestamp(pfad.stat().st_mtime, tz = UTC).isoformat(timespec = "seconds"),
        )
        gemerkte += 1
    return gemerkte
