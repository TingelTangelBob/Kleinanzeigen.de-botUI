# SPDX-FileCopyrightText: © Anzeigen-Studio contributors
# SPDX-ArtifactOfProjectHomePage: https://github.com/TingelTangelBob/Kleinanzeigen.de-botUI/
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# HTTP-Endpunkte des KI-Entwurfsmoduls (AP-4.1, AP-4.4, AP-4.6).
#
# Zwei Wege, und dass es zwei sind, ist Absicht:
#
#   POST /api/ki/entwurf   Bilder rein, Vorschlag und Rueckfragen raus.
#                          Kostet Geld. Legt nichts an.
#   POST /api/ki/anlegen   Vorschlag plus Antworten rein, Anzeigendatei raus.
#                          Kostet nichts. Ruft den Anbieter NICHT noch einmal.
#
# Der zweite Weg nimmt die Bilder erneut entgegen, statt sie zwischen den
# Aufrufen serverseitig zu halten. Das spart einen Zwischenspeicher mit
# Verfallszeit, den man aufraeumen und begrenzen muesste - und die Bilder
# liegen ohnehin noch im Browser.

from __future__ import annotations

import json
import logging
import sqlite3
from typing import TYPE_CHECKING, Annotated, Any

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from pydantic import BaseModel

from anzeigen_studio.ai import anbieter as anbieter_dienst
from anzeigen_studio.ai import bilder as ki_bilder
from anzeigen_studio.ai import entwurf as entwurf_dienst
from anzeigen_studio.ai import stil as stil_dienst
from anzeigen_studio.bestand import anlegen as anlegen_dienst
from anzeigen_studio.core import db, ki_zugang
from anzeigen_studio.core import profile as profile_dienst
from anzeigen_studio.core.errors import FachlicherFehler
from anzeigen_studio.core.settings import Settings

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path

LOG = logging.getLogger(__name__)

router = APIRouter(prefix = "/api/ki", tags = ["KI"])

#: Preise des eingestellten Modells in USD je 1 Mio. Token, Stand 2026-08-27.
#: Nur zur Anzeige - abgerechnet wird beim Anbieter. Steht hier, damit die
#: Oberflaeche sagen kann, was ein Entwurf gekostet hat, statt es zu verschweigen.
#: Quelle und Vergleich: 00_Agentenordner/04_Serververwaltung/KI-API-Zugaenge.md
_PREIS_EINGABE_USD_JE_TOKEN = 0.20 / 1_000_000
_PREIS_AUSGABE_USD_JE_TOKEN = 1.20 / 1_000_000


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


def _profil_wurzel(conn: sqlite3.Connection, cfg: Settings, slug: str) -> Path:
    p = profile_dienst.nach_slug(conn, slug)
    if p is None:
        raise FachlicherFehler("Profil nicht gefunden.", status = 404, feld = "profil")
    return profile_dienst.pfade_fuer(cfg.profiles_dir, p.slug).wurzel


# ---------------------------------------------------------------- Schluessel

class StatusAusgabe(BaseModel):
    hinterlegt: bool
    endet_auf: str | None = None
    geaendert_am: str | None = None
    modell: str
    bildkante: int


class SchluesselEingabe(BaseModel):
    api_schluessel: str


@router.get("/status", response_model = StatusAusgabe)
def status(conn: Verbindung, cfg: Konfiguration) -> StatusAusgabe:
    z = ki_zugang.status(conn, schluessel = cfg.secret_key)
    return StatusAusgabe(
        hinterlegt = z.hinterlegt, endet_auf = z.endet_auf, geaendert_am = z.geaendert_am,
        modell = cfg.ki_modell, bildkante = cfg.ki_bildkante,
    )


@router.put("/schluessel", response_model = StatusAusgabe)
def schluessel_setzen(daten: SchluesselEingabe, conn: Verbindung, cfg: Konfiguration) -> StatusAusgabe:
    z = ki_zugang.setzen(conn, daten.api_schluessel, schluessel = cfg.secret_key)
    LOG.info("OpenAI-Schlüssel hinterlegt")  # ohne Wert, auch nicht gekuerzt
    return StatusAusgabe(
        hinterlegt = z.hinterlegt, endet_auf = z.endet_auf, geaendert_am = z.geaendert_am,
        modell = cfg.ki_modell, bildkante = cfg.ki_bildkante,
    )


