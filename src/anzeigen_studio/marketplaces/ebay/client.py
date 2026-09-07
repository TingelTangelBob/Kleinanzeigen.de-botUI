# SPDX-FileCopyrightText: © Anzeigen-Studio contributors
# SPDX-ArtifactOfProjectHomePage: https://github.com/TingelTangelBob/Kleinanzeigen.de-botUI/
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# Kleiner Sell-Inventory-HTTP-Adapter (AP-E-04).
#
# Kein universelles SDK. Schreibmethoden in Tests nur mit Fake-Transport.
# Produktion gesperrt. Nach Timeout/unklarer Schreibantwort: SKU-Abgleich
# vor Wiederholung – kein blindes createOffer/publishOffer.
# getListingFees ist optionaler Sandbox-/API-Lauf, kein lokaler Dry-Run und
# kein fingierter Validate-Endpunkt.

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from typing import Final, Protocol
from urllib.parse import quote

from anzeigen_studio.core.errors import FachlicherFehler
from anzeigen_studio.marketplaces.ebay.models import (
    EbayApiFehler,
    EbayFeeErgebnis,
    EbayFeeKenntnis,
    EbayFeeQuelle,
    EbayInventoryItemStand,
    EbayOfferStand,
    EbayPublishErgebnis,
    EbaySchreibAusgang,
    EbaySchreibSchritt,
    EbaySkuAbgleich,
    EbayUmgebung,
    EbayWiederaufnahmeAktion,
)

LOG = logging.getLogger(__name__)

HTTP_TIMEOUT_S: Final[float] = 20.0

_API_BASIS: Final[dict[EbayUmgebung, str]] = {
    EbayUmgebung.SANDBOX: "https://api.sandbox.ebay.com",
    EbayUmgebung.PRODUCTION: "https://api.ebay.com",
}


@dataclass(frozen = True, slots = True)
class ApiHttpAntwort:
    """Rohantwort eines Sell-API-Aufrufs – ohne Request-Echo/Tokens."""

    status_code: int
    body: dict[str, object] | list[object] | None
    text: str


class ApiTransport(Protocol):
    """Austauschbarer HTTP-Transport – Fakes in Tests, kein Netz nötig."""

    def request(
        self,
        method: str,
        url: str,
        *,
        headers: dict[str, str],
        json_body: dict[str, object] | None,
        timeout: float,
    ) -> ApiHttpAntwort:
        ...


class HttpxApiTransport:
    """Echter httpx-Transport. Lazy-Import. Für spätere Sandbox-Abnahme."""

    def request(
        self,
        method: str,
        url: str,
        *,
        headers: dict[str, str],
        json_body: dict[str, object] | None,
        timeout: float,
    ) -> ApiHttpAntwort:
        import httpx  # noqa: PLC0415 - nur hier gebraucht

        try:
            with httpx.Client(timeout = timeout) as klient:
                antwort = klient.request(method, url, headers = headers, json = json_body)
        except httpx.TimeoutException as fehler:
            raise FachlicherFehler(
                "eBay hat nicht rechtzeitig geantwortet. Bitte Status prüfen, nicht blind wiederholen.",
                status = 504,
            ) from fehler
        except httpx.HTTPError as fehler:
            LOG.warning("eBay-Sell-API nicht erreichbar: %s", type(fehler).__name__)
            raise FachlicherFehler(
                "Der eBay-API-Endpunkt ist nicht erreichbar.",
                status = 502,
            ) from fehler

        body: dict[str, object] | list[object] | None
        try:
            gelesen = antwort.json()
            if isinstance(gelesen, dict):
                body = gelesen
            elif isinstance(gelesen, list):
                body = gelesen
            else:
                body = None
        except ValueError:
            body = None
        return ApiHttpAntwort(status_code = antwort.status_code, body = body, text = antwort.text)


def _umgebung(wert: EbayUmgebung | str) -> EbayUmgebung:
    try:
        return wert if isinstance(wert, EbayUmgebung) else EbayUmgebung(wert)
    except ValueError as fehler:
        raise FachlicherFehler(
            "Unbekannte eBay-Umgebung. Erlaubt sind „sandbox“ und „production“.",
            feld = "umgebung",
        ) from fehler


