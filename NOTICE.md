# Anzeigen-Studio – Hinweise zur Herkunft

<!--
SPDX-License-Identifier: AGPL-3.0-or-later
Diese Datei ist eine Ergänzung des Forks und im Upstream nicht vorhanden.
-->

Dieses Repository ist eine **Fork-Weiterentwicklung** von
[`Second-Hand-Friends/kleinanzeigen-bot`](https://github.com/Second-Hand-Friends/kleinanzeigen-bot).
Es ist **nicht** der Upstream und wird von dessen Autoren weder betreut noch unterstützt. Fehler in
diesem Fork gehören hierher, nicht in den Upstream-Bugtracker.

## Lizenz

Das Gesamtwerk steht unter der **GNU Affero General Public License, Version 3 oder später**
(`AGPL-3.0-or-later`). Der vollständige Lizenztext liegt unverändert in
[`LICENSE.txt`](LICENSE.txt).

Einzelne Dateien tragen statt des vollen Textes die Kennung:

```text
SPDX-License-Identifier: AGPL-3.0-or-later
```

### § 13 – Netzwerkklausel

Die AGPL verpflichtet dazu, allen Nutzern, die **über ein Netzwerk** mit der Software
interagieren, den vollständigen korrespondierenden Quelltext der laufenden Fassung anzubieten –
auch ohne jede Weitergabe von Programmdateien.

Bei der ursprünglichen Kommandozeilenanwendung schlummerte diese Klausel. Die in diesem Fork
entstehende **Weboberfläche ist genau ihr Auslöser**. Sobald jemand außer dem Betreiber selbst die
Oberfläche erreicht, muss der Quelltext dieser Fassung erreichbar sein – einschließlich aller
Erweiterungen dieses Forks. Verschärfend kommt hinzu, dass die Browser-Bibliothek `nodriver` selbst
unter AGPL-3.0 steht; ein Ausweichen durch Neuschreiben des Bot-Codes gibt es also nicht.

## Herkünfte

| Quelle | Lizenz | Übernommen wird |
|---|---|---|
| [`Second-Hand-Friends/kleinanzeigen-bot`](https://github.com/Second-Hand-Friends/kleinanzeigen-bot) | AGPL-3.0-or-later | die vollständige Bot-Logik unter `src/kleinanzeigen_bot/`, die JSON-Schemas, die Kategoriendaten und die Werkzeugkette |
| SoloOffice | AGPL-3.0-or-later | Bausteine der Weboberfläche: App-Schale, Dialogverhalten, Designsystem, Formular- und Tabellenlogik |
| Eigene Beiträge | AGPL-3.0-or-later | Backend, Job-Verwaltung, Profilverwaltung, KI-Entwurfsmodul, Nachrichtenansicht |

Die ursprünglichen Copyright-Vermerke bleiben erhalten. Der Upstream-Quelltext trägt
`© Jens Bergmann and contributors` sowie `© Sebastian Thomschke and contributors`.

SoloOffice ist seinerseits eine Fork-Weiterentwicklung der AGPL-lizenzierten Codebasis von Belego;
dessen Copyright-Vermerk `Belego Contributors` bleibt in übernommenen Dateien ebenfalls stehen.

Copyright © 2026 Anzeigen-Studio Contributors für die eigenen Beiträge dieser Fork-Weiterentwicklung.

## Verhältnis zum Upstream

Der Upstream erklärt sich ausdrücklich zur **reinen Kommandozeilenanwendung** und sagt Stabilität
nur für CLI-Befehle, Optionen, Exit-Verhalten und Dateiformate zu; interne Importpfade dürfen
jederzeit brechen (`AGENTS.md` im Upstream). Dieser Fork richtet sich danach: Er ruft den Bot als
**Unterprozess über die Kommandozeile** auf und importiert aus dem Upstream nur die Datenmodelle
und Schemas, die Teil des zugesagten Dateiformat-Vertrags sind.

Allgemein nützliche Verbesserungen werden als Pull Request an den Upstream zurückgegeben, statt sie
hier liegen zu lassen. Der Upstream verlangt kein CLA, sondern nur eine Lizenzbestätigung.

## Geänderte Upstream-Dateien

Nach AGPL § 5 a trägt jede geänderte Datei einen deutlich sichtbaren, datierten Änderungshinweis.
Diese Liste wird bei jeder Änderung fortgeschrieben.

| Datei | Datum | Änderung |
|---|---|---|
| `.gitignore` | 2026-08-22 | Additiver Abschnitt am Dateiende für die neuen Verzeichnisse `src/anzeigen_studio/` und `webui/` sowie für Laufzeitdaten. Bestehende Regeln unverändert. |
| `README.md` | 2026-08-22 | Fork-Hinweis am Dateianfang vorangestellt. Übriger Inhalt unverändert. |

**Neue Dateien** dieses Forks stehen nicht in dieser Liste – sie sind keine Änderungen an fremdem
Werk. Sie tragen die SPDX-Kennung und sind an ihrer Lage erkennbar: `src/anzeigen_studio/`,
`webui/`, `NOTICE.md` sowie die Fork-eigenen Dokumente unter `docs/`.

## Abhängigkeiten und deren Lizenzen

Die vollständige Aufstellung der Laufzeitabhängigkeiten steht in
[`docs/LIZENZEN.md`](docs/LIZENZEN.md). Sie ist Teil der Sorgfaltspflicht: Eine Abhängigkeit unter
einer AGPL-unverträglichen Lizenz würde das Gesamtwerk unverteilbar machen.
