# SPDX-FileCopyrightText: © Anzeigen-Studio contributors
# SPDX-ArtifactOfProjectHomePage: https://github.com/TingelTangelBob/Kleinanzeigen.de-botUI/
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# Abbildung Anzeige → eBay Festpreis-Payload (AP-E-05).
#
# Nur lesen am Anzeigenmodell. Kleine Whitelist, keine Taxonomie/KI.
# KA-Versandpakete sind keine eBay-Policies. Geldwerte als Decimal.

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any, Final, Mapping

from anzeigen_studio.marketplaces.ebay.mapping_data import (
    BLOCKIERTE_PREISTYPEN,
    FESTPREIS_TYPEN,
    KA_KATEGORIE_ALIAS,
    KATEGORIE_WHITELIST,
    ZUSTAND_WHITELIST,
    EbayKategorieMapping,
)
from anzeigen_studio.marketplaces.ebay.models import (
    MARKETPLACE_ID_DE,
    WAEHRUNG_EUR,
    EbayDryRunEingabe,
    EbayFeldfehler,
)

_CENT: Final = Decimal("0.01")


@dataclass(frozen = True, slots = True)
class EbayMappingAnzeige:
    """Readonly-Ausschnitt einer Anzeige für das Mapping (kein YAML-Schreiben)."""

    titel: str
    beschreibung: str
    kategorie: str | None = None
    preis: Decimal | int | float | str | None = None
    preistyp: str | None = None
    versandart: str | None = None
    versandpakete: tuple[str, ...] = ()
    condition_s: str | None = None
    special_attributes: Mapping[str, str] = field(default_factory = dict)
    bild_urls: tuple[str, ...] = ()

    @classmethod
    def aus_dict(cls, daten: Mapping[str, Any]) -> EbayMappingAnzeige:
        """Liest typische YAML-/Bestandsfelder, ohne sie zu verändern."""
        attrs = daten.get("special_attributes") or {}
        if not isinstance(attrs, Mapping):
            attrs = {}
        condition = attrs.get("condition_s") if isinstance(attrs.get("condition_s"), str) else None
        if condition is None and isinstance(daten.get("condition_s"), str):
            condition = daten["condition_s"]
        if condition is None and isinstance(daten.get("zustand"), str):
            condition = daten["zustand"]

        pakete_roh = daten.get("shipping_options") or daten.get("versandpakete") or ()
        if isinstance(pakete_roh, list | tuple):
            pakete = tuple(str(p) for p in pakete_roh)
        else:
            pakete = ()

        bilder_roh = daten.get("images") or daten.get("bild_urls") or ()
        bild_urls: list[str] = []
        if isinstance(bilder_roh, list | tuple):
            for eintrag in bilder_roh:
                if isinstance(eintrag, str):
                    bild_urls.append(eintrag)
                elif isinstance(eintrag, Mapping):
                    url = eintrag.get("url") or eintrag.get("path")
                    if isinstance(url, str):
                        bild_urls.append(url)

        preis = daten.get("price", daten.get("preis"))
        preistyp = daten.get("price_type", daten.get("preistyp"))
        return cls(
            titel = str(daten.get("title") or daten.get("titel") or ""),
            beschreibung = str(daten.get("description") or daten.get("beschreibung") or ""),
            kategorie = _opt_str(daten.get("category", daten.get("kategorie"))),
            preis = preis,  # type: ignore[arg-type]
            preistyp = _opt_str(preistyp),
            versandart = _opt_str(daten.get("shipping_type", daten.get("versandart"))),
            versandpakete = pakete,
            condition_s = condition,
            special_attributes = {str(k): str(v) for k, v in attrs.items()},
            bild_urls = tuple(bild_urls),
        )


@dataclass(frozen = True, slots = True)
class EbayMappingAbsicht:
    """Ausdrückliche eBay-Nutzerabsicht (platforms.ebay) – Policies nicht raten."""

    sku: str
    kategorie_schluessel: str | None = None
    ebay_kategorie_id: str | None = None
    zustand: str | None = None
    artikelmerkmale: Mapping[str, str] = field(default_factory = dict)
    ebay_preis: Decimal | str | None = None
    merchant_location_key: str = ""
    fulfillment_policy_id: str = ""
    payment_policy_id: str = ""
    return_policy_id: str = ""
    bild_urls: tuple[str, ...] = ()


