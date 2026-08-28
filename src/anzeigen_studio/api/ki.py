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

from anzeigen_studio import bestand as bestand_dienst
from anzeigen_studio.ai import anbieter as anbieter_dienst
from anzeigen_studio.ai import bilder as ki_bilder
from anzeigen_studio.ai import budget as budget_dienst
from anzeigen_studio.ai import entwurf as entwurf_dienst
from anzeigen_studio.ai import stil as stil_dienst
from anzeigen_studio.ai import vorschlag as vorschlag_dienst
from anzeigen_studio.bestand import anlegen as anlegen_dienst
from anzeigen_studio.core import db, ki_zugang
from anzeigen_studio.core import profile as profile_dienst
from anzeigen_studio.core.errors import FachlicherFehler
from anzeigen_studio.core.settings import Settings
from anzeigen_studio.katalog import daten as katalog

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
    #: Verbrauch des laufenden Monats (AP-4.7). Steht im Status, damit die
    #: Grenze sichtbar ist, bevor sie greift - nicht erst als Fehlermeldung.
    verbrauch_usd: float = 0.0
    budget_usd: float = 0.0
    verbrauch_aufrufe: int = 0


class SchluesselEingabe(BaseModel):
    api_schluessel: str


def _status_ausgabe(
    conn: sqlite3.Connection, cfg: Settings, *,
    hinterlegt: bool, endet_auf: str | None, geaendert_am: str | None,
) -> StatusAusgabe:
    """Baut die Statusantwort. Eine Stelle statt drei fast gleicher."""
    stand = budget_dienst.verbrauch(conn, grenze_usd = cfg.ki_budget_usd)
    return StatusAusgabe(
        hinterlegt = hinterlegt, endet_auf = endet_auf, geaendert_am = geaendert_am,
        modell = cfg.ki_modell, bildkante = cfg.ki_bildkante,
        verbrauch_usd = round(stand.usd, 4),
        budget_usd = round(stand.grenze_usd, 2),
        verbrauch_aufrufe = stand.aufrufe,
    )


@router.get("/status", response_model = StatusAusgabe)
def status(conn: Verbindung, cfg: Konfiguration) -> StatusAusgabe:
    z = ki_zugang.status(conn, schluessel = cfg.secret_key)
    return _status_ausgabe(
        conn, cfg,
        hinterlegt = z.hinterlegt, endet_auf = z.endet_auf, geaendert_am = z.geaendert_am,
    )


@router.put("/schluessel", response_model = StatusAusgabe)
def schluessel_setzen(daten: SchluesselEingabe, conn: Verbindung, cfg: Konfiguration) -> StatusAusgabe:
    z = ki_zugang.setzen(conn, daten.api_schluessel, schluessel = cfg.secret_key)
    LOG.info("OpenAI-Schlüssel hinterlegt")  # ohne Wert, auch nicht gekuerzt
    return _status_ausgabe(
        conn, cfg,
        hinterlegt = z.hinterlegt, endet_auf = z.endet_auf, geaendert_am = z.geaendert_am,
    )


@router.delete("/schluessel", response_model = StatusAusgabe)
def schluessel_entfernen(conn: Verbindung, cfg: Konfiguration) -> StatusAusgabe:
    ki_zugang.entfernen(conn)
    LOG.info("OpenAI-Schlüssel entfernt")
    return _status_ausgabe(
        conn, cfg, hinterlegt = False, endet_auf = None, geaendert_am = None,
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


class KategorieVorschlagAusgabe(BaseModel):
    wert: str
    name: str


class VersandVorschlagAusgabe(BaseModel):
    wert: str
    groesse: str
    preis: float | None


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
    #: Gegen den echten Katalog abgeglichene Vorschlaege (AP-4.5). Was hier
    #: steht, gibt es wirklich - gesetzt wird es trotzdem erst auf Zuruf.
    kategorie_vorschlaege: list[KategorieVorschlagAusgabe] = []
    versandgroesse: str | None = None
    versand_vorschlaege: list[VersandVorschlagAusgabe] = []


class KostenAusgabe(BaseModel):
    modell: str
    token_eingabe: int
    token_ausgabe: int
    usd: float
    bilder_gesendet: int
    bytes_gesendet: int
    #: Woran sich der Ton ausgerichtet hat (AP-4.2/4.3). Sichtbar, damit
    #: erkennbar ist, ob eigene Texte gewirkt haben oder die Standardvorgabe.
    stil_eigene_texte: int = 0
    #: Monatsstand nach diesem Aufruf.
    verbrauch_usd: float = 0.0
    budget_usd: float = 0.0


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
        versandgroesse = e.versandgroesse,
        kategorie_vorschlaege = [
            KategorieVorschlagAusgabe(wert = k.wert, name = k.name)
            for k in vorschlag_dienst.kategorie_treffer(e.kategorie)
        ],
        versand_vorschlaege = [
            VersandVorschlagAusgabe(wert = v.wert, groesse = v.groesse, preis = v.preis)
            for v in vorschlag_dienst.versand_treffer(e.versandgroesse)
        ],
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

    # Vor dem Aufruf, nicht danach: Eine Grenze, die erst nach dem Bezahlen
    # greift, ist keine.
    budget_dienst.pruefen(conn, grenze_usd = cfg.ki_budget_usd)

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

    usd = (antwort.token_eingabe * _PREIS_EINGABE_USD_JE_TOKEN
           + antwort.token_ausgabe * _PREIS_AUSGABE_USD_JE_TOKEN)

    # Gebucht wird VOR dem Auswerten der Antwort: Bezahlt ist sie auch dann,
    # wenn sich daraus kein brauchbarer Entwurf lesen laesst. Ein
    # Verbrauchsbuch, das nur gelungene Aufrufe kennt, zaehlt ausgerechnet die
    # teure Fehlersuche nicht mit.
    budget_dienst.buchen(
        conn,
        profil_slug = profil,
        modell = antwort.modell,
        token_eingabe = antwort.token_eingabe,
        token_ausgabe = antwort.token_ausgabe,
        mikro_usd = round(usd * budget_dienst.MIKRO_JE_USD),
    )
    stand = budget_dienst.verbrauch(conn, grenze_usd = cfg.ki_budget_usd)

    ergebnis = entwurf_dienst.aus_antwort(antwort.daten)
    LOG.info(
        "KI-Entwurf fertig: %d/%d Token, rund %.4f USD, %d Rückfragen, "
        "Monatsstand %.4f von %.2f USD",
        antwort.token_eingabe, antwort.token_ausgabe, usd, len(ergebnis.fragen),
        stand.usd, stand.grenze_usd,
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
            stil_eigene_texte = len(stilprofil.beispiele),
            verbrauch_usd = round(stand.usd, 4),
            budget_usd = round(stand.grenze_usd, 2),
        ),
    )


