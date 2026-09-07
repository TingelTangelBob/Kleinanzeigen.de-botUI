# eBay Sell-API DE – Machbarkeit (AP-E-01)

<!-- SPDX-License-Identifier: AGPL-3.0-or-later -->
<!-- Neue Datei des Forks. Kurzcheck zu AP-6.1 / AP-E-01. Keine Rechtsberatung. -->

**Paket** AP-E-01 · **füllt** AP-6.1 · **Stand Recherche** 2026-09-07 (UTC+2)  
**Agent** Grok Bot Executor (Luna `gpt-5.6-luna` high)  
**Scope** Docs only – kein Code, keine Registrierung, kein OAuth, keine Veröffentlichung.

## Kurzempfehlung

| Spur | Empfehlung |
|---|---|
| **Sandbox** | **Go** – Entwicklerkonto + Sandbox-Keyset + Testnutzer + OAuth User Token mit `sell.inventory` / `sell.account`; Business Policies und Inventarstandort am Testkonto anlegen; lokaler Dry-Run vor API-Schreiben (AP-E-02…04). |
| **Produktion** | **Blocker getrennt** – Production-Keyset erst nach Marketplace-Account-Deletion-Endpoint (oder dokumentiertem Opt-out); Kontoeignung (Policies/KYC/Bank/Limits), Bildweg, Gebührenanzeige und Verkaufsabgleich (AP-6.5) vor produktivem Publish. |
| **AP-6.1 abschließen?** | **Nein** – Matrix und Quellen liegen vor, aber kontospezifische Nachweise (Steffen) und einige Live-API-Details sind **offen**. |

**Nicht behauptet:** Gewerbekonto sei zwingend; konkrete Gebührenhöhen für Steffens Konto; „Einstellen = 0 €“.

---

## Entscheidungsmatrix

