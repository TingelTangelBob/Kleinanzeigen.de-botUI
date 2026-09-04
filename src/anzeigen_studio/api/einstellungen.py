# SPDX-FileCopyrightText: © Anzeigen-Studio contributors
# SPDX-ArtifactOfProjectHomePage: https://github.com/TingelTangelBob/Kleinanzeigen.de-botUI/
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# HTTP-Endpunkte der Einstellungen (AP-2.9).
#
# Die Werte liegen je Profil in nutzer.yaml. Vor dem Lauf mischt die
# Warteschlange sie in config.yaml - siehe botbridge.konfiguration.schreiben.
# Gesperrte Felder (AP-1.11) und Login-Klartext werden hier abgewiesen.

from __future__ import annotations

import shutil
import sqlite3
from typing import TYPE_CHECKING, Annotated, Any

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, Field

from anzeigen_studio.core import db
from anzeigen_studio.core import nutzerconfig
from anzeigen_studio.core import profile as profile_dienst
from anzeigen_studio.core.errors import FachlicherFehler
from anzeigen_studio.core.settings import Settings

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path

router = APIRouter(prefix = "/api/einstellungen", tags = ["Einstellungen"])


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


def _profil(conn: sqlite3.Connection, cfg: Settings, slug: str) -> tuple[profile_dienst.Profil, Path]:
    p = profile_dienst.nach_slug(conn, slug)
    if p is None:
        raise FachlicherFehler("Profil nicht gefunden.", status = 404, feld = "profil")
    return p, profile_dienst.pfade_fuer(cfg.profiles_dir, p.slug).wurzel


class EinstellungenAusgabe(BaseModel):
    profil: str
    werte: dict[str, Any]
    gruppen: list[dict[str, Any]]


class EinstellungenEingabe(BaseModel):
    werte: dict[str, Any] = Field(default_factory = dict)


class SpeichernAusgabe(BaseModel):
    profil: str
    werte: dict[str, Any]


@router.get("", response_model = EinstellungenAusgabe)
def lesen(conn: Verbindung, cfg: Konfiguration, profil: ProfilSlug) -> EinstellungenAusgabe:
    _p, wurzel = _profil(conn, cfg, profil)
    return EinstellungenAusgabe(
        profil = profil,
        werte = nutzerconfig.fuer_ui(wurzel),
        gruppen = nutzerconfig.gruppen_fuer_ui(),
    )


@router.put("", response_model = SpeichernAusgabe)
def speichern(
    daten: EinstellungenEingabe, conn: Verbindung, cfg: Konfiguration, profil: ProfilSlug,
) -> SpeichernAusgabe:
    _p, wurzel = _profil(conn, cfg, profil)
    gespeichert = nutzerconfig.schreiben(wurzel, daten.werte)
    return SpeichernAusgabe(profil = profil, werte = gespeichert)


@router.post("/browserprofil-zuruecksetzen", status_code = 204)
def browserprofil_zuruecksetzen(conn: Verbindung, cfg: Konfiguration, profil: ProfilSlug) -> None:
    """Loescht nur das Chromium-Profil, nicht Anzeigen und nicht die Datenbank.

    Ein kaputtes Browserprofil laesst jeden Lauf scheitern. Neu anlegen tut
    der Bot beim naechsten Start von selbst.
    """
    p = profile_dienst.nach_slug(conn, profil)
    if p is None:
        raise FachlicherFehler("Profil nicht gefunden.", status = 404, feld = "profil")
    pfade = profile_dienst.pfade_fuer(cfg.profiles_dir, p.slug)
    ziel = pfade.browser_profil
    # Gegenprobe: der Ordner muss unter dem Profilwurzel liegen, sonst waere
    # ein Tippfehler in ProfilPfade ein Loeschweg fuer fremde Daten.
    if not ziel.resolve().is_relative_to(pfade.wurzel.resolve()):
        raise FachlicherFehler("Ungültiger Browserprofilpfad.", status = 500)
    if ziel.exists():
        shutil.rmtree(ziel)
