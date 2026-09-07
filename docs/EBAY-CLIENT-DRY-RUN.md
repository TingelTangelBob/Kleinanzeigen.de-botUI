# eBay-Client und lokaler Dry-Run (AP-E-04)

<!-- SPDX-License-Identifier: AGPL-3.0-or-later -->
<!-- Ergebnisvertrag Fee/Validate – kein fingierter Validate-Endpunkt. -->

**Paket** AP-E-04 · **Stand** 2026-09-07 (UTC+2)  
**Ziel** Kleiner HTTP-Adapter + netzwerkfreier lokaler Prüfvertrag für Inventory Item, Offer und Publish.  
**Nicht enthalten** Universelle SDK-Schicht, Production-Aufrufe, Mapping (E-05), Policies-UI (E-06), Publish-Job (E-07), echte Sandbox-Schreibläufe (E-12).

## Betriebsarten

| Betriebsart | Verhalten | Gebührenaussage |
|---|---|---|
| **Lokaler Dry-Run** | `validation.dry_run_pruefen` – Pflichtfelder, Standort, Bild-URLs; **kein Netzwerk** | Immer **Gebühren unbekannt** (Quelle `lokaler_dry_run`) – niemals 0 € |
| **Sandbox/API** | `EbayClient` gegen `api.sandbox.ebay.com` (in AP-E-04 nur mit **Fake-Transport** abgenommen) | Optional `get_listing_fees` → bekannt **nur** bei auswertbarem Betrag; sonst unbekannt. Keine Aussage über reale Produktionsgebühren |
| **Produktion** | Client lehnt `umgebung=production` mit 409 ab | – |

„Fee/Validate“ ist ein **Ergebnisvertrag**, kein behaupteter universeller Validate-Endpunkt. Lokale Prüfung und API-Gebührenschätzung sind getrennt; eine Fee-Schätzung kann ein angelegtes Angebot voraussetzen.

## Standort (`merchantLocationKey`)

Vor `publishOffer` muss am Verkäuferkonto ein Inventarstandort existieren und als `merchantLocationKey` am Inventory Item / Offer referenziert werden.

- Lokaler Dry-Run prüft nur: Schlüssel **gesetzt** (nicht leer).
- Ob der Schlüssel remote existiert, prüft erst ein späterer Sandbox-Lauf (Account API Location) – nicht Teil des Dry-Runs.
- Einstellungen/UI für Standortwahl: AP-E-09 / Policies AP-E-06.

## Bilder

eBay braucht **abrufbare http(s)-URLs**. Lokale Dateipfade (absolut, relativ, `file://`) reichen **nicht**.

| Sandbox-Nachweis | Eigene Bilder |
|---|---|
| Freigegebene **Testbild-URLs** sind zulässig | Hosting-Weg bleibt **explizit offen** |
| Studio wird dafür **nicht** ungeplant öffentlich erreichbar gemacht | Kein lokaler Dateiserver als Produktionslösung |

## SKU-Abgleich vor Wiederholung

Nach Timeout, Abbruch oder unklarer Schreibantwort (5xx nach Schreibversuch, Publish ohne `listingId`, Offer ohne `offerId`):

1. `GET` Inventory Item zur **stabilen SKU**
2. `GET` Offers zur SKU
3. Nächste Aktion wählen – **kein** blindes `createOffer` / `publishOffer`

| Remote-Stand | Aktion (`EbayWiederaufnahmeAktion`) |
|---|---|
| Kein Inventory | `inventory_schreiben` |
| Inventory, kein Offer | `offer_anlegen` |
| Offer unveröffentlicht | `publish` (bestehende `offerId`) |
| Offer veröffentlicht / `listingId` da | `nichts_status_pruefen` |
| Lesefehler / Auth / Rate-Limit | `fehler_beheben` bzw. Status prüfen |

## Module

| Datei | Rolle |
|---|---|
| `marketplaces/ebay/models.py` | Fee-Ergebnis (bekannt/unbekannt), Schreibausgang, Dry-Run-Eingabe, SKU-Abgleich |
| `marketplaces/ebay/validation.py` | `dry_run_pruefen`, `ist_abrufbare_bild_url` |
| `marketplaces/ebay/client.py` | `EbayClient`, `ApiTransport` / Fake, Inventory/Offer/Publish/Fees, `sku_abgleich_vor_wiederholung` |

Wiederverwendet: `oauth.py` / `credentials.py` (Token-Vertrag E-02/E-03) – der Client nimmt den Access-Token entgegen, speichert keine Secrets.

## Nächster Bau

AP-E-05 erledigt – siehe `docs/EBAY-MAPPING.md`. Nächster Bau: AP-E-06 (Business Policies).