def _jetzt() -> str:
    return datetime.now(UTC).isoformat(timespec = "seconds")


def _ebay_error_id(body: dict[str, object] | list[object] | None) -> str | None:
    if not isinstance(body, dict):
        return None
    errors = body.get("errors")
    if isinstance(errors, list) and errors:
        erster = errors[0]
        if isinstance(erster, dict):
            eid = erster.get("errorId")
            if eid is not None:
                return str(eid)
    return None


def _ebay_error_meldung(body: dict[str, object] | list[object] | None, fallback: str) -> str:
    if not isinstance(body, dict):
        return fallback
    errors = body.get("errors")
    if isinstance(errors, list) and errors:
        erster = errors[0]
        if isinstance(erster, dict):
            msg = erster.get("message")
            if isinstance(msg, str) and msg.strip():
                return msg.strip()[:300]
    return fallback


def klassifiziere_http(
    status: int,
    *,
    schreibversuch: bool,
    body: dict[str, object] | list[object] | None = None,
) -> EbaySchreibAusgang:
    """Mappt HTTP auf Auth / Rate-Limit / Fehler / Erfolg / unklar."""
    if status == 401:
        return EbaySchreibAusgang.AUTH
    if status == 429:
        return EbaySchreibAusgang.RATE_LIMIT
    if 200 <= status < 300:
        return EbaySchreibAusgang.ERFOLG
    # 5xx nach Schreibversuch: remote kann trotzdem durch sein → unklar
    if schreibversuch and status >= 500:
        return EbaySchreibAusgang.UNKLAR
    _ = body
    return EbaySchreibAusgang.FEHLER


