# SPDX-FileCopyrightText: © Anzeigen-Studio contributors
# SPDX-ArtifactOfProjectHomePage: https://github.com/TingelTangelBob/Kleinanzeigen.de-botUI/
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# eBay-Modelle: Zugang (AP-E-02) und Client/Dry-Run-Vertrag (AP-E-04).
#
# Tokens und App-Secrets gehoeren in credentials.py und nie in HTTP-Antworten,
# Logs oder Anzeigen-YAML. Fee/Validate ist ein Ergebnisvertrag – kein
# behaupteter universeller Validate-Endpunkt.

from __future__ import annotations

import enum
from dataclasses import dataclass
from decimal import Decimal
from typing import Final


#: Persistenzformat der Token-Zeile. Steigt nur bei inkompatiblen Aenderungen.
SCHEMA_VERSION: Final[int] = 1

#: MVP-Scopes laut Feinplan. sell.fulfillment erst bei Verkaufsabgleich.
MVP_SCOPES: Final[tuple[str, ...]] = ("sell.inventory", "sell.account")

#: Festpreis-Marktplatz und Waehrung fuer den ersten Schnitt.
MARKETPLACE_ID_DE: Final[str] = "EBAY_DE"
WAEHRUNG_EUR: Final[str] = "EUR"

#: Inventarstandort-Schluessel ist Pflicht vor publishOffer (Account API Location).
HINWEIS_STANDORT: Final[str] = (
    "Vor publishOffer muss ein Inventarstandort mit merchantLocationKey am "
    "Verkäuferkonto hinterlegt und am Inventory Item / Offer referenziert sein. "
    "Die lokale Prüfung prüft nur, dass der Schlüssel gesetzt ist – nicht, "
    "ob er remote existiert."
)

#: Bildweg: eBay braucht abrufbare URLs; lokale Pfade reichen nicht.
HINWEIS_BILDER: Final[str] = (
    "Bilder müssen für eBay unter http(s)-URLs abrufbar sein. Lokale Dateipfade "
    "(absolut, relativ, file://) reichen nicht. Für den ersten Sandbox-Nachweis "
    "dürfen freigegebene Testbild-URLs verwendet werden. Der Weg für eigene "
    "Bilder (Hosting) bleibt bewusst offen; die lokale Studio-Anwendung wird "
    "dafür nicht ungeplant öffentlich erreichbar gemacht."
)

#: Lokaler Dry-Run liefert keine Gebührenzahl – nie 0 € vortäuschen.
HINWEIS_GEBUEHREN_DRY_RUN: Final[str] = (
    "Lokaler Dry-Run: Gebühren unbekannt. Eine API-Gebührenschätzung "
    "(z. B. getListingFees) gehört zum gekennzeichneten Sandbox-/API-Lauf und "
    "kann ein angelegtes Angebot voraussetzen – kein fingierter Validate-Endpunkt."
)


class EbayUmgebung(enum.StrEnum):
    """Getrennte eBay-Umgebungen – Sandbox und Produktion niemals mischen."""

    SANDBOX = "sandbox"
    PRODUCTION = "production"


class EbayVerbindung(enum.StrEnum):
    """Was die Oberflaeche ueber die Kontoverbindung erfahren darf."""

    NICHT_VERBUNDEN = "nicht_verbunden"
    VERBUNDEN = "verbunden"
    ERNEUT_VERBINDEN = "erneut_verbinden"


class EbayFeeKenntnis(enum.StrEnum):
    """Ob ein Geldbetrag belegt ist – Unbekanntes nie als 0 € ausgeben."""

    UNBEKANNT = "unbekannt"
    BEKANNT = "bekannt"


class EbayFeeQuelle(enum.StrEnum):
    """Woher die Gebührenaussage stammt (Ergebnisvertrag, kein Fake-Validate)."""

    LOKALER_DRY_RUN = "lokaler_dry_run"
    API_LISTING_FEES = "api_listing_fees"
    NICHT_ABGERUFEN = "nicht_abgerufen"


class EbaySchreibSchritt(enum.StrEnum):
    """Sell-Inventory-Schritte – kein universelles SDK, nur diese Aufrufe."""

    INVENTORY_ITEM = "inventory_item"
    OFFER = "offer"
    PUBLISH = "publish"
    LISTING_FEES = "listing_fees"
    SKU_ABGLEICH = "sku_abgleich"


class EbaySchreibAusgang(enum.StrEnum):
    """Klassifikation einer Client-Antwort inkl. unklarer Schreiblage."""

    ERFOLG = "erfolg"
    FEHLER = "fehler"
    AUTH = "auth"
    RATE_LIMIT = "rate_limit"
    UNKLAR = "unklar"
    PRODUKTION_GESPERRT = "produktion_gesperrt"


class EbayWiederaufnahmeAktion(enum.StrEnum):
    """Nächster Schritt nach SKU-Abgleich – kein blindes createOffer/publish."""

    INVENTORY_SCHREIBEN = "inventory_schreiben"
    OFFER_ANLEGEN = "offer_anlegen"
    OFFER_AKTUALISIEREN = "offer_aktualisieren"
    PUBLISH = "publish"
    NICHTS_STATUS_PRUEFEN = "nichts_status_pruefen"
    FEHLER_BEHEBEN = "fehler_beheben"


