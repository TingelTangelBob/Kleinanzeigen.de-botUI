<!--
SPDX-FileCopyrightText: © Anzeigen-Studio contributors
SPDX-License-Identifier: AGPL-3.0-or-later
-->

# Sicherung, Export und Import

Es gibt **zwei** Sicherungen, und sie sind ausdrücklich nicht dasselbe. Der
Unterschied ist wichtig, weil die eine gefahrlos weitergegeben werden kann und
die andere nicht.

| | Profilarchiv | Volumensicherung |
|---|---|---|
| Was | Anzeigen, Bilder, Vorlagen, Bot-Einstellungen eines Profils | **alles**: Datenbank, alle Profile, Browserprofile |
| Wo | Einstellungen › Bot › Sicherung | Kommandozeile auf dem Server |
| Geheimnisse | **keine** | verschlüsselte Zugangsdaten, LLM-Schlüssel, angemeldete Browsersitzungen |
| Weitergeben | unbedenklich | **niemals** |
| Wofür | Umzug, Zweitrechner, einzelne Anzeigen zurückholen | Betrieb, Wiederherstellung nach einem Ausfall |

## 1. Profilarchiv (in der Oberfläche)

Unter **Einstellungen › Bot › Sicherung** lädt „Archiv herunterladen" das
aktive Profil als ZIP herunter.

**Was mitgeht** — eine Positivliste, kein Ausschlussverfahren:

- `ads/`, `downloaded-ads/`, `fremde-ads/` mit YAML und Bildern
- `vorlagen/`
- `nutzer.yaml` (die in der Oberfläche gesetzten Bot-Einstellungen)

**Was nicht mitgeht, und warum:**

- **`.temp/browser-profile/`** — das Chromium-Profil einer *angemeldeten*
  Sitzung. Die Cookies darin sind so gut wie das Passwort. Das ist der
  wichtigste Ausschluss.
- `.temp/diagnostics/` — Bildschirmfotos und vollständiges DOM, mit Klarname,
  Adresse und Telefonnummer.
- `config.yaml` — wird vor jedem Lauf neu geschrieben.
- Protokolle.

Zugangsdaten und der LLM-Schlüssel liegen ohnehin nicht im Profilordner,
sondern verschlüsselt in der Datenbank. Sie können gar nicht hineinrutschen.

Das Archiv trägt einen Beipackzettel (`anzeigen-studio-archiv.json`), der
festhält, was drin ist und was nicht. Er ist reine Auskunft — der Import liest
keinen einzigen Wert daraus.

### Einspielen

Dreistufig, mit Absicht: **Datei wählen → Ansehen → Einspielen.** Die Vorschau
sagt vorher, wie viele Anzeigen und Bilder kommen, was neu ist, was es lokal
schon gibt und was abgewiesen wurde. Danach steht das Ergebnisprotokoll mit
denselben Zahlen.

Vorhandene Dateien werden **nicht** überschrieben, solange das Ersetzen nicht
ausdrücklich eingeschaltet wird. Der häufige Fall ist das Zurückholen einzelner
Anzeigen in einen Bestand, an dem lokal gearbeitet wurde — ein Import, der
dabei stillschweigend überschreibt, ist ein Datenverlust, den niemand bemerkt.

Ein Archiv kommt aus fremder Hand und wird wie eine Eingabe behandelt: Pfade,
die aus dem Profil herauszeigen (`../`, absolute Pfade), fremde Ordner, fremde
Dateitypen, zu große oder zu viele Einträge werden abgewiesen und benannt.

**Nicht nur der Name zählt, sondern auch der Inhalt.** `nutzer.yaml` ist die
Bot-Konfiguration; darin gibt es Felder, die einen Codeausführungspfad öffnen
(`browser.binary_location`, `browser.arguments`, `browser.extensions`,
`ad_files` — AP-1.11). Ein fremdes Archiv könnte sie mitbringen. Beim Import
läuft die Datei deshalb durch dieselbe Prüfung wie der Einstellungen-Endpunkt;
enthält sie ein gesperrtes oder unbekanntes Feld, wird sie mit Begründung
abgewiesen und **nicht** geschrieben. (Gefährlich wären die Felder ohnehin erst
beim nächsten Lauf, und dort werden sie zweimal abgestreift — die Anwendung ist
also nicht verwundbar. Eine Datei, die die Oberfläche selbst nie schreiben
würde, hat trotzdem nichts im Profil zu suchen.)

Anzeigendateien werden bewusst **nicht** inhaltlich geprüft: Eine kaputte
Anzeige erscheint in der Bestandsliste als „unlesbar", mehr kann sie nicht
anrichten — und wer eine beschädigte Anzeige zurückholt, will meist genau das.

**Größe.** Das Archiv darf bis zu 512 MB groß sein; entpackt gilt eine eigene
Grenze von 2 GB gegen Zip-Bomben. Die 512 MB stehen an zwei Stellen und müssen
zusammenpassen: `MAX_ARCHIV_BYTES` in `src/anzeigen_studio/bestand/archiv.py`
und `client_max_body_size` für `/api/archiv/` in
`docker/anzeigen-studio/nginx.conf`. Ohne den eigenen nginx-Ort griffe dort die
16-MB-Grenze der übrigen API, und der Import scheiterte an einer englischen
HTML-Fehlerseite, bevor das Backend eine deutsche Meldung erzeugen könnte.

**Der Import stellt nichts online.** Er legt Dateien ab. Was davon auf
kleinanzeigen.de geht, entscheidet weiterhin ein ausdrücklich gestarteter Lauf.

## 2. Volumensicherung (für den Betrieb)

Die Nutzdaten liegen im Docker-Volume `studio-data`, nicht im Git-Checkout.
Sie überleben jeden Neubau — aber keinen gelöschten Server.

```bash
docker run --rm \
  -v anzeigen-studio_studio-data:/data:ro \
  -v "$PWD":/sicherung \
  alpine tar czf "/sicherung/studio-data_$(date +%F).tar.gz" -C /data .
```

Zurückspielen in ein leeres Volume:

```bash
docker compose -f docker-compose.yml -f docker/anzeigen-studio/docker-compose.lan.yml down
docker run --rm \
  -v anzeigen-studio_studio-data:/data \
  -v "$PWD":/sicherung \
  alpine sh -c 'rm -rf /data/* && tar xzf /sicherung/studio-data_JJJJ-MM-TT.tar.gz -C /data'
docker compose -f docker-compose.yml -f docker/anzeigen-studio/docker-compose.lan.yml up -d
```

**Zwei Dinge, ohne die die Sicherung wertlos ist:**

1. **`ANZEIGEN_STUDIO_SECRET_KEY` gehört dazu.** Er steht in `.env` neben dem
   Compose-Stand, *nicht* im Volume. Ohne ihn sind die Zugangsdaten in der
   zurückgespielten Datenbank unentschlüsselbar — die Sicherung ist dann eine
   Sicherung ohne Anmeldung. Den Schlüssel getrennt vom Archiv aufbewahren; wer
   beides am selben Ort ablegt, hat die Verschlüsselung aufgehoben.
2. **Diese Sicherung enthält Geheimnisse.** Verschlüsselte Zugangsdaten, den
   LLM-Schlüssel und die Browserprofile angemeldeter Sitzungen. Sie gehört
   nicht in eine Cloud, in einen Chat oder in ein Ticket. Für Weitergabe ist
   das Profilarchiv aus Abschnitt 1 gedacht.

Eine Rückspielprobe — nicht behaupten, sondern vorführen — ist als AP-7.2
vorgemerkt und steht noch aus.
