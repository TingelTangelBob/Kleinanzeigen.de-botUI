# SPDX-FileCopyrightText: © Anzeigen-Studio contributors
# SPDX-ArtifactOfProjectHomePage: https://github.com/TingelTangelBob/Kleinanzeigen.de-botUI/
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# Lokaler Dry-Run Fee/Validate (AP-E-04) – netzwerkfrei.
#
# Fee/Validate ist ein Ergebnisvertrag: Pflichtfelder lokal prüfen, Gebühren
# ausdrücklich als unbekannt markieren. Kein fingierter Validate-Endpunkt,
# kein Netzwerk, keine Gebührenzahl (niemals 0 € vortäuschen).

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from urllib.parse import urlparse

from anzeigen_studio.marketplaces.ebay.models import (
    HINWEIS_BILDER,
    HINWEIS_GEBUEHREN_DRY_RUN,
    HINWEIS_STANDORT,
    MARKETPLACE_ID_DE,
    WAEHRUNG_EUR,
    EbayDryRunEingabe,
    EbayDryRunErgebnis,
    EbayFeeErgebnis,
    EbayFeeKenntnis,
    EbayFeeQuelle,
    EbayFeldfehler,
    EbayUmgebung,
)


def _leer(wert: object) -> bool:
    if wert is None:
        return True
    if isinstance(wert, str):
        return not wert.strip()
    return False


def _preis_als_decimal(roh: Decimal | str) -> Decimal | None:
    try:
        if isinstance(roh, Decimal):
            wert = roh
        else:
            wert = Decimal(str(roh).strip().replace(",", "."))
    except (InvalidOperation, AttributeError, ValueError):
        return None
    if wert.is_nan() or wert.is_infinite():
        return None
    return wert


def ist_abrufbare_bild_url(url: str) -> bool:
    """True nur für http(s)-URLs – lokale Pfade und file:// fallen durch."""
    if not url or not str(url).strip():
        return False
    text = str(url).strip()
    # Windows-/Unix-Pfade und relative Dateinamen
    if "://" not in text:
        return False
    geparst = urlparse(text)
    if geparst.scheme not in {"http", "https"}:
        return False
    if not geparst.netloc:
        return False
    return True


def dry_run_pruefen(
    eingabe: EbayDryRunEingabe,
    *,
    umgebung: EbayUmgebung = EbayUmgebung.SANDBOX,
) -> EbayDryRunErgebnis:
    """Prüft Pflichtfelder lokal. Kein HTTP, kein eBay-Validate-Endpunkt.

    Gebühren sind im lokalen Dry-Run immer ``unbekannt`` – unabhängig davon,
    ob die Felder ok sind. Sandbox-API-Schätzung ist ein getrennter Lauf.
    """
    fehler: list[EbayFeldfehler] = []
    hinweise: list[str] = [HINWEIS_STANDORT, HINWEIS_BILDER, HINWEIS_GEBUEHREN_DRY_RUN]

    if _leer(eingabe.sku):
        fehler.append(EbayFeldfehler("sku", "SKU fehlt. Vor dem ersten API-Schreiben dauerhaft vergeben."))
    if _leer(eingabe.titel):
        fehler.append(EbayFeldfehler("titel", "Titel fehlt."))
    elif len(eingabe.titel.strip()) > 80:
        fehler.append(EbayFeldfehler("titel", "Titel darf höchstens 80 Zeichen haben."))
    if _leer(eingabe.beschreibung):
        fehler.append(EbayFeldfehler("beschreibung", "Beschreibung fehlt."))
    if _leer(eingabe.kategorie_id):
        fehler.append(EbayFeldfehler("kategorie_id", "eBay-Kategorie fehlt."))
    if _leer(eingabe.zustand_id):
        fehler.append(EbayFeldfehler("zustand_id", "Zustand (Condition) fehlt."))

    if (eingabe.marketplace_id or "").strip() != MARKETPLACE_ID_DE:
        fehler.append(EbayFeldfehler(
            "marketplace_id",
            f"Nur {MARKETPLACE_ID_DE} ist im MVP vorgesehen.",
        ))

    if (eingabe.waehrung or "").strip().upper() != WAEHRUNG_EUR:
        fehler.append(EbayFeldfehler("waehrung", "Nur EUR ist im MVP vorgesehen."))

    if eingabe.menge != 1:
        fehler.append(EbayFeldfehler("menge", "Menge muss 1 sein (ein eindeutig zugeordneter Artikel)."))

    preis = _preis_als_decimal(eingabe.preis)
    if preis is None:
        fehler.append(EbayFeldfehler("preis", "Festpreis ist ungültig."))
    elif preis <= 0:
        fehler.append(EbayFeldfehler("preis", "Festpreis muss größer als 0 sein."))

    if _leer(eingabe.merchant_location_key):
        fehler.append(EbayFeldfehler(
            "merchant_location_key",
            "Inventarstandort (merchantLocationKey) fehlt.",
        ))

    if _leer(eingabe.fulfillment_policy_id):
        fehler.append(EbayFeldfehler("fulfillment_policy_id", "Versandregel (Fulfillment Policy) fehlt."))
    if _leer(eingabe.payment_policy_id):
        fehler.append(EbayFeldfehler("payment_policy_id", "Zahlungsregel (Payment Policy) fehlt."))
    if _leer(eingabe.return_policy_id):
        fehler.append(EbayFeldfehler("return_policy_id", "Rückgaberegel (Return Policy) fehlt."))

    if not eingabe.bild_urls:
        fehler.append(EbayFeldfehler(
            "bild_urls",
            "Mindestens eine für eBay abrufbare Bild-URL (http/https) ist erforderlich.",
        ))
    else:
        for index, url in enumerate(eingabe.bild_urls):
            if not ist_abrufbare_bild_url(url):
                fehler.append(EbayFeldfehler(
                    f"bild_urls[{index}]",
                    "Bild ist keine abrufbare http(s)-URL (lokale Pfade reichen nicht).",
                ))

    gebuehren = EbayFeeErgebnis(
        kenntnis = EbayFeeKenntnis.UNBEKANNT,
        quelle = EbayFeeQuelle.LOKALER_DRY_RUN,
        umgebung = umgebung,
        hinweis = HINWEIS_GEBUEHREN_DRY_RUN,
        betrag = None,
        waehrung = None,
        ermittelt_am = None,
    )

    return EbayDryRunErgebnis(
        ok = not fehler,
        feldfehler = tuple(fehler),
        gebuehren = gebuehren,
        hinweise = tuple(hinweise),
    )
