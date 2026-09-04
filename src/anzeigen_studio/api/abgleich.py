# SPDX-FileCopyrightText: © Anzeigen-Studio contributors
# SPDX-ArtifactOfProjectHomePage: https://github.com/TingelTangelBob/Kleinanzeigen.de-botUI/
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# HTTP-Endpunkte des taeglichen Abgleichs (AP-3.12).
#
# Der Schalter liegt NICHT in nutzer.yaml wie die uebrigen Einstellungen: Dort
# darf nur stehen, was das Upstream-Schema kennt (`core/nutzerconfig.py` weist
# alles andere ab), und der Abgleich ist eine Funktion des Studios, nicht des
# Bots. Er gehoert deshalb in die Datenbank, neben Zeitpunkt und Ergebnis des
# letzten Laufs.

from __future__ import annotations

import sqlite3
from typing import TYPE_CHECKING, Annotated, Any

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel

from anzeigen_studio.bestand import tagesabgleich
from anzeigen_studio.core import db, zugang
from anzeigen_studio.core import profile as profile_dienst
from anzeigen_studio.core.errors import FachlicherFehler
from anzeigen_studio.core.settings import Settings
from anzeigen_studio.jobs import speicher

if TYPE_CHECKING:
    from collections.abc import Iterator

router = APIRouter(prefix = "/api/abgleich", tags = ["Abgleich"])


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


class AbgleichAusgabe(BaseModel):
    profil: str
    eingeschaltet: bool
    letzter_lauf_am: str | None = None
    letztes_ergebnis: str | None = None
    #: Der Lauf von heute ist eingereiht und noch nicht ausgewertet.
    laeuft: bool = False
    #: Heute wurde bereits eingereiht - ein zweiter Lauf kommt nicht.
    heute_gelaufen: bool = False
    #: Ohne hinterlegtes Passwort startet der Abgleich gar nicht erst.
    zugang_vorhanden: bool = False


class AbgleichEingabe(BaseModel):
    eingeschaltet: bool


class Meldung(BaseModel):
    id: int
    profil: str
    profil_name: str
    zeitpunkt: str
    art: str
    titel: str
    text: str


def _profil(conn: sqlite3.Connection, slug: str) -> profile_dienst.Profil:
    p = profile_dienst.nach_slug(conn, slug)
    if p is None:
        raise FachlicherFehler("Profil nicht gefunden.", status = 404, feld = "profil")
    return p


def _ausgabe(conn: sqlite3.Connection, p: profile_dienst.Profil) -> AbgleichAusgabe:
    zustand = tagesabgleich.lesen(conn, p.id)
    status = zugang.status(conn, p.id)
    laeuft = False
    if zustand.job_id is not None:
        job = speicher.holen(conn, zustand.job_id)
        laeuft = job is not None and job.laeuft_noch
    return AbgleichAusgabe(
        profil = p.slug,
        eingeschaltet = zustand.eingeschaltet,
        letzter_lauf_am = zustand.letzter_lauf_am,
        letztes_ergebnis = zustand.letztes_ergebnis,
        laeuft = laeuft,
        heute_gelaufen = zustand.letzter_tag == tagesabgleich.heutiger_tag(),
        zugang_vorhanden = status is not None and status.passwort_hinterlegt,
    )


@router.get("", response_model = AbgleichAusgabe)
def lesen(conn: Verbindung, _cfg: Konfiguration, profil: ProfilSlug) -> AbgleichAusgabe:
    return _ausgabe(conn, _profil(conn, profil))


@router.put("", response_model = AbgleichAusgabe)
def schalten(
    daten: AbgleichEingabe, conn: Verbindung, _cfg: Konfiguration, profil: ProfilSlug,
) -> AbgleichAusgabe:
    """Schaltet den taeglichen Abgleich ein oder aus.

    Einschalten heisst: Ab morgen fasst das Studio dieses Konto einmal am Tag
    von selbst an. Die Oberflaeche sagt das vor dem Umlegen ausdruecklich; hier
    wird es nur gespeichert.
    """
    p = _profil(conn, profil)
    with db.transaction(conn):
        tagesabgleich.einschalten(conn, p.id, an = daten.eingeschaltet)
    return _ausgabe(conn, p)


@router.get("/meldungen", response_model = list[Meldung])
def meldungen(conn: Verbindung, _cfg: Konfiguration) -> list[Meldung]:
    """Die juengsten Befunde aller Profile - Quelle der Glocke.

    Bewusst ueber alle Profile: Die Glocke steht in der Kopfleiste und gehoert
    keinem Profil. Wer zwei Konten betreibt, soll nicht erst umschalten
    muessen, um zu erfahren, dass im anderen eine Anzeige verschwunden ist.
    """
    roh: list[dict[str, Any]] = tagesabgleich.meldungen(conn)
    return [
        Meldung(
            id = int(eintrag["id"]),
            profil = str(eintrag["slug"]),
            profil_name = str(eintrag["anzeigename"]),
            zeitpunkt = str(eintrag["zeitpunkt"]),
            art = str(eintrag["art"]),
            titel = str(eintrag["titel"]),
            text = str(eintrag["text"]),
        )
        for eintrag in roh
    ]
