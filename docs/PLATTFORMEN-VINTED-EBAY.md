<!-- SPDX-License-Identifier: AGPL-3.0-or-later -->
# Weitere Plattformen: eBay.de und Vinted – und parallel veröffentlichen

Stand 2026-09-30 · Claude. Recherche, keine Umsetzung. Kein Konto wurde angefasst.

## Kurzfassung

| Plattform | Offizieller Weg | Für einen **privaten** Verkäufer nutzbar? | Empfehlung |
|---|---|---|---|
| Kleinanzeigen | kein API; Bot über Browser (Upstream) | ja – bereits im Betrieb | bleibt Leitplattform |
| eBay.de | Sell-API (Inventory, Account, Fulfillment) mit OAuth | ja, nach Entwicklerkonto und Freischaltung – kontospezifisch offen, siehe `EBAY-MACHBARKEIT.md` | weiterbauen wie geplant (AP-E-06 …) |
| Vinted | **Vinted Pro Integrations** – nur für gewerbliche Pro-Konten auf Freigabeliste | **nein**. Für Privatkonten gibt es keine offizielle Schnittstelle; Automatisierung verbieten die AGB, und Vinted setzt Bot-Erkennung ein | **Vinted-Übergabe** (Text und Fotos fertig vorbereitet, Einstellen per Hand), API erst mit Pro-Konto |

**Parallel veröffentlichen ist machbar**, aber nicht als „ein Knopf, alles gleichzeitig". Der richtige
Zuschnitt: eine Anzeige, je Plattform ein eigener Veröffentlichungsauftrag mit eigenem Status, und
ein Abgleich, der nach einem Verkauf die anderen Plattformen beendet. Dieser Abgleich (AP-6.5) ist
der eigentlich schwere Teil – ohne ihn verkauft man denselben Gegenstand zweimal.

## eBay.de

Bereits entschieden (2026-09-04) und fein geplant in `controlling/EBAY-PUBLISH-PLAN-Astra.md`
(Steuerordner außerhalb dieses Repositorys). Umgesetzt
und in Prüfung: Machbarkeit (E-01), verschlüsselter Token-Speicher (E-02), OAuth für die Sandbox
(E-03), Client mit Probelauf (E-04), Feldabbildung (E-05).

Was vor der ersten echten eBay-Anzeige fehlt, in dieser Reihenfolge:

1. **Kontonachweise des Inhabers** (AP-6.1): Kontotyp, Business Policies im Seller Hub angelegt,
   Verifizierung und Bankverbindung, Verkaufslimits. Das kann keine Software erledigen.
2. **Sandbox-App mit Callback-Adresse** (RuName) – Vorbedingung für den ersten echten
   Verbindungsnachweis aus E-03.
3. **Bildweg**: eBay verlangt abrufbare Bild-URLs. Die Anwendung ist bewusst nicht aus dem Netz
   erreichbar. Lösung ohne Öffnung: Bilder vorher über eine Bild-Upload-Schnittstelle von eBay
   hochladen und die zurückgegebenen URLs verwenden (Commerce Media API bzw.
   `UploadSiteHostedPictures`; welche für ein deutsches Privatkonto greift, ist noch zu prüfen).
   Offen in E-04.
4. **Pakete E-06 bis E-12** (Policies wählen, Job `ebay_publish`, Editor-Schalter „auch eBay",
   Einstellungen, Plattformkennungen im Bestand, Gebührenhinweise, Sandbox-Abnahme).
5. **AP-6.5 Verkaufsabgleich** als Voraussetzung für den Produktivbetrieb.

## Vinted

### Was es offiziell gibt

