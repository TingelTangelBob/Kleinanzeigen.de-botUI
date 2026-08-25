# SPDX-FileCopyrightText: © Anzeigen-Studio contributors
# SPDX-ArtifactOfProjectHomePage: https://github.com/TingelTangelBob/Kleinanzeigen.de-botUI/
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# Kategorien und Versandpakete zum Auswählen (AP-2.7).
#
# Beide Listen gehoeren dem Upstream: Die Kategorien liegen als
# `resources/categories.yaml` bei, die Paketnamen stehen in seinem Datenmodell.
# Hier wird nichts nachgebaut - eine zweite Liste waere eine Liste, die
# irgendwann abweicht. Gelesen wird einmal je Prozess.
#
# Die Preise kommen von der Plattform selbst. Sie sind das eigentlich
# Wertvolle an der Auswahl: Ohne sie muesste man raten, welches Paket zu den
# Versandkosten einer bestehenden Anzeige passt. Der Abruf ist bewusst
# nachrangig - schlaegt er fehl, gibt es die Liste ohne Preise statt gar keine.

from __future__ import annotations

import json
import logging
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from functools import lru_cache
from importlib.resources import files
from typing import Any

from ruamel.yaml import YAML

LOG = logging.getLogger(__name__)

#: Oeffentliche Preisliste der Plattform. Kein Konto, keine Anmeldung - genau
#: die Adresse, die auch der Bot beim Herunterladen abfragt.
_PREIS_URL = "https://gateway.kleinanzeigen.de/postad/api/v1/shipping-options?posterType=PRIVATE"
_PREIS_FRIST_S = 4.0
_PREIS_HALTBARKEIT_S = 6 * 60 * 60

#: Auch ein Fehlschlag wird gemerkt, nur kuerzer. Sonst zahlt jede einzelne
#: Anfrage die volle Frist oben, solange die Plattform nicht erreichbar ist -
#: und der Versandblock fuehlt sich bei jedem Oeffnen tot an.
_PREIS_FEHLER_HALTBARKEIT_S = 5 * 60

_preise_zwischenspeicher: tuple[float, dict[str, float]] | None = None


@dataclass(frozen = True, slots = True)
class Kategorie:
    name: str
    wert: str


@dataclass(frozen = True, slots = True)
class Versandpaket:
    wert: str
    anbieter: str
    groesse: str
    preis: float | None


@lru_cache(maxsize = 1)
def kategorien() -> list[Kategorie]:
    """Alle Kategorien aus `categories.yaml` des Bots."""
    try:
        from kleinanzeigen_bot import resources  # noqa: PLC0415 - Bot-Import bewusst lokal

        roh = (files(resources) / "categories.yaml").read_text(encoding = "utf-8")
    except Exception as fehler:  # noqa: BLE001 - ohne Kategorien bleibt das Feld ein Textfeld
        LOG.warning("Kategorien nicht lesbar: %s", fehler)
        return []

    daten: dict[str, Any] = YAML(typ = "safe").load(roh) or {}
    return [Kategorie(name = str(name), wert = str(wert)) for name, wert in daten.items()]


def kategorie_name(wert: str | None) -> str | None:
    """Der lesbare Pfad zu einer Kategorienummer, oder None.

    None ist ein normaler Fall, kein Fehler: Heruntergeladene Anzeigen tragen
    mitunter Werte, die `categories.yaml` nicht kennt - beobachtet an
    `161/278/laptop`, waehrend die Liste nur `161/278` fuehrt. Die Oberflaeche
    muss so einen Wert anzeigen koennen, ohne ihn zu ersetzen.
    """
    if not wert:
        return None
    return next((k.name for k in kategorien() if k.wert == wert), None)