@dataclass(frozen = True, slots = True)
class EbayMappingErgebnis:
    """Reproduzierbare Payloads oder präzise Feldfehler."""

    ok: bool
    feldfehler: tuple[EbayFeldfehler, ...]
    inventory_payload: dict[str, object] | None = None
    offer_payload: dict[str, object] | None = None
    dry_run_eingabe: EbayDryRunEingabe | None = None
    hinweise: tuple[str, ...] = ()


def _opt_str(wert: object) -> str | None:
    if wert is None:
        return None
    text = str(wert).strip()
    return text or None


def _preis_als_decimal(roh: object) -> Decimal | None:
    if roh is None:
        return None
    try:
        if isinstance(roh, Decimal):
            wert = roh
        elif isinstance(roh, bool):
            return None
        elif isinstance(roh, int):
            wert = Decimal(roh)
        elif isinstance(roh, float):
            # float nur über str, um Binärballast zu vermeiden soweit möglich
            wert = Decimal(str(roh))
        else:
            text = str(roh).strip().replace(",", ".").replace("€", "").strip()
            if not text:
                return None
            wert = Decimal(text)
    except (InvalidOperation, ValueError, AttributeError):
        return None
    if wert.is_nan() or wert.is_infinite():
        return None
    return wert


def _preis_formatieren(wert: Decimal) -> str:
    """Immer zwei Nachkommastellen, Decimal-sicher (keine float-Rechnung)."""
    return str(wert.quantize(_CENT, rounding = ROUND_HALF_UP))


def _kategorie_aufloesen(
    anzeige: EbayMappingAnzeige,
    absicht: EbayMappingAbsicht,
) -> tuple[EbayKategorieMapping | None, EbayFeldfehler | None]:
    schluessel = _opt_str(absicht.kategorie_schluessel)
    if schluessel and schluessel in KATEGORIE_WHITELIST:
        return KATEGORIE_WHITELIST[schluessel], None

    ebay_id = _opt_str(absicht.ebay_kategorie_id)
    if ebay_id:
        for eintrag in KATEGORIE_WHITELIST.values():
            if eintrag.ebay_category_id == ebay_id:
                return eintrag, None
        return None, EbayFeldfehler(
            "kategorie_id",
            f"eBay-Kategorie „{ebay_id}“ ist nicht in der MVP-Whitelist.",
        )

    ka = _opt_str(anzeige.kategorie)
    if ka:
        alias = KA_KATEGORIE_ALIAS.get(ka)
        if alias and alias in KATEGORIE_WHITELIST:
            return KATEGORIE_WHITELIST[alias], None
        if ka in KATEGORIE_WHITELIST:
            return KATEGORIE_WHITELIST[ka], None
        return None, EbayFeldfehler(
            "kategorie",
            "Unbekannte Kategorie – Kleinanzeigen-Kategorie wird nicht als "
            "eBay-ID übernommen; Whitelist-Eintrag oder ausdrücklicher "
            "eBay-Kategorie-Schlüssel fehlt.",
        )

    return None, EbayFeldfehler(
        "kategorie",
        "eBay-Kategorie fehlt (kein Whitelist-Schlüssel, keine freigegebene "
        "KA-Zuordnung, keine ebay_kategorie_id).",
    )


def _zustand_aufloesen(
    anzeige: EbayMappingAnzeige,
    absicht: EbayMappingAbsicht,
) -> tuple[str | None, EbayFeldfehler | None]:
    kandidaten = [
        _opt_str(absicht.zustand),
        _opt_str(anzeige.condition_s),
        _opt_str(anzeige.special_attributes.get("condition_s")),
    ]
    roh = next((k for k in kandidaten if k), None)
    if roh is None:
        return None, EbayFeldfehler("zustand", "Zustand fehlt.")
    gemappt = ZUSTAND_WHITELIST.get(roh)
    if gemappt is None:
        return None, EbayFeldfehler(
            "zustand",
            f"Unbekannter Zustand „{roh}“ – nicht in der MVP-Whitelist.",
        )
    return gemappt, None


