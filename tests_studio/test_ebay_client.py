# SPDX-FileCopyrightText: © Anzeigen-Studio contributors
# SPDX-ArtifactOfProjectHomePage: https://github.com/TingelTangelBob/Kleinanzeigen.de-botUI/
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# Tests eBay-Client + lokaler Dry-Run Fee/Validate (AP-E-04).
#
# Abgedeckt: netzwerkfreier Dry-Run, Pflichtfelder vs. Gebühren-unbekannt,
# Fake-Transport Timeout/401/429/unklare Schreibantwort, SKU-Abgleich vor
# Retry, Production gesperrt, Fees bekannt nur mit API-Beleg. Kein Netz.

from __future__ import annotations

from decimal import Decimal
from typing import Any

import pytest

from anzeigen_studio.core.errors import FachlicherFehler
from anzeigen_studio.marketplaces.ebay import client as ebay_client
from anzeigen_studio.marketplaces.ebay.client import ApiHttpAntwort, EbayClient
from anzeigen_studio.marketplaces.ebay.models import (
    EbayDryRunEingabe,
    EbayFeeKenntnis,
    EbayFeeQuelle,
    EbaySchreibAusgang,
    EbayUmgebung,
    EbayWiederaufnahmeAktion,
)
from anzeigen_studio.marketplaces.ebay.validation import dry_run_pruefen, ist_abrufbare_bild_url


class FakeApiTransport:
    """Steuerbarer Sell-API-Transport ohne Netzwerk."""

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []
        self.antworten: list[ApiHttpAntwort | BaseException] = []

    def queuee(self, antwort: ApiHttpAntwort | BaseException) -> None:
        self.antworten.append(antwort)

    def request(
        self,
        method: str,
        url: str,
        *,
        headers: dict[str, str],
        json_body: dict[str, object] | None,
        timeout: float,
    ) -> ApiHttpAntwort:
        self.calls.append({
            "method": method,
            "url": url,
            "headers": headers,
            "json_body": json_body,
            "timeout": timeout,
        })
        # Token darf in Assertions nicht aus Headers geleakt werden – nur Präsenz.
        assert "Authorization" in headers
        if not self.antworten:
            raise AssertionError("FakeApiTransport ohne Antwort")
        antwort = self.antworten.pop(0)
        if isinstance(antwort, BaseException):
            raise antwort
        return antwort


def _eingabe(**overrides: Any) -> EbayDryRunEingabe:
    basis: dict[str, Any] = {
        "sku": "ad-uuid-001",
        "titel": "Testartikel Sandbox",
        "beschreibung": "Beschreibung für Dry-Run.",
        "kategorie_id": "12345",
        "zustand_id": "USED_EXCELLENT",
        "preis": Decimal("19.99"),
        "merchant_location_key": "home-de-1",
        "bild_urls": ("https://i.ebayimg.com/images/test/1.jpg",),
        "fulfillment_policy_id": "ful-1",
        "payment_policy_id": "pay-1",
        "return_policy_id": "ret-1",
    }
    basis.update(overrides)
    return EbayDryRunEingabe(**basis)


class TestBildUrl:

    def test_https_ok(self) -> None:
        assert ist_abrufbare_bild_url("https://cdn.example/img.jpg")

    def test_lokaler_pfad_nein(self) -> None:
        assert not ist_abrufbare_bild_url("/Users/x/bild.jpg")
        assert not ist_abrufbare_bild_url("bilder/a.jpg")
        assert not ist_abrufbare_bild_url("file:///tmp/a.jpg")


class TestDryRun:

    def test_ok_gebuehren_unbekannt(self) -> None:
        ergebnis = dry_run_pruefen(_eingabe())
        assert ergebnis.ok
        assert ergebnis.feldfehler == ()
        assert ergebnis.gebuehren.kenntnis is EbayFeeKenntnis.UNBEKANNT
        assert ergebnis.gebuehren.quelle is EbayFeeQuelle.LOKALER_DRY_RUN
        assert ergebnis.gebuehren.betrag is None
        assert "Gebühren unbekannt" in ergebnis.gebuehren.hinweis
        assert any("merchantLocationKey" in h for h in ergebnis.hinweise)
        assert any("http(s)" in h for h in ergebnis.hinweise)

    def test_fehlende_pflichtfelder(self) -> None:
        ergebnis = dry_run_pruefen(_eingabe(
            sku = "",
            titel = "",
            merchant_location_key = "",
            fulfillment_policy_id = "",
            bild_urls = (),
        ))
        assert not ergebnis.ok
        felder = {f.feld for f in ergebnis.feldfehler}
        assert "sku" in felder
        assert "titel" in felder
        assert "merchant_location_key" in felder
        assert "fulfillment_policy_id" in felder
        assert "bild_urls" in felder
        # Gebühren bleiben unbekannt – unterscheidbar von Feldfehlern
        assert ergebnis.gebuehren.kenntnis is EbayFeeKenntnis.UNBEKANNT
        assert ergebnis.gebuehren.betrag is None

    def test_lokales_bild_blockiert(self) -> None:
        ergebnis = dry_run_pruefen(_eingabe(bild_urls = ("/tmp/photo.jpg",)))
        assert not ergebnis.ok
        assert any(f.feld == "bild_urls[0]" for f in ergebnis.feldfehler)

    def test_ungueltiger_preis_und_menge(self) -> None:
        ergebnis = dry_run_pruefen(_eingabe(preis = "0", menge = 2, waehrung = "USD"))
        felder = {f.feld for f in ergebnis.feldfehler}
        assert "preis" in felder
        assert "menge" in felder
        assert "waehrung" in felder

    def test_kein_netzwerk_kein_validate_endpunkt(self) -> None:
        # Dry-Run importiert/benutzt keinen Transport – reine lokale Funktion.
        ergebnis = dry_run_pruefen(_eingabe())
        assert ergebnis.ok
        assert ergebnis.gebuehren.quelle is not EbayFeeQuelle.API_LISTING_FEES