@router.delete("/schluessel", response_model = StatusAusgabe)
def schluessel_entfernen(conn: Verbindung, cfg: Konfiguration) -> StatusAusgabe:
    ki_zugang.entfernen(conn)
    LOG.info("OpenAI-Schlüssel entfernt")
    return StatusAusgabe(
        hinterlegt = False, endet_auf = None, geaendert_am = None,
        modell = cfg.ki_modell, bildkante = cfg.ki_bildkante,
    )


# ------------------------------------------------------------------ Entwurf

class OptionAusgabe(BaseModel):
    text: str
    wert: str


class FrageAusgabe(BaseModel):
    id: str
    frage: str
    feld: str
    freitext_erlaubt: bool
    optionen: list[OptionAusgabe]


class EntwurfAusgabe(BaseModel):
    titel: str
    beschreibung: str
    zustand: str | None
    zustand_text: str | None
    kategorie: str | None
    preis_euro: float | None
    preis_begruendung: str | None
    sicherheit: str
    fragen: list[FrageAusgabe]


class KostenAusgabe(BaseModel):
    modell: str
    token_eingabe: int
    token_ausgabe: int
    usd: float
    bilder_gesendet: int
    bytes_gesendet: int


class EntwurfAntwort(BaseModel):
    entwurf: EntwurfAusgabe
    kosten: KostenAusgabe


def _als_ausgabe(e: entwurf_dienst.Entwurf) -> EntwurfAusgabe:
    return EntwurfAusgabe(
        titel = e.titel,
        beschreibung = e.beschreibung,
        zustand = e.zustand,
        zustand_text = entwurf_dienst.ZUSTAND_BESCHRIFTUNG.get(e.zustand or ""),
        kategorie = e.kategorie,
        preis_euro = e.preis_euro,
        preis_begruendung = e.preis_begruendung,
        sicherheit = e.sicherheit,
        fragen = [
            FrageAusgabe(
                id = f.id, frage = f.frage, feld = f.feld,
                freitext_erlaubt = f.freitext_erlaubt,
                optionen = [OptionAusgabe(text = o.text, wert = o.wert) for o in f.optionen],
            )
            for f in e.fragen
        ],
    )


async def _dateien_lesen(bilder: list[UploadFile]) -> list[bytes]:
    """Liest die hochgeladenen Dateien, mit Groessengrenze je Datei.

    Wie beim Bild-Upload im Bestand wird begrenzt gelesen und nicht erst
    hinterher gemessen - sonst laege eine absichtlich grosse Datei bereits
    vollstaendig im Speicher.
    """
    inhalte: list[bytes] = []
    for datei in bilder:
        stuecke: list[bytes] = []
        gelesen = 0
        grenze = ki_bilder.MAX_EINGABE_BYTES
        while gelesen <= grenze:
            stueck = await datei.read(min(64 * 1024, grenze + 1 - gelesen))
            if not stueck:
                break
            stuecke.append(stueck)
            gelesen += len(stueck)
        if gelesen > grenze:
            raise FachlicherFehler(
                f"Ein Bild ist größer als {grenze // (1024 * 1024)} MB.",
                status = 413, feld = "bilder",
            )
        if stuecke:
            inhalte.append(b"".join(stuecke))
    return inhalte