def _preis_aufloesen(
    anzeige: EbayMappingAnzeige,
    absicht: EbayMappingAbsicht,
) -> tuple[Decimal | None, EbayFeldfehler | None]:
    if absicht.ebay_preis is not None and str(absicht.ebay_preis).strip() != "":
        preis = _preis_als_decimal(absicht.ebay_preis)
        if preis is None:
            return None, EbayFeldfehler("preis", "Festpreis ist ungültig.")
        if preis <= 0:
            return None, EbayFeldfehler("preis", "Festpreis muss größer als 0 sein.")
        return preis, None

    preistyp = _opt_str(anzeige.preistyp)
    if preistyp is not None:
        typ = preistyp.upper()
        if typ in BLOCKIERTE_PREISTYPEN:
            return None, EbayFeldfehler(
                "price_type",
                f"Preistyp „{typ}“ ist kein Festpreis – Auktionen/VB/zu verschenken "
                "sind im MVP nicht erlaubt.",
            )
        if typ not in FESTPREIS_TYPEN:
            return None, EbayFeldfehler(
                "price_type",
                f"Unbekannter Preistyp „{typ}“ – nur FIXED (Festpreis) ist erlaubt.",
            )

    if anzeige.preis is None:
        return None, EbayFeldfehler(
            "preis",
            "Festpreis fehlt (weder eBay-Preis noch Anzeigenpreis).",
        )

    # Ohne Preistyp: nur akzeptieren wenn numerisch gültig und > 0, aber
    # explizit FIXED verlangen wenn price_type gesetzt war – oben erledigt.
    # Fehlt price_type komplett → blockieren (kein stilles FIXED annehmen),
    # außer ebay_preis war gesetzt (oben).
    if preistyp is None:
        return None, EbayFeldfehler(
            "price_type",
            "Preistyp fehlt – für eBay ist Festpreis (FIXED) erforderlich.",
        )

    preis = _preis_als_decimal(anzeige.preis)
    if preis is None:
        return None, EbayFeldfehler("preis", "Festpreis ist ungültig.")
    if preis <= 0:
        return None, EbayFeldfehler("preis", "Festpreis muss größer als 0 sein.")
    return preis, None


def _merkmale_pruefen(
    kategorie: EbayKategorieMapping,
    merkmale: Mapping[str, str],
) -> list[EbayFeldfehler]:
    fehler: list[EbayFeldfehler] = []
    for aspekt in kategorie.pflicht_aspekte:
        wert = merkmale.get(aspekt)
        if wert is None or not str(wert).strip():
            fehler.append(EbayFeldfehler(
                f"artikelmerkmale.{aspekt}",
                f"Pflichtmerkmal „{aspekt}“ fehlt für Kategorie "
                f"„{kategorie.schluessel}“.",
            ))
    return fehler


def _aspekte_payload(merkmale: Mapping[str, str]) -> dict[str, list[str]]:
    """Stabile Sortierung der Aspekt-Namen für reproduzierbare Payloads."""
    ergebnis: dict[str, list[str]] = {}
    for name in sorted(merkmale.keys()):
        wert = str(merkmale[name]).strip()
        if wert:
            ergebnis[name] = [wert]
    return ergebnis