class TestEbayClient:

    def test_production_gesperrt(self) -> None:
        with pytest.raises(FachlicherFehler) as fehler:
            EbayClient(access_token = "tok", umgebung = EbayUmgebung.PRODUCTION)
        assert fehler.value.status == 409

    def test_inventory_put_ok(self) -> None:
        fake = FakeApiTransport()
        fake.queuee(ApiHttpAntwort(status_code = 204, body = None, text = ""))
        c = EbayClient(access_token = "tok-sandbox", transport = fake)
        stand = c.create_or_replace_inventory_item(
            "sku-1",
            {"product": {"title": "T"}, "availability": {}},
        )
        assert not isinstance(stand, ebay_client.EbayApiFehler)
        assert stand.vorhanden and stand.sku == "sku-1"
        assert fake.calls[0]["method"] == "PUT"
        assert "inventory_item/sku-1" in fake.calls[0]["url"]
        assert "api.sandbox.ebay.com" in fake.calls[0]["url"]

    def test_timeout_schreibversuch_unklar(self) -> None:
        fake = FakeApiTransport()
        fake.queuee(FachlicherFehler(
            "eBay hat nicht rechtzeitig geantwortet. Bitte Status prüfen, nicht blind wiederholen.",
            status = 504,
        ))
        c = EbayClient(access_token = "tok", transport = fake)
        ergebnis = c.create_or_replace_inventory_item("sku-t", {"product": {"title": "T"}})
        assert isinstance(ergebnis, ebay_client.EbayApiFehler)
        assert ergebnis.ausgang is EbaySchreibAusgang.UNKLAR
        assert ergebnis.http_status == 504

    def test_401_auth(self) -> None:
        fake = FakeApiTransport()
        fake.queuee(ApiHttpAntwort(
            status_code = 401,
            body = {"errors": [{"errorId": 1001, "message": "Invalid access token"}]},
            text = "{}",
        ))
        c = EbayClient(access_token = "tok", transport = fake)
        ergebnis = c.publish_offer("offer-1", sku = "sku-1")
        assert isinstance(ergebnis, ebay_client.EbayApiFehler)
        assert ergebnis.ausgang is EbaySchreibAusgang.AUTH
        assert ergebnis.ebay_error_id == "1001"

    def test_429_rate_limit(self) -> None:
        fake = FakeApiTransport()
        fake.queuee(ApiHttpAntwort(status_code = 429, body = None, text = "rate"))
        c = EbayClient(access_token = "tok", transport = fake)
        ergebnis = c.create_offer({"sku": "sku-1", "marketplaceId": "EBAY_DE"})
        assert isinstance(ergebnis, ebay_client.EbayApiFehler)
        assert ergebnis.ausgang is EbaySchreibAusgang.RATE_LIMIT

    def test_publish_ohne_listing_id_unklar(self) -> None:
        fake = FakeApiTransport()
        fake.queuee(ApiHttpAntwort(status_code = 200, body = {}, text = "{}"))
        c = EbayClient(access_token = "tok", transport = fake)
        ergebnis = c.publish_offer("offer-x", sku = "sku-x")
        assert isinstance(ergebnis, ebay_client.EbayApiFehler)
        assert ergebnis.ausgang is EbaySchreibAusgang.UNKLAR

    def test_publish_ok(self) -> None:
        fake = FakeApiTransport()
        fake.queuee(ApiHttpAntwort(
            status_code = 200,
            body = {"listingId": "listing-99"},
            text = "{}",
        ))
        c = EbayClient(access_token = "tok", transport = fake)
        ergebnis = c.publish_offer("offer-2", sku = "sku-2")
        assert not isinstance(ergebnis, ebay_client.EbayApiFehler)
        assert ergebnis.listing_id == "listing-99"
        assert ergebnis.ausgang is EbaySchreibAusgang.ERFOLG

    def test_5xx_nach_schreibversuch_unklar(self) -> None:
        fake = FakeApiTransport()
        fake.queuee(ApiHttpAntwort(status_code = 503, body = None, text = "down"))
        c = EbayClient(access_token = "tok", transport = fake)
        ergebnis = c.create_offer({"sku": "sku-5", "marketplaceId": "EBAY_DE"})
        assert isinstance(ergebnis, ebay_client.EbayApiFehler)
        assert ergebnis.ausgang is EbaySchreibAusgang.UNKLAR