class AnlegenAntwort(BaseModel):
    datei: str
    titel: str
    bilder: int


def _pakete_lesen(roh: str | None) -> list[str]:
    """Liest die gewaehlten Versandpakete und weist Unmoegliches ab.

    Gemischte Groessen laesst Kleinanzeigen nicht zu; der Lauf braeche sonst
    mitten im Versanddialog ab. Dieselbe Regel wie beim Speichern
    (`bestand/bearbeiten.versandgroessen_pruefen`), hier nur frueher.
    """
    if not roh or not roh.strip():
        return []
    try:
        gewaehlt = json.loads(roh)
    except ValueError as fehler:
        raise FachlicherFehler("Die Versandauswahl war unlesbar.", status = 400) from fehler
    if not isinstance(gewaehlt, list):
        raise FachlicherFehler("Die Versandauswahl hatte die falsche Form.", status = 400)

    namen = [str(name) for name in gewaehlt if isinstance(name, str) and name.strip()]
    if not namen:
        return []

    bekannt = katalog.groesse_je_paket()
    unbekannt = [name for name in namen if name not in bekannt]
    if unbekannt:
        raise FachlicherFehler(
            f"Unbekanntes Versandpaket: {', '.join(unbekannt)}",
            status = 422, feld = "versandpakete",
        )
    if len({bekannt[name] for name in namen}) > 1:
        raise FachlicherFehler(
            bestand_dienst.GEMISCHTE_GROESSEN_MELDUNG, status = 422, feld = "versandpakete",
        )
    return namen


@router.post("/anlegen", response_model = AnlegenAntwort, status_code = 201)
async def anzeige_anlegen(
    conn: Verbindung,
    cfg: Konfiguration,
    *,
    profil: Annotated[str, Form()],
    entwurf_json: Annotated[str, Form()],
    antworten_json: Annotated[str, Form()],
    bilder: Annotated[list[UploadFile], File()],
    kategorie: Annotated[str | None, Form()] = None,
    versandpakete_json: Annotated[str | None, Form()] = None,
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

    felder = entwurf_dienst.als_anzeigenfelder(fertig)

    # Kategorie und Versand kommen NUR, wenn der Mensch einen Vorschlag
    # angeklickt hat. Beide werden gegen den Katalog geprueft, nicht
    # uebernommen wie geliefert: Der Weg fuehrt zwar ueber unsere eigene
    # Oberflaeche, aber ein Endpunkt ist eine Schnittstelle und keine
    # Vertrauensbeziehung.
    if kategorie:
        if not any(k.wert == kategorie for k in katalog.kategorien()):
            raise FachlicherFehler(
                "Diese Kategorie steht nicht im Katalog.", status = 422, feld = "kategorie",
            )
        felder["category"] = kategorie

    pakete = _pakete_lesen(versandpakete_json)
    if pakete:
        felder["shipping_type"] = "SHIPPING"
        felder["shipping_options"] = pakete

    angelegt = anlegen_dienst.anlegen(wurzel, felder, inhalte)
    return AnlegenAntwort(
        datei = angelegt.datei, titel = angelegt.titel, bilder = angelegt.bilder,
    )
