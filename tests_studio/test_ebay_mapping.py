# SPDX-FileCopyrightText: © Anzeigen-Studio contributors
# SPDX-ArtifactOfProjectHomePage: https://github.com/TingelTangelBob/Kleinanzeigen.de-botUI/
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# Tests eBay-Mapping Kategorie/Zustand/Versand/Preis (AP-E-05).
#
# Fünf Anzeigen-Fixtures → reproduzierbare Payloads oder präzise Feldfehler.
# Kein Netz, keine Taxonomie-KI, KA-Pakete ≠ Policies, Decimal-sicher.

from __future__ import annotations

from decimal import Decimal

from anzeigen_studio.marketplaces.ebay.mapping import (
    EbayMappingAbsicht,
    EbayMappingAnzeige,
    anzeige_nach_ebay_payload,
)
from anzeigen_studio.marketplaces.ebay.models import MARKETPLACE_ID_DE, WAEHRUNG_EUR
from anzeigen_studio.marketplaces.ebay.validation import dry_run_pruefen


def _absicht(**overrides: object) -> EbayMappingAbsicht:
    basis: dict[str, object] = {
        "sku": "ad-uuid-map-001",
        "kategorie_schluessel": "elektronik.handy",
        "zustand": "neu",
        "artikelmerkmale": {"Marke": "Fairphone", "Modell": "5"},
        "merchant_location_key": "home-de-1",
        "fulfillment_policy_id": "ful-1",
        "payment_policy_id": "pay-1",
        "return_policy_id": "ret-1",
        "bild_urls": ("https://i.ebayimg.com/images/test/1.jpg",),
    }
    basis.update(overrides)
    return EbayMappingAbsicht(**basis)  # type: ignore[arg-type]


def _anzeige_festpreis_handy() -> dict[str, object]:
    """Fixture 1 – Happy path Handy/Festpreis."""
    return {
        "title": "Fairphone 5 256GB",
        "description": "Gepflegtes Fairphone, Rechnung vorhanden.",
        "category": "Elektronik.Handy & Telefon.Handys & Smartphones",
        "price": "249.90",
        "price_type": "FIXED",
        "shipping_type": "SHIPPING",
        "shipping_options": ["DHL_2", "HERMES_BIS_10KG"],
        "special_attributes": {"condition_s": "new"},
        "images": ["https://i.ebayimg.com/images/test/1.jpg"],
    }


def _anzeige_tablet_wie_neu() -> dict[str, object]:
    """Fixture 2 – andere Kategorie/Zustand; eBay-Preis überschreibt."""
    return {
        "title": "iPad Air 64GB",
        "description": "Wie neu, mit OVP.",
        "category": "Elektronik.Computer.Tablets & Reader",
        "price": 400,
        "price_type": "FIXED",
        "shipping_type": "PICKUP",
        "shipping_options": [],
        "special_attributes": {"condition_s": "like_new"},
        "images": ["https://i.ebayimg.com/images/test/2.jpg"],
    }


def _anzeige_unbekannte_kategorie() -> dict[str, object]:
    """Fixture 3 – unbekannte KA-Kategorie ohne Whitelist-Absicht."""
    return {
        "title": "Seltenes Sammlerstück",
        "description": "Beschreibung.",
        "category": "Freizeit.Sammeln.Obskur.12345",
        "price": 10,
        "price_type": "FIXED",
        "special_attributes": {"condition_s": "ok"},
        "images": ["https://i.ebayimg.com/images/test/3.jpg"],
    }


def _anzeige_ohne_merkmal() -> dict[str, object]:
    """Fixture 4 – bekannte Kategorie, Zustand ok, Pflichtmerkmal fehlt in Absicht."""
    return {
        "title": "Schreibtisch Eiche",
        "description": "Massivholz.",
        "category": "Haus & Garten.Möbel & Wohnen.Möbel",
        "price": "120.00",
        "price_type": "FIXED",
        "special_attributes": {"condition_s": "alright"},
        "images": ["https://i.ebayimg.com/images/test/4.jpg"],
    }


