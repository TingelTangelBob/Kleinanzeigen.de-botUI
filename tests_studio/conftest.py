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

# src/ auf den Pfad, damit die Tests ohne Installation laufen.
_SRC = Path(__file__).resolve().parent.parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))
