# SPDX-FileCopyrightText: © Anzeigen-Studio contributors
# SPDX-ArtifactOfProjectHomePage: https://github.com/TingelTangelBob/Kleinanzeigen.de-botUI/
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# Kostengrenze und Verbrauchsbuch fuer das KI-Modul (AP-4.7).
#
# Ein Entwurf kostet Bruchteile eines Cents. Genau das ist die Gefahr: Eine
# Schleife, ein hakender Knopf, ein Skript, das den Endpunkt in einer Schleife
# ruft - und die Summe faellt erst der Kreditkartenabrechnung auf. Deshalb
# steht hier eine Grenze, obwohl der Einzelbetrag lachhaft ist.
#
# Die Grenze wird VOR dem Aufruf geprueft, gebucht wird DANACH mit dem
# tatsaechlichen Verbrauch. Etwas anderes ist nicht moeglich: Wie viele Token
# eine Antwort braucht, weiss vorher niemand. Die Grenze kann deshalb um den
# Betrag eines einzelnen Aufrufs ueberschritten werden - das ist die bewusste
# Ungenauigkeit eines Systems, das nicht vorab abrechnen kann.
#
# Gezaehlt wird in Mikro-Dollar als ganze Zahl. Ueber viele kleine Summanden
# driftet Fliesskomma, und die Summe ist hier die Zahl, auf die es ankommt.

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Final

from anzeigen_studio.core.db import transaction
from anzeigen_studio.core.errors import FachlicherFehler

if TYPE_CHECKING:
    import sqlite3

#: Ein Dollar in Mikro-Dollar.
MIKRO_JE_USD: Final[int] = 1_000_000


@dataclass(frozen = True, slots = True)
class Verbrauch:
    """Was in diesem Kalendermonat zusammengekommen ist."""

    monat: str
    mikro_usd: int
    aufrufe: int
    grenze_mikro_usd: int

    @property
    def usd(self) -> float:
        return self.mikro_usd / MIKRO_JE_USD

    @property
    def grenze_usd(self) -> float:
        return self.grenze_mikro_usd / MIKRO_JE_USD

    @property
    def erschoepft(self) -> bool:
        return self.mikro_usd >= self.grenze_mikro_usd

    @property
    def anteil(self) -> float:
        """Wie viel der Grenze verbraucht ist, zwischen 0 und 1."""
        if self.grenze_mikro_usd <= 0:
            return 1.0
        return min(1.0, self.mikro_usd / self.grenze_mikro_usd)


def _monat(zeitpunkt: datetime | None = None) -> str:
    return (zeitpunkt or datetime.now(UTC)).strftime("%Y-%m")


def verbrauch(conn: sqlite3.Connection, *, grenze_usd: float) -> Verbrauch:
    """Liest den Verbrauch des laufenden Kalendermonats.

    Kalendermonat und nicht 30 Tage: Wer eine Grenze setzt, denkt in
    Abrechnungszeitraeumen, und der Anbieter rechnet ebenfalls monatlich ab.
    """
    monat = _monat()
    zeile = conn.execute(
        "SELECT COALESCE(SUM(mikro_usd), 0) AS summe, COUNT(*) AS anzahl "
        "FROM ki_verbrauch WHERE substr(zeitpunkt, 1, 7) = ?",
        (monat,),
    ).fetchone()

    return Verbrauch(
        monat = monat,
        mikro_usd = int(zeile["summe"] or 0),
        aufrufe = int(zeile["anzahl"] or 0),
        grenze_mikro_usd = round(grenze_usd * MIKRO_JE_USD),
    )


def pruefen(conn: sqlite3.Connection, *, grenze_usd: float) -> Verbrauch:
    """Weist ab, wenn die Monatsgrenze schon erreicht ist.

    Bewusst vor dem Anbieteraufruf und mit einer Meldung, die den Stand nennt -
    "Budget erschoepft" ohne Zahlen laesst den Nutzer im Dunkeln, ob er einen
    Cent oder zehn Dollar von der Grenze entfernt ist.
    """
    stand = verbrauch(conn, grenze_usd = grenze_usd)
    if stand.erschoepft:
        raise FachlicherFehler(
            f"Die Monatsgrenze für KI-Entwürfe ist erreicht: "
            f"{stand.usd:.2f} von {stand.grenze_usd:.2f} US-Dollar in {stand.monat}, "
            f"{stand.aufrufe} Entwürfe. "
            f"Die Grenze lässt sich über ANZEIGEN_STUDIO_KI_BUDGET_USD ändern.",
            status = 429,
        )
    return stand


def buchen(
    conn: sqlite3.Connection,
    *,
    profil_slug: str | None,
    modell: str,
    token_eingabe: int,
    token_ausgabe: int,
    mikro_usd: int,
) -> None:
    """Schreibt einen Aufruf ins Verbrauchsbuch.

    Wird auch dann gerufen, wenn die Antwort unbrauchbar war: Bezahlt wurde
    sie trotzdem. Ein Verbrauchsbuch, das nur gelungene Aufrufe kennt, zaehlt
    ausgerechnet die teure Fehlersuche nicht mit.
    """
    with transaction(conn):
        conn.execute(
            "INSERT INTO ki_verbrauch "
            "(zeitpunkt, profil_slug, modell, token_eingabe, token_ausgabe, mikro_usd) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (
                datetime.now(UTC).isoformat(timespec = "seconds"),
                profil_slug, modell, token_eingabe, token_ausgabe, max(0, mikro_usd),
            ),
        )
