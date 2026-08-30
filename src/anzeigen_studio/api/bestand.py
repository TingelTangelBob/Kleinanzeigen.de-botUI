# SPDX-FileCopyrightText: © Anzeigen-Studio contributors
# SPDX-ArtifactOfProjectHomePage: https://github.com/TingelTangelBob/Kleinanzeigen.de-botUI/
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# HTTP-Endpunkte des lokalen Anzeigenbestands (AP-3.2).

from __future__ import annotations

import sqlite3
from typing import TYPE_CHECKING, Annotated

from fastapi import APIRouter, Depends, File, Query, Request, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from anzeigen_studio import bestand as bestand_dienst
from anzeigen_studio.bestand import anlegen as anlegen_dienst
from anzeigen_studio.bestand import stand as stand_dienst
from anzeigen_studio.bestand import vorlagen as vorlagen_dienst
from anzeigen_studio.core import db
from anzeigen_studio.core import profile as profile_dienst
from anzeigen_studio.core.errors import FachlicherFehler
from anzeigen_studio.core.settings import Settings
from anzeigen_studio.jobs import speicher

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path

    from anzeigen_studio.jobs.warteschlange import Warteschlange

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


def _warteschlange(request: Request) -> Warteschlange:
    ws: Warteschlange = request.app.state.warteschlange
    return ws


Verbindung = Annotated[sqlite3.Connection, Depends(_verbindung)]
Konfiguration = Annotated[Settings, Depends(_einstellungen)]
Schlange = Annotated["Warteschlange", Depends(_warteschlange)]


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


class AnzeigeInhalt(BaseModel):
    """Die Anzeige mit allen Feldern - Grundlage des Editors (AP-2.5)."""

    kopf: AnzeigeAusgabe
    felder: dict[str, object]
    aenderbar: list[str]


class SpeichernEingabe(BaseModel):
    datei: str = Field(min_length = 1, max_length = 400)
    felder: dict[str, object]


class SpeichernAusgabe(BaseModel):
    kopf: AnzeigeAusgabe
    hinweise: list[str]


@router.get("/anzeige", response_model = AnzeigeInhalt)
def anzeige_lesen(
    profil: str,
    datei: Annotated[str, Query(max_length = 400)],
    conn: Verbindung,
    cfg: Konfiguration,
) -> AnzeigeInhalt:
    """Eine einzelne Anzeige mit allen Feldern."""
    wurzel = _profil_wurzel(conn, cfg, profil)
    felder = bestand_dienst.rohdaten_lesen(wurzel, datei)
    kopf = next(
        (a for a in bestand_dienst.bestand_lesen(wurzel) if a.datei == datei),
        None,
    )
    if kopf is None:
        raise FachlicherFehler("Anzeige nicht gefunden.", status = 404)
    return AnzeigeInhalt(
        kopf = _ausgabe(kopf),
        felder = dict(felder),
        aenderbar = sorted(bestand_dienst.AENDERBAR),
    )


class UnterschiedAusgabe(BaseModel):
    feld: str
    beschriftung: str
    vorher: str
    jetzt: str


class VergleichAusgabe(BaseModel):
    """Was sich seit dem letzten Abgleich mit der Plattform geändert hat (AP-3.5)."""

    #: Wann die Datei zuletzt mit der Plattform übereinstimmte, und wodurch
    #: (`download` oder `update`). `null` heißt: kein Abgleich bekannt - dann
    #: sagt die Oberfläche das, statt einen Unterschied zu behaupten.
    stand_von: str | None
    quelle: str | None
    unterschiede: list[UnterschiedAusgabe]


