# eBay OAuth Sandbox – Verdrahtung (AP-E-03)

<!-- SPDX-License-Identifier: AGPL-3.0-or-later -->
<!-- Anleitung ohne Geheimnisse. Kein Production-Connect, keine Sell-API-Aufrufe. -->

**Paket** AP-E-03 · **Stand** 2026-09-07 (UTC+2)  
**Ziel** Sandbox Authorization-Code-Flow + Refresh in den Credential-Store (AP-E-02).  
**Nicht enthalten** Production-Verbindung, Verkaufsaufrufe, Browserautomatisierung, UI (AP-E-09).

## Was Steffen im Developer Portal einrichtet

1. [developer.ebay.com](https://developer.ebay.com) → Entwicklerkonto → **Sandbox-Keyset** anlegen.  
   Notieren (nur lokal, nicht ins Repo):
   - **App ID** (Client ID)
   - **Cert ID** (Client Secret)
   - optional Dev ID
2. Unter dem Keyset **User Tokens / OAuth** die Scopes freischalten, mindestens:
   - `sell.inventory`
   - `sell.account`  
   (im Portal oft als volle URLs `https://api.ebay.com/oauth/api_scope/...` sichtbar)
3. **RuName** (Redirect URL Name) anlegen:
   - Auth Accepted URL / Redirect:  
     `https://<dein-host>/api/ebay/oauth/callback`  
     Lokal z. B. über den LAN-/HTTPS-Endpunkt, den nginx bereits ausliefert – **nicht** `localhost` im Portal, wenn eBay von außen redirecten muss; für rein lokale Tests ggf. Tunnel oder den bereits freigegebenen Host nutzen.
   - Den **RuName-String** (nicht die URL allein) merken – eBay erwartet ihn als `redirect_uri`.
4. Sandbox-**Testnutzer** (Verkäufer) anlegen und später manuell der Zustimmungsseite zustimmen.

Production-Keyset und Production-RuName **nicht** für AP-E-03 verdrahten.

## Geheimnisse außerhalb des Repos

| Wert | Wohin | Nicht |
|---|---|---|
| App ID | `.env` als `EBAY_SANDBOX_APP_ID` **oder** `PUT /api/ebay/app` | Repo, YAML, Jobs, Logs |
| Cert ID | `.env` als `EBAY_SANDBOX_CERT_ID` **oder** verschlüsselt über `PUT /api/ebay/app` | Klartext in Git |
| RuName | `.env` als `EBAY_SANDBOX_RUNAME` und/oder beim `POST /api/ebay/oauth/start` | – (kein Geheimnis, aber hostspezifisch) |
| Access/Refresh Token | nur verschlüsselt in `ebay_zugang` nach Callback/Refresh | Anzeigen-YAML, Status-JSON, Logs |

Vorlage: `.env.example` (Zeilen auskommentiert). Zusätzlich braucht das Backend weiterhin `ANZEIGEN_STUDIO_SECRET_KEY` (AES-GCM).

## Studio-Endpunkte (Sandbox)

| Methode | Pfad | Zweck |
|---|---|---|
| `GET` | `/api/ebay/status?profil=<slug>&umgebung=sandbox` | Status ohne Tokens |
| `PUT` | `/api/ebay/app?profil=…&umgebung=sandbox` | App ID + Cert ID speichern |
| `POST` | `/api/ebay/oauth/start?profil=…&umgebung=sandbox` | `authorize_url` + einmaliger `state` |
| `GET` | `/api/ebay/oauth/callback` | eBay-Redirect; öffentlich, prüft `state`↔Sitzung |
| `POST` | `/api/ebay/oauth/refresh?profil=…` | Access-Token erneuern (serialisiert) |
| `POST` | `/api/ebay/oauth/widerrufen?profil=…` | lokal „erneut verbinden“ |
| `DELETE` | `/api/ebay/verbindung?profil=…` | Zeile entfernen |

`umgebung=production` wird für Start/App/Refresh mit **409** abgewiesen.

## Manueller Sandbox-Nachweis (wenn App + RuName stehen)

1. Backend mit Secret-Key und den drei `EBAY_SANDBOX_*`-Werten starten (oder App per API setzen + RuName in Env).  
2. Anmelden → `POST /api/ebay/oauth/start?profil=<slug>`.  
3. `authorize_url` im **eigenen** Browser öffnen, als Sandbox-Testnutzer zustimmen.  
4. Redirect landet auf `/api/ebay/oauth/callback` → Tokens verschlüsselt gespeichert → Weiterleitung `#einstellungen?ebay=verbunden`.  
5. `GET /api/ebay/status` zeigt `verbunden`, Tokens nur als Booleans.  
6. Optional `POST /api/ebay/oauth/refresh` nach Ablauf des Access-Tokens.

Kein Commit von Tokens, Keysets oder RuName-Geheimdokumenten. Belege für Controlling: Status-JSON ohne Secrets, Screenshot der Portal-RuName-URL (ohne Cert ID).

## Sicherheit kurz

- `state`: kurzlebig (~10 min), einmalig, gebunden an Sitzungs-Fingerprint + Profil + Umgebung.  
- Callback in der Public-Whitelist, aber ohne gültigen `state`/Sitzung wirkungslos.  
- Refresh je Profil/Umgebung per Lock serialisiert; abgelehnter Refresh → `erneut_verbinden`.  
- HTTP-Timeout am Token-Endpunkt → fachliche 504 (in Tests mit Fake).

## Nächster Bau

AP-E-04 – eBay-Client und Dry-Run Fee/Validate (noch keine produktiven Sell-Schreiben).