def _anzeige_kein_festpreis() -> dict[str, object]:
    """Fixture 5 – VB / ungültiger Festpreis."""
    return {
        "title": "Lampe VB",
        "description": "Verhandlungsbasis.",
        "category": "Haus & Garten.Möbel & Wohnen.Möbel",
        "price": 25,
        "price_type": "NEGOTIABLE",
        "special_attributes": {"condition_s": "ok"},
        "images": ["https://i.ebayimg.com/images/test/5.jpg"],
    }


def test_fixture1_festpreis_handy_payload_reproduzierbar() -> None:
    anzeige = _anzeige_festpreis_handy()
    ergebnis = anzeige_nach_ebay_payload(anzeige, _absicht())
    assert ergebnis.ok is True
    assert ergebnis.feldfehler == ()
    assert ergebnis.inventory_payload is not None
    assert ergebnis.offer_payload is not None

    inv = ergebnis.inventory_payload
    assert inv["condition"] == "NEW"
    assert inv["availability"]["shipToLocationAvailability"]["quantity"] == 1
    assert inv["product"]["title"] == "Fairphone 5 256GB"
    assert inv["product"]["aspects"] == {
        "Marke": ["Fairphone"],
        "Modell": ["5"],
    }

    offer = ergebnis.offer_payload
    assert offer["marketplaceId"] == MARKETPLACE_ID_DE
    assert offer["format"] == "FIXED_PRICE"
    assert offer["categoryId"] == "9355"
    assert offer["availableQuantity"] == 1
    assert offer["pricingSummary"]["price"] == {
        "currency": WAEHRUNG_EUR,
        "value": "249.90",
    }
    # KA-Pakete dürfen nicht als Policy landen
    assert offer["listingPolicies"]["fulfillmentPolicyId"] == "ful-1"
    assert "DHL_2" not in str(offer["listingPolicies"])
    assert any("Versandpakete" in h for h in ergebnis.hinweise)

    # Reproduzierbarkeit
    erneut = anzeige_nach_ebay_payload(anzeige, _absicht())
    assert erneut.inventory_payload == ergebnis.inventory_payload
    assert erneut.offer_payload == ergebnis.offer_payload

    assert ergebnis.dry_run_eingabe is not None
    dry = dry_run_pruefen(ergebnis.dry_run_eingabe)
    assert dry.ok is True


def test_fixture2_tablet_ebay_preis_ueberschreibt_zustand_like_new() -> None:
    ergebnis = anzeige_nach_ebay_payload(
        _anzeige_tablet_wie_neu(),
        _absicht(
            sku = "ad-uuid-map-002",
            kategorie_schluessel = "elektronik.tablet",
            zustand = "wie_neu",
            artikelmerkmale = {"Marke": "Apple", "Modell": "iPad Air"},
            ebay_preis = Decimal("349.95"),
            bild_urls = ("https://i.ebayimg.com/images/test/2.jpg",),
        ),
    )
    assert ergebnis.ok is True
    assert ergebnis.offer_payload is not None
    assert ergebnis.offer_payload["categoryId"] == "171485"
    assert ergebnis.offer_payload["pricingSummary"]["price"]["value"] == "349.95"
    assert ergebnis.inventory_payload is not None
    assert ergebnis.inventory_payload["condition"] == "LIKE_NEW"


def test_fixture3_unbekannte_kategorie_feldfehler() -> None:
    ergebnis = anzeige_nach_ebay_payload(
        _anzeige_unbekannte_kategorie(),
        _absicht(
            kategorie_schluessel = None,
            artikelmerkmale = {"Marke": "X"},
        ),
    )
    assert ergebnis.ok is False
    assert ergebnis.inventory_payload is None
    assert ergebnis.offer_payload is None
    felder = {f.feld for f in ergebnis.feldfehler}
    assert "kategorie" in felder
    assert any("Whitelist" in f.meldung or "unbekannt" in f.meldung.lower()
               or "Unbekannte" in f.meldung for f in ergebnis.feldfehler)