class EbayClient:
    """Dünner Adapter für Inventory Item, Offer, Publish und optional Fees.

    Production-Aufrufe sind gesperrt. Für Schreibpfade in AP-E-04 ausschließlich
    Fake-Transport verwenden – kein Produktionsnetz, kein behaupteter Validate.
    """

    def __init__(
        self,
        *,
        access_token: str,
        umgebung: EbayUmgebung | str = EbayUmgebung.SANDBOX,
        transport: ApiTransport | None = None,
        timeout: float = HTTP_TIMEOUT_S,
    ) -> None:
        if not access_token or not access_token.strip():
            raise FachlicherFehler("Access-Token fehlt für den eBay-Client.", feld = "access_token")
        self._token = access_token.strip()
        self._umgebung = _umgebung(umgebung)
        if self._umgebung is EbayUmgebung.PRODUCTION:
            raise FachlicherFehler(
                "Produktive eBay-API-Aufrufe sind noch gesperrt. Bitte die Sandbox nutzen.",
                status = 409,
                feld = "umgebung",
            )
        self._transport = transport or HttpxApiTransport()
        self._timeout = timeout
        self._basis = _API_BASIS[self._umgebung]

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
            "Content-Language": "de-DE",
        }

    def _request(
        self,
        method: str,
        pfad: str,
        *,
        json_body: dict[str, object] | None = None,
        schritt: EbaySchreibSchritt,
        sku: str | None = None,
        offer_id: str | None = None,
        schreibversuch: bool = False,
    ) -> ApiHttpAntwort | EbayApiFehler:
        url = f"{self._basis}{pfad}"
        try:
            antwort = self._transport.request(
                method,
                url,
                headers = self._headers(),
                json_body = json_body,
                timeout = self._timeout,
            )
        except FachlicherFehler as fehler:
            # Timeout / Netz: nach Schreibversuch → unklar (Remote ggf. schon ok)
            ausgang = (
                EbaySchreibAusgang.UNKLAR
                if schreibversuch or fehler.status == 504
                else EbaySchreibAusgang.FEHLER
            )
            return EbayApiFehler(
                schritt = schritt,
                ausgang = ausgang,
                meldung = fehler.meldung,
                http_status = fehler.status,
                sku = sku,
                offer_id = offer_id,
            )

        ausgang = klassifiziere_http(
            antwort.status_code,
            schreibversuch = schreibversuch,
            body = antwort.body,
        )
        if ausgang is not EbaySchreibAusgang.ERFOLG:
            return EbayApiFehler(
                schritt = schritt,
                ausgang = ausgang,
                meldung = _ebay_error_meldung(
                    antwort.body,
                    {
                        EbaySchreibAusgang.AUTH: "eBay-Zugang abgelehnt (401). Bitte erneut verbinden.",
                        EbaySchreibAusgang.RATE_LIMIT: "eBay Rate-Limit erreicht (429). Bitte später erneut versuchen.",
                        EbaySchreibAusgang.UNKLAR: "eBay-Schreibantwort ist unklar. Bitte Status anhand der SKU prüfen.",
                        EbaySchreibAusgang.FEHLER: f"eBay meldet einen Fehler ({antwort.status_code}).",
                    }.get(ausgang, f"eBay-Fehler ({antwort.status_code})."),
                ),
                http_status = antwort.status_code,
                ebay_error_id = _ebay_error_id(antwort.body),
                sku = sku,
                offer_id = offer_id,
            )
        return antwort

    def create_or_replace_inventory_item(
        self,
        sku: str,
        payload: dict[str, object],
    ) -> EbayInventoryItemStand | EbayApiFehler:
        """PUT /sell/inventory/v1/inventory_item/{sku}."""
        if not sku or not sku.strip():
            raise FachlicherFehler("SKU fehlt.", feld = "sku")
        sku_s = sku.strip()
        ergebnis = self._request(
            "PUT",
            f"/sell/inventory/v1/inventory_item/{quote(sku_s, safe = '')}",
            json_body = payload,
            schritt = EbaySchreibSchritt.INVENTORY_ITEM,
            sku = sku_s,
            schreibversuch = True,
        )
        if isinstance(ergebnis, EbayApiFehler):
            return ergebnis
        # 204 No Content ist üblich – Erfolg ohne Body
        return EbayInventoryItemStand(sku = sku_s, vorhanden = True, titel = _titel_aus_payload(payload))

    def get_inventory_item(self, sku: str) -> EbayInventoryItemStand | EbayApiFehler:
        """GET Inventory Item – für SKU-Abgleich vor Wiederholung."""
        sku_s = sku.strip()
        ergebnis = self._request(
            "GET",
            f"/sell/inventory/v1/inventory_item/{quote(sku_s, safe = '')}",
            schritt = EbaySchreibSchritt.SKU_ABGLEICH,
            sku = sku_s,
            schreibversuch = False,
        )
        if isinstance(ergebnis, EbayApiFehler):
            if ergebnis.http_status == 404:
                return EbayInventoryItemStand(sku = sku_s, vorhanden = False)
            return ergebnis
        titel = None
        if isinstance(ergebnis.body, dict):
            produkt = ergebnis.body.get("product")
            if isinstance(produkt, dict):
                t = produkt.get("title")
                if isinstance(t, str):
                    titel = t
        return EbayInventoryItemStand(sku = sku_s, vorhanden = True, titel = titel)

    def create_offer(self, payload: dict[str, object]) -> EbayOfferStand | EbayApiFehler:
        """POST /sell/inventory/v1/offer – nur wenn Abgleich kein Offer liefert."""
        sku_roh = payload.get("sku")
        sku_s = sku_roh.strip() if isinstance(sku_roh, str) else None
        ergebnis = self._request(
            "POST",
            "/sell/inventory/v1/offer",
            json_body = payload,
            schritt = EbaySchreibSchritt.OFFER,
            sku = sku_s,
            schreibversuch = True,
        )
        if isinstance(ergebnis, EbayApiFehler):
            return ergebnis
        offer_id = None
        if isinstance(ergebnis.body, dict):
            oid = ergebnis.body.get("offerId")
            if isinstance(oid, str):
                offer_id = oid
        if not offer_id:
            return EbayApiFehler(
                schritt = EbaySchreibSchritt.OFFER,
                ausgang = EbaySchreibAusgang.UNKLAR,
                meldung = "eBay-Antwort ohne offerId – Status anhand der SKU prüfen.",
                http_status = ergebnis.status_code,
                sku = sku_s,
            )
        return EbayOfferStand(
            sku = sku_s or "",
            offer_id = offer_id,
            status = "UNPUBLISHED",
            marketplace_id = str(payload.get("marketplaceId") or "") or None,
        )

    def get_offers_for_sku(self, sku: str) -> list[EbayOfferStand] | EbayApiFehler:
        """GET /sell/inventory/v1/offer?sku=… – Abgleich vor createOffer."""
        sku_s = sku.strip()
        ergebnis = self._request(
            "GET",
            f"/sell/inventory/v1/offer?sku={quote(sku_s, safe = '')}",
            schritt = EbaySchreibSchritt.SKU_ABGLEICH,
            sku = sku_s,
            schreibversuch = False,
        )
        if isinstance(ergebnis, EbayApiFehler):
            if ergebnis.http_status == 404:
                return []
            return ergebnis
        angebote: list[EbayOfferStand] = []
        body = ergebnis.body
        offers_roh: list[object] = []
        if isinstance(body, dict):
            offers = body.get("offers")
            if isinstance(offers, list):
                offers_roh = offers
        elif isinstance(body, list):
            offers_roh = body
        for eintrag in offers_roh:
            if not isinstance(eintrag, dict):
                continue
            oid = eintrag.get("offerId")
            if not isinstance(oid, str) or not oid:
                continue
            lid = eintrag.get("listingId")
            status = eintrag.get("status")
            mp = eintrag.get("marketplaceId")
            angebote.append(EbayOfferStand(
                sku = sku_s,
                offer_id = oid,
                listing_id = lid if isinstance(lid, str) else None,
                status = status if isinstance(status, str) else None,
                marketplace_id = mp if isinstance(mp, str) else None,
            ))
        return angebote

    def publish_offer(self, offer_id: str, *, sku: str | None = None) -> EbayPublishErgebnis | EbayApiFehler:
        """POST /sell/inventory/v1/offer/{offerId}/publish."""
        if not offer_id or not offer_id.strip():
            raise FachlicherFehler("offerId fehlt.", feld = "offer_id")
        oid = offer_id.strip()
        ergebnis = self._request(
            "POST",
            f"/sell/inventory/v1/offer/{quote(oid, safe = '')}/publish",
            schritt = EbaySchreibSchritt.PUBLISH,
            sku = sku,
            offer_id = oid,
            schreibversuch = True,
        )
        if isinstance(ergebnis, EbayApiFehler):
            return ergebnis
        listing_id = None
        if isinstance(ergebnis.body, dict):
            lid = ergebnis.body.get("listingId")
            if isinstance(lid, str) and lid.strip():
                listing_id = lid.strip()
        if not listing_id:
            return EbayApiFehler(
                schritt = EbaySchreibSchritt.PUBLISH,
                ausgang = EbaySchreibAusgang.UNKLAR,
                meldung = "Publish-Antwort ohne listingId – Status prüfen, nicht blind wiederholen.",
                http_status = ergebnis.status_code,
                sku = sku,
                offer_id = oid,
            )
        return EbayPublishErgebnis(
            sku = sku or "",
            offer_id = oid,
            listing_id = listing_id,
            ausgang = EbaySchreibAusgang.ERFOLG,
            meldung = "Angebot veröffentlicht.",
        )

    def get_listing_fees(self, offer_ids: list[str]) -> EbayFeeErgebnis | EbayApiFehler:
        """Optionaler Sandbox-/API-Lauf (getListingFees) – kein lokaler Dry-Run.

        Fehlender oder unklarer Nachweis → Gebühren unbekannt, niemals 0 €.
        """
        ids = [o.strip() for o in offer_ids if o and o.strip()]
        if not ids:
            return EbayFeeErgebnis(
                kenntnis = EbayFeeKenntnis.UNBEKANNT,
                quelle = EbayFeeQuelle.NICHT_ABGERUFEN,
                umgebung = self._umgebung,
                hinweis = "Keine offerId für Gebührenschätzung – Gebühren unbekannt.",
            )
        payload: dict[str, object] = {
            "offers": [{"offerId": oid} for oid in ids],
        }
        ergebnis = self._request(
            "POST",
            "/sell/inventory/v1/offer/get_listing_fees",
            json_body = payload,
            schritt = EbaySchreibSchritt.LISTING_FEES,
            offer_id = ids[0],
            schreibversuch = False,
        )
        if isinstance(ergebnis, EbayApiFehler):
            return EbayFeeErgebnis(
                kenntnis = EbayFeeKenntnis.UNBEKANNT,
                quelle = EbayFeeQuelle.API_LISTING_FEES,
                umgebung = self._umgebung,
                hinweis = (
                    f"Gebührenschätzung fehlgeschlagen ({ergebnis.ausgang.value}): "
                    f"{ergebnis.meldung} – Gebühren unbekannt."
                ),
                ermittelt_am = _jetzt(),
            )
        betrag, waehrung = _fees_aus_antwort(ergebnis.body)
        if betrag is None:
            return EbayFeeErgebnis(
                kenntnis = EbayFeeKenntnis.UNBEKANNT,
                quelle = EbayFeeQuelle.API_LISTING_FEES,
                umgebung = self._umgebung,
                hinweis = (
                    "API-Antwort ohne auswertbaren Gebührenbetrag – Gebühren unbekannt. "
                    "Sandbox: keine Aussage über reale Produktionsgebühren."
                ),
                ermittelt_am = _jetzt(),
            )
        return EbayFeeErgebnis(
            kenntnis = EbayFeeKenntnis.BEKANNT,
            quelle = EbayFeeQuelle.API_LISTING_FEES,
            umgebung = self._umgebung,
            hinweis = (
                "Gebührenschätzung aus getListingFees (Sandbox/API). "
                "Keine Aussage über reale Produktionsgebühren."
            ),
            betrag = betrag,
            waehrung = waehrung or "EUR",
            ermittelt_am = _jetzt(),
        )

    def sku_abgleich_vor_wiederholung(self, sku: str) -> EbaySkuAbgleich | EbayApiFehler:
        """Definiert den nächsten Schritt nach Timeout/unklarer Schreibantwort.

        Reihenfolge: Inventory lesen → Offers zur SKU lesen → Aktion wählen.
        Nie blind createOffer oder publishOffer wiederholen.
        """
        if not sku or not sku.strip():
            raise FachlicherFehler("SKU fehlt für den Abgleich.", feld = "sku")
        sku_s = sku.strip()

        inventory = self.get_inventory_item(sku_s)
        if isinstance(inventory, EbayApiFehler):
            if inventory.ausgang in {EbaySchreibAusgang.AUTH, EbaySchreibAusgang.RATE_LIMIT}:
                return inventory
            return EbaySkuAbgleich(
                sku = sku_s,
                inventory = EbayInventoryItemStand(sku = sku_s, vorhanden = False),
                offer = None,
                naechste_aktion = EbayWiederaufnahmeAktion.FEHLER_BEHEBEN,
                hinweis = (
                    f"SKU-Abgleich: Inventory nicht lesbar ({inventory.meldung}). "
                    "Nächste Aktion: Fehler beheben / Status prüfen – nicht blind schreiben."
                ),
            )

        if not inventory.vorhanden:
            return EbaySkuAbgleich(
                sku = sku_s,
                inventory = inventory,
                offer = None,
                naechste_aktion = EbayWiederaufnahmeAktion.INVENTORY_SCHREIBEN,
                hinweis = "Kein Inventory Item zur SKU – zuerst createOrReplaceInventoryItem.",
            )

        offers = self.get_offers_for_sku(sku_s)
        if isinstance(offers, EbayApiFehler):
            if offers.ausgang in {EbaySchreibAusgang.AUTH, EbaySchreibAusgang.RATE_LIMIT}:
                return offers
            return EbaySkuAbgleich(
                sku = sku_s,
                inventory = inventory,
                offer = None,
                naechste_aktion = EbayWiederaufnahmeAktion.NICHTS_STATUS_PRUEFEN,
                hinweis = (
                    f"Offers zur SKU nicht lesbar ({offers.meldung}). "
                    "Status prüfen – kein createOffer."
                ),
            )

        if not offers:
            return EbaySkuAbgleich(
                sku = sku_s,
                inventory = inventory,
                offer = None,
                naechste_aktion = EbayWiederaufnahmeAktion.OFFER_ANLEGEN,
                hinweis = "Inventory vorhanden, kein Offer – createOffer einmalig anlegen.",
            )

        # Erstes Offer zur SKU (MVP: ein Artikel / Menge 1)
        offer = offers[0]
        status = (offer.status or "").upper()
        if offer.listing_id or status == "PUBLISHED":
            return EbaySkuAbgleich(
                sku = sku_s,
                inventory = inventory,
                offer = offer,
                naechste_aktion = EbayWiederaufnahmeAktion.NICHTS_STATUS_PRUEFEN,
                hinweis = (
                    f"Offer {offer.offer_id} bereits veröffentlicht "
                    f"(listingId={offer.listing_id!r}). Nicht erneut publishOffer."
                ),
            )
        if offer.offer_id:
            return EbaySkuAbgleich(
                sku = sku_s,
                inventory = inventory,
                offer = offer,
                naechste_aktion = EbayWiederaufnahmeAktion.PUBLISH,
                hinweis = (
                    f"Offer {offer.offer_id} vorhanden und unveröffentlicht – "
                    "publishOffer; kein erneutes createOffer."
                ),
            )
        return EbaySkuAbgleich(
            sku = sku_s,
            inventory = inventory,
            offer = offer,
            naechste_aktion = EbayWiederaufnahmeAktion.OFFER_AKTUALISIEREN,
            hinweis = "Offer-Eintrag unvollständig – aktualisieren statt neu anlegen.",
        )