def anzeige_nach_ebay_payload(
    anzeige: EbayMappingAnzeige | Mapping[str, Any],
    absicht: EbayMappingAbsicht,
) -> EbayMappingErgebnis:
    """Bildet Festpreis-EUR-Menge-1-Payloads oder liefert präzise Feldfehler.

    KA-``shipping_options`` werden bewusst **nicht** zu Fulfillment-Policy-IDs.
    Policies kommen nur aus der ausdrücklichen Absicht (AP-E-06).
    """
    if not isinstance(anzeige, EbayMappingAnzeige):
        anzeige = EbayMappingAnzeige.aus_dict(anzeige)

    fehler: list[EbayFeldfehler] = []
    hinweise: list[str] = []

    if anzeige.versandpakete:
        hinweise.append(
            "Kleinanzeigen-Versandpakete werden nicht als eBay-Business-Policies "
            "übernommen; Fulfillment-/Payment-/Return-Policy-IDs müssen ausdrücklich "
            "gewählt werden (AP-E-06)."
        )

    if not absicht.sku or not absicht.sku.strip():
        fehler.append(EbayFeldfehler("sku", "SKU fehlt."))

    titel = anzeige.titel.strip()
    if not titel:
        fehler.append(EbayFeldfehler("titel", "Titel fehlt."))

    beschreibung = anzeige.beschreibung.strip()
    if not beschreibung:
        fehler.append(EbayFeldfehler("beschreibung", "Beschreibung fehlt."))

    kategorie, kat_fehler = _kategorie_aufloesen(anzeige, absicht)
    if kat_fehler:
        fehler.append(kat_fehler)

    zustand_id, zustand_fehler = _zustand_aufloesen(anzeige, absicht)
    if zustand_fehler:
        fehler.append(zustand_fehler)

    preis, preis_fehler = _preis_aufloesen(anzeige, absicht)
    if preis_fehler:
        fehler.append(preis_fehler)

    merkmale = {str(k): str(v) for k, v in absicht.artikelmerkmale.items()}
    if kategorie is not None:
        fehler.extend(_merkmale_pruefen(kategorie, merkmale))

    if not (absicht.merchant_location_key or "").strip():
        fehler.append(EbayFeldfehler(
            "merchant_location_key",
            "Inventarstandort (merchantLocationKey) fehlt.",
        ))
    if not (absicht.fulfillment_policy_id or "").strip():
        fehler.append(EbayFeldfehler(
            "fulfillment_policy_id",
            "Versandregel (Fulfillment Policy) fehlt – KA-Versandpakete zählen nicht.",
        ))
    if not (absicht.payment_policy_id or "").strip():
        fehler.append(EbayFeldfehler(
            "payment_policy_id",
            "Zahlungsregel (Payment Policy) fehlt.",
        ))
    if not (absicht.return_policy_id or "").strip():
        fehler.append(EbayFeldfehler(
            "return_policy_id",
            "Rückgaberegel (Return Policy) fehlt.",
        ))

    bild_urls = absicht.bild_urls or anzeige.bild_urls
    if not bild_urls:
        fehler.append(EbayFeldfehler(
            "bild_urls",
            "Mindestens eine Bild-URL ist erforderlich.",
        ))

    if fehler:
        return EbayMappingErgebnis(
            ok = False,
            feldfehler = tuple(fehler),
            hinweise = tuple(hinweise),
        )

    assert kategorie is not None
    assert zustand_id is not None
    assert preis is not None

    preis_str = _preis_formatieren(preis)
    aspekten = _aspekte_payload(merkmale)
    artikelmerkmale_tuple = tuple(
        (name, aspekten[name][0]) for name in sorted(aspekten.keys())
    )

    inventory_payload: dict[str, object] = {
        "availability": {
            "shipToLocationAvailability": {
                "quantity": 1,
            },
        },
        "condition": zustand_id,
        "product": {
            "title": titel,
            "description": beschreibung,
            "aspects": aspekten,
            "imageUrls": list(bild_urls),
        },
    }

    offer_payload: dict[str, object] = {
        "sku": absicht.sku.strip(),
        "marketplaceId": MARKETPLACE_ID_DE,
        "format": "FIXED_PRICE",
        "listingDescription": beschreibung,
        "availableQuantity": 1,
        "categoryId": kategorie.ebay_category_id,
        "listingPolicies": {
            "fulfillmentPolicyId": absicht.fulfillment_policy_id.strip(),
            "paymentPolicyId": absicht.payment_policy_id.strip(),
            "returnPolicyId": absicht.return_policy_id.strip(),
        },
        "pricingSummary": {
            "price": {
                "currency": WAEHRUNG_EUR,
                "value": preis_str,
            },
        },
        "merchantLocationKey": absicht.merchant_location_key.strip(),
    }

    dry_run = EbayDryRunEingabe(
        sku = absicht.sku.strip(),
        titel = titel,
        beschreibung = beschreibung,
        kategorie_id = kategorie.ebay_category_id,
        zustand_id = zustand_id,
        preis = preis_str,
        merchant_location_key = absicht.merchant_location_key.strip(),
        bild_urls = tuple(bild_urls),
        fulfillment_policy_id = absicht.fulfillment_policy_id.strip(),
        payment_policy_id = absicht.payment_policy_id.strip(),
        return_policy_id = absicht.return_policy_id.strip(),
        waehrung = WAEHRUNG_EUR,
        menge = 1,
        marketplace_id = MARKETPLACE_ID_DE,
        artikelmerkmale = artikelmerkmale_tuple,
    )

    return EbayMappingErgebnis(
        ok = True,
        feldfehler = (),
        inventory_payload = inventory_payload,
        offer_payload = offer_payload,
        dry_run_eingabe = dry_run,
        hinweise = tuple(hinweise),
    )
