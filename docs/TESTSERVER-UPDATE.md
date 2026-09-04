# SPDX-FileCopyrightText: © Anzeigen-Studio contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
#

# Testserver aktualisieren

Für den ausdrücklich freigegebenen Anzeigen-Studio-LAN-Testserver gibt es
einen gebündelten Ablauf:

```bash
./scripts/aktualisiere_testserver.sh --pruefen
```

Das Skript überträgt den aktuellen Arbeitsstand nach
`/opt/studio-wip`, baut Backend und Weboberfläche, führt die Frontend-Prüfungen
im Webimage aus, prüft mit `--pruefen` zusätzlich Ruff, Mypy, SPDX und
`tests_studio`, startet danach den LAN-Stack und wartet auf HTTP 200 an Port
8080.

Mypy läuft dabei seit dem 2026-09-04 gegen `docker/anzeigen-studio/mypy.ini` —
dieselbe Konfiguration wie im Projekt. Davor stand dort `--config-file
/dev/null` mit einer eigenen Befehlszeile: Der Server prüfte nach anderen
Regeln als das Projekt und übersah unter anderem `tests_studio` vollständig.

## Was dort gerade läuft: `BUILD_STAND`

Das Zielverzeichnis ist ein Git-Checkout, aber ausgeliefert wird per
tar-Overlay. Nach jeder Auslieferung meldet `git status` dort deshalb
Änderungen, die niemand committet hat — der laufende Stand ist aus dem Checkout
**nicht** ablesbar.

Das Skript schreibt darum bei jeder Auslieferung `/opt/studio-wip/BUILD_STAND`
mit Zeitpunkt, Commit, Zweig und der Anzahl ungespeicherter Dateien (dasselbe
Verfahren wie `BUILD_COMMIT` in SoloOffice):

```bash
ssh -i ~/.ssh/id_kabot_test root@192.168.178.127 'cat /opt/studio-wip/BUILD_STAND'
```

Beide Betriebsarten sind zulässig — `git pull --ff-only` für einen
committeten Stand (siehe `Server-Zugang.md`), das Overlay für einen noch nicht
committeten. Nur der Unterschied muss sichtbar bleiben.

Der Ablauf prüft keine echte Plattform-Löschung. Das Mini-Skript
`scripts/pruefe_kleinanzeigen_loeschung.py` wird nur bewusst separat mit einer
konkreten URL ausgeführt; auch die maßgebliche Anbieterliste muss dann von
Hand geprüft werden.

Ohne `--pruefen` ist der Ablauf für schnelle Iterationen kürzer:

```bash
./scripts/aktualisiere_testserver.sh
```

Die Standardwerte sind `root@192.168.178.127`, SSH-Schlüssel
`~/.ssh/id_kabot_test` und `/opt/studio-wip`. Für einen anderen freigegebenen
Testserver können `ANZEIGEN_STUDIO_TESTSERVER_HOST`,
`ANZEIGEN_STUDIO_TESTSERVER_BENUTZER`,
`ANZEIGEN_STUDIO_TESTSERVER_ORDNER` und
`ANZEIGEN_STUDIO_SSH_SCHLUESSEL` gesetzt werden.

Wichtig:

- `.env`, `.env.*`, das Daten-Volume, `.git`, `node_modules`, `dist` und
  temporäre Verzeichnisse werden nicht übertragen.
- Das Skript verwendet **keinen `--delete`-Schritt** und schaltet erst nach
  einem erfolgreichen Bau und den angeforderten Prüfungen um. Das hat eine
  Folge, die man kennen muss: Eine Datei, die lokal gelöscht wurde, bleibt auf
  dem Server liegen und **wird dort weiter mitgebaut**. Eine entfernte
  Komponente kann also noch laufen. Wer etwas löscht, löscht es auf dem Server
  von Hand nach — oder klont das Zielverzeichnis einmal frisch aus Git.
- Der Zielpfad wird auf einfache absolute Pfade begrenzt, bevor er in einen
  Remote-Befehl eingesetzt wird.
- Der LAN-Override ist nur für den Testserver gedacht. Keine echte Anzeige,
  kein echtes Konto und kein anderer Server werden dadurch freigegeben.