def _titel_aus_payload(payload: dict[str, object]) -> str | None:
    produkt = payload.get("product")
    if isinstance(produkt, dict):
        t = produkt.get("title")
        if isinstance(t, str):
            return t
    return None


def _fees_aus_antwort(
    body: dict[str, object] | list[object] | None,
) -> tuple[Decimal | None, str | None]:
    """Extrahiert Summe falls klar vorhanden; sonst (None, None) → unbekannt."""
    if not isinstance(body, dict):
        return None, None
    # Typische Sell-Inventory getListingFees-Struktur (feeSummaries[].fees[].amount)
    summaries = body.get("feeSummaries")
    if not isinstance(summaries, list) or not summaries:
        # Manche Antworten: totalFees / amount
        total = body.get("totalFees")
        if isinstance(total, dict):
            return _amount_dict(total)
        return None, None
    summe = Decimal("0")
    waehrung: str | None = None
    gefunden = False
    for summary in summaries:
        if not isinstance(summary, dict):
            continue
        fees = summary.get("fees")
        if not isinstance(fees, list):
            continue
        for fee in fees:
            if not isinstance(fee, dict):
                continue
            amount = fee.get("amount")
            if isinstance(amount, dict):
                wert, cur = _amount_dict(amount)
                if wert is None:
                    return None, None
                summe += wert
                waehrung = waehrung or cur
                gefunden = True
    if not gefunden:
        return None, None
    return summe, waehrung


def _amount_dict(amount: dict[str, object]) -> tuple[Decimal | None, str | None]:
    roh = amount.get("value")
    cur = amount.get("currency")
    waehrung = cur if isinstance(cur, str) else None
    try:
        if roh is None:
            return None, waehrung
        wert = Decimal(str(roh))
    except (InvalidOperation, ValueError):
        return None, waehrung
    return wert, waehrung
