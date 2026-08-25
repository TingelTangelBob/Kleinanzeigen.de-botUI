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
    if _preise_zwischenspeicher and jetzt - _preise_zwischenspeicher[0] < _PREIS_HALTBARKEIT_S:
        return _preise_zwischenspeicher[1]

    try:
        with urllib.request.urlopen(_PREIS_URL, timeout = _PREIS_FRIST_S) as antwort:  # noqa: S310 - feste https-Adresse
            daten = json.loads(antwort.read().decode("utf-8"))
        optionen = daten["data"]["shippingOptionsResponse"]["options"]
        preise = {
            str(o["id"]): int(o["priceInEuroCent"]) / 100
            for o in optionen
            if isinstance(o.get("priceInEuroCent"), int)
        }
    except (urllib.error.URLError, OSError, KeyError, ValueError, TypeError) as fehler:
        LOG.info("Versandpreise nicht abrufbar, Liste bleibt ohne Preise: %s", fehler)
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
