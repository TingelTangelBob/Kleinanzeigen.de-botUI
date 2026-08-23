# SPDX-FileCopyrightText: © Anzeigen-Studio contributors
# SPDX-ArtifactOfProjectHomePage: https://github.com/TingelTangelBob/Kleinanzeigen.de-botUI/
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# Taktung der Warteschlange (AP-1.12).
#
# Warum es das gibt: Die Warteschlange serialisiert je Profil, aber sie
# verlangsamt nichts. Zwanzig Anzeigen hintereinander in drei Minuten sehen
# anders aus als ein Mensch, der Anzeigen einstellt - und das ist genau das
# Muster, das einer Plattform auffaellt.
#
# Der Bot bringt bereits Verlangsamung INNERHALB eines Laufs mit (Tippjitter,
# Pausen zwischen Aktionen). Diese Schicht ergaenzt sie ZWISCHEN Laeufen.
#
# Bewusst zurueckhaltend voreingestellt: Wer bewusst schneller will, kann die
# Pause auf null setzen. Die Vorgabe soll aber nicht diejenige sein, die am
# ehesten Aerger macht.

from __future__ import annotations

import random
from dataclasses import dataclass
from datetime import UTC, datetime, time, timedelta
from typing import Final

#: Vorgabe: eine Minute Mindestabstand, mit bis zu 50 % Streuung nach oben.
#: Ein exakt gleichmaessiger Abstand ist selbst ein Muster.
STANDARD_MINDESTPAUSE_S: Final[int] = 60
STANDARD_STREUUNG: Final[float] = 0.5

#: Vorgabe-Zeitfenster: 7 bis 23 Uhr Ortszeit. Laeufe um drei Uhr nachts sind
#: nicht verboten, fallen aber auf.
STANDARD_VON = time(7, 0)
STANDARD_BIS = time(23, 0)


@dataclass(frozen = True, slots = True)
class Taktung:
    """Wie stark Laeufe eines Profils gebremst werden."""

    #: Mindestabstand zwischen zwei Laeufen desselben Profils, in Sekunden.
    #: 0 schaltet die Bremse ab.
    mindestpause_s: int = STANDARD_MINDESTPAUSE_S

    #: Zufaellige Verlaengerung, als Anteil der Mindestpause.
    streuung: float = STANDARD_STREUUNG

    #: Zeitfenster, in dem ueberhaupt gelaufen wird. Beide gleich = kein Fenster.
    fenster_von: time = STANDARD_VON
    fenster_bis: time = STANDARD_BIS

    #: Ob das Zeitfenster gilt. Aus heisst: rund um die Uhr.
    fenster_aktiv: bool = True

    def pause_nach_lauf(self) -> float:
        """Wie lange nach einem Lauf gewartet wird, bevor der naechste startet."""
        if self.mindestpause_s <= 0:
            return 0.0
        # Streuung nur nach oben: Die Mindestpause soll eine Untergrenze sein,
        # keine Mitte.
        return self.mindestpause_s * (1.0 + random.random() * self.streuung)  # noqa: S311

    def im_fenster(self, jetzt: datetime | None = None) -> bool:
        if not self.fenster_aktiv or self.fenster_von == self.fenster_bis:
            return True
        # Ortszeit, nicht UTC: Ein Fenster "7 bis 23 Uhr" meint die Uhrzeit
        # des Betreibers. Die Zeitzone setzt das Container-Abbild (TZ).
        aktuell = (jetzt or datetime.now(UTC).astimezone()).time()
        if self.fenster_von <= self.fenster_bis:
            return self.fenster_von <= aktuell < self.fenster_bis
        # Fenster ueber Mitternacht, z. B. 22 bis 6 Uhr.
        return aktuell >= self.fenster_von or aktuell < self.fenster_bis

    def wartezeit_bis_fenster(self, jetzt: datetime | None = None) -> float:
        """Sekunden bis zum naechsten Fensterbeginn. 0, wenn wir schon drin sind."""
        if self.im_fenster(jetzt):
            return 0.0
        aktuell = jetzt or datetime.now(UTC).astimezone()
        start = aktuell.replace(
            hour = self.fenster_von.hour, minute = self.fenster_von.minute,
            second = 0, microsecond = 0,
        )
        if start <= aktuell:
            start += timedelta(days = 1)
        return (start - aktuell).total_seconds()
