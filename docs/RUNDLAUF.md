<!--
SPDX-FileCopyrightText: © Anzeigen-Studio contributors
SPDX-ArtifactOfProjectHomePage: https://github.com/TingelTangelBob/Kleinanzeigen.de-botUI/
SPDX-License-Identifier: AGPL-3.0-or-later
-->

# Rundlauf: was Herunterladen und Hochladen erhalten

**Arbeitspaket AP-3.4 · Stand 2026-08-24**

„Heruntergeladene Anzeigen lassen sich wieder hochladen" ist eine Zusage. Dieses Dokument prüft
sie, Feld für Feld, und benennt was dabei verloren geht. Die Hinweistexte der Oberfläche leiten
sich daraus ab — ein Verlust, den nur die Dokumentation kennt, ist keiner, den der Nutzer kennt.

## 1. Womit geprüft wurde

Acht eigene Anzeigen eines echten Kontos, heruntergeladen am 23. und 24.08.2026:

| Anzeige | Art | Kategorie | Sonderfelder | Versand | Bilder |
|---|---|---|---|---|---|
| iMac 21,5" | OFFER | 161/228 | 1 | Hermes_L, 9,90 € | 4 |
| Wi-Fi Smart Switch | OFFER | 161/168 | 0 | Hermes_Päckchen, 0,49 € | 2 |
| 1CH Wi-Fi Dimmer | OFFER | 161/168 | 0 | **kein Paket**, 3,00 € | 3 |
| LAN Karte | OFFER | 161/225/netzwerk_modem | 2 | Hermes_Päckchen, 0,49 € | 4 |
| Junge Familie sucht Haus | **WANTED** | 195/208 | 3 | keiner | 1 |
| MacBook Pro 2015 | OFFER | 161/278/laptop | **11** | Hermes_M, 1,49 € | 5 |
| Dyson Airwrap | OFFER | 153/224/haarpflege | 1 | Hermes_Päckchen, 0,49 € | **9** |
| Logitech Webcam | OFFER | 161/225/sonstiges | 2 | Hermes_Päckchen, 0,49 € | 1 |

Damit sind die Fälle abgedeckt, die der Plan verlangt: mehr als drei Anzeigentypen, Suchanzeige
neben Angeboten, Sonderfelder von null bis elf, Bildzahl von eins bis neun, alle drei
Versandvarianten.

## 2. Wie geprüft wurde — und was daran offen bleibt

Verglichen werden drei Stände: was die Plattform zeigt, was in der YAML landet, und was ein
Hochladen zurückschreibt.

Die ersten beiden sind **beobachtet** — an den acht Anzeigen oben. Der dritte ist **aus dem
Quelltext abgeleitet** (`publishing_form.py`, `publishing_submission.py`,
`publishing_workflow.py`), denn Wieder-Hochladen ist noch nicht gebaut (AP-3.3). Diese Spalte ist
damit begründet, nicht bewiesen. Sie gehört wiederholt, sobald AP-3.3 steht — dann an einer
Wegwerf-Anzeige, nicht am Bestand.

## 3. Plattform → lokale Kopie

### Was ankommt

| Feld | Herkunft | Anmerkung |
|---|---|---|
| Titel, Beschreibung | Anzeigenseite | Beschreibung ohne den konfigurierten Vor-/Nachspann |
| Kategorie | Anzeigenseite | als ID-Pfad, z. B. `161/278/laptop` |
| Sonderfelder | Anzeigenseite | kategorieabhängig, bis 11 beobachtet |
| Preis, Preistyp | Anzeigenseite | FIXED / NEGOTIABLE / GIVE_AWAY |
| Versandart, Versandkosten | Anzeigenseite | |
| Versandpaket | **abgeleitet** | über Preisgleichheit, siehe § 5 |
| Direkt kaufen | `buyNowEligible` | |
| Bilder | Anzeigenseite | als Dateien, Reihenfolge der Seite |
| Kontakt | Anzeigenseite | Name, PLZ, Ort; Straße und Telefon nur wenn vorhanden |
| Anzeigen-ID | URL | |
| Erstelldatum | Anzeigenseite | **nur das Datum**, Uhrzeit wird auf 00:00 gesetzt |
| Aktiv ja/nein | Profilübersicht | `state == "active"` |

### Was nicht ankommt

| Verloren | Warum das zählt |
|---|---|
| **Aufrufe** | Bei der Dimmer-Anzeige 22. Nach einem Neuveröffentlichen steht dort 0. |
| **Merker / Beobachter** | dito |
| **Anzeigenalter, „Aktiv seit"** | Bestimmt die Position in Suchergebnissen mit |
| **Restlaufzeit / Ablaufdatum** | Der Bot rechnet Verlängerungen selbst, aber der Stand der Plattform ist weg |
| **Reserviert-/Verkauft-Kennzeichnung** | Im Quelltext kommt „reserved" nicht vor |
| **Bezahlte Zusatzoptionen** | Hervorhebung, Top-Anzeige, Galerie — nicht gelesen, also auch nicht wiederherstellbar |
| **Genauer Zustand jenseits von aktiv** | Pausiert, in Prüfung, gelöscht fallen alle auf `active: false` zusammen |
| **Nachrichten und Anfragen** | Gehören zur Anzeige, nicht zur Anzeigendatei |
| **Uhrzeit der Veröffentlichung** | Nur das Datum wird übernommen |