@router.get("/vergleich", response_model = VergleichAusgabe)
def vergleich_lesen(
    profil: str,
    datei: Annotated[str, Query(max_length = 400)],
    conn: Verbindung,
    cfg: Konfiguration,
) -> VergleichAusgabe:
    """Was würde sich beim Hochladen auf der Plattform ändern? (AP-3.5)"""
    wurzel = _profil_wurzel(conn, cfg, profil)
    p = profile_dienst.nach_slug(conn, profil)
    if p is None:  # pragma: no cover - _profil_wurzel hat das schon geprueft
        raise FachlicherFehler("Profil nicht gefunden.", status = 404, feld = "profil")

    jetzt = bestand_dienst.rohdaten_lesen(wurzel, datei)
    gemerkt = stand_dienst.gemerkt(conn, p.id, datei)
    if gemerkt is None:
        return VergleichAusgabe(stand_von = None, quelle = None, unterschiede = [])

    vorher, quelle, zeitpunkt = gemerkt
    return VergleichAusgabe(
        stand_von = zeitpunkt,
        quelle = quelle,
        unterschiede = [
            UnterschiedAusgabe(
                feld = u.feld, beschriftung = u.beschriftung,
                vorher = u.vorher, jetzt = u.jetzt,
            )
            for u in stand_dienst.vergleichen(vorher, dict(jetzt))
        ],
    )


@router.put("/anzeige", response_model = SpeichernAusgabe)
def anzeige_speichern(
    profil: str,
    daten: SpeichernEingabe,
    conn: Verbindung,
    cfg: Konfiguration,
) -> SpeichernAusgabe:
    """Speichert geänderte Felder einer Anzeige.

    Der Inhaltsstempel bleibt stehen: Nur so bleibt sichtbar, dass die Anzeige
    von der zuletzt veröffentlichten Fassung abweicht - und dass ein Download
    sie überschreiben würde.
    """
    wurzel = _profil_wurzel(conn, cfg, profil)
    felder = dict(daten.felder)

    # Die Reihenfolge der Bilder darf nur umsortieren, nicht hinzufuegen oder
    # entfernen - dafuer gibt es eigene Wege, die auch die Dateien anfassen.
    if "images" in felder:
        roh = felder["images"] or []
        if not isinstance(roh, list):
            raise FachlicherFehler("Bilder müssen eine Liste sein.", status = 400, feld = "images")
        bestand_dienst.reihenfolge_pruefen(wurzel, daten.datei, [str(b) for b in roh])

    kopf, hinweise = bestand_dienst.speichern(wurzel, daten.datei, felder)
    return SpeichernAusgabe(kopf = _ausgabe(kopf), hinweise = hinweise)


class BildAusgabe(BaseModel):
    name: str
    kopf: AnzeigeAusgabe


#: Haeppchengroesse beim Einlesen. Klein genug, um nicht ins Gewicht zu
#: fallen, gross genug, um nicht in Tausenden Schleifendurchlaeufen zu enden.
_HAEPPCHEN = 64 * 1024


async def _begrenzt_lesen(bild: UploadFile, grenze: int) -> bytes:
    """Liest hoechstens *grenze* + 1 Bytes und weist alles Groessere ab.

    Das eine Byte darueber ist der ganze Trick: Es beweist, dass die Datei die
    Grenze reisst, ohne dass der Rest je in den Speicher muss. `await
    bild.read()` ohne Angabe wuerde die vollstaendige Datei laden - bei einem
    absichtlich grossen Upload also beliebig viel, und die Groessenpruefung
    kaeme erst danach.

    Abgewiesen wird hier, vor dem Anlegen der Datei. Damit kann kein halbes
    Bild im Datenverzeichnis liegenbleiben.
    """
    teile: list[bytes] = []
    gelesen = 0
    while gelesen <= grenze:
        # Nie mehr anfordern, als bis zum Beweisbyte fehlt - sonst laege am
        # Ende doch ein Haeppchen mehr im Speicher als zugesagt.
        haeppchen = await bild.read(min(_HAEPPCHEN, grenze + 1 - gelesen))
        if not haeppchen:
            break
        teile.append(haeppchen)
        gelesen += len(haeppchen)

    if gelesen > grenze:
        raise FachlicherFehler(
            f"Das Bild ist größer als {grenze // (1024 * 1024)} MB.",
            status = 413, feld = "bild",
        )
    return b"".join(teile)


