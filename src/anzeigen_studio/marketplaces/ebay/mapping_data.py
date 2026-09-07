# SPDX-FileCopyrightText: © Anzeigen-Studio contributors
# SPDX-ArtifactOfProjectHomePage: https://github.com/TingelTangelBob/Kleinanzeigen.de-botUI/
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# Kleine, geprüfte Mapping-Whitelist (AP-E-05).
#
# Keine vollständige Taxonomie, keine KI-Raterei. Unbekannte Schlüssel
# blockieren – sie werden nicht geraten. eBay-categoryId-Werte sind
# MVP-/Sandbox-Whitelist-Einträge und ersetzen keinen Live-Taxonomie-Abruf.

from __future__ import annotations

from dataclasses import dataclass
from typing import Final


@dataclass(frozen = True, slots = True)
class EbayKategorieMapping:
    """Ein erlaubter Kategorie-Eintrag inkl. Pflicht-Aspekte."""

    schluessel: str
    ebay_category_id: str
    bezeichnung: str
    pflicht_aspekte: tuple[str, ...]


#: Bewusst kleine Menge. Schlüssel sind Studio-/Absicht-Keys, optional
#: auch exakte KA-category-Strings, die manuell freigegeben wurden.
#: KA-IDs werden nie stillschweigend als eBay-IDs übernommen.
KATEGORIE_WHITELIST: Final[dict[str, EbayKategorieMapping]] = {
    "elektronik.handy": EbayKategorieMapping(
        schluessel = "elektronik.handy",
        ebay_category_id = "9355",
        bezeichnung = "Handys & Smartphones (MVP-Whitelist)",
        pflicht_aspekte = ("Marke", "Modell"),
    ),
    "elektronik.tablet": EbayKategorieMapping(
        schluessel = "elektronik.tablet",
        ebay_category_id = "171485",
        bezeichnung = "Tablets & eBook-Reader (MVP-Whitelist)",
        pflicht_aspekte = ("Marke", "Modell"),
    ),
    "haus_garten.moebel": EbayKategorieMapping(
        schluessel = "haus_garten.moebel",
        ebay_category_id = "3197",
        bezeichnung = "Möbel (MVP-Whitelist)",
        pflicht_aspekte = ("Marke",),
    ),
}

#: Alias: exakte KA-category-Pfade, die bewusst auf denselben Whitelist-Eintrag
#: zeigen. Nur Einträge hier – alles andere ist „unbekannte Kategorie“.
KA_KATEGORIE_ALIAS: Final[dict[str, str]] = {
    "Elektronik.Handy & Telefon.Handys & Smartphones": "elektronik.handy",
    "Elektronik.Computer.Tablets & Reader": "elektronik.tablet",
    "Haus & Garten.Möbel & Wohnen.Möbel": "haus_garten.moebel",
}

#: Kleinanzeigen condition_s / Studio-Zustand → eBay Condition-Enum (Sell Inventory).
#: Unbekannte Werte blockieren.
ZUSTAND_WHITELIST: Final[dict[str, str]] = {
    # Studio-Schlüssel
    "neu": "NEW",
    "wie_neu": "LIKE_NEW",
    "gut": "USED_EXCELLENT",
    "in_ordnung": "USED_GOOD",
    "defekt": "FOR_PARTS_OR_NOT_WORKING",
    # KA API-Werte (special_attributes.condition_s)
    "new": "NEW",
    "like_new": "LIKE_NEW",
    "ok": "USED_EXCELLENT",
    "alright": "USED_GOOD",
    "defect": "FOR_PARTS_OR_NOT_WORKING",
    # Bereits eBay-Enums (Absicht darf direkt liefern)
    "NEW": "NEW",
    "LIKE_NEW": "LIKE_NEW",
    "USED_EXCELLENT": "USED_EXCELLENT",
    "USED_GOOD": "USED_GOOD",
    "USED_ACCEPTABLE": "USED_ACCEPTABLE",
    "FOR_PARTS_OR_NOT_WORKING": "FOR_PARTS_OR_NOT_WORKING",
}

#: Preistypen, die als Festpreis gelten dürfen.
FESTPREIS_TYPEN: Final[frozenset[str]] = frozenset({"FIXED"})

#: Preistypen, die ausdrücklich blockieren (kein Auction-Fallback).
BLOCKIERTE_PREISTYPEN: Final[frozenset[str]] = frozenset({
    "NEGOTIABLE",
    "GIVE_AWAY",
    "NOT_APPLICABLE",
})
