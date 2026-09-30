# SPDX-FileCopyrightText: © Anzeigen-Studio contributors
# SPDX-ArtifactOfProjectHomePage: https://github.com/TingelTangelBob/Kleinanzeigen.de-botUI/
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# HTTP-Endpunkte des KI-Entwurfsmoduls (AP-4.1, AP-4.4, AP-4.6).
# Geaendert am 2026-09-13: asynchrone, persistente Erkennungswarteschlange.
#
# Drei Wege, und dass der Hintergrundweg getrennt ist, ist Absicht:
#
#   POST /api/ki/entwurf   Bilder rein, Vorschlag und Rueckfragen raus.
#                          Kostet Geld. Legt nichts an.
#   POST /api/ki/erkennungen Bilder rein, Analyse laeuft im Hintergrund.
#                            Kostet Geld. Der Entwurf bleibt zur Pruefung liegen.
#   POST /api/ki/anlegen   Vorschlag plus Antworten rein, Anzeigendatei raus.
#                          Kostet nichts. Ruft den Anbieter NICHT noch einmal.
#
# Der direkte Entwurf bleibt als kompatibler API-Weg bestehen. Neue Anzeigen
# nutzen die wartende Variante, damit weitere Erkennungen nicht auf die erste
# Antwort warten muessen.

from __future__ import annotations

import json
import logging
import sqlite3
from typing import TYPE_CHECKING, Annotated, Any, Literal

from fastapi import APIRouter, Depends, File, Form, Query, Request, UploadFile
from pydantic import BaseModel, Field

from anzeigen_studio import bestand as bestand_dienst
from anzeigen_studio.ai import bilder as ki_bilder
from anzeigen_studio.ai import budget as budget_dienst
from anzeigen_studio.ai import entwurf as entwurf_dienst
from anzeigen_studio.ai import entwurf_lauf, erkennungswarteschlange
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
    #: Open-Source-Installationen verwalten den Schluessel selbst; in der
    #: gehosteten Variante bleibt er beim Betreiber.
    modus: Literal["open_source", "gehostet"]
    schluessel_selbst_setzbar: bool
    max_bilder: int


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
        modus = "gehostet" if cfg.hosted else "open_source",
        schluessel_selbst_setzbar = not cfg.hosted,
        max_bilder = cfg.ki_max_bilder,
    )


@router.get("/status", response_model = StatusAusgabe)
def status(conn: Verbindung, cfg: Konfiguration) -> StatusAusgabe:
    z = (
        ki_zugang.status(conn, schluessel = cfg.secret_key)
        if not cfg.hosted
        else None
    )
    return _status_ausgabe(
        conn, cfg,
        hinterlegt = bool(cfg.openai_api_schluessel) if z is None else z.hinterlegt,
        endet_auf = None if z is None else z.endet_auf,
        geaendert_am = None if z is None else z.geaendert_am,
    )


@router.put("/schluessel", response_model = StatusAusgabe)
def schluessel_setzen(daten: SchluesselEingabe, conn: Verbindung, cfg: Konfiguration) -> StatusAusgabe:
    if cfg.hosted:
        raise FachlicherFehler(
            "Der KI-Zugang wird bei dieser gehosteten Installation vom Betreiber bereitgestellt.",
            status = 403,
        )
    z = ki_zugang.setzen(conn, daten.api_schluessel, schluessel = cfg.secret_key)
    LOG.info("OpenAI-Schlüssel hinterlegt")  # ohne Wert, auch nicht gekuerzt
    return _status_ausgabe(
        conn, cfg,
        hinterlegt = z.hinterlegt, endet_auf = z.endet_auf, geaendert_am = z.geaendert_am,
    )


@router.delete("/schluessel", response_model = StatusAusgabe)
def schluessel_entfernen(conn: Verbindung, cfg: Konfiguration) -> StatusAusgabe:
    if cfg.hosted:
        raise FachlicherFehler(
            "Der KI-Zugang wird bei dieser gehosteten Installation vom Betreiber bereitgestellt.",
            status = 403,
        )
    ki_zugang.entfernen(conn)
    LOG.info("OpenAI-Schlüssel entfernt")
    return _status_ausgabe(
        conn, cfg, hinterlegt = False, endet_auf = None, geaendert_am = None,
    )