@dataclass(frozen = True, slots = True)
class EbayZugangStatus:
    """Bereinigter Status – bewusst ohne Tokens, Secrets und Laengenangaben."""

    profil_id: int
    umgebung: EbayUmgebung
    verbindung: EbayVerbindung
    konto_id: str | None
    app_id: str | None
    scopes: tuple[str, ...]
    schema_version: int
    access_token_hinterlegt: bool
    refresh_token_hinterlegt: bool
    app_secret_hinterlegt: bool
    access_token_laeuft_ab: str | None
    refresh_token_laeuft_ab: str | None
    verbunden_am: str | None
    geaendert_am: str | None


@dataclass(frozen = True, slots = True)
class EbayGeheimnisse:
    """Klartext-Geheimnisse ausschliesslich fuer interne OAuth-/API-Aufrufe.

    Darf nie serialisiert, geloggt oder an die Oberflaeche gegeben werden.
    ``__repr__`` / ``__str__`` geben absichtlich nichts Brauchbares preis.
    """

    access_token: str | None
    refresh_token: str | None
    app_secret: str | None
    app_id: str | None
    konto_id: str | None
    scopes: tuple[str, ...]
    schema_version: int
    access_token_laeuft_ab: str | None
    refresh_token_laeuft_ab: str | None
    umgebung: EbayUmgebung

    def __repr__(self) -> str:
        return (
            "EbayGeheimnisse("
            f"umgebung={self.umgebung!r}, "
            f"konto_id={self.konto_id!r}, "
            f"app_id={self.app_id!r}, "
            f"scopes={self.scopes!r}, "
            f"schema_version={self.schema_version}, "
            f"access_token={'***' if self.access_token else None}, "
            f"refresh_token={'***' if self.refresh_token else None}, "
            f"app_secret={'***' if self.app_secret else None}, "
            f"access_token_laeuft_ab={self.access_token_laeuft_ab!r}, "
            f"refresh_token_laeuft_ab={self.refresh_token_laeuft_ab!r})"
        )

    __str__ = __repr__


@dataclass(frozen = True, slots = True)
class EbayFeeErgebnis:
    """Gebührenergebnis: bekannt nur mit Beleg; sonst ausdrücklich unbekannt."""

    kenntnis: EbayFeeKenntnis
    quelle: EbayFeeQuelle
    umgebung: EbayUmgebung
    hinweis: str
    betrag: Decimal | None = None
    waehrung: str | None = None
    ermittelt_am: str | None = None

    def __post_init__(self) -> None:
        if self.kenntnis is EbayFeeKenntnis.BEKANNT:
            if self.betrag is None:
                raise ValueError("Bekannte Gebühren brauchen einen Betrag.")
            if self.betrag < 0:
                raise ValueError("Gebührenbetrag darf nicht negativ sein.")
        elif self.betrag is not None:
            raise ValueError("Unbekannte Gebühren dürfen keinen Betrag tragen.")


@dataclass(frozen = True, slots = True)
class EbayApiFehler:
    """Strukturierter Sell-API-Fehler (Inventory / Offer / Publish)."""

    schritt: EbaySchreibSchritt
    ausgang: EbaySchreibAusgang
    meldung: str
    http_status: int | None = None
    ebay_error_id: str | None = None
    sku: str | None = None
    offer_id: str | None = None


@dataclass(frozen = True, slots = True)
class EbayInventoryItemStand:
    """Remote-Stand eines Inventory Items (SKU)."""

    sku: str
    vorhanden: bool
    titel: str | None = None


@dataclass(frozen = True, slots = True)
class EbayOfferStand:
    """Remote-Stand eines Offers zu einer SKU."""

    sku: str
    offer_id: str | None
    listing_id: str | None = None
    status: str | None = None  # z. B. PUBLISHED / UNPUBLISHED
    marketplace_id: str | None = None


@dataclass(frozen = True, slots = True)
class EbayPublishErgebnis:
    """Ergebnis von publishOffer – listingId nur bei bestätigt erfolgreichem Publish."""

    sku: str
    offer_id: str
    listing_id: str | None
    ausgang: EbaySchreibAusgang
    meldung: str


@dataclass(frozen = True, slots = True)
class EbaySkuAbgleich:
    """Abgleich vor Wiederholung nach Timeout/unklarer Schreibantwort."""

    sku: str
    inventory: EbayInventoryItemStand
    offer: EbayOfferStand | None
    naechste_aktion: EbayWiederaufnahmeAktion
    hinweis: str


@dataclass(frozen = True, slots = True)
class EbayFeldfehler:
    """Lokaler Pflichtfeldfehler – Feldname für die Oberfläche."""

    feld: str
    meldung: str


@dataclass(frozen = True, slots = True)
class EbayDryRunEingabe:
    """Eingabe für den netzwerkfreien lokalen Prüfvertrag (kein API-Validate)."""

    sku: str
    titel: str
    beschreibung: str
    kategorie_id: str
    zustand_id: str
    preis: Decimal | str
    merchant_location_key: str
    bild_urls: tuple[str, ...]
    fulfillment_policy_id: str
    payment_policy_id: str
    return_policy_id: str
    waehrung: str = WAEHRUNG_EUR
    menge: int = 1
    marketplace_id: str = MARKETPLACE_ID_DE
    artikelmerkmale: tuple[tuple[str, str], ...] = ()


@dataclass(frozen = True, slots = True)
class EbayDryRunErgebnis:
    """Lokales Prüfresultat: Feldfehler getrennt von Gebühren-Unbekannt."""

    ok: bool
    feldfehler: tuple[EbayFeldfehler, ...]
    gebuehren: EbayFeeErgebnis
    hinweise: tuple[str, ...]
