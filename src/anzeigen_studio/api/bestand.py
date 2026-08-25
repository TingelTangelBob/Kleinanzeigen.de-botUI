# SPDX-FileCopyrightText: © Anzeigen-Studio contributors
# SPDX-ArtifactOfProjectHomePage: https://github.com/TingelTangelBob/Kleinanzeigen.de-botUI/
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# HTTP-Endpunkte des lokalen Anzeigenbestands (AP-3.2).

from __future__ import annotations

import sqlite3
from typing import TYPE_CHECKING, Annotated

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel

from anzeigen_studio import bestand as bestand_dienst
from anzeigen_studio.core import db
from anzeigen_studio.core import profile as profile_dienst
from anzeigen_studio.core.errors import FachlicherFehler
from anzeigen_studio.core.settings import Settings

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path

router = APIRouter(prefix = "/api/bestand", tags = ["Bestand"])


def _verbindung(request: Request) -> Iterator[sqlite3.Connection]:
    cfg: Settings = request.app.state.settings
    conn = db.connect(cfg.database_path)
    try:
        yield conn
    finally:
        conn.close()


def _einstellungen(request: Request) -> Settings:
    cfg: Settings = request.app.state.settings
    return cfg


Verbindung = Annotated[sqlite3.Connection, Depends(_verbindung)]
Konfiguration = Annotated[Settings, Depends(_einstellungen)]


class AnzeigeAusgabe(BaseModel):
    datei: str
    ordner: str
    titel: str
    id: int | None
    art: str
    aktiv: bool
    kategorie: str | None
    preis: float | None
    preistyp: str | None
    versandart: str | None
    versandkosten: float | None
    versandpakete: list[str]
    direkt_kaufen: bool
    bilder: int
    vorschaubild: str | None
    erstellt_am: str | None
    aktualisiert_am: str | None
    neueinstellung_am: str | None
    faellig: bool
    lokal_geaendert: bool
    hinweise: list[str]
    unlesbar: str | None


def _profil_wurzel(conn: sqlite3.Connection, cfg: Settings, slug: str) -> Path:
    p = profile_dienst.nach_slug(conn, slug)
    if p is None:
        raise FachlicherFehler("Profil nicht gefunden.", status = 404, feld = "profil")
    return profile_dienst.pfade_fuer(cfg.profiles_dir, p.slug).wurzel


def _ausgabe(a: bestand_dienst.BestandsAnzeige) -> AnzeigeAusgabe:
    return AnzeigeAusgabe(
        datei = a.datei, ordner = a.ordner, titel = a.titel, id = a.id, art = a.art,
        aktiv = a.aktiv, kategorie = a.kategorie, preis = a.preis, preistyp = a.preistyp,
        versandart = a.versandart, versandkosten = a.versandkosten,
        versandpakete = a.versandpakete, direkt_kaufen = a.direkt_kaufen,
        bilder = a.bilder, vorschaubild = a.vorschaubild, erstellt_am = a.erstellt_am,
        aktualisiert_am = a.aktualisiert_am, neueinstellung_am = a.neueinstellung_am,
        faellig = a.faellig, lokal_geaendert = a.lokal_geaendert, hinweise = a.hinweise,
        unlesbar = a.unlesbar,
    )


@router.get("", response_model = list[AnzeigeAusgabe])
def auflisten(profil: str, conn: Verbindung, cfg: Konfiguration) -> list[AnzeigeAusgabe]:
    """Alle Anzeigen eines Profils, so wie sie auf der Platte liegen."""
    wurzel = _profil_wurzel(conn, cfg, profil)
    return [_ausgabe(a) for a in bestand_dienst.bestand_lesen(wurzel)]


@router.get("/lokale-aenderungen", response_model = list[AnzeigeAusgabe])
def lokale_aenderungen(profil: str, conn: Verbindung, cfg: Konfiguration) -> list[AnzeigeAusgabe]:
    """Anzeigen, die ein erneutes Herunterladen ueberschreiben wuerde.

    Grundlage der Warnung vor dem Download (AP-3.1). Der Bot uebernimmt beim
    Herunterladen den Stand der Plattform und erhaelt nur vier Automatikfelder -
    siehe `docs/RUNDLAUF.md`. Wer lokal etwas geaendert hat, soll das vorher
    erfahren und nicht hinterher.
    """
    wurzel = _profil_wurzel(conn, cfg, profil)
    return [_ausgabe(a) for a in bestand_dienst.lokal_geaenderte(wurzel)]


@router.get("/bild")
def bild(
    profil: str,
    datei: Annotated[str, Query(max_length = 400)],
    name: Annotated[str, Query(max_length = 200)],
    conn: Verbindung,
    cfg: Konfiguration,
) -> FileResponse:
    """Liefert ein Anzeigenbild aus dem Profilverzeichnis."""
    wurzel = _profil_wurzel(conn, cfg, profil)
    pfad = bestand_dienst.bildpfad(wurzel, datei, name)
    # Bilder aendern sich nur, wenn die Anzeige neu heruntergeladen wird. Eine
    # Stunde Zwischenspeicher spart in einer Liste mit Vorschaubildern viele
    # Anfragen, ohne dass ein Bild lange falsch waere.
    return FileResponse(pfad, headers = {"Cache-Control": "private, max-age=3600"})
