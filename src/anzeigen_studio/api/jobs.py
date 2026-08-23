# SPDX-FileCopyrightText: © Anzeigen-Studio contributors
# SPDX-ArtifactOfProjectHomePage: https://github.com/TingelTangelBob/Kleinanzeigen.de-botUI/
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# HTTP-Endpunkte der Warteschlange (AP-1.6) und der Log-Auslieferung (AP-1.7).

from __future__ import annotations

import asyncio
import json
import sqlite3
from typing import TYPE_CHECKING, Annotated, Any

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from anzeigen_studio.botbridge.runner import ERLAUBTE_BEFEHLE
from anzeigen_studio.core import db
from anzeigen_studio.core import profile as profile_dienst
from anzeigen_studio.core.errors import FachlicherFehler
from anzeigen_studio.core.settings import Settings
from anzeigen_studio.jobs import speicher

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Iterator

    from anzeigen_studio.jobs.modelle import Job
    from anzeigen_studio.jobs.warteschlange import Warteschlange

router = APIRouter(prefix = "/api/jobs", tags = ["Jobs"])

#: Abstand zwischen zwei Abfragen im Log-Strom. Kurz genug, dass es live
#: wirkt, lang genug, dass es die Datenbank nicht belastet.
_STROM_TAKT_S = 1.0

#: Nach dieser Zeit ohne neue Zeilen wird ein Kommentar geschickt, damit
#: Reverse Proxies die Verbindung nicht als tot verwerfen.
_HERZSCHLAG_S = 15.0


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


def _warteschlange(request: Request) -> Warteschlange:
    ws: Warteschlange = request.app.state.warteschlange
    return ws


Verbindung = Annotated[sqlite3.Connection, Depends(_verbindung)]
Konfiguration = Annotated[Settings, Depends(_einstellungen)]
Schlange = Annotated["Warteschlange", Depends(_warteschlange)]


class JobAusgabe(BaseModel):
    id: int
    profil_slug: str
    befehl: str
    argumente: list[str]
    zustand: str
    eingereicht_am: str
    gestartet_am: str | None
    beendet_am: str | None
    rueckgabecode: int | None
    aufmerksamkeit: list[str]
    eingriff: str | None
    meldung: str | None
    wartet_bis: str | None
    wartegrund: str | None


class JobEingabe(BaseModel):
    profil: str = Field(min_length = 1, max_length = 32)
    befehl: str = Field(min_length = 1, max_length = 40)
    argumente: list[str] = Field(default_factory = list, max_length = 20)


class EingabeAntwort(BaseModel):
    text: str = Field(default = "", max_length = 200)


def _ausgabe(job: Job) -> JobAusgabe:
    return JobAusgabe(
        id = job.id, profil_slug = job.profil_slug, befehl = job.befehl,
        argumente = job.argumente, zustand = str(job.zustand),
        eingereicht_am = job.eingereicht_am, gestartet_am = job.gestartet_am,
        beendet_am = job.beendet_am, rueckgabecode = job.rueckgabecode,
        aufmerksamkeit = job.aufmerksamkeit, eingriff = job.eingriff, meldung = job.meldung,
        wartet_bis = job.wartet_bis, wartegrund = job.wartegrund,
    )


@router.get("", response_model = list[JobAusgabe])
def auflisten(conn: Verbindung, profil: str | None = None, grenze: int = Query(default = 50, le = 200)) -> list[JobAusgabe]:
    profil_id = None
    if profil is not None:
        p = profile_dienst.nach_slug(conn, profil)
        if p is None:
            raise FachlicherFehler("Profil nicht gefunden.", status = 404)
        profil_id = p.id
    return [_ausgabe(j) for j in speicher.liste(conn, profil_id = profil_id, grenze = grenze)]


@router.post("", response_model = JobAusgabe, status_code = 202)
async def einreihen(daten: JobEingabe, conn: Verbindung, cfg: Konfiguration, ws: Schlange) -> JobAusgabe:
    if daten.befehl not in ERLAUBTE_BEFEHLE:
        raise FachlicherFehler(
            f"Der Befehl „{daten.befehl}“ ist nicht zulässig.", feld = "befehl",
        )
    p = profile_dienst.nach_slug(conn, daten.profil)
    if p is None:
        raise FachlicherFehler("Profil nicht gefunden.", status = 404, feld = "profil")

    verzeichnis = profile_dienst.pfade_fuer(cfg.profiles_dir, p.slug).wurzel
    job_id = await ws.einreihen(conn, p.id, daten.befehl, daten.argumente, profil_verzeichnis = verzeichnis)

    job = speicher.holen(conn, job_id)
    if job is None:  # pragma: no cover
        raise FachlicherFehler("Der Lauf konnte nicht eingereiht werden.", status = 500)
    return _ausgabe(job)