class TestSkuAbgleich:

    def test_kein_inventory_dann_schreiben(self) -> None:
        fake = FakeApiTransport()
        fake.queuee(ApiHttpAntwort(status_code = 404, body = None, text = ""))
        c = EbayClient(access_token = "tok", transport = fake)
        ab = c.sku_abgleich_vor_wiederholung("sku-new")
        assert not isinstance(ab, ebay_client.EbayApiFehler)
        assert ab.naechste_aktion is EbayWiederaufnahmeAktion.INVENTORY_SCHREIBEN

    def test_inventory_ohne_offer_anlegen(self) -> None:
        fake = FakeApiTransport()
        fake.queuee(ApiHttpAntwort(
            status_code = 200,
            body = {"product": {"title": "T"}},
            text = "{}",
        ))
        fake.queuee(ApiHttpAntwort(status_code = 200, body = {"offers": []}, text = "{}"))
        c = EbayClient(access_token = "tok", transport = fake)
        ab = c.sku_abgleich_vor_wiederholung("sku-2")
        assert not isinstance(ab, ebay_client.EbayApiFehler)
        assert ab.inventory.vorhanden
        assert ab.naechste_aktion is EbayWiederaufnahmeAktion.OFFER_ANLEGEN

    def test_unveröffentlichtes_offer_publish_kein_create(self) -> None:
        fake = FakeApiTransport()
        fake.queuee(ApiHttpAntwort(
            status_code = 200,
            body = {"product": {"title": "T"}},
            text = "{}",
        ))
        fake.queuee(ApiHttpAntwort(
            status_code = 200,
            body = {"offers": [{"offerId": "off-7", "status": "UNPUBLISHED"}]},
            text = "{}",
        ))
        c = EbayClient(access_token = "tok", transport = fake)
        ab = c.sku_abgleich_vor_wiederholung("sku-7")
        assert not isinstance(ab, ebay_client.EbayApiFehler)
        assert ab.naechste_aktion is EbayWiederaufnahmeAktion.PUBLISH
        assert ab.offer is not None and ab.offer.offer_id == "off-7"

    def test_bereits_veroeffentlicht_status_pruefen(self) -> None:
        fake = FakeApiTransport()
        fake.queuee(ApiHttpAntwort(status_code = 200, body = {"product": {}}, text = "{}"))
        fake.queuee(ApiHttpAntwort(
            status_code = 200,
            body = {"offers": [{
                "offerId": "off-9",
                "status": "PUBLISHED",
                "listingId": "list-9",
            }]},
            text = "{}",
        ))
        c = EbayClient(access_token = "tok", transport = fake)
        ab = c.sku_abgleich_vor_wiederholung("sku-9")
        assert not isinstance(ab, ebay_client.EbayApiFehler)
        assert ab.naechste_aktion is EbayWiederaufnahmeAktion.NICHTS_STATUS_PRUEFEN


class TestListingFees:

    def test_bekannter_betrag_aus_api(self) -> None:
        fake = FakeApiTransport()
        fake.queuee(ApiHttpAntwort(
            status_code = 200,
            body = {
                "feeSummaries": [{
                    "fees": [{
                        "amount": {"value": "0.35", "currency": "EUR"},
                    }],
                }],
            },
            text = "{}",
        ))
        c = EbayClient(access_token = "tok", transport = fake)
        fees = c.get_listing_fees(["off-1"])
        assert not isinstance(fees, ebay_client.EbayApiFehler)
        assert fees.kenntnis is EbayFeeKenntnis.BEKANNT
        assert fees.betrag == Decimal("0.35")
        assert fees.waehrung == "EUR"
        assert fees.quelle is EbayFeeQuelle.API_LISTING_FEES
        assert fees.umgebung is EbayUmgebung.SANDBOX

    def test_leere_api_antwort_unbekannt_nicht_null(self) -> None:
        fake = FakeApiTransport()
        fake.queuee(ApiHttpAntwort(status_code = 200, body = {}, text = "{}"))
        c = EbayClient(access_token = "tok", transport = fake)
        fees = c.get_listing_fees(["off-2"])
        assert not isinstance(fees, ebay_client.EbayApiFehler)
        assert fees.kenntnis is EbayFeeKenntnis.UNBEKANNT
        assert fees.betrag is None
        assert "unbekannt" in fees.hinweis.lower()
