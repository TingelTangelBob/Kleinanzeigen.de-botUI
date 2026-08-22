# Upstream-Updates übernehmen

<!-- SPDX-License-Identifier: AGPL-3.0-or-later -->
<!-- Neue Datei des Forks. Nicht im Upstream vorhanden. -->

Arbeitspaket AP-0.8. Beschreibt, wie Änderungen aus
[`Second-Hand-Friends/kleinanzeigen-bot`](https://github.com/Second-Hand-Friends/kleinanzeigen-bot)
in diesen Fork übernommen werden.

## Warum das nicht optional ist

Der Bot läuft gegen eine Website, die sich jederzeit ändern kann. Genau die Korrekturen, die man
dann braucht – angepasste Selektoren, neue Anmeldeabläufe, geänderte Formularfelder – entstehen im
Upstream. Ein Fork, der Updates nicht zieht, verliert innerhalb weniger Monate die Pflege, wegen
der man überhaupt geforkt hat.

Umgekehrt gilt: je mehr Upstream-Dateien dieser Fork anfasst, desto teurer wird jeder Merge. Die
Liste der geänderten Dateien in [`../NOTICE.md`](../NOTICE.md) ist deshalb kein Formalismus,
sondern die Rechnung, die bei jedem Sync fällig wird. **Sie kurz zu halten ist eine
Architekturaufgabe, keine Fleißaufgabe.**

## Aufbau der Remotes

| Remote | Zweck |
|---|---|
| `origin` | eigenes Repository, Ziel für Pushes |
| `upstream` | Original, **Push gesperrt** (`push-url = DISABLED`) |

Zusätzlich gibt es den Zweig **`upstream-main`**. Er folgt `upstream/main` und trägt den
unveränderten Originalstand. Er wird nie bearbeitet – er dient dazu, jederzeit sauber vergleichen
zu können, was der Fork tatsächlich verändert hat:

```bash
git diff upstream-main main -- src/kleinanzeigen_bot/
```

Liefert dieser Befehl mehr als die in `NOTICE.md` gelisteten Änderungen, stimmt etwas nicht.

## Rhythmus

- **Monatlich**, und zusätzlich
- **bei jedem Upstream-Release**, und
- **sofort**, wenn im Upstream ein Fehler behoben wurde, der uns betrifft (typisch: geänderte
  Selektoren nach einer Umstellung bei kleinanzeigen.de).

## Ablauf

### 1. Vorbereiten

```bash
git switch main && git status --short
```

Der Arbeitsbaum muss sauber sein. Offene Änderungen vorher committen oder mit `git stash -u`
beiseitelegen.

### 2. Upstream holen und Spiegelzweig nachziehen

```bash
git fetch upstream && git switch upstream-main && git merge --ff-only upstream/main
```

`--ff-only` ist Absicht: Wenn dieser Zweig sich nicht vorspulen lässt, hat jemand darauf
gearbeitet. Das ist ein Fehler und soll auffallen, statt still gemergt zu werden.

### 3. Sehen, was kommt

```bash
git log --oneline main..upstream-main
git diff --stat main..upstream-main
```

**Vor dem Merge gezielt auf die Dateien schauen, die der Fork angefasst hat** – die Liste steht in
`NOTICE.md`:

```bash
git diff main..upstream-main -- .gitignore README.md
```

Das sind die Stellen, an denen Konflikte entstehen werden. Wer sie vorher kennt, löst sie in
Minuten statt in einer Stunde.

### 4. Mergen

```bash
git switch main && git merge upstream-main
```

Bei Konflikten gilt: **Die Upstream-Fassung ist im Zweifel die richtige.** Die Fork-Ergänzungen
sind bewusst additiv gebaut (Fork-Hinweis am Anfang der README, angehängter Block am Ende der
`.gitignore`), damit sie sich nach einem Konflikt einfach wieder oben bzw. unten anfügen lassen.

### 5. Nachziehen – die Checkliste

Nach jedem Merge prüfen, ob sich etwas geändert hat, das den Fork betrifft:

| Prüfen | Warum | Wenn geändert |
|---|---|---|
| `schemas/ad.schema.json`, `schemas/config.schema.json` | Das Anzeigen- und Einstellungsformular wird daraus erzeugt | Formular in `webui/` prüfen, neue Felder ergänzen oder ausdrücklich ausblenden |
| `src/kleinanzeigen_bot/model/` | Datenmodelle sind der Vertrag zur API-Schicht | Backend-Typen und API-Antworten prüfen |
| `src/kleinanzeigen_bot/resources/categories.yaml` | Quelle der Kategorieauswahl | Auswahl in der Oberfläche gegentesten |
| `src/kleinanzeigen_bot/cli.py` | **Die zugesagte stabile Schnittstelle.** Der Fork ruft den Bot als Unterprozess auf | Aufrufe im Bot-Adapter prüfen: neue oder umbenannte Befehle, geänderte Optionen, geändertes Exit-Verhalten |
| Meldungstexte in `login_flow.py`, `captcha_flow.py` | Die Captcha-Übernahme erkennt Wartepunkte am Ausgabetext | Erkennungsmuster im Bot-Adapter nachziehen – **stiller Bruch, fällt sonst erst im Betrieb auf** |
| `pyproject.toml`, `pdm.lock` | Neue oder geänderte Abhängigkeiten | [`LIZENZEN.md`](LIZENZEN.md) neu erheben |
| `docker/image/Dockerfile` | Fork hat ein eigenes Image mit Xvfb und Nicht-root | Änderungen sinngemäß übernehmen |

Der fünfte Punkt ist der gefährlichste. Er bricht nichts sichtbar – kein Test schlägt fehl, kein
Build bricht ab. Er führt nur dazu, dass ein Lauf bei einem Captcha stehen bleibt, ohne dass die
Oberfläche es merkt.

### 6. Prüfen

```bash
docker compose run --rm backend pytest
```

Dazu die Fork-eigenen Prüfungen: `ruff`, `mypy`, ESLint, `tsc --noEmit`,
`python3 scripts/check_spdx.py`, und ein Trockenlauf des Bot-Adapters gegen Testdaten.

**Kein Lauf gegen ein echtes Konto** als Teil eines Syncs.

### 7. Nachtragen

- `NOTICE.md`: Liste der geänderten Dateien aktualisieren, falls beim Konfliktlösen etwas
  dazugekommen ist.
- Diese Datei: falls beim Sync eine Falle auftauchte, die in der Checkliste oben fehlt.

## Wenn ein Merge weh tut

Mehr als eine Handvoll Konflikte bedeutet, dass der Fork zu tief in Upstream-Dateien eingreift.
Dann **nicht** einfach durchbeißen, sondern die Ursache beheben:

1. Welche Datei verursacht die Konflikte?
2. Lässt sich die Änderung dort durch eine additive Lösung in einem neuen Modul ersetzen?
3. Oder gehört sie als Pull Request in den Upstream, damit sie dort dauerhaft gepflegt wird?

Möglichkeit 3 ist fast immer die beste. Der Upstream verlangt kein CLA. Die vorbereiteten
Kandidaten stehen in AP-0.10 des Projektplans.

## Erste Durchführung

Der erste vollständige Durchlauf ist **AP-7.5** im Projektplan und dient zugleich als Nachweis,
dass das Trennprinzip trägt. Ergebnis dort festhalten: Anzahl der Konflikte, betroffene Dateien,
benötigte Zeit.