@router.post("/entwurf", response_model = EntwurfAntwort)
async def entwurf_erzeugen(
    conn: Verbindung,
    cfg: Konfiguration,
    profil: Annotated[str, Form()],
    bilder: Annotated[list[UploadFile], File()],
) -> EntwurfAntwort:
    """Schickt die Bilder an den Anbieter und gibt den Vorschlag zurueck.

    Der einzige Weg, der Geld kostet. Er legt nichts an und veraendert nichts.
    """
    wurzel = _profil_wurzel(conn, cfg, profil)
    api_schluessel = ki_zugang.lesen(conn, schluessel = cfg.secret_key)
    inhalte = await _dateien_lesen(bilder)

    vorbereitet = ki_bilder.alle_vorbereiten(inhalte, kante = cfg.ki_bildkante)
    LOG.info(
        "KI-Entwurf: %d Bilder, %d KB nach der Verkleinerung (vorher %d KB)",
        len(vorbereitet),
        sum(b.bytes_nachher for b in vorbereitet) // 1024,
        sum(b.bytes_vorher for b in vorbereitet) // 1024,
    )

    dienst = anbieter_dienst.OpenAI(api_schluessel = api_schluessel, modell = cfg.ki_modell)
    stilprofil = stil_dienst.aus_bestand(wurzel)
    antwort = await dienst.erkennen(
        vorbereitet,
        anweisung = entwurf_dienst.anweisung(stilprofil.anweisungsteil()),
        schema = entwurf_dienst.schema(),
        schema_name = "anzeigenentwurf",
    )

    ergebnis = entwurf_dienst.aus_antwort(antwort.daten)
    usd = (antwort.token_eingabe * _PREIS_EINGABE_USD_JE_TOKEN
           + antwort.token_ausgabe * _PREIS_AUSGABE_USD_JE_TOKEN)
    LOG.info(
        "KI-Entwurf fertig: %d/%d Token, rund %.4f USD, %d Rückfragen",
        antwort.token_eingabe, antwort.token_ausgabe, usd, len(ergebnis.fragen),
    )

    return EntwurfAntwort(
        entwurf = _als_ausgabe(ergebnis),
        kosten = KostenAusgabe(
            modell = antwort.modell,
            token_eingabe = antwort.token_eingabe,
            token_ausgabe = antwort.token_ausgabe,
            usd = round(usd, 6),
            bilder_gesendet = len(vorbereitet),
            bytes_gesendet = sum(b.bytes_nachher for b in vorbereitet),
        ),
    )


class AnlegenAntwort(BaseModel):
    datei: str
    titel: str
    bilder: int


@router.post("/anlegen", response_model = AnlegenAntwort, status_code = 201)
async def anzeige_anlegen(
    conn: Verbindung,
    cfg: Konfiguration,
    profil: Annotated[str, Form()],
    entwurf_json: Annotated[str, Form()],
    antworten_json: Annotated[str, Form()],
    bilder: Annotated[list[UploadFile], File()],
) -> AnlegenAntwort:
    """Legt die Anzeige lokal an. Ohne Anbieter, ohne Kosten, ohne Veroeffentlichen.

    Die Anzeige landet als Datei unter `ads/` im Profilverzeichnis. Sie geht
    nicht online - dafuer braucht es einen ausdruecklichen Lauf (AP-4.6).
    """
    wurzel = _profil_wurzel(conn, cfg, profil)

    try:
        roh_entwurf: dict[str, Any] = json.loads(entwurf_json)
        roh_antworten: dict[str, Any] = json.loads(antworten_json or "{}")
    except ValueError as fehler:
        raise FachlicherFehler("Der Entwurf war unlesbar.", status = 400) from fehler
    if not isinstance(roh_entwurf, dict) or not isinstance(roh_antworten, dict):
        raise FachlicherFehler("Der Entwurf hatte die falsche Form.", status = 400)

    vorschlag = entwurf_dienst.aus_antwort(roh_entwurf)
    antworten = {str(k): str(v) for k, v in roh_antworten.items() if v is not None}
    fertig = entwurf_dienst.anwenden(vorschlag, antworten)

    inhalte = await _dateien_lesen(bilder)
    if not inhalte:
        raise FachlicherFehler("Ohne Bild wird keine Anzeige angelegt.", status = 400, feld = "bilder")

    angelegt = anlegen_dienst.anlegen(
        wurzel, entwurf_dienst.als_anzeigenfelder(fertig), inhalte,
    )
    return AnlegenAntwort(
        datei = angelegt.datei, titel = angelegt.titel, bilder = angelegt.bilder,
    )
