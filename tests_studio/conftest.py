# SPDX-FileCopyrightText: © Anzeigen-Studio contributors
# SPDX-ArtifactOfProjectHomePage: https://github.com/TingelTangelBob/Kleinanzeigen.de-botUI/
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# Eigenes Testverzeichnis, bewusst NEBEN tests/ statt darin.
#
# Grund: tests/conftest.py des Upstreams importiert beim Sammeln den kompletten
# Bot. Laegen unsere Tests darunter, braeuchten sie dessen gesamten
# Abhaengigkeitsbaum, obwohl sie ihn nicht anfassen - langsam und unnoetig
# zerbrechlich. Ein Nebeneffekt davon war der Fund, dass `requests` im Upstream
# zur Laufzeit importiert, aber nicht als Abhaengigkeit deklariert ist.
#
# Trennung heisst hier auch: Upstream-Tests bleiben unberuehrt und laufen
# weiterhin ueber dessen eigene CI.

from __future__ import annotations

import sys
from pathlib import Path

# Repo-Wurzel und src/ auf den Pfad, damit die Tests ohne Installation laufen.
# Die Wurzel braucht z. B. test_pruefe_kleinanzeigen_loeschung fuer
# `import scripts...` - ohne sie scheitert die Sammlung unter nacktem `pytest`
# (CI), waehrend `python -m pytest` die Wurzel zufaellig schon setzt.
_ROOT = Path(__file__).resolve().parent.parent
_SRC = _ROOT / "src"
for _pfad in (_SRC, _ROOT):
    if str(_pfad) not in sys.path:
        sys.path.insert(0, str(_pfad))
