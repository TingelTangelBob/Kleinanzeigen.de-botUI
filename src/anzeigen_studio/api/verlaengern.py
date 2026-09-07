# SPDX-FileCopyrightText: © Anzeigen-Studio contributors
# SPDX-ArtifactOfProjectHomePage: https://github.com/TingelTangelBob/Kleinanzeigen.de-botUI/
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# HTTP-Endpunkte des automatischen kostenlosen Verlaengerns (AP-3.15).
#
# Wie beim taeglichen Abgleich: Der Schalter liegt in der Datenbank, nicht in
# nutzer.yaml. Free-only - kein Paid-Boost, kein Hochschieben.

from __future__ import annotations

import sqlite3
from typing import TYPE_CHECKING, Annotated

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel

from anzeigen_studio.bestand import verlaengern as verlaengern_dienst
from anzeigen_studio.core import db, zugang
from anzeigen_studio.core import profile as profile_dienst
from anzeigen_studio.core.errors import FachlicherFehler
from anzeigen_studio.core.settings import Settings
from anzeigen_studio.jobs import speicher

if TYPE_CHECKING:
    from collections.abc import Iterator

router = APIRouter(prefix = "/api/verlaengern", tags = ["Verlaengern"])


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
ProfilSlug = Annotated[str, Query(min_length = 1, max_length = 32, description = "Aktives Profil")]


class VerlaengernAusgabe(BaseModel):
    profil: str
    eingeschaltet: bool
    letzter_lauf_am: str | None = None
    letztes_ergebnis: str | None = None
    laeuft: bool = False
    heute_gelaufen: bool = False
    zugang_vorhanden: bool = False


class VerlaengernEingabe(BaseModel):
    eingeschaltet: bool


def _profil(conn: sqlite3.Connection, slug: str) -> profile_dienst.Profil:
    p = profile_dienst.nach_slug(conn, slug)
    if p is None:
        raise FachlicherFehler("Profil nicht gefunden.", status = 404, feld = "profil")
    return p


def _ausgabe(conn: sqlite3.Connection, p: profile_dienst.Profil) -> VerlaengernAusgabe:
    zustand = verlaengern_dienst.lesen(conn, p.id)
    status = zugang.status(conn, p.id)
    laeuft = False
    if zustand.job_id is not None:
        job = speicher.holen(conn, zustand.job_id)
        laeuft = job is not None and job.laeuft_noch
    return VerlaengernAusgabe(
        profil = p.slug,
        eingeschaltet = zustand.eingeschaltet,
        letzter_lauf_am = zustand.letzter_lauf_am,
        letztes_ergebnis = zustand.letztes_ergebnis,
        laeuft = laeuft,
        heute_gelaufen = zustand.letzter_tag == verlaengern_dienst.heutiger_tag(),
        zugang_vorhanden = status is not None and status.passwort_hinterlegt,
    )


@router.get("", response_model = VerlaengernAusgabe)
def lesen(conn: Verbindung, _cfg: Konfiguration, profil: ProfilSlug) -> VerlaengernAusgabe:
    return _ausgabe(conn, _profil(conn, profil))


@router.put("", response_model = VerlaengernAusgabe)
def schalten(
    daten: VerlaengernEingabe, conn: Verbindung, _cfg: Konfiguration, profil: ProfilSlug,
) -> VerlaengernAusgabe:
    """Schaltet das taegliche kostenlose Verlaengern ein oder aus.

    Einschalten heisst: Das Studio reiht einmal am Tag einen Free-`extend`
    ein (+60 Tage, kein Hochschieben). Ohne hinterlegte Zugangsdaten startet
    nichts.
    """
    p = _profil(conn, profil)
    with db.transaction(conn):
        verlaengern_dienst.einschalten(conn, p.id, an = daten.eingeschaltet)
    return _ausgabe(conn, p)