@router.post("/bild", response_model = BildAusgabe, status_code = 201)
async def bild_hochladen(
    profil: str,
    datei: Annotated[str, Query(max_length = 400)],
    conn: Verbindung,
    cfg: Konfiguration,
    bild: Annotated[UploadFile, File()],
) -> BildAusgabe:
    """Legt ein Bild neben die Anzeige und trägt es hinten ein (AP-2.6)."""
    wurzel = _profil_wurzel(conn, cfg, profil)
    inhalt = await _begrenzt_lesen(bild, bestand_dienst.MAX_BYTES)
    name, kopf = bestand_dienst.bild_hinzufuegen(wurzel, datei, inhalt)
    return BildAusgabe(name = name, kopf = _ausgabe(kopf))


@router.delete("/bild", response_model = AnzeigeAusgabe)
def bild_entfernen(
    profil: str,
    datei: Annotated[str, Query(max_length = 400)],
    name: Annotated[str, Query(max_length = 200)],
    conn: Verbindung,
    cfg: Konfiguration,
) -> AnzeigeAusgabe:
    """Nimmt ein Bild aus der Anzeige und löscht die Datei."""
    wurzel = _profil_wurzel(conn, cfg, profil)
    return _ausgabe(bestand_dienst.bild_entfernen(wurzel, datei, name))


class HochladenEingabe(BaseModel):
    datei: str = Field(min_length = 1, max_length = 400)


class HochladenAusgabe(BaseModel):
    job_id: int
    anzeige: AnzeigeAusgabe


def _hochladbar(anzeige: bestand_dienst.BestandsAnzeige, felder: dict[str, object]) -> None:
    """Weist ab, was der Bot ohnehin nicht einstellen könnte.

    Lieber hier mit einem Satz erklären als mitten im Formular scheitern. Die
    Fälle stammen aus der Verlustanalyse (`docs/RUNDLAUF.md`) und aus der
    Prüfung, die `publishing_form.py` beim Ausfüllen selbst vornimmt.
    """
    if anzeige.unlesbar:
        raise FachlicherFehler("Diese Anzeige ist nicht lesbar.", status = 422)

    if anzeige.id is None:
        raise FachlicherFehler(
            "Diese Anzeige hat keine Anzeigennummer – sie war nie veröffentlicht. "
            "Bestehende Anzeigen lassen sich aktualisieren, neue einzustellen kommt später.",
            status = 422,
        )

    if "direktkauf_ohne_paket" in anzeige.hinweise:
        raise FachlicherFehler(
            "\u201eDirekt kaufen\u201c ist gesetzt, aber kein Versandpaket ausgewählt. Der Bot kann "
            "im Formular nur vordefinierte Pakete wählen – der Lauf würde mittendrin abbrechen. "
            "Wähle ein Paket oder schalte \u201eDirekt kaufen\u201c aus.",
            status = 422, feld = "shipping_options",
        )

    if "versand_ohne_paket" in anzeige.hinweise:
        raise FachlicherFehler(
            "Es sind eigene Versandkosten ohne Versandpaket gesetzt. Der Bot kann das im Formular "
            "nicht abbilden. Wähle ein Paket, das zum Preis passt.",
            status = 422, feld = "shipping_options",
        )

    # Dieselbe Pruefung wie beim Speichern. Eine Datei kann gemischte Groessen
    # tragen, ohne je durch das Speichern gegangen zu sein - heruntergeladen
    # oder von Hand bearbeitet.
    bestand_dienst.versandgroessen_pruefen(felder)

    fehler = bestand_dienst.pruefen_zum_veroeffentlichen(felder)
    if fehler:
        raise FachlicherFehler(" · ".join(fehler), status = 422)