| Thema | Stand | Antwort / Beleg | Offen / Nachweis |
|---|---|---|---|
| **Kontotyp** | teilweise | eBay.de unterscheidet **private** und **gewerbliche** Verkäufer (eigene Gebührenhilfen). Sell Inventory verlangt **Business-Policy-Opt-in** und Policy-IDs am Offer – das ist eine **API-/Konto-Voraussetzung**, keine pauschale Aussage „nur Gewerbe“. Gewerbekonto wird hier **nicht** als Pflicht festgeschrieben. | **Steffen:** Ist das Zielkonto privat oder gewerblich? Sind Business Policies am Konto freigeschaltet / anlegbar? |
| **Developer App** | belegt (Dok) | Entwicklerkonto unter `developer.ebay.com`; getrennte **Sandbox**- und **Production**-Keysets (App ID / Cert ID / Dev ID). Scopes werden dem Keyset zugeordnet. | **Steffen:** Sandbox-App anlegen (RuName/Redirect). Production erst später. |
| **OAuth** | belegt (Dok) | Sell-Aufrufe brauchen **User Access Token** (Authorization-Code-Flow + Refresh). MVP-Scopes laut Feinplan: `sell.inventory`, `sell.account`; `sell.fulfillment` erst bei Bestell-/Verkaufsabgleich. Zustimmung durch Kontoinhaber – **keine** Browserautomatisierung der Verkaufs-UI. | Exakte Scope-Liste am Keyset im Developer Portal prüfen; Token-Laufzeiten am Portal/Docs bestätigen (nicht hier festnageln). |
| **Business Policies** | belegt (Dok) | Inventory Overview: jedes Offer muss **payment**, **fulfillment** und **return** Policy referenzieren; Verkäufer muss opted-in sein und Policies vorhalten. Account API: Policies anlegen/auflisten. Rückgabe-/Zahlungsregeln sind **rechtliche Zusagen** → keine stille Vorbelegung (vgl. RECHTLICHES §7 / AP-6.3). | **Steffen:** Opt-in + drei Policies (Sandbox). Produktion: eigene Policy-IDs, keine Defaults raten. |
| **KYC / Bank** | kontospezifisch **offen** | Identitäts- und Auszahlungs-/Bankprüfung laufen über Seller Hub beim Kontoinhaber. Hilfeseiten zu Verifizierung/Limits waren ohne Login nicht auslesbar (Challenge-Seite). | **Steffen:** Seller-Hub-Status (Identität, Bank, Auszahlung) dokumentieren; Screenshot/Notiz reicht für Controlling. |
| **Limits** | teilweise | Privat (Hilfeseite): u. a. **320 Angebote/Monat ohne Angebotsgebühr**, danach **EUR 0,50**/Angebot (Stand Abruf). Verkaufslimits und API-Call-Limits sind **konten-/Keyset-abhängig**. | **Steffen:** aktuelle Verkaufslimits im Konto; API-Limits im Developer Portal. Keine Annahmen als Soft-Cap im Produkt hardcoden. |
| **Gebühren** | Struktur belegt; Beträge kontospezifisch | **Privat DE (Inland):** Grundaussage Hilfeseite „Verkauf … innerhalb Deutschlands kostenlos“; Zusatzoptionen/Ausland/Überkontingent können kosten. **Gewerblich:** Verkaufsprovision (%-Satz kategorieabhängig + Fixbetrag pro Bestellung) und ggf. Angebots-/Zusatzgebühren; zzgl. MwSt. laut Hilfeseite. Fee-Schätzung später über API/`getListingFees` (AP-E-04) – fehlend = „Gebühren unbekannt“, nie 0 € vortäuschen. | **Steffen:** Kontotyp bestätigen und aktuelle Rate Card für die genutzten Kategorien lesen. Keine erfundenen %-Sätze im Produkttext. |
| **Inventarstandort / Bilder** | belegt (Dok) / teilweise offen | Mindestens ein Inventory Location mit `merchantLocationKey`. Bilder müssen für eBay **abrufbare URLs** sein (lokale Pfade reichen nicht). | Bildbereitstellungsweg (AP-E-04); Sandbox darf freigegebene Testbild-URLs. |
| **Marketplace Account Deletion** | belegt (Dok) | Production: Endpoint abonnieren **oder** Opt-out, wenn keine eBay-Nutzerdaten gespeichert werden; sonst Keyset/API-Zugang gefährdet. Sandbox-Arbeit blockiert das nicht zwingend. | Production-Blocker; für SoloOffice-Selbstnutzung Opt-out vs. Endpoint entscheiden, bevor Production-Keyset. |
| **Rechtliche Pflichten DE** | bedingt / offen | Bei **gewerblichem** Verkauf typischerweise Impressum, Widerruf, Gewährleistung u. a. – schwerer als private Kleinanzeigen. Einstufung privat/gewerblich und Texte sind **Verantwortung des Kontoinhabers**, keine Produktgarantie. | **Steffen / ggf. Rechtsberatung:** Kontotyp, Pflichttexte, Rückgabepolicy-Inhalt. Studio speichert nur ausdrücklich gewählte Policy-IDs. |
| **Technikpfad** | entschieden | **Sell Inventory only** (`createOrReplaceInventoryItem` → Offer → `publishOffer`). Keine Browserautomatisierung. Trading API nur als erwähnter Legacy-Hinweis, kein zweiter MVP-Pfad. | – |

---

## Quellen (Abruf / Snapshot)