Diese Felder gehören der Plattform. Sie sind nicht „vergessen worden" — sie lassen sich durch
Hochladen grundsätzlich nicht wiederherstellen. Genau deshalb muss die Oberfläche sie benennen,
bevor jemand eine laufende Anzeige ersetzt.

## 4. Lokale Kopie → Plattform

Der Bot kennt zwei Wege zurück, und der Unterschied ist der wichtigste Satz dieses Dokuments:

| | `update` (MODIFY) | `publish` (REPLACE) |
|---|---|---|
| Weg | bearbeitet die bestehende Anzeige | löscht die alte, stellt eine neue ein |
| Anzeigen-ID | **bleibt** | **neu** |
| Aufrufe, Merker, Alter | **bleiben** | **auf null** |
| Position im Suchergebnis | bleibt | beginnt von vorn |
| Wann nötig | Anzeige existiert noch | Anzeige ist gelöscht oder abgelaufen |

Belegt in `publishing_workflow.py:131-161`: REPLACE ruft `delete_old_ad_if_needed` und öffnet das
Aufgabeformular; MODIFY öffnet `p-anzeige-bearbeiten.html?adId=…`.

**Folge für AP-3.3:** Wieder-Hochladen muss standardmäßig bearbeiten, nicht ersetzen. Ersetzen ist
der Sonderfall, und er kostet sichtbar etwas.

Zurückgeschrieben werden Titel, Beschreibung, Kategorie, Sonderfelder, Preis und Preistyp,
Versand, Direkt-kaufen, Bilder (in der Reihenfolge der Liste) und die Kontaktfelder. Rein lokale
Felder — `auto_price_reduction`, `republication_interval`, `repost_count`,
`price_reduction_count`, `content_hash` — bleiben, wo sie sind: Sie beschreiben die Automatik
dieses Werkzeugs, nicht die Anzeige.

## 5. Drei bekannte Brüche

**a) Eigene Versandkosten kommen nicht zurück.** Eine Anzeige mit frei gesetztem Versandpreis statt
eines Kleinanzeigen-Pakets lässt sich lesen, aber nicht wieder einstellen: Der Upstream hat
individuelle Versandkosten im Formular ausgebaut (`publishing_form.py:674-680`, „Individual
shipping is no longer supported"). Betroffen im Bestand: 1 von 8.

**b) Die Paketzuordnung hängt am Tagespreis.** Der Download sucht zum angezeigten Versandpreis ein
Paket mit **exakt demselben Betrag** (`extract.py:989`). Der Katalog steht derzeit auf
Aktionspreisen — Hermes Päckchen 0,49 € statt regulär 3,99 €. Genau diese 0,49 € stehen in vier
der acht Anzeigen. Ändert Kleinanzeigen die Preise zurück, findet der Download für sie kein Paket
mehr, und aus vier lesbaren Anzeigen werden vier mit unvollständigem Versand. Nichts an den
Anzeigen selbst muss sich dafür ändern.

**c) Ein erneuter Download überschreibt lokale Änderungen.** `preserve_local_settings` ist
standardmäßig an, rettet aber **nur** die vier Automatikfelder aus § 4
(`extract.py:347-400`). Wer im Studio den Text ändert und danach herunterlädt, verliert die
Änderung — der Stand der Plattform gewinnt. Das ist für ein Kommandozeilenwerkzeug vertretbar und
für einen Anzeigeneditor nicht. Gehört vor AP-2.5 entschieden.

## 6. Was die Oberfläche sagen muss

Abgeleitete Hinweistexte, wörtlich zu verwenden:

**Vor dem Ersetzen einer laufenden Anzeige:**

> Diese Anzeige wird gelöscht und neu eingestellt. Aufrufe, Merker und das Anzeigenalter beginnen
> damit bei null, und die Anzeige bekommt eine neue Nummer. Wenn die Anzeige noch online ist,
> bearbeite sie stattdessen — dann bleibt all das erhalten.

**Bei einer Anzeige mit eigenen Versandkosten:**

> Diese Anzeige hat einen selbst gesetzten Versandpreis (3,00 €) statt eines
> Kleinanzeigen-Pakets. Sie lässt sich derzeit nicht hochladen: Der Bot kann im Formular nur
> vordefinierte Pakete auswählen.

**Bei fehlendem Versandpaket nach dem Herunterladen:**

> Der Versandpreis ließ sich keinem Paket zuordnen. Die Anzeige ist vollständig gespeichert, beim
> Hochladen fehlt aber die Versandangabe.

**Vor einem erneuten Herunterladen mit lokalen Änderungen:**

> Beim Herunterladen wird der Stand der Plattform übernommen. Deine lokalen Änderungen an dieser
> Anzeige gehen dabei verloren.

## 7. Offen

- Die Spalte „Hochladen" ist abgeleitet, nicht beobachtet. Wiederholung mit AP-3.3 an einer
  Wegwerf-Anzeige.
- Ob die Bildreihenfolge nach dem Hochladen wirklich der Liste entspricht, ist ungeprüft. Die
  Codeprüfung hatte genau hier ein Fragezeichen gesetzt.
- Ob Sonderfelder vollständig zurückgeschrieben werden, ist an der Anzeige mit elf Feldern zu
  prüfen — das ist der harte Fall.
- Bruch (c) braucht eine Entscheidung, keine Untersuchung.