@router.post("/hochladen", response_model = HochladenAusgabe, status_code = 202)
async def hochladen(
    profil: str,
    daten: HochladenEingabe,
    conn: Verbindung,
    cfg: Konfiguration,
    ws: Schlange,
) -> HochladenAusgabe:
    """Reiht einen Lauf ein, der genau diese eine Anzeige aktualisiert (AP-3.3).

    Bewusst `update` und nicht `publish`: `update` bearbeitet die bestehende
    Anzeige. `publish` löscht sie und stellt sie neu ein - Anzeigennummer,
    Aufrufe, Merker und Alter wären weg (siehe `docs/RUNDLAUF.md`).

    Der Lauf sieht ausschließlich diese eine Datei: Die Anzeigennummer steht im
    Auswahlschalter, und der Dateiausschnitt der erzeugten Konfiguration nennt
    nur sie. Zwei Grenzen für einen Vorgang, der etwas auf der Plattform
    verändert.
    """
    p = profile_dienst.nach_slug(conn, profil)
    if p is None:
        raise FachlicherFehler("Profil nicht gefunden.", status = 404, feld = "profil")
    wurzel = profile_dienst.pfade_fuer(cfg.profiles_dir, p.slug).wurzel

    felder = bestand_dienst.rohdaten_lesen(wurzel, daten.datei)
    anzeige = next(
        (a for a in bestand_dienst.bestand_lesen(wurzel) if a.datei == daten.datei), None,
    )
    if anzeige is None:
        raise FachlicherFehler("Anzeige nicht gefunden.", status = 404)

    _hochladbar(anzeige, dict(felder))

    job_id = await ws.einreihen(
        conn, p.id, "update", [f"--ads={anzeige.id}"],
        profil_verzeichnis = wurzel,
        anzeigen_glob = f"./{daten.datei}",
    )
    if speicher.holen(conn, job_id) is None:  # pragma: no cover - Schutz gegen stille Fehlschlaege
        raise FachlicherFehler("Der Lauf konnte nicht eingereiht werden.", status = 500)

    return HochladenAusgabe(job_id = job_id, anzeige = _ausgabe(anzeige))


class LinksEingabe(BaseModel):
    text: str = Field(min_length = 1, max_length = 20000)


class LinksAusgabe(BaseModel):
    neu: list[int]
    schon_vorhanden: list[int]
    unlesbare_zeilen: list[str]


class NachladenAusgabe(BaseModel):
    job_id: int
    nummern: list[int]


def _nummern_ordnen(conn: sqlite3.Connection, cfg: Settings, profil: str, text: str) -> LinksAusgabe:
    wurzel = _profil_wurzel(conn, cfg, profil)
    fund = bestand_dienst.nummern_lesen(text)
    vorhanden = {a.id for a in bestand_dienst.bestand_lesen(wurzel) if a.id is not None}
    return LinksAusgabe(
        neu = [n for n in fund.nummern if n not in vorhanden],
        schon_vorhanden = [n for n in fund.nummern if n in vorhanden],
        unlesbare_zeilen = fund.unlesbare_zeilen,
    )


class DuplizierenEingabe(BaseModel):
    datei: str = Field(max_length = 400)


@router.post("/duplizieren", response_model = AnzeigeAusgabe, status_code = 201)
def duplizieren(
    profil: str, daten: DuplizierenEingabe, conn: Verbindung, cfg: Konfiguration,
) -> AnzeigeAusgabe:
    """Legt eine Kopie einer Anzeige als neuen Entwurf an (AP-3.3).

    Nur lokal. Die Kopie hat keine Anzeigennummer und ist damit fuer den Bot
    eine neue Anzeige - das Original bleibt unangetastet.
    """
    wurzel = _profil_wurzel(conn, cfg, profil)
    return _ausgabe(anlegen_dienst.duplizieren(wurzel, daten.datei))


class VorlageAusgabe(BaseModel):
    datei: str
    ordner: str
    titel: str
    bilder: int
    vorschaubild: str | None
    erstellt_am: str | None
    unlesbar: str | None


def _vorlage_ausgabe(v: bestand_dienst.Vorlage) -> VorlageAusgabe:
    return VorlageAusgabe(
        datei = v.datei, ordner = v.ordner, titel = v.titel, bilder = v.bilder,
        vorschaubild = v.vorschaubild, erstellt_am = v.erstellt_am, unlesbar = v.unlesbar,
    )


class VorlageEingabe(BaseModel):
    datei: str = Field(max_length = 400)


@router.get("/vorlagen", response_model = list[VorlageAusgabe])
def vorlagen_auflisten(
    profil: str, conn: Verbindung, cfg: Konfiguration,
) -> list[VorlageAusgabe]:
    """Alle Vorlagen eines Profils (AP-3.3).

    Eigene Liste, nicht Teil des Bestands: Eine Vorlage ist keine Anzeige und
    hat auf der Plattform nichts verloren.
    """
    wurzel = _profil_wurzel(conn, cfg, profil)
    return [_vorlage_ausgabe(v) for v in vorlagen_dienst.lesen(wurzel)]