@router.get("/{job_id}", response_model = JobAusgabe)
def einzeln(job_id: int, conn: Verbindung) -> JobAusgabe:
    job = speicher.holen(conn, job_id)
    if job is None:
        raise FachlicherFehler("Lauf nicht gefunden.", status = 404)
    return _ausgabe(job)


@router.post("/{job_id}/abbrechen", status_code = 202)
async def abbrechen(job_id: int, ws: Schlange) -> dict[str, str]:
    await ws.abbrechen(job_id)
    return {"status": "abbruch angefordert"}


@router.post("/{job_id}/eingabe", status_code = 202)
async def eingabe(job_id: int, daten: EingabeAntwort, ws: Schlange) -> dict[str, str]:
    """Beantwortet einen Wartepunkt - Grundlage der Captcha-Übernahme (AP-1.8)."""
    await ws.eingabe_senden(job_id, daten.text)
    return {"status": "eingabe gesendet"}


@router.get("/{job_id}/log")
def log_lesen(job_id: int, conn: Verbindung, ab_id: int = 0) -> list[dict[str, Any]]:
    if speicher.holen(conn, job_id) is None:
        raise FachlicherFehler("Lauf nicht gefunden.", status = 404)
    return speicher.log_lesen(conn, job_id, ab_id = ab_id)


@router.get("/{job_id}/strom")
async def log_strom(job_id: int, request: Request, cfg: Konfiguration, ab_id: int = 0) -> StreamingResponse:
    """Liefert neue Protokollzeilen als Server-Sent-Events (AP-1.7).

    Bewusst mit einer eigenen Verbindung je Strom und einem einfachen Takt
    statt einer Benachrichtigung: Der Aufwand einer Ereignisverteilung lohnt
    sich bei einem Betreiber und wenigen gleichzeitigen Läufen nicht.
    """
    async def erzeugen() -> AsyncIterator[str]:
        conn = db.connect(cfg.database_path)
        letzte = ab_id
        seit_herzschlag = 0.0
        try:
            if speicher.holen(conn, job_id) is None:
                yield f"event: fehler\ndata: {json.dumps({'meldung': 'Lauf nicht gefunden.'})}\n\n"
                return
            while True:
                if await request.is_disconnected():
                    return

                zeilen = speicher.log_lesen(conn, job_id, ab_id = letzte)
                for zeile in zeilen:
                    kennung = zeile["id"]
                    letzte = kennung if isinstance(kennung, int) else int(str(kennung))
                    yield f"event: log\ndata: {json.dumps(zeile, ensure_ascii = False)}\n\n"

                job = speicher.holen(conn, job_id)
                if job is not None and not job.laeuft_noch and not zeilen:
                    # Endzustand mitschicken, damit die Oberfläche nicht
                    # zusätzlich nachfragen muss.
                    abschluss = {"zustand": str(job.zustand), "meldung": job.meldung,
                                 "aufmerksamkeit": job.aufmerksamkeit}
                    yield f"event: ende\ndata: {json.dumps(abschluss, ensure_ascii = False)}\n\n"
                    return

                if zeilen:
                    seit_herzschlag = 0.0
                else:
                    seit_herzschlag += _STROM_TAKT_S
                    if seit_herzschlag >= _HERZSCHLAG_S:
                        yield ": herzschlag\n\n"
                        seit_herzschlag = 0.0

                await asyncio.sleep(_STROM_TAKT_S)
        finally:
            conn.close()

    return StreamingResponse(
        erzeugen(),
        media_type = "text/event-stream",
        headers = {
            "Cache-Control": "no-cache",
            # Ohne dies puffert nginx den Strom und die Ausgabe käme erst am
            # Ende des Laufs an.
            "X-Accel-Buffering": "no",
        },
    )
