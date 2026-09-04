# SPDX-FileCopyrightText: © Anzeigen-Studio contributors
# SPDX-ArtifactOfProjectHomePage: https://github.com/TingelTangelBob/Kleinanzeigen.de-botUI/
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# HTTP-Endpunkte fuer Sicherung, Export und Import (AP-3.6).
#
# Drei Endpunkte, und die Reihenfolge ist Absicht: erst herunterladen, dann
# ANSEHEN, dann einspielen. Ein Import ohne Vorschau waere ein Knopf, hinter
# dem sich der Bestand veraendert, ohne dass vorher jemand sagen konnte, was
# passiert - `EXPECTATIONS.md` Paragraph 2 verlangt fuer Massenvorgaenge
# ausdruecklich Vorschau, Duplikatbehandlung und Ergebnisprotokoll.
#
# Was hier NICHT passiert: Es wird nichts auf kleinanzeigen.de geaendert. Der
# Import legt Dateien auf der Platte ab, mehr nicht. Was davon online geht,
# entscheidet weiterhin ein ausdruecklich gestarteter Lauf.

from __future__ import annotations

import sqlite3
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING, Annotated

import anyio.to_thread
from fastapi import APIRouter, Depends, File, Query, Request, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel

from anzeigen_studio.bestand import archiv as archiv_dienst
from anzeigen_studio.core import db
from anzeigen_studio.core import profile as profile_dienst
from anzeigen_studio.core.errors import FachlicherFehler
from anzeigen_studio.core.settings import Settings

if TYPE_CHECKING:
    from collections.abc import Iterator

router = APIRouter(prefix = "/api/archiv", tags = ["Archiv"])

#: Haeppchengroesse beim Entgegennehmen des Uploads.
_HAEPPCHEN = 1024 * 1024


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
Ersetzen = Annotated[bool, Query(description = "Vorhandene Dateien überschreiben")]


class VorschauAusgabe(BaseModel):
    dateien: int
    anzeigen: int
    bilder: int
    neu: list[str]
    doppelt: list[str]
    abgewiesen: list[str]


class ImportAusgabe(BaseModel):
    geschrieben: list[str]
    ersetzt: list[str]
    uebersprungen: list[str]
    abgewiesen: list[str]
    zusammenfassung: str


def _profil(conn: sqlite3.Connection, cfg: Settings, slug: str) -> tuple[str, Path]:
    p = profile_dienst.nach_slug(conn, slug)
    if p is None:
        raise FachlicherFehler("Profil nicht gefunden.", status = 404, feld = "profil")
    return p.slug, profile_dienst.pfade_fuer(cfg.profiles_dir, p.slug).wurzel


def _wegwerfen(ziel: Path) -> None:
    ziel.unlink(missing_ok = True)


async def _upload_ablegen(datei: UploadFile, ziel: Path) -> None:
    """Nimmt den Upload entgegen, ohne ihn vollstaendig in den Speicher zu holen.

    Dieselbe Ueberlegung wie beim Bild-Upload (`api/bestand.py`): `await
    datei.read()` ohne Angabe wuerde ein absichtlich grosses Archiv komplett
    laden, und die Groessenpruefung kaeme zu spaet. Hier kommt dazu, dass ein
    Archiv ohnehin auf die Platte muss - `zipfile` braucht eine Datei, die es
    springen kann.

    Geschrieben wird ueber `anyio.to_thread`, nicht direkt. Ein Archiv darf
    hunderte Megabyte gross sein; synchron in der Ereignisschleife geschrieben
    wuerde es die gesamte Anwendung anhalten - keine zweite Anfrage, kein
    Fortschritt eines laufenden Jobs, bis die letzte Bytefolge auf der Platte
    ist.
    """
    grenze = archiv_dienst.MAX_ARCHIV_BYTES
    gelesen = 0
    with ziel.open("wb") as ausgabe:
        while gelesen <= grenze:
            haeppchen = await datei.read(min(_HAEPPCHEN, grenze + 1 - gelesen))
            if not haeppchen:
                break
            await anyio.to_thread.run_sync(ausgabe.write, haeppchen)
            gelesen += len(haeppchen)
    if gelesen > grenze:
        await anyio.to_thread.run_sync(_wegwerfen, ziel)
        raise FachlicherFehler(
            f"Das Archiv ist größer als {grenze // (1024 * 1024)} MB.",
            status = 413, feld = "datei",
        )


@router.get("/export")
def exportieren(
    conn: Verbindung, cfg: Konfiguration, profil: ProfilSlug,
) -> FileResponse:
    """Laedt das Profil als ZIP herunter - ohne Zugangsdaten, ohne Browserprofil.

    Was genau drin ist und was nicht, entscheidet die Positivliste in
    `bestand/archiv.py`; das Archiv traegt sie zusaetzlich als Beipackzettel
    bei sich.
    """
    slug, wurzel = _profil(conn, cfg, profil)
    name = archiv_dienst.archivname(slug)
    # In das Datenverzeichnis, nicht nach /tmp: Ein grosses Profil soll nicht
    # am tmpfs des Containers scheitern.
    ausgabe = cfg.data_dir / ".export" / name
    archiv_dienst.exportieren(wurzel, ausgabe, profil_slug = slug)
    return FileResponse(
        ausgabe, media_type = "application/zip", filename = name,
        headers = {"Content-Disposition": f'attachment; filename="{name}"'},
    )


@router.post("/vorschau", response_model = VorschauAusgabe)
async def vorschau(
    conn: Verbindung, cfg: Konfiguration, profil: ProfilSlug,
    datei: Annotated[UploadFile, File()],
) -> VorschauAusgabe:
    """Sagt, was ein Import täte. Schreibt nichts in den Bestand."""
    _slug, wurzel = _profil(conn, cfg, profil)
    with tempfile.TemporaryDirectory(dir = cfg.data_dir) as ordner:
        zwischen = Path(ordner) / "archiv.zip"
        await _upload_ablegen(datei, zwischen)
        gesehen = archiv_dienst.vorschau(zwischen, wurzel)
    return VorschauAusgabe(
        dateien = gesehen.dateien, anzeigen = gesehen.anzeigen, bilder = gesehen.bilder,
        neu = gesehen.neu, doppelt = gesehen.doppelt, abgewiesen = gesehen.abgewiesen,
    )


@router.post("/import", response_model = ImportAusgabe)
async def einspielen(
    conn: Verbindung, cfg: Konfiguration, profil: ProfilSlug,
    datei: Annotated[UploadFile, File()],
    *,
    ersetzen: Ersetzen = False,
) -> ImportAusgabe:
    """Spielt ein Archiv ein und gibt das Protokoll zurück.

    `ersetzen` ist standardmäßig aus: Der häufige Fall ist das Zurückholen
    einzelner Anzeigen in einen bestehenden Bestand, und ein Import, der dabei
    stillschweigend lokale Änderungen überschreibt, ist ein Datenverlust, den
    niemand bemerkt.
    """
    _slug, wurzel = _profil(conn, cfg, profil)
    with tempfile.TemporaryDirectory(dir = cfg.data_dir) as ordner:
        zwischen = Path(ordner) / "archiv.zip"
        await _upload_ablegen(datei, zwischen)
        ergebnis = archiv_dienst.importieren(
            zwischen, wurzel, vorhandene_ersetzen = ersetzen,
        )
    return ImportAusgabe(
        geschrieben = ergebnis.geschrieben, ersetzt = ergebnis.ersetzt,
        uebersprungen = ergebnis.uebersprungen, abgewiesen = ergebnis.abgewiesen,
        zusammenfassung = ergebnis.zusammenfassung,
    )
