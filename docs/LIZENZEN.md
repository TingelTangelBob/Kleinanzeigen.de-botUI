# Lizenzen der Abhängigkeiten

<!-- SPDX-License-Identifier: AGPL-3.0-or-later -->
<!-- Neue Datei des Forks. Nicht im Upstream vorhanden. -->

**Stand:** 2026-08-25 · **Erhoben aus:** `pdm.lock` (vollständige aufgelöste Hülle, Gruppe
`default`) · **Lizenzangaben:** live über die PyPI-JSON-API abgefragt, nicht aus dem Gedächtnis.

> **Nachtrag 2026-08-25.** Ergänzt um `python-multipart` (Apache-2.0), gebraucht für die
> Bild-Uploads aus AP-2.6. Lizenz am selben Tag über die PyPI-API abgefragt, nicht aus dem
> Gedächtnis — dieselbe Regel wie beim ersten Durchgang.

## Warum es diese Liste gibt

Das Gesamtwerk steht unter AGPL-3.0-or-later. Eine einzige Abhängigkeit unter einer
AGPL-unverträglichen Lizenz – proprietär, SSPL, BUSL, „nur nicht-kommerziell" – würde es
unverteilbar machen. Diese Prüfung gehört deshalb vor jede neue Abhängigkeit, nicht danach.

Der Upstream-Prüfbericht hatte die zehn **direkten** Laufzeitabhängigkeiten geprüft und die
transitive Hülle ausdrücklich offengelassen. Diese Liste schließt genau diese Lücke.

## Ergebnis

**Alle 30 Laufzeitabhängigkeiten sind mit AGPL-3.0-or-later verträglich.** Keine proprietäre,
keine SSPL-, keine BUSL-Abhängigkeit, keine Nicht-kommerziell-Klausel.

Zwei Einträge verdienen eine Erläuterung:

- **`nodriver` steht selbst unter AGPL-3.0.** Verträglich, weil identische Lizenzfamilie – aber es
  bedeutet, dass die Herausgabepflicht nach § 13 auch dann bestehen bliebe, wenn der gesamte
  Bot-Code ersetzt würde. Einen Ausweichpfad über „wir schreiben das neu" gibt es nicht.
- **`certifi` steht unter MPL-2.0.** Verträglich: MPL 2.0 § 3.3 erlaubt die Kombination mit
  (A)GPL-lizenzierten Werken ausdrücklich.

Die **Entwicklungsabhängigkeiten** (Gruppe `dev`, 65 weitere Pakete) sind nicht aufgeführt. Sie
landen nicht im Auslieferungsartefakt und wirken sich daher nicht auf dessen Lizenz aus. Sollte
künftig ein Entwicklungswerkzeug Code **erzeugen**, der mit ausgeliefert wird, gehört es
hierher.

## Laufzeitabhängigkeiten

| Paket | Version | Lizenz |
|---|---|---|
| `annotated-doc` | 0.0.5 | MIT |
| `annotated-types` | 0.8.0 | MIT |
| `bracex` | 3.0.1 | MIT |
| `certifi` | 2026.7.22 | MPL-2.0 |
| `colorama` | 0.4.6 | BSD License |
| `deprecated` | 1.3.1 | MIT |
| `jaraco-context` | 6.1.2 | MIT |
| `jaraco-functools` | 4.6.0 | MIT |
| `jaraco-text` | 4.3.0 | MIT |
| `markdown-it-py` | 4.2.0 | MIT License |
| `mdurl` | 0.1.2 | MIT License |
| `more-itertools` | 11.1.0 | MIT |
| `mss` | 10.2.0 | MIT License |
| `nodriver` | 0.50.3 | GNU AFFERO GENERAL PUBLIC LICENSE
                          … |
| `platformdirs` | 4.11.3 | MIT |
| `psutil` | 7.2.2 | BSD-3-Clause |
| `pydantic` | 2.13.4 | MIT |
| `python-multipart` | 0.0.32 | Apache-2.0 |
| `pydantic-core` | 2.46.4 | MIT |
| `pygments` | 2.21.0 | BSD-2-Clause |
| `rich` | 15.0.0 | MIT |
| `ruamel-yaml` | 0.19.1 | MIT |
| `sanitize-filename` | 1.2.0 | MIT License |
| `shellingham` | 1.5.4 | ISC License |
| `typer` | 0.27.1 | MIT |
| `typer-slim` | 0.24.0 | MIT |
| `typing-extensions` | 4.16.0 | PSF-2.0 |
| `typing-inspection` | 0.4.4 | MIT |
| `wcmatch` | 11.0.1 | MIT |
| `websockets` | 17.0.1 | BSD-3-Clause |
| `wrapt` | 2.3.0 | BSD-2-Clause |

## Pflege

Diese Liste wird bei jeder Änderung an `pyproject.toml` oder `pdm.lock` neu erhoben – in der Praxis
also nach jedem Upstream-Merge (siehe [`UPSTREAM-SYNC.md`](UPSTREAM-SYNC.md)) und bei jeder eigenen
neuen Abhängigkeit.

Die vorhandene CI führt `pip-audit` aus. Das prüft **Sicherheitslücken, keine Lizenzen** – die
beiden Prüfungen ersetzen einander nicht. Eine automatische Lizenzprüfung in der CI ist als Teil
von AP-0.7 vorgesehen.
