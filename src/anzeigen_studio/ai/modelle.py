# SPDX-FileCopyrightText: © Anzeigen-Studio contributors
# SPDX-ArtifactOfProjectHomePage: https://github.com/TingelTangelBob/Kleinanzeigen.de-botUI/
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# Welche KI-Modelle die Oberflaeche anbieten darf, und was sie kosten.
# Neue Datei, Anzeigen-Studio, 2026-09-30.
#
# WARUM EINE FESTE LISTE UND KEIN FREITEXTFELD: Der Modellname geht
# unveraendert in die Anfrage beim Anbieter. Frueher stand er deshalb nur in
# der Serverumgebung (settings.py, AP-4.1). Die Auswahl in der Oberflaeche
# bleibt auf diese Liste beschraenkt: Jedes Modell hier ist gegen die
# Anbieterdokumentation geprueft - bildfaehig, Structured Outputs ueber die
# Responses-Schnittstelle - und hat einen Preis, mit dem das Verbrauchsbuch
# (AP-4.7) rechnen kann. Ein unbekanntes Modell haette keinen.
#
# Neue Modelle kommen hier hinzu, nicht ueber ein Formular.

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Final

from anzeigen_studio.core.db import transaction
from anzeigen_studio.core.errors import FachlicherFehler

if TYPE_CHECKING:
    from anzeigen_studio.core.settings import Settings


@dataclass(frozen = True, slots = True)
class Modell:
    """Ein waehlbares Modell samt Preis je 1 Mio. Token in USD."""

    kennung: str
    name: str
    beschreibung: str
    preis_eingabe_usd: float
    preis_ausgabe_usd: float
    #: `reasoning.effort` fuer die Responses-Schnittstelle, oder None, wenn
    #: das Modell ohne diese Angabe aufgerufen wird. Fuer einen Anzeigentext
    #: aus Fotos reicht wenig Nachdenken; die Vorgabe "medium" des Anbieters
    #: kostet Ausgabe-Token und Wartezeit, ohne den Entwurf besser zu machen.
    denkstufe: str | None = None


#: Quelle der Preise: https://developers.openai.com/api/docs/models/<kennung>,
#: abgerufen am 2026-09-30. Nur eine Schaetzung fuer das Verbrauchsbuch -
#: abgerechnet wird beim Anbieter.
MODELLE: Final[tuple[Modell, ...]] = (
    Modell(
        kennung = "gpt-6-luna",
        name = "GPT-6 Luna",
        beschreibung = "Neueste Generation, günstigster Preis je Entwurf.",
        preis_eingabe_usd = 0.10,
        preis_ausgabe_usd = 0.50,
        denkstufe = "low",
    ),
    Modell(
        kennung = "gpt-5.6-luna",
        name = "GPT-5.6 Luna",
        beschreibung = "Bisheriges Modell, seit August 2026 im Einsatz.",
        preis_eingabe_usd = 0.20,
        preis_ausgabe_usd = 1.20,
    ),
)

STANDARD: Final[str] = MODELLE[0].kennung

#: Unter diesem Namen liegt die Auswahl in `einstellung`.
_EINSTELLUNG: Final[str] = "ki_modell"


def nach_kennung(kennung: str) -> Modell | None:
    return next((m for m in MODELLE if m.kennung == kennung), None)


def fuer_unbekannt(kennung: str) -> Modell:
    """Ein Modell, das nur ueber die Serverumgebung gesetzt wurde.

    Es wird aufgerufen, wie der Betreiber es verlangt. Fuer das Verbrauchsbuch
    gilt der hoechste bekannte Preis: Eine zu hohe Schaetzung stoppt eine
    Schleife frueher, eine zu niedrige gar nicht.
    """
    return Modell(
        kennung = kennung,
        name = kennung,
        beschreibung = "Über die Serverumgebung festgelegt.",
        preis_eingabe_usd = max(m.preis_eingabe_usd for m in MODELLE),
        preis_ausgabe_usd = max(m.preis_ausgabe_usd for m in MODELLE),
    )


def _gespeichert(conn: sqlite3.Connection) -> str | None:
    try:
        zeile = conn.execute(
            "SELECT wert FROM einstellung WHERE schluessel = ?", (_EINSTELLUNG,),
        ).fetchone()
    except sqlite3.OperationalError:
        # Vor Migration 17 gibt es die Tabelle nicht. Dann gilt die Vorgabe.
        return None
    return None if zeile is None else str(zeile[0])


def aktiv(conn: sqlite3.Connection, cfg: Settings) -> Modell:
    """Das Modell, mit dem der naechste Entwurf erzeugt wird.

    Gehostet entscheidet der Betreiber ueber die Umgebung. Sonst gilt die
    Auswahl aus der Oberflaeche, solange sie noch im Katalog steht - ein
    gestrichenes Modell faellt still auf die Servervorgabe zurueck, statt
    jeden Entwurf mit "Modell unbekannt" scheitern zu lassen.
    """
    if not cfg.hosted:
        gewaehlt = _gespeichert(conn)
        if gewaehlt is not None and (m := nach_kennung(gewaehlt)) is not None:
            return m
    return nach_kennung(cfg.ki_modell) or fuer_unbekannt(cfg.ki_modell)


def waehlen(conn: sqlite3.Connection, cfg: Settings, kennung: str) -> Modell:
    """Speichert die Auswahl aus der Oberflaeche."""
    if cfg.hosted:
        raise FachlicherFehler(
            "Das KI-Modell wird bei dieser gehosteten Installation vom Betreiber festgelegt.",
            status = 403,
        )
    modell = nach_kennung(kennung)
    if modell is None:
        raise FachlicherFehler(
            "Dieses Modell steht nicht zur Auswahl.", status = 422, feld = "modell",
        )
    with transaction(conn):
        conn.execute(
            "INSERT INTO einstellung (schluessel, wert, geaendert_am) VALUES (?, ?, ?) "
            "ON CONFLICT(schluessel) DO UPDATE SET wert = excluded.wert, "
            "geaendert_am = excluded.geaendert_am",
            (_EINSTELLUNG, modell.kennung, datetime.now(UTC).isoformat(timespec = "seconds")),
        )
    return modell
