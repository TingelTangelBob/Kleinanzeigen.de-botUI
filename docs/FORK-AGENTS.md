# Agentenregeln dieses Forks

<!-- SPDX-License-Identifier: AGPL-3.0-or-later -->
<!-- Neue Datei des Forks. Nicht im Upstream vorhanden. -->

**Ergänzung, kein Ersatz.** Die Upstream-Fassung [`../AGENTS.md`](../AGENTS.md) gilt unverändert
weiter, insbesondere für alles unter `src/kleinanzeigen_bot/`. Bei Widerspruch gewinnt sie – außer
in den unten genannten Punkten, die es im Upstream nicht gibt.

Der Verweis steht hier statt in `AGENTS.md`, damit diese Upstream-Datei unberührt bleibt und bei
Merges keine Konflikte erzeugt.

## Erst lesen

Die Steuerdokumente liegen **außerhalb dieses Repositorys**, im übergeordneten Arbeitsordner:
`CONTEXT.md`, `EXPECTATIONS.md`, `Anzeigen-Studio-Projektplan.md`, `Upstream-Codepruefung.md`.
Sie sind bewusst nicht Teil des öffentlichen Repos.

Im Repo selbst: [`../NOTICE.md`](../NOTICE.md), [`RECHTLICHES.md`](RECHTLICHES.md),
[`UPSTREAM-SYNC.md`](UPSTREAM-SYNC.md), [`LIZENZEN.md`](LIZENZEN.md).

## Nicht verhandelbar

- **Alles Neue in neue Verzeichnisse.** `src/anzeigen_studio/`, `webui/`,
  `docker/anzeigen-studio/`. Eine Änderung an `src/kleinanzeigen_bot/` braucht eine Begründung und
  einen Eintrag in `NOTICE.md` – jede ist ein künftiger Merge-Konflikt.
- **Der Bot wird als Unterprozess aufgerufen, nicht importiert.** Der Upstream sagt Stabilität nur
  für CLI und Dateiformate zu. Importiert werden ausschließlich die Datenmodelle und Schemas.
- **Ein Browser je Profil, ein Lauf gleichzeitig.** Chromium sperrt sein Profilverzeichnis;
  parallele Sitzungen auf einem Konto fallen zudem der Plattform auf.
- **Zugangsdaten verschlüsselt.** Nie im Klartext in `config.yaml`, Logs, Screenshots oder
  Diagnoseartefakten. Das Passwort wird zur Laufzeit als Umgebungsvariable eingespeist.
- **Diese vier Konfigurationsfelder sind in der Oberfläche niemals beschreibbar:**
  `browser.binary_location`, `browser.extensions`, `browser.arguments`, `ad_files`.
  Zusammen sind sie ein Codeausführungspfad.
- **KI-Ausgaben sind Entwürfe.** Kein Weg von der Erzeugung direkt zur Veröffentlichung.
- **Das Postfach ist nur lesbar.** Kein Antworten, kein Weiterleiten, kein automatischer Versand.
  Nachrichteninhalte gehen nie an einen LLM-Anbieter.
- **Captchas werden nicht umgangen.** Bei Captcha oder Zwei-Faktor hält der Lauf an, der Mensch
  übernimmt.
- **Kein Lauf gegen ein echtes Konto** ohne ausdrückliche Freigabe des Projektinhabers.
- **Alle sichtbaren Oberflächentexte sind Deutsch.**

## Wiederverwenden statt neu bauen

Bausteine der Oberfläche stammen aus SoloOffice (AGPL-3.0-or-later, siehe `CONTEXT.md`). Vor jeder
neuen Komponente dort nachsehen. Übernommene Dateien bekommen einen Herkunftsvermerk im Kopf.

## Prüfen

```bash
docker compose build                    # enthält Lint und Typprüfung des Frontends
python3 scripts/check_spdx.py           # Lizenzkennungen der Fork-Dateien
```

Technische und manuelle Prüfung **getrennt** berichten. Ein grüner Build sagt nichts darüber, ob
ein Dialog im Viewport bleibt.