def _preise() -> dict[str, float]:
    """Aktuelle Paketpreise der Plattform, je Traegercode in Euro."""
    global _preise_zwischenspeicher  # noqa: PLW0603 - ein Prozess, ein Zwischenspeicher

    jetzt = time.monotonic()
    if _preise_zwischenspeicher:
        gemerkt, alter_stand = _preise_zwischenspeicher
        frist = _PREIS_HALTBARKEIT_S if alter_stand else _PREIS_FEHLER_HALTBARKEIT_S
        if jetzt - gemerkt < frist:
            return alter_stand

    try:
        with urllib.request.urlopen(_PREIS_URL, timeout = _PREIS_FRIST_S) as antwort:  # noqa: S310 - feste https-Adresse
            daten = json.loads(antwort.read().decode("utf-8"))
        optionen = daten["data"]["shippingOptionsResponse"]["options"]
        # Jeder Eintrag wird einzeln geprueft, statt der Antwort ihre Form zu
        # glauben: Ein einzelner missratener Eintrag darf nicht die ganze
        # Preisliste kosten - und erst recht keine Ausnahme werden, die als
        # 500 bis in die Oberflaeche durchschlaegt. Dort kaeme sie als leere
        # Paketliste an, also als das Gegenteil dessen, was der Modulkopf
        # zusichert.
        preise = {
            str(o["id"]): int(o["priceInEuroCent"]) / 100
            for o in optionen
            if isinstance(o, dict) and "id" in o and isinstance(o.get("priceInEuroCent"), int)
        }
    except (urllib.error.URLError, OSError, AttributeError, KeyError, ValueError, TypeError) as fehler:
        LOG.info("Versandpreise nicht abrufbar, Liste bleibt ohne Preise: %s", fehler)
        _preise_zwischenspeicher = (jetzt, {})
        return {}

    _preise_zwischenspeicher = (jetzt, preise)
    return preise


def versandpakete(*, mit_preisen: bool = True) -> list[Versandpaket]:
    """Die vom Bot unterstützten Versandpakete, nach Größe sortiert."""
    try:
        from kleinanzeigen_bot.model.ad_model import (  # noqa: PLC0415 - Bot-Import bewusst lokal
            CARRIER_CODE_BY_OPTION,
            SIZE_INFO_BY_CARRIER_CODE,
        )
    except ImportError as fehler:  # pragma: no cover - im Betrieb liegt der Bot daneben
        LOG.warning("Versandpakete nicht verfügbar: %s", fehler)
        return []

    preise = _preise() if mit_preisen else {}
    reihenfolge = {"Klein": 0, "Mittel": 1, "Groß": 2}

    pakete = [
        Versandpaket(
            wert = name,
            anbieter = name.split("_")[0],
            groesse = SIZE_INFO_BY_CARRIER_CODE.get(code, ("Unbekannt", ""))[0],
            preis = preise.get(code),
        )
        for name, code in CARRIER_CODE_BY_OPTION.items()
    ]
    return sorted(pakete, key = lambda p: (reihenfolge.get(p.groesse, 9), p.preis if p.preis is not None else 999, p.wert))


@lru_cache(maxsize = 1)
def groesse_je_paket() -> dict[str, str]:
    """Paketname aus der Anzeigendatei -> Größengruppe ("Klein", "Mittel", "Groß").

    Zwei Tabellen des Bots hintereinandergeschaltet, keine dritte daneben:
    `CARRIER_CODE_BY_OPTION` uebersetzt den Namen aus der YAML in den
    Traegercode, `SIZE_INFO_BY_CARRIER_CODE` den Code in die Gruppe.
    """
    try:
        from kleinanzeigen_bot.model.ad_model import (  # noqa: PLC0415 - Bot-Import bewusst lokal
            CARRIER_CODE_BY_OPTION,
            SIZE_INFO_BY_CARRIER_CODE,
        )
    except ImportError as fehler:  # pragma: no cover - im Betrieb liegt der Bot daneben
        LOG.warning("Paketgrößen nicht verfügbar: %s", fehler)
        return {}

    return {
        name: SIZE_INFO_BY_CARRIER_CODE[code][0]
        for name, code in CARRIER_CODE_BY_OPTION.items()
        if code in SIZE_INFO_BY_CARRIER_CODE
    }


def gemischte_versandgroessen(pakete: list[Any]) -> bool:
    """Ob eine Paketliste mehr als eine Größengruppe nennt.

    Kleinanzeigen laesst nur Pakete einer Groesse zu. Der Upstream bricht
    deshalb beim Veroeffentlichen ab (`publishing_form.py`: "You can only
    specify shipping options for one package size!") - und zwar erst im
    bereits geoeffneten Versanddialog, mit halb ausgefuelltem Formular. Weder
    `AdPartial` noch `Ad` pruefen die Regel, sie gilt also bis dahin nirgends.

    Unbekannte Namen zaehlen nicht mit: Ueber sie laesst sich nichts sagen,
    und ein falscher Alarm waere schlimmer als ein fehlender.
    """
    tabelle = groesse_je_paket()
    gruppen = {tabelle[str(p)] for p in pakete if str(p) in tabelle}
    return len(gruppen) > 1
