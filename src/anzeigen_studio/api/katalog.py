# SPDX-FileCopyrightText: © Anzeigen-Studio contributors
# SPDX-ArtifactOfProjectHomePage: https://github.com/TingelTangelBob/Kleinanzeigen.de-botUI/
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# HTTP-Endpunkte der Nachschlagewerke: Kategorien und Versandpakete (AP-2.7).

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from anzeigen_studio import katalog as katalog_dienst

router = APIRouter(prefix = "/api/katalog", tags = ["Katalog"])


class KategorieAusgabe(BaseModel):
    name: str
    wert: str


class VersandpaketAusgabe(BaseModel):
    wert: str
    anbieter: str
    groesse: str
    preis: float | None


@router.get("/kategorien", response_model = list[KategorieAusgabe])
def kategorien() -> list[KategorieAusgabe]:
    """Alle Kategorien mit lesbarem Pfad.

    Die Liste ist rund 580 Einträge lang und ändert sich nur mit dem Upstream.
    Sie wandert deshalb einmal komplett in die Oberfläche, die dann ohne
    weitere Anfragen sucht - das fühlt sich beim Tippen sofort an.
    """
    return [KategorieAusgabe(name = k.name, wert = k.wert) for k in katalog_dienst.kategorien()]


@router.get("/versandpakete", response_model = list[VersandpaketAusgabe])
def versandpakete() -> list[VersandpaketAusgabe]:
    """Die auswählbaren Versandpakete, mit tagesaktuellem Preis wenn erreichbar."""
    return [
        VersandpaketAusgabe(wert = p.wert, anbieter = p.anbieter, groesse = p.groesse, preis = p.preis)
        for p in katalog_dienst.versandpakete()
    ]