# ------------------------------------------------------------------ Entwurf

def _bilder_pruefen(bilder: list[UploadFile], cfg: Settings) -> None:
    if len(bilder) > cfg.ki_max_bilder:
        raise FachlicherFehler(
            f"Bitte höchstens {cfg.ki_max_bilder} Bilder auswählen.",
            status = 413, feld = "bilder",
        )


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


class EigenerPreisAusgabe(BaseModel):
    titel: str
    preis: float


class EntwurfAusgabe(BaseModel):
    titel: str
    beschreibung: str
    zustand: str | None
    zustand_text: str | None
    kategorie: str | None
    #: Die geschaetzte Spanne (AP-4.5) - eine Einordnung, kein Preis.
    preis_von_euro: float | None
    preis_bis_euro: float | None
    preis_begruendung: str | None
    #: Nur gefuellt, wenn ein Mensch die Zahl bestaetigt hat. Sonst null, und
    #: dann bleibt das Preisfeld der Anzeige leer.
    preis_euro: float | None = None
    #: Eigene frueher verlangte Preise fuer Aehnliches. Der einzige belastbare
    #: Anker neben der Schaetzung.
    eigene_preise: list[EigenerPreisAusgabe] = []
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


class ErkennungAusgabe(BaseModel):
    """Ein Hintergrundlauf fuer die Anzeige im Dashboard und in der Queue."""

    id: int
    profil_slug: str
    zustand: str
    eingereicht_am: str
    gestartet_am: str | None
    beendet_am: str | None
    bilder: int
    entwurf: EntwurfAusgabe | None
    kosten: KostenAusgabe | None
    meldung: str | None


class ErkennungAnlegenEingabe(BaseModel):
    """Menschliche Entscheidungen zum lokalen Speichern eines Entwurfs."""

    antworten: dict[str, str] = Field(default_factory = dict)
    beschreibung: str | None = None
    kategorie: str | None = None
    versandpakete: list[str] = Field(default_factory = list)
    preis: float | None = None