def test_fixture4_fehlendes_pflichtmerkmal_oder_unbekannter_zustand() -> None:
    # 4a Pflichtmerkmal fehlt
    ergebnis = anzeige_nach_ebay_payload(
        _anzeige_ohne_merkmal(),
        _absicht(
            kategorie_schluessel = "haus_garten.moebel",
            zustand = "in_ordnung",
            artikelmerkmale = {},  # Marke fehlt
        ),
    )
    assert ergebnis.ok is False
    assert any(f.feld == "artikelmerkmale.Marke" for f in ergebnis.feldfehler)

    # 4b unbekannter Zustand
    ergebnis2 = anzeige_nach_ebay_payload(
        {
            **_anzeige_ohne_merkmal(),
            "special_attributes": {"condition_s": "super_rare_condition"},
        },
        _absicht(
            kategorie_schluessel = "haus_garten.moebel",
            zustand = None,
            artikelmerkmale = {"Marke": "Ikea"},
        ),
    )
    assert ergebnis2.ok is False
    assert any(f.feld == "zustand" for f in ergebnis2.feldfehler)


def test_fixture5_ungültiger_festpreis_blockiert() -> None:
    ergebnis = anzeige_nach_ebay_payload(
        _anzeige_kein_festpreis(),
        _absicht(
            kategorie_schluessel = "haus_garten.moebel",
            zustand = "gut",
            artikelmerkmale = {"Marke": "Ikea"},
            ebay_preis = None,
        ),
    )
    assert ergebnis.ok is False
    assert any(f.feld == "price_type" for f in ergebnis.feldfehler)

    # ≤ 0
    ergebnis_null = anzeige_nach_ebay_payload(
        {**_anzeige_festpreis_handy(), "price": 0, "price_type": "FIXED"},
        _absicht(ebay_preis = None),
    )
    assert ergebnis_null.ok is False
    assert any(f.feld == "preis" for f in ergebnis_null.feldfehler)

    # Give-away
    ergebnis_ga = anzeige_nach_ebay_payload(
        {**_anzeige_kein_festpreis(), "price_type": "GIVE_AWAY", "price": 0},
        _absicht(
            kategorie_schluessel = "haus_garten.moebel",
            artikelmerkmale = {"Marke": "Ikea"},
            ebay_preis = None,
        ),
    )
    assert ergebnis_ga.ok is False
    assert any(f.feld == "price_type" for f in ergebnis_ga.feldfehler)


def test_ka_versandpakete_nicht_als_policy() -> None:
    ergebnis = anzeige_nach_ebay_payload(
        _anzeige_festpreis_handy(),
        _absicht(fulfillment_policy_id = ""),
    )
    assert ergebnis.ok is False
    assert any(f.feld == "fulfillment_policy_id" for f in ergebnis.feldfehler)
    # Auch wenn KA-Pakete gesetzt sind, kein stilles Mapping
    assert all(
        "DHL" not in (ergebnis.offer_payload or {}).get("listingPolicies", {}).get("fulfillmentPolicyId", "")
        for _ in (0,)
    )


def test_decimal_cent_genau_kein_float_ballast() -> None:
    ergebnis = anzeige_nach_ebay_payload(
        _anzeige_festpreis_handy(),
        _absicht(ebay_preis = Decimal("19.90")),
    )
    assert ergebnis.ok is True
    assert ergebnis.offer_payload is not None
    assert ergebnis.offer_payload["pricingSummary"]["price"]["value"] == "19.90"
    # String-Eingabe mit Komma
    ergebnis2 = anzeige_nach_ebay_payload(
        _anzeige_festpreis_handy(),
        _absicht(ebay_preis = "19,90"),
    )
    assert ergebnis2.ok is True
    assert ergebnis2.offer_payload is not None
    assert ergebnis2.offer_payload["pricingSummary"]["price"]["value"] == "19.90"


def test_readonly_dataclass_eingabe() -> None:
    anzeige = EbayMappingAnzeige.aus_dict(_anzeige_festpreis_handy())
    ergebnis = anzeige_nach_ebay_payload(anzeige, _absicht())
    assert ergebnis.ok is True
