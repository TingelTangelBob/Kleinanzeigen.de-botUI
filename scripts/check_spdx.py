#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# Neue Datei der Anzeigen-Studio-Fork-Weiterentwicklung. Nicht im Upstream vorhanden.
#
# Prueft, dass jede Quelldatei die SPDX-Kennung im Kopf traegt.
#
# Bewusst NICHT auf src/kleinanzeigen_bot/ angewandt: der Upstream pflegt seine Koepfe selbst
# und tut das nachweislich zuverlaessig (55 von 58 Dateien; die drei Ausnahmen sind leere
# __init__.py unterhalb der ruff-Schwelle von 256 Byte). Dort zu pruefen brauchte es nicht,
# und ein Fehlschlag waere ein Upstream-Thema, kein Fork-Thema.
#
# scripts/ ist ein gemischtes Verzeichnis - Upstream-Skripte und Fork-Skripte liegen dort
# nebeneinander. Es wird mitgeprueft, weil die Upstream-Skripte die Kennung ohnehin tragen.
#
# Aufruf:  python3 scripts/check_spdx.py
# Rueckgabe: 0 = alles in Ordnung, 1 = mindestens eine Datei ohne Kennung

from __future__ import annotations

import sys
from pathlib import Path

TAG = "SPDX-License-Identifier: AGPL-3.0-or-later"

# Nur Fork-eigene Verzeichnisse. Waechst mit dem Projekt mit.
ROOTS = ("src/anzeigen_studio", "webui/src", "scripts")

SUFFIXES = {".py", ".ts", ".tsx", ".js", ".jsx", ".css", ".sh"}

# Dateien unterhalb dieser Groesse brauchen keinen Kopf (leere __init__.py, Index-Reexporte).
# Gleiche Schwelle wie die ruff-Regel des Upstreams, damit beide Pruefungen konsistent sind.
MIN_BYTES = 256

SKIP_PARTS = {"node_modules", "dist", "__pycache__", ".venv", "build"}


def main() -> int:
    repo = Path(__file__).resolve().parent.parent
    missing: list[Path] = []
    checked = 0

    for root in ROOTS:
        base = repo / root
        if not base.is_dir():
            continue  # Verzeichnis existiert noch nicht - kein Fehler
        for path in sorted(base.rglob("*")):
            if not path.is_file() or path.suffix not in SUFFIXES:
                continue
            if SKIP_PARTS & set(path.parts):
                continue
            if path.stat().st_size < MIN_BYTES:
                continue
            checked += 1
            # Nur den Dateianfang lesen: die Kennung gehoert in den Kopf, nicht irgendwohin.
            head = path.read_text(encoding="utf-8", errors="replace")[:2048]
            if TAG not in head:
                missing.append(path.relative_to(repo))

    if missing:
        print(f"FEHLER: {len(missing)} Datei(en) ohne '{TAG}' im Kopf:", file=sys.stderr)
        for path in missing:
            print(f"  {path}", file=sys.stderr)
        print(
            "\nBitte die Kennung als Kommentar in den Dateikopf aufnehmen.",
            file=sys.stderr,
        )
        return 1

    print(f"OK: {checked} Datei(en) geprueft, alle mit SPDX-Kennung.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