def _als_ausgabe(
    e: entwurf_dienst.Entwurf,
    bestand: list[bestand_dienst.BestandsAnzeige] | None = None,
) -> EntwurfAusgabe:
    return EntwurfAusgabe(
        titel = e.titel,
        beschreibung = e.beschreibung,
        zustand = e.zustand,
        zustand_text = entwurf_dienst.ZUSTAND_BESCHRIFTUNG.get(e.zustand or ""),
        kategorie = e.kategorie,
        preis_von_euro = e.preis_von_euro,
        preis_bis_euro = e.preis_bis_euro,
        preis_begruendung = e.preis_begruendung,
        preis_euro = e.preis_euro,
        eigene_preise = [
            EigenerPreisAusgabe(titel = p.titel, preis = p.preis)
            for p in vorschlag_dienst.eigene_preise(e.titel, bestand or [])
        ],
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

    Dieser direkte Weg kostet Geld. Er legt nichts an und veraendert nichts.
    """
    wurzel = _profil_wurzel(conn, cfg, profil)

    # Vor dem Lesen und vor dem Anbieteraufruf: Auch ein direkter HTTP-Aufruf
    # darf die sichtbare Obergrenze der Installation nicht umgehen.
    _bilder_pruefen(bilder, cfg)

    inhalte = await _dateien_lesen(bilder)
    ergebnis = await entwurf_lauf.erzeugen(
        conn,
        cfg,
        profil_slug = profil,
        profil_wurzel = wurzel,
        inhalte = inhalte,
    )

    return EntwurfAntwort(
        # Der Bestand wird erst hier gelesen, nicht vor dem Anbieteraufruf:
        # Ohne brauchbaren Titel gaebe es nichts zu vergleichen.
        entwurf = _als_ausgabe(ergebnis.entwurf, bestand_dienst.bestand_lesen(wurzel)),
        kosten = KostenAusgabe(**entwurf_lauf.kosten_zu_dict(ergebnis.kosten)),
    )


def _erkennung_als_ausgabe(
    erkennung: erkennungswarteschlange.Erkennung,
    bestand: list[bestand_dienst.BestandsAnzeige] | None = None,
) -> ErkennungAusgabe:
    entwurf: EntwurfAusgabe | None = None
    if erkennung.entwurf is not None:
        entwurf = _als_ausgabe(
            entwurf_lauf.entwurf_aus_dict(erkennung.entwurf), bestand,
        )
    kosten = (
        None if erkennung.kosten is None
        else KostenAusgabe(
            **entwurf_lauf.kosten_zu_dict(entwurf_lauf.kosten_aus_dict(erkennung.kosten)),
        )
    )
    return ErkennungAusgabe(
        id = erkennung.id,
        profil_slug = erkennung.profil_slug,
        zustand = erkennung.zustand,
        eingereicht_am = erkennung.eingereicht_am,
        gestartet_am = erkennung.gestartet_am,
        beendet_am = erkennung.beendet_am,
        bilder = erkennung.bilder,
        entwurf = entwurf,
        kosten = kosten,
        meldung = erkennung.meldung,
    )


@router.post("/erkennungen", response_model = ErkennungAusgabe, status_code = 202)
async def erkennung_starten(
    request: Request,
    conn: Verbindung,
    cfg: Konfiguration,
    profil: Annotated[str, Form()],
    bilder: Annotated[list[UploadFile], File()],
) -> ErkennungAusgabe:
    """Nimmt Bilder an und reiht die teure Analyse im Hintergrund ein."""
    p = profile_dienst.nach_slug(conn, profil)
    wurzel = _profil_wurzel(conn, cfg, profil)
    if p is None:  # `_profil_wurzel` wirft bereits; nur fuer den Typchecker.
        raise FachlicherFehler("Profil nicht gefunden.", status = 404, feld = "profil")
    _bilder_pruefen(bilder, cfg)
    inhalte = await _dateien_lesen(bilder)
    if not inhalte:
        raise FachlicherFehler("Ohne Bild kann kein Entwurf erkannt werden.", status = 400, feld = "bilder")

    warteschlange: erkennungswarteschlange.ErkennungsWarteschlange = request.app.state.ki_warteschlange
    lauf = await warteschlange.einreihen(
        conn,
        profil_id = p.id,
        profil_slug = p.slug,
        profil_wurzel = wurzel,
        inhalte = inhalte,
    )
    return _erkennung_als_ausgabe(lauf)


@router.get("/erkennungen", response_model = list[ErkennungAusgabe])
def erkennungen(
    conn: Verbindung,
    cfg: Konfiguration,
    profil: Annotated[str, Query(min_length = 1, max_length = 32)],
) -> list[ErkennungAusgabe]:
    """Liefert laufende und pruefbare Entwuerfe eines Profils."""
    wurzel = _profil_wurzel(conn, cfg, profil)
    bestand = bestand_dienst.bestand_lesen(wurzel)
    return [
        _erkennung_als_ausgabe(lauf, bestand)
        for lauf in erkennungswarteschlange.liste(conn, profil)
    ]


@router.get("/erkennungen/{erkennung_id}", response_model = ErkennungAusgabe)
def erkennung_einzeln(
    erkennung_id: int,
    conn: Verbindung,
    cfg: Konfiguration,
    profil: Annotated[str, Query(min_length = 1, max_length = 32)],
) -> ErkennungAusgabe:
    """Liest einen Entwurf nur aus dem angefragten Profil."""
    wurzel = _profil_wurzel(conn, cfg, profil)
    lauf = erkennungswarteschlange.einzeln(conn, erkennung_id, profil)
    return _erkennung_als_ausgabe(lauf, bestand_dienst.bestand_lesen(wurzel))


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


def _anzeige_anlegen_aus_inhalten(
    wurzel: Path,
    *,
    roh_entwurf: dict[str, Any],
    roh_antworten: dict[str, Any],
    inhalte: list[bytes],
    kategorie: str | None,
    versandpakete: list[str],
    preis: float | None,
) -> AnlegenAntwort:
    """Legt einen bereits geprueften Entwurf mit seinen Bildern lokal an."""
    vorschlag = entwurf_dienst.aus_antwort(roh_entwurf)
    antworten = {str(k): str(v) for k, v in roh_antworten.items() if v is not None}
    fertig = entwurf_dienst.anwenden(vorschlag, antworten)

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

    # Ein Preis kommt nur ueber diesen Weg in die Anzeige - angeklickt oder
    # eingetippt, nie aus der Schaetzung, siehe `als_anzeigenfelder`.
    if preis is not None:
        if preis <= 0:
            raise FachlicherFehler(
                "Ein Preis muss groesser als null sein.", status = 422, feld = "preis",
            )
        felder["price"] = round(preis, 2)
        felder["price_type"] = "NEGOTIABLE"

    if versandpakete:
        felder["shipping_type"] = "SHIPPING"
        felder["shipping_options"] = versandpakete

    angelegt = anlegen_dienst.anlegen(wurzel, felder, inhalte)
    return AnlegenAntwort(
        datei = angelegt.datei, titel = angelegt.titel, bilder = angelegt.bilder,
    )


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
    preis: Annotated[float | None, Form()] = None,
) -> AnlegenAntwort:
    """Legt die Anzeige lokal an. Ohne Anbieter, ohne Kosten, ohne Veroeffentlichen.

    Die Anzeige landet als Datei unter `ads/` im Profilverzeichnis. Sie geht
    nicht online - dafuer braucht es einen ausdruecklichen Lauf (AP-4.6).
    """
    wurzel = _profil_wurzel(conn, cfg, profil)

    _bilder_pruefen(bilder, cfg)

    try:
        roh_entwurf: dict[str, Any] = json.loads(entwurf_json)
        roh_antworten: dict[str, Any] = json.loads(antworten_json or "{}")
    except ValueError as fehler:
        raise FachlicherFehler("Der Entwurf war unlesbar.", status = 400) from fehler
    if not isinstance(roh_entwurf, dict) or not isinstance(roh_antworten, dict):
        raise FachlicherFehler("Der Entwurf hatte die falsche Form.", status = 400)

    inhalte = await _dateien_lesen(bilder)
    return _anzeige_anlegen_aus_inhalten(
        wurzel,
        roh_entwurf = roh_entwurf,
        roh_antworten = roh_antworten,
        inhalte = inhalte,
        kategorie = kategorie,
        versandpakete = _pakete_lesen(versandpakete_json),
        preis = preis,
    )


@router.post("/erkennungen/{erkennung_id}/anlegen", response_model = AnlegenAntwort, status_code = 201)
def erkennung_anlegen(
    erkennung_id: int,
    daten: ErkennungAnlegenEingabe,
    request: Request,
    conn: Verbindung,
    cfg: Konfiguration,
    profil: Annotated[str, Query(min_length = 1, max_length = 32)],
) -> AnlegenAntwort:
    """Speichert einen fertigen Hintergrundentwurf lokal ohne neuen KI-Aufruf."""
    wurzel = _profil_wurzel(conn, cfg, profil)
    warteschlange: erkennungswarteschlange.ErkennungsWarteschlange = request.app.state.ki_warteschlange
    lauf = warteschlange.fuer_anlegen(conn, erkennung_id, profil)
    if lauf.entwurf is None:
        warteschlange.speichern_zuruecksetzen(conn, erkennung_id)
        raise FachlicherFehler("Zu diesem Lauf gibt es noch keinen Entwurf.", status = 409)

    roh_entwurf = dict(lauf.entwurf)
    if daten.beschreibung is not None:
        roh_entwurf["beschreibung"] = daten.beschreibung
    try:
        bilder = warteschlange.bilder_fuer_anlegen(conn, erkennung_id, profil, wurzel)
        ergebnis = _anzeige_anlegen_aus_inhalten(
            wurzel,
            roh_entwurf = roh_entwurf,
            roh_antworten = daten.antworten,
            inhalte = bilder,
            kategorie = daten.kategorie,
            versandpakete = _pakete_lesen(json.dumps(daten.versandpakete)),
            preis = daten.preis,
        )
    except Exception:
        warteschlange.speichern_zuruecksetzen(conn, erkennung_id)
        raise

    warteschlange.speichern_abgeschlossen(conn, erkennung_id, profil, wurzel)
    return ergebnis