**Vinted Pro Integrations** ([Doku](https://pro-docs.svc.vinted.com/)) ist eine echte Schnittstelle:
Artikel anlegen, ändern und löschen in Stapeln bis 100, Webhook `ITEM_SOLD`, Bestellungen und
Versandetiketten. Deutschland ist unterstützt. Aber:

- nur für **freigeschaltete Vinted-Pro-Unternehmen** (Freigabeliste, Zugang über das Pro-Portal);
- Vinted Pro setzt ein **Gewerbe** voraus (Gewerbeanmeldung oder Handelsregister, Steuernummer,
  Geschäftskonto, Impressum);
- zu Beginn höchstens **500 aktive Artikel** je API-Zugang;
- Fotos als **öffentlich abrufbare URLs** – dasselbe Bildproblem wie bei eBay, nur ohne eigenen
  Upload-Endpunkt.

### Was es für Privatkonten nicht gibt

Keine offizielle API. Die Werkzeuge, die im Netz als „Vinted-API" kursieren, sprechen die interne
Schnittstelle der Website mit einer Browsersitzung an. Das verstößt gegen die
Nutzungsbedingungen, Vinted arbeitet mit dem Bot-Schutz DataDome und sperrt seit 2025 auch Konten,
die in kurzer Folge gleiche Bilder einstellen. Ein Browser-Bot wie für Kleinanzeigen würde genau
das tun, was dieses Projekt ausschließt: Bot-Erkennung umgehen (siehe `CONTEXT.md`, Rechtliche
Rahmenbedingungen). **Deshalb keine Vinted-Automatisierung für Privatkonten.**

### Was trotzdem hilft: die Vinted-Übergabe

Der aufwendige Teil beim Einstellen ist Text, Kategorie, Zustand und Fotoauswahl – und genau das
liegt im Studio schon vor. Vorschlag für ein kleines, sauberes Paket:

- Im Editor ein Knopf **„Für Vinted vorbereiten"**: Titel (Vinted: 5–100 Zeichen), Beschreibung
  (bis 2000), Preis, Zustand in Vinted-Stufen, Marke und Größe als eigene Felder, Fotos als ZIP
  in Vinted-Reihenfolge.
- Kopieren-Knöpfe je Feld und ein Link, der die Vinted-Seite „Artikel verkaufen" öffnet. Das
  Ausfüllen und Absenden macht der Mensch.
- In der Anzeige wird „auf Vinted eingestellt am …" vermerkt, damit der Verkaufsabgleich weiß,
  wo der Gegenstand noch steht. Das Beenden auf Vinted bleibt Handarbeit, wird aber als offene
  Aufgabe in der Glocke gemeldet.

Mit einem Pro-Konto wird daraus später ein echter Plattform-Adapter nach demselben Muster wie eBay.

## Parallel auf mehreren Plattformen veröffentlichen

### Zuschnitt

- **Eine Anzeige im Bestand, mehrere Plattform-Zuordnungen.** Je Plattform eigene Kennung, eigener
  Status (`nicht verknüpft`, `veröffentlicht`, `Fehler`, `unklar`, `verkauft`, `beendet`) und eigene
  Wiederholung. Die Datenhaltung dafür ist AP-E-10; Vinted und weitere Plattformen hängen sich dort
  an, statt eigene Nebenablagen zu bekommen.
- **Je Plattform ein eigener Job.** Kleinanzeigen läuft wie heute über den Bot (ein Browser je
  Profil, ein Lauf zur Zeit). eBay braucht keinen Browser und darf daneben laufen. Ein Fehler auf
  eBay macht den Kleinanzeigen-Erfolg nicht rückgängig und löst dort nichts aus.
- **Eine Bestätigung, die alle Ziele nennt.** Der Dialog vor dem Hochladen zeigt, welche Plattformen
  angesprochen werden, und nur die angehakten laufen. Standard bleibt: nur Kleinanzeigen.
- **Plattformgerechte Texte.** Titel- und Beschreibungsgrenzen unterscheiden sich. Die KI kann je
  Plattform eine Fassung vorschlagen; der Mensch prüft sie wie heute.

### Der schwere Teil: Verkauf auf einer Plattform

| Plattform | Wie erfährt das Studio vom Verkauf? |
|---|---|
| eBay | Fulfillment-API (Bestellungen) – zuverlässig, abrufbar |
| Kleinanzeigen | kein Verkaufsereignis. Nur „Anzeige ist weg" aus dem täglichen Abgleich (AP-3.12) oder die Meldung des Menschen „verkauft" |
| Vinted (privat) | gar nicht automatisch – Meldung des Menschen |

Daraus folgt: **Nach einem Verkauf beendet das Studio die anderen Angebote nicht still, sondern
schlägt es vor** und führt es nach Bestätigung aus (eBay per API, Kleinanzeigen per Bot-Löschen aus
AP-3.13, Vinted als Aufgabe für den Menschen). Zwischen Verkauf und Beenden bleibt ein Zeitfenster,
in dem doppelt verkauft werden kann. Das lässt sich verkleinern, nicht ausschließen – die
Oberfläche muss das sagen.

## Vorgeschlagene Pakete (noch nicht im Plan, Entscheidung des Inhabers)

| ID | Paket | Grad | Vorbedingung |
|---|---|:--:|---|
| AP-P-01 | Plattform-Zuordnungen je Anzeige (Datenmodell für alle Plattformen, erweitert AP-E-10) | S3 | AP-E-10 |
| AP-P-02 | Hochladen-Dialog mit Plattformwahl, getrennte Jobs je Plattform | S3 | AP-P-01, AP-E-07 |
| AP-P-03 | „Verkauft"-Meldung und bestätigtes Beenden auf den anderen Plattformen | S4 | AP-P-01, AP-6.5, AP-3.13 |
| AP-V-01 | Vinted-Übergabe: Felder, Kopieren, Foto-ZIP, Vermerk | S2 | – |
| AP-V-02 | Vinted-Pro-Adapter (nur mit Pro-Konto und Freischaltung) | S4 | Entscheidung Gewerbe, AP-P-01 |

## Quellen

- Vinted Pro Integrations, Dokumentation: <https://pro-docs.svc.vinted.com/> (abgerufen 2026-09-30)
- Vinted Pro in Deutschland, Voraussetzungen (Sekundärquelle):
  <https://fripio.app/de/blog/vinted-pro-gewerblich>
- Automatisierung und Kontosperren bei Vinted (Sekundärquellen, AGB-Wortlaut noch nicht selbst
  zitiert – vor einer Entscheidung nachholen): <https://www.redrip.app/en/blog/automate-vinted-legal/>,
  <https://www.vintagelab.org/blog/vinted-bot-legal-erlaubt>
- eBay: `docs/EBAY-MACHBARKEIT.md`, `docs/RECHTLICHES.md` §7