| Quelle | Was | Stand |
|---|---|---|
| [Gebühren private Verkäufer](https://www.ebay.de/help/selling/fees-credits-invoices/selling-fees?id=4822) | Inland privat „kostenlos“-Aussage; Angebotsgebühr nach Kontingent 320 / EUR 0,50; Verweis auf gewerblich | Live-Abruf **2026-09-07** |
| [Gebühren gewerbliche Verkäufer](https://www.ebay.de/help/selling/fees-credits-invoices/fees-business-sellers?id=4809) | Verkaufsprovision + Fix/Bestellung; Angebots-/Zusatzgebühren; zzgl. MwSt. | Live-Abruf **2026-09-07** |
| Inventory API Overview (developer.ebay.com) | Location, Inventory Item, Offer, **Business Policies Pflicht**, Account-/Fulfillment-Bezug, `getListingFees` | Wayback Snapshot **2025-02-11** (`20250211042629`) – Live-Portal vom Abrufrechner **403** |
| OAuth / Authorization Guide | Keysets Sandbox+Production, Scopes, Authorization-Code / Refresh | Wayback Snapshot **2026-04-17** (`20260417181547`) |
| Marketplace Account Deletion Workflow | Pflicht Subscribe oder Opt-out vor Production-Nutzung | Wayback Snapshot **2024-12-04** (`20241204091156`) |
| Feinplan | Annahmen Sell-API only, Scopes, Dry-Run vs. Sandbox vs. Prod | `controlling/EBAY-PUBLISH-PLAN-Astra.md` (2026-09-07) |
| Rechtsdossier §7 | Sell-API only; keine stille Rückgaberegel | `docs/RECHTLICHES.md` |

Hinweis: Live-`developer.ebay.com` lieferte am 2026-09-07 vom Arbeitsrechner HTTP **403**; technische API-Aussagen stützen sich deshalb auf Wayback-Snapshots der offiziellen Docs und sind bei Keyset-Anlage am Portal gegen den Live-Stand zu halten.

---

## Sandbox vs. Produktionsblocker

### Sandbox – empfohlen als nächster Schritt (kein Blocker aus dieser Matrix)

1. Entwicklerkonto + Sandbox-Keyset  
2. Sandbox-Testnutzer / Verkäuferkonto mit Policy-Opt-in und Location  
3. RuName / Redirect für OAuth (AP-E-03) – siehe `docs/EBAY-OAUTH-SANDBOX.md`  
4. Credential-Store (AP-E-02) vor echten Tokens  

### Produktion – explizit gesperrt bis

1. MAD-Endpoint oder dokumentierter Opt-out  
2. Kontonachweise: Policies, KYC/Bank, Limits, Kontotyp  
3. Gebührenanzeige mit Quelle/Zeitpunkt (nicht geraten)  
4. Zulässiger Bildweg  
5. Verkaufsabgleich AP-6.5 abgenommen  

---

## Offene Punkte für Steffen

1. Kontotyp des Zielverkäuferkontos (privat / gewerblich) – **ohne** daraus pauschal „API unmöglich“ oder „Gewerbe Pflicht“ abzuleiten.  
2. Business-Policies-Opt-in und drei Policy-IDs (zuerst Sandbox).  
3. Seller-Hub: Identität / Bank / Auszahlung.  
4. Aktuelle Verkaufslimits und relevante Gebührenzeilen der Rate Card.  
5. Sandbox-App + Redirect-URI bereitstellen (für AP-E-03).  
6. Später: Production MAD vs. Opt-out; Bild-Hosting-Entscheidung.  

---

## Bezug AP-6.1 Prüffragen

| Frage aus AP-6.1 | Erledigt? |
|---|---|
| Welches Entwicklerkonto / Freischaltung? | Ja – Developer Program; Sandbox jetzt, Production nach MAD/Opt-out |
| Grenzen? | Teilweise – Policies, Location, Bilder, Kontingente; Rest kontospezifisch offen |
| Gewerbliches Konto Voraussetzung? | **Nicht als Pflicht behauptet**; Eignung des konkreten Kontos offen |
| Widerruf / Impressum / Gewährleistung? | Bedingt am gewerblichen Verkauf; Inhalte offen / Verkäuferpflicht |
| Geschäftsbedingungen & Rückgabe hinterlegen? | Ja für Inventory-Offers (Business Policies); Auswahl ausdrücklich |
| Welche Gebühren? | Struktur aus offiziellen Hilfeseiten; konkrete Beträge für Steffen offen |

→ **AP-6.1 bleibt offen** (🟠 prüfen), bis die Steffen-Nachweise vorliegen oder bewusst als Restrisiko akzeptiert und dokumentiert sind.

## AP-E-04 Nachtrag (Standort/Bilder/Fees)

Siehe `docs/EBAY-CLIENT-DRY-RUN.md`: lokaler Dry-Run netzwerkfrei; Gebühren unbekannt vs. API-Schätzung; `merchantLocationKey`; Sandbox-Testbild-URLs; SKU-Abgleich vor Retry. Kein fingierter Validate-Endpunkt.

## Mapping (AP-E-05)

Kleine Whitelist Kategorie/Zustand/Festpreis: `docs/EBAY-MAPPING.md`.
