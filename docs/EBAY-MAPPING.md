# eBay-Mapping Kategorie/Zustand/Versand/Preis (AP-E-05)

<!-- SPDX-License-Identifier: AGPL-3.0-or-later -->
<!-- Kleine Whitelist – keine volle Taxonomie, keine KI. -->

**Paket** AP-E-05 · **Stand** 2026-09-07 (UTC+2)  
**Ziel** Nachvollziehbare Abbildung auf Festpreis, `EBAY_DE`, EUR, Menge 1.  
**Module** `marketplaces/ebay/mapping.py`, `mapping_data.py`  
**Reuse** Dry-Run-Eingabe/Feldfehler aus E-04 (`models` / `validation.dry_run_pruefen`).

## Was gemappt wird

| Quelle | Ziel |
|---|---|
| Ausdrücklicher Kategorie-Schlüssel / freigegebener KA-Alias / Whitelist-`ebay_category_id` | `offer.categoryId` |
| Studio-Zustand / `condition_s` / eBay-Enum | `inventory.condition` |
| Absicht-Merkmale | `product.aspects` (Pflichtaspekte je Kategorie) |
| `ebay_preis` oder Anzeigenpreis bei `price_type=FIXED` | `pricingSummary.price` (Decimal, 2 Nachkommastellen) |
| Ausdrückliche Policy-IDs + `merchantLocationKey` | `listingPolicies` / Standort |

## Bewusste Nicht-Ziele

- Keine vollständige eBay-Taxonomie, kein Live-Category-Tree, keine KI-Zuordnung.
- Kleinanzeigen-`category`-IDs werden **nie** still als eBay-IDs übernommen.
- Keine Auktionen, keine Varianten, Menge immer 1, Format immer `FIXED_PRICE`.
- **KA-`shipping_options` ≠ eBay-Policies.** Fehlende Fulfillment-/Payment-/Return-IDs sind Feldfehler; Paketnamen werden nicht umgedeutet (AP-E-06 wählt Policies).
- Unbekannte Kategorie/Zustand, fehlende Pflichtmerkmale, VB/zu verschenken/ungültiger Preis → präziser `EbayFeldfehler`, kein Payload-Raten.

## Whitelist (MVP)

Siehe `mapping_data.py`: wenige Kategorie-Schlüssel (`elektronik.handy`, `elektronik.tablet`, `haus_garten.moebel`) inkl. Pflichtaspekte; Zustands-Map Studio/KA → Sell-Inventory-Condition.

Erweiterung nur durch **geprüfte** Einträge in der Ressource – nicht durch Heuristik.

## API

```text
anzeige_nach_ebay_payload(anzeige, absicht) → EbayMappingErgebnis
```

Bei `ok`: `inventory_payload`, `offer_payload`, optional `dry_run_eingabe` für E-04.  
Anzeigenmodell nur lesend (`EbayMappingAnzeige.aus_dict` / Readonly-Dataclass).

## Nächster Bau

AP-E-06 – Business Policies ausdrücklich auswählen.
