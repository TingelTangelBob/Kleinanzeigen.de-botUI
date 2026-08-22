# SPDX-FileCopyrightText: © Anzeigen-Studio contributors
# SPDX-ArtifactOfProjectHomePage: https://github.com/TingelTangelBob/Kleinanzeigen.de-botUI/
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# HTTP-Endpunkte der Profilverwaltung (AP-1.3).

from __future__ import annotations

import sqlite3
from typing import TYPE_CHECKING, Annotated

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, Field

from anzeigen_studio.core import db
from anzeigen_studio.core import profile as profile_dienst
from anzeigen_studio.core import zugang as zugang_dienst
from anzeigen_studio.core.errors import FachlicherFehler
from anzeigen_studio.core.settings import Settings

if TYPE_CHECKING:
    from collections.abc import Iterator

router = APIRouter(prefix = "/api/profile", tags = ["Profile"])


def _verbindung(request: Request) -> Iterator[sqlite3.Connection]:
    """Eine Verbindung je Anfrage - siehe Begruendung in main.py."""
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


class ProfilAusgabe(BaseModel):
    slug: str
    anzeigename: str
    angelegt_am: str
    geaendert_am: str


class ProfilEingabe(BaseModel):
    # Laengen- und Musterpruefung liegt bewusst zusaetzlich im Dienst
    # (core/profile.py): die Pruefung hier ist Bequemlichkeit fuer den Browser,
    # die dort ist die verbindliche.
    slug: str = Field(min_length = 1, max_length = 32)
    anzeigename: str = Field(min_length = 1, max_length = 120)


class UmbenennenEingabe(BaseModel):
    anzeigename: str = Field(min_length = 1, max_length = 120)


def _ausgabe(p: profile_dienst.Profil) -> ProfilAusgabe:
    return ProfilAusgabe(
        slug = p.slug,
        anzeigename = p.anzeigename,
        angelegt_am = p.angelegt_am,
        geaendert_am = p.geaendert_am,
    )


@router.get("", response_model = list[ProfilAusgabe])
def auflisten(conn: Verbindung) -> list[ProfilAusgabe]:
    return [_ausgabe(p) for p in profile_dienst.alle(conn)]


@router.post("", response_model = ProfilAusgabe, status_code = 201)
def anlegen(daten: ProfilEingabe, conn: Verbindung, cfg: Konfiguration) -> ProfilAusgabe:
    p = profile_dienst.anlegen(conn, cfg.profiles_dir, daten.slug, daten.anzeigename)
    return _ausgabe(p)


@router.patch("/{slug}", response_model = ProfilAusgabe)
def umbenennen(slug: str, daten: UmbenennenEingabe, conn: Verbindung) -> ProfilAusgabe:
    p = profile_dienst.umbenennen(conn, slug, daten.anzeigename)
    return _ausgabe(p)


#: Muss ausdruecklich gesetzt werden. Standardmaessig aus, weil Loeschen
#: unumkehrbar ist und der Anzeigenbestand das Wertvollste am Profil ist -
#: die Oberflaeche fragt vorher nach, bevor sie es auf true setzt.
MitDaten = Annotated[bool, Query(description = "Anzeigenbestand mitlöschen")]


@router.delete("/{slug}", status_code = 204)
def loeschen(slug: str, conn: Verbindung, cfg: Konfiguration, *, mit_daten: MitDaten = False) -> None:
    profile_dienst.loeschen(conn, cfg.profiles_dir, slug, mit_daten = mit_daten)


# --- Zugangsdaten (AP-1.4) --------------------------------------------------


class ZugangAusgabe(BaseModel):
    """Was die Oberfläche sehen darf.

    Enthält bewusst kein Passwort und auch keine Längenangabe - nur die
    Tatsache, ob eines hinterlegt ist.
    """

    benutzername: str
    passwort_hinterlegt: bool
    geaendert_am: str


class ZugangEingabe(BaseModel):
    benutzername: str = Field(min_length = 1, max_length = 200)
    #: None lässt ein vorhandenes Passwort unverändert - so kann der
    #: Benutzername korrigiert werden, ohne das Passwort erneut einzugeben.
    passwort: str | None = Field(default = None, min_length = 1, max_length = 400)


def _profil_id(conn: sqlite3.Connection, slug: str) -> int:
    p = profile_dienst.nach_slug(conn, slug)
    if p is None:
        raise FachlicherFehler("Profil nicht gefunden.", status = 404)
    return p.id


@router.get("/{slug}/zugang", response_model = ZugangAusgabe | None)
def zugang_lesen(slug: str, conn: Verbindung) -> ZugangAusgabe | None:
    st = zugang_dienst.status(conn, _profil_id(conn, slug))
    if st is None:
        return None
    return ZugangAusgabe(
        benutzername = st.benutzername,
        passwort_hinterlegt = st.passwort_hinterlegt,
        geaendert_am = st.geaendert_am,
    )


@router.put("/{slug}/zugang", response_model = ZugangAusgabe)
def zugang_setzen(slug: str, daten: ZugangEingabe, conn: Verbindung, cfg: Konfiguration) -> ZugangAusgabe:
    st = zugang_dienst.setzen(
        conn,
        _profil_id(conn, slug),
        benutzername = daten.benutzername,
        passwort = daten.passwort,
        schluessel = cfg.secret_key,
    )
    return ZugangAusgabe(
        benutzername = st.benutzername,
        passwort_hinterlegt = st.passwort_hinterlegt,
        geaendert_am = st.geaendert_am,
    )


@router.delete("/{slug}/zugang", status_code = 204)
def zugang_entfernen(slug: str, conn: Verbindung) -> None:
    zugang_dienst.entfernen(conn, _profil_id(conn, slug))
