# Rechtlicher Rahmen

<!-- SPDX-License-Identifier: AGPL-3.0-or-later -->
<!-- Neue Datei des Forks. Nicht im Upstream vorhanden. -->

Arbeitspaket AP-0.4. **Keine Rechtsberatung.** Dieses Dokument hält fest, was geprüft wurde, was
daraus für das Produkt folgt und wo Unsicherheit bleibt – damit diese Fragen nicht in jeder
Diskussion neu erfunden werden.

**Stand:** 2026-08-22

---

## 1. Lizenz – geklärt

Siehe [`../NOTICE.md`](../NOTICE.md) und [`LIZENZEN.md`](LIZENZEN.md).

Kurz: Das Gesamtwerk ist AGPL-3.0-or-later. Alle 30 Laufzeitabhängigkeiten sind verträglich.
Private Nutzung löst keine Pflichten aus. Sobald jemand außer dem Betreiber die Oberfläche über
ein Netz benutzt, greift § 13 – Quelltext der laufenden Fassung anbieten. Ein geschlossenes
Produkt auf dieser Basis ist ausgeschlossen; `nodriver` ist selbst AGPL, ein Ausweichen durch
Neuschreiben gibt es nicht.

**Produktentscheidung:** Repository ist öffentlich. § 13 wird über AP-7.6 umgesetzt – Verweis auf
den Quelltext mit Commit-Kennung in der Oberfläche, beim Bauen eingesetzt statt von Hand gepflegt.

---

## 2. Nutzungsbedingungen von kleinanzeigen.de – teilweise offen

### Was belegt ist

Die **`robots.txt`** von `www.kleinanzeigen.de` wurde am 2026-08-22 abgerufen (HTTP 200, 399
Zeilen). Sie sperrt unter anderem:

```text
Disallow: /messages/
Disallow: /m-nachrichten.html
Disallow: /ad/
Disallow: /m-einstellungen.html
Disallow: /m-anzeige-loeschen.html
Disallow: /m-anzeige-pausieren.html
Disallow: /m-anzeige-verlaengern-mail.html
Disallow: /m-merkliste.html
Disallow: /m-verifikation.html
```

Das ist ein **belegter Befund mit unmittelbarer Produktrelevanz**: Die für Phase 5
(Nachrichtenansicht) nötigen Pfade sind ausdrücklich gesperrt, ebenso mehrere Pfade der
Anzeigenverwaltung.

**Einordnung, ohne zu beschönigen und ohne zu dramatisieren:** `robots.txt` richtet sich an
Suchmaschinen-Crawler und ist kein Vertrag. Sie ist in Deutschland nicht unmittelbar
rechtsverbindlich. Sie ist aber ein **dokumentierter, unmissverständlicher Wille des Betreibers**,
dass diese Bereiche nicht automatisiert abgerufen werden. Wer das ignoriert, kann sich nicht darauf
berufen, es nicht gewusst zu haben. Für die Bewertung von Phase 5 ist das das stärkste
Einzelargument, das wir bisher haben.

### Was nicht geprüft werden konnte

Die Nutzungsbedingungen selbst (`https://themen.kleinanzeigen.de/nutzungsbedingungen/`) waren
**maschinell nicht abrufbar** – zwei Abrufversuche liefen in eine Zeitüberschreitung, vermutlich
durch Bot-Abwehr. Damit sind **nicht** belegt:

- ob und mit welchem Wortlaut die AGB automatisierten Zugriff untersagen
- die zugehörigen Abschnittsnummern
- Regelungen zu mehreren Konten
- die Abgrenzung privat/gewerblich
- der Stand der AGB

**Offene Aufgabe:** Der Projektinhaber ruft die Seite im Browser auf, kopiert die einschlägigen
Absätze hier herein und ergänzt Abschnittsnummer und Datum. Bis dahin gilt dieser Punkt als
**ungeklärt** und darf nicht als geklärt dargestellt werden.

Was der Upstream selbst sagt, ist dagegen belegt – seine README enthält den Hinweis, die Nutzung
könne gegen die jeweils geltenden AGB verstoßen und die Verantwortung liege beim Nutzer.

### Produktentscheidungen daraus

1. **Der Hinweis bleibt sichtbar in der Oberfläche.** Nicht im Kleingedruckten. Eine Oberfläche
   senkt die Hemmschwelle gegenüber einer Kommandozeile – der Hinweis muss dort stehen, wo
   gehandelt wird.
2. **Keine überhöhten Frequenzen.** Die Humanisierung des Bots bleibt eingeschaltet, die
   Zeitgrenzen werden nicht heruntergesetzt.
3. **Eine Sitzung je Konto.** Die Warteschlange serialisiert je Profil – auch aus technischen
   Gründen, aber hier zählt der zweite Grund: parallele Sitzungen auf einem Konto fallen auf.
4. **Keine Preisrecherche durch Abfragen fremder Anzeigen.** Zusätzliche Last für einen Nebenzweck.
5. **Phase 5 steht unter Vorbehalt.** Der `robots.txt`-Befund ist in AP-5.1 (Machbarkeitsprüfung)
   als Entscheidungsgrundlage aufzunehmen. Es ist eine bewusste Entscheidung des Projektinhabers,
   ob Phase 5 trotzdem gebaut wird – keine, die stillschweigend im Code getroffen wird.

