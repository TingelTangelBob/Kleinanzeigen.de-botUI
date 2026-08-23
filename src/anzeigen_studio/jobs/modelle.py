# SPDX-FileCopyrightText: © Anzeigen-Studio contributors
# SPDX-ArtifactOfProjectHomePage: https://github.com/TingelTangelBob/Kleinanzeigen.de-botUI/
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# Datenmodell der Job-Warteschlange (AP-1.6).

from __future__ import annotations

import enum
from dataclasses import dataclass, field


class JobZustand(enum.StrEnum):
    """Lebenslauf eines Jobs.

    BRAUCHT_EINGABE ist ein eigener Zustand und kein Unterfall von LAEUFT:
    Die Oberflaeche muss ihn unuebersehbar anzeigen koennen, sonst wartet ein
    Lauf stumm vor sich hin, bis die Frist ablaeuft.

    PRUEFEN ebenso: Der Bot kennt drei Faelle, in denen lokaler und entfernter
    Zustand auseinanderlaufen koennen. Die als gewoehnlichen Erfolg oder
    Fehlschlag zu melden waere falsch - sie brauchen einen Blick von Hand.
    """

    WARTET = "wartet"
    LAEUFT = "laeuft"
    BRAUCHT_EINGABE = "braucht_eingabe"
    FERTIG = "fertig"
    PRUEFEN = "pruefen"
    GESCHEITERT = "gescheitert"
    ABGEBROCHEN = "abgebrochen"


#: Zustaende, in denen ein Job nicht mehr weiterlaeuft.
ENDZUSTAENDE = frozenset({
    JobZustand.FERTIG,
    JobZustand.PRUEFEN,
    JobZustand.GESCHEITERT,
    JobZustand.ABGEBROCHEN,
})

#: Zustaende, in denen ein Job das Profil belegt.
AKTIVE_ZUSTAENDE = frozenset({
    JobZustand.LAEUFT,
    JobZustand.BRAUCHT_EINGABE,
})


@dataclass(frozen = True, slots = True)
class Job:
    id: int
    profil_id: int
    profil_slug: str
    befehl: str
    argumente: list[str]
    zustand: JobZustand
    eingereicht_am: str
    gestartet_am: str | None = None
    beendet_am: str | None = None
    rueckgabecode: int | None = None
    aufmerksamkeit: list[str] = field(default_factory = list)
    eingriff: str | None = None
    meldung: str | None = None

    #: Bis wann der Job absichtlich wartet (ISO-8601), und warum. Gesetzt von
    #: der Taktung aus AP-1.12. Eine Funktion, die bremst, muss sagen dass sie
    #: bremst - sonst sieht sie aus wie ein Fehler.
    wartet_bis: str | None = None
    wartegrund: str | None = None

    @property
    def laeuft_noch(self) -> bool:
        return self.zustand not in ENDZUSTAENDE