@router.post("/vorlagen", response_model = VorlageAusgabe, status_code = 201)
def vorlage_anlegen(
    profil: str, daten: VorlageEingabe, conn: Verbindung, cfg: Konfiguration,
) -> VorlageAusgabe:
    """Macht aus einer vorhandenen Anzeige eine Vorlage (AP-3.3).

    Die Anzeige bleibt, wie sie ist. Kopiert wird, nicht markiert - eine
    Markierung laege weiter unter `ads/`, wo der Bot sie faende.
    """
    wurzel = _profil_wurzel(conn, cfg, profil)
    return _vorlage_ausgabe(vorlagen_dienst.aus_anzeige(wurzel, daten.datei))


@router.post("/vorlagen/anwenden", response_model = AnzeigeAusgabe, status_code = 201)
def vorlage_anwenden(
    profil: str, daten: VorlageEingabe, conn: Verbindung, cfg: Konfiguration,
) -> AnzeigeAusgabe:
    """Erzeugt aus einer Vorlage eine neue Anzeige (AP-3.3).

    Nur lokal, ohne Anzeigennummer. Die Vorlage bleibt liegen und laesst sich
    erneut anwenden - sie wird benutzt, nicht verbraucht.
    """
    wurzel = _profil_wurzel(conn, cfg, profil)
    return _ausgabe(vorlagen_dienst.anwenden(wurzel, daten.datei))


@router.delete("/vorlagen", status_code = 204)
def vorlage_entfernen(
    profil: str, datei: str, conn: Verbindung, cfg: Konfiguration,
) -> None:
    """Loescht eine Vorlage samt Bildern. Anzeigen bleiben unberuehrt."""
    wurzel = _profil_wurzel(conn, cfg, profil)
    vorlagen_dienst.entfernen(wurzel, datei)


@router.post("/links-lesen", response_model = LinksAusgabe)
def links_lesen(
    profil: str, daten: LinksEingabe, conn: Verbindung, cfg: Konfiguration,
) -> LinksAusgabe:
    """Liest Anzeigennummern aus eingefügtem Text - ohne etwas zu tun (AP-3.7).

    Getrennt vom Holen, damit vor dem Lauf sichtbar ist, was er holen würde.
    """
    return _nummern_ordnen(conn, cfg, profil, daten.text)


@router.post("/nachladen", response_model = NachladenAusgabe, status_code = 202)
async def nachladen(
    profil: str, daten: LinksEingabe, conn: Verbindung, cfg: Konfiguration, ws: Schlange,
) -> NachladenAusgabe:
    """Holt Anzeigen zu eingefügten Links in den Bestand (AP-3.7).

    Nur lesend: Der Lauf ist derselbe `download`, den die Oberfläche schon
    kennt, nur mit einer Liste von Nummern statt „alle". Anzeigen, die es nicht
    mehr gibt, meldet er einzeln - zurückholen kann sie niemand.
    """
    p = profile_dienst.nach_slug(conn, profil)
    if p is None:
        raise FachlicherFehler("Profil nicht gefunden.", status = 404, feld = "profil")

    geordnet = _nummern_ordnen(conn, cfg, profil, daten.text)
    zu_holen = geordnet.neu
    if not zu_holen:
        raise FachlicherFehler(
            "In dem Text steckt keine Anzeigennummer, die noch fehlt."
            if geordnet.schon_vorhanden
            else "In dem Text steckt keine Anzeigennummer.",
            status = 400, feld = "text",
        )

    verzeichnis = profile_dienst.pfade_fuer(cfg.profiles_dir, p.slug).wurzel
    job_id = await ws.einreihen(
        conn, p.id, "download", [f"--ads={','.join(str(n) for n in zu_holen)}"],
        profil_verzeichnis = verzeichnis,
    )
    return NachladenAusgabe(job_id = job_id, nummern = zu_holen)