---

## 3. Captchas und Bot-Erkennung – entschieden

**Es werden keine Captchas automatisch gelöst und keine Bot-Erkennung umgangen.** Das ist eine
gesetzte Grenze dieses Projekts, keine Verhandlungsposition.

Erkennt der Bot ein Captcha oder eine SMS-/E-Mail-Prüfung, hält der Lauf an, und der Mensch
übernimmt in der eingebetteten Browsersicht (AP-1.8). Captcha-Lösungsdienste werden nicht
eingebunden.

Begründung: Ein Captcha ist eine ausdrückliche technische Zugangsbeschränkung. Sie zu umgehen ist
qualitativ etwas anderes, als die eigene Bedienung zu automatisieren – auch strafrechtlich
(§ 202a StGB, Ausspähen von Daten, setzt eine Überwindung von Zugangssicherungen voraus). Diese
Linie ist billig einzuhalten und teuer zu überschreiten.

---

## 4. Fremde personenbezogene Daten – Regeln stehen, Bewertung offen

Nachrichten enthalten Namen, Kaufinteressen und Gesprächsinhalte Dritter, die dem Verkäufer
geschrieben haben.

**Produktentscheidungen:**

- Nachrichten bleiben **lokal**. Kein Versand an Dritte.
- Nachrichteninhalte gehen **nie** an einen LLM-Anbieter. Harte Grenze im Code, keine Konvention.
- **Aufbewahrungsfrist** einstellbar, Vorschlag 90 Tage, mit tatsächlicher Löschung (AP-5.4).
- Beim Löschen eines Profils gehen dessen Nachrichten mit.
- Der Export nimmt Nachrichten nicht mit, außer sie werden ausdrücklich ausgewählt.
- **Nur lesen.** Kein Antworten, kein Weiterleiten, kein automatischer Versand.

**Offen und juristisch zu prüfen, falls gewerblich genutzt:** Rechtsgrundlage nach Art. 6 DSGVO,
Informationspflichten, Betroffenenrechte, Verzeichnis von Verarbeitungstätigkeiten. Bei rein
privater Nutzung greift die Haushaltsausnahme (Art. 2 Abs. 2 lit. c DSGVO) – **ob sie greift, hängt
an der tatsächlichen Nutzung und ist hier nicht bewertet.**

---

## 5. Datenabfluss an LLM-Anbieter – Regeln stehen

Fotos und Texte, die zur Entwurfserstellung an einen Anbieter gehen, verlassen das System.

Fotos von Verkaufsgegenständen zeigen oft mehr als den Gegenstand: Wohnung, Kennzeichen, Dokumente
im Hintergrund, andere Personen. **EXIF-Daten enthalten regelmäßig GPS-Koordinaten** – ein Foto aus
der eigenen Wohnung trägt sonst die Adresse mit.

**Produktentscheidungen (AP-4.7):**

- Bilder werden vor dem Versand verkleinert und **von Metadaten befreit**, GPS zwingend.
- Vor dem allerersten Versand ein deutlicher, einmalig zu bestätigender Hinweis, welcher Anbieter
  welche Daten erhält.
- Nachrichteninhalte gehen nie mit.
- Der Nachweis erfolgt am **tatsächlich verschickten Datenstrom**, nicht an der Absicht.

---

## 6. Marke – Regel steht

„Kleinanzeigen" ist eine geschützte Marke der Kleinanzeigen GmbH.

- Logo, Wortmarke und Schriftzug werden **nicht** übernommen.
- Die Oberfläche darf sich gestalterisch anlehnen, aber keine Zugehörigkeit vortäuschen.
- Beschreibende Nutzung im Repositorynamen folgt dem Präzedenzfall des Upstreams, der selbst
  `kleinanzeigen-bot` heißt.
- Der endgültige Produktname ist **Entscheidung 1** im Projektplan und noch offen.

---

## 7. eBay.de – nicht begonnen

Seit der Abspaltung eine eigenständige Plattform mit eigenem Regelwerk.

- Vorgesehen ist **ausschließlich** die offizielle Sell-API. Keine Browserautomatisierung.
- Gewerbliches Einstellen zieht Pflichten nach sich, die bei privaten Kleinanzeigen nicht
  bestehen: Widerrufsrecht, Impressumspflicht, Gewährleistung, hinterlegte Rückgaberegeln.
- Eine geratene Rückgaberegel ist eine rechtliche Zusage – deshalb in AP-6.3 **keine stille
  Vorbelegung**, sondern ein sichtbares Pflichtfeld.

Vollständige Prüfung ist AP-6.1 und noch nicht erfolgt.

---

## Zusammenfassung des Prüfstands

| Punkt | Stand |
|---|---|
| Lizenz und Abhängigkeiten | **geklärt und belegt** |
| `robots.txt` | **geprüft, belegt** – sperrt Nachrichten- und Verwaltungspfade |
| AGB im Wortlaut | **offen** – maschinell nicht abrufbar, vom Projektinhaber nachzutragen |
| Captcha-Haltung | **entschieden** |
| Umgang mit Nachrichtendaten | **Regeln stehen**, DSGVO-Bewertung bei gewerblicher Nutzung offen |
| LLM-Datenabfluss | **Regeln stehen** |
| Marke | **Regel steht**, Produktname offen |
| eBay | **nicht begonnen** |
