# SPDX-FileCopyrightText: © Anzeigen-Studio contributors
# SPDX-ArtifactOfProjectHomePage: https://github.com/TingelTangelBob/Kleinanzeigen.de-botUI/
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# Profil sichern, ausfuehren, wieder einspielen (AP-3.6).
#
# WAS NICHT MITGEHT, UND WARUM DAS DER KERN DIESER DATEI IST.
#
# Ein Archiv wandert erfahrungsgemaess in eine Cloud, an einen zweiten Rechner
# oder in einen Chat. Deshalb wird hier NICHT ausgeschlossen, was gefaehrlich
# ist, sondern EINGESCHLOSSEN, was harmlos ist - eine Positivliste. Wer eine
# Sperrliste pflegt, vergisst irgendwann einen Eintrag, und der Fehler faellt
# erst auf, wenn das Archiv schon unterwegs ist.
#
# Draussen bleiben damit unter anderem:
#
#   * `.temp/browser-profile/` - das Chromium-Profil einer ANGEMELDETEN
#     Sitzung. Cookies darin sind so gut wie das Passwort. Das ist der
#     wichtigste Ausschluss dieser Datei.
#   * `.temp/diagnostics/` - Bildschirmfotos und vollstaendiges DOM, mit
#     Klarname, Adresse und Telefonnummer (siehe Einstellungen, Diagnose).
#   * `config.yaml` - wird vor jedem Lauf neu geschrieben und traegt die
#     Login-Platzhalter. Nichts, was man sichern muesste.
#   * `kleinanzeigen_bot.log` - Protokolle koennen alles enthalten.
#
# Zugangsdaten und der LLM-Schluessel liegen ohnehin nicht im Profilordner,
# sondern verschluesselt in der Datenbank (AP-1.4, AP-4.1). Sie koennen hier
# also gar nicht hineinrutschen - die Positivliste sorgt dafuer, dass das auch
# so bleibt, wenn jemand spaeter eine Datei danebenlegt.

from __future__ import annotations

import logging
import zipfile
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import TYPE_CHECKING, Final

from anzeigen_studio.bestand.lesen import ANZEIGEN_ORDNER, BILD_ENDUNGEN
from anzeigen_studio.bestand.vorlagen import ORDNER as VORLAGEN_ORDNER
from anzeigen_studio.core.errors import FachlicherFehler

if TYPE_CHECKING:
    from collections.abc import Iterator

LOG = logging.getLogger(__name__)

#: Verzeichnisse, deren Inhalt ins Archiv darf.
ERLAUBTE_ORDNER: Final[tuple[str, ...]] = (*ANZEIGEN_ORDNER, VORLAGEN_ORDNER)

#: Einzelne Dateien im Profilstamm, die mitgehen. `config.yaml` steht bewusst
#: nicht dabei: Sie wird vor jedem Lauf neu erzeugt.
ERLAUBTE_DATEIEN: Final[tuple[str, ...]] = ("nutzer.yaml",)

#: Endungen, die innerhalb der erlaubten Ordner mitgehen.
ERLAUBTE_ENDUNGEN: Final[frozenset[str]] = frozenset(
    {".yaml", ".yml", ".json"} | BILD_ENDUNGEN,
)

#: Groesse des hochgeladenen Archivs. Zwei Grenzen, weil es zwei verschiedene
#: Gefahren sind: Diese hier begrenzt, was ueber die Leitung kommt und auf der
#: Platte landet - `MAX_ENTPACKT_BYTES` darunter begrenzt, was daraus entpackt
#: wird (eine Zip-Bombe ist klein und wird gross).
#:
#: WICHTIG: Dieser Wert haengt an `client_max_body_size` fuer `/api/archiv/` in
#: docker/anzeigen-studio/nginx.conf. Wer hier etwas aendert, muss dort
#: nachziehen - sonst weist nginx den Upload mit einer englischen HTML-Seite
#: ab, bevor das Backend ihn ueberhaupt sieht, und die Oberflaeche zeigt einen
#: Fehler, den niemand einordnen kann.
MAX_ARCHIV_BYTES: Final[int] = 512 * 1024 * 1024

#: Grenzen gegen ein praepariertes Archiv. Ein Profil mit Dutzenden Anzeigen
#: liegt um Groessenordnungen darunter; wer hier anstoesst, hat kein Profil sondern
#: eine Zip-Bombe.
MAX_EINTRAEGE: Final[int] = 20_000
MAX_ENTPACKT_BYTES: Final[int] = 2 * 1024 * 1024 * 1024
MAX_EINZELDATEI_BYTES: Final[int] = 64 * 1024 * 1024

#: Name der Beipackdatei im Archiv. Sie beschreibt nur, sie steuert nichts -
#: der Import verlaesst sich auf keinen einzigen Wert daraus.
MANIFEST: Final[str] = "anzeigen-studio-archiv.json"


@dataclass(frozen = True, slots = True)
class Eintrag:
    """Eine Datei im Archiv, wie der Import sie sieht."""

    pfad: str
    """Pfad relativ zum Profilverzeichnis, immer mit Schrägstrichen."""

    bytes_gross: int
    ist_anzeige: bool


@dataclass(frozen = True, slots = True)
class Vorschau:
    """Was ein Import tun wuerde - ohne dass er etwas tut."""

    dateien: int = 0
    anzeigen: int = 0
    bilder: int = 0
    neu: list[str] = field(default_factory = list)
    doppelt: list[str] = field(default_factory = list)
    """Dateien, die es lokal schon gibt - Pfad identisch."""

    abgewiesen: list[str] = field(default_factory = list)
    """Was nicht durch die Positivliste kam, mit Begruendung."""


@dataclass(frozen = True, slots = True)
class Ergebnis:
    """Das Protokoll eines tatsaechlich ausgefuehrten Imports."""

    geschrieben: list[str] = field(default_factory = list)
    uebersprungen: list[str] = field(default_factory = list)
    ersetzt: list[str] = field(default_factory = list)
    abgewiesen: list[str] = field(default_factory = list)

    @property
    def zusammenfassung(self) -> str:
        teile = [f"{len(self.geschrieben)} übernommen"]
        if self.ersetzt:
            teile.append(f"{len(self.ersetzt)} ersetzt")
        if self.uebersprungen:
            teile.append(f"{len(self.uebersprungen)} übersprungen (schon vorhanden)")
        if self.abgewiesen:
            teile.append(f"{len(self.abgewiesen)} abgewiesen")
        return ", ".join(teile) + "."


# -- gemeinsame Pruefung ------------------------------------------------------

def _erlaubt(pfad: str) -> str | None:
    """Darf diese Datei ins Archiv bzw. aus ihm heraus? Sonst der Grund.

    Wird von Export UND Import benutzt. Zwei getrennte Regelwerke waeren die
    Art Fehler, die auffaellt, wenn ein Import etwas anlegt, das ein Export
    nie erzeugt haette.
    """
    if not pfad or pfad != pfad.strip():
        return "Leerer oder unsauberer Pfad."
    rein = PurePosixPath(pfad)
    if rein.is_absolute() or any(teil in ("..", "") for teil in rein.parts):
        # Zip-Slip: Ein Eintrag "../../etc/cron.d/x" wuerde sonst ausserhalb
        # des Profils landen.
        return "Pfad zeigt aus dem Profil heraus."
    teile = rein.parts
    if len(teile) == 1:
        if teile[0] in ERLAUBTE_DATEIEN:
            return None
        return "Keine der erlaubten Profildateien."
    if teile[0] not in ERLAUBTE_ORDNER:
        return f"Ordner „{teile[0]}“ gehört nicht ins Archiv."
    if rein.suffix.lower() not in ERLAUBTE_ENDUNGEN:
        return f"Dateityp „{rein.suffix or 'ohne Endung'}“ gehört nicht ins Archiv."
    return None


#: Groesse, bis zu der eine Datei fuer die Inhaltspruefung gelesen wird.
#: `nutzer.yaml` ist ein paar Kilobyte gross; alles daraeber ist keine
#: Konfiguration mehr und wird gar nicht erst geparst.
_PRUEFBAR_BYTES: Final[int] = 256 * 1024


def _inhalt_pruefen(pfad: str, rohdaten: bytes) -> str | None:
    """Prueft den INHALT einer Datei, nicht nur ihren Namen. Sonst der Grund.

    Bisher entschied allein der Pfad, ob eine Datei ins Profil darf. Fuer
    Anzeigen reicht das - eine kaputte Anzeigendatei zeigt die Bestandsliste
    als "unlesbar" an, mehr kann sie nicht anrichten.

    Fuer `nutzer.yaml` reicht es NICHT. Sie ist die Bot-Konfiguration, und
    darin gibt es Felder, die einen Codeausfuehrungspfad oeffnen
    (`browser.binary_location`, `browser.arguments`, `browser.extensions`,
    `ad_files` - AP-1.11). Ein fremdes Archiv koennte sie mitbringen.
    Gefaehrlich waeren sie erst beim naechsten Lauf, und dort werden sie
    zweimal abgestreift (`nutzerconfig.lesen` und
    `Warteschlange._nutzer_konfiguration`) - die Anwendung ist also nicht
    verwundbar. Trotzdem hat eine Datei, die die Oberflaeche selbst nie
    schreiben wuerde, nichts im Profil zu suchen: Sie waere eine Falle fuer
    den naechsten, der `nutzer.yaml` einmal ohne Filter liest.

    Geprueft wird mit derselben Funktion, die auch der Einstellungen-Endpunkt
    benutzt. Zwei Regelwerke waeren die Art Fehler, bei der ein Import etwas
    anlegt, das die Oberflaeche danach nicht mehr speichern kann.
    """
    if PurePosixPath(pfad).name != "nutzer.yaml" or len(PurePosixPath(pfad).parts) != 1:
        return None
    if len(rohdaten) > _PRUEFBAR_BYTES:
        return "nutzer.yaml ist unplausibel groß."

    from ruamel.yaml import YAML  # noqa: PLC0415 - nur hier gebraucht

    from anzeigen_studio.core import nutzerconfig  # noqa: PLC0415 - sonst Ringschluss beim Start

    try:
        geladen = YAML(typ = "safe").load(rohdaten.decode("utf-8"))
    except Exception:  # noqa: BLE001 - jede Lesefehlerart ist derselbe Befund
        return "nutzer.yaml ist keine lesbare YAML-Datei."
    if geladen is None:
        return None
    if not isinstance(geladen, dict):
        return "nutzer.yaml enthält keine Einstellungen."
    try:
        nutzerconfig.pruefen_und_saeubern(geladen)
    except FachlicherFehler as fehler:
        return f"nutzer.yaml wird nicht übernommen: {fehler.meldung}"
    return None


def _ist_anzeige(pfad: str) -> bool:
    rein = PurePosixPath(pfad)
    return (
        len(rein.parts) > 1
        and rein.parts[0] in ANZEIGEN_ORDNER
        and rein.suffix.lower() in {".yaml", ".yml", ".json"}
    )


def _ist_bild(pfad: str) -> bool:
    return PurePosixPath(pfad).suffix.lower() in BILD_ENDUNGEN


# -- Export -------------------------------------------------------------------

def _sammeln(profil_wurzel: Path) -> Iterator[tuple[Path, str]]:
    """Alle Dateien, die ins Archiv duerfen - als (Quelle, Zielpfad)."""
    wurzel = profil_wurzel.resolve()
    for name in ERLAUBTE_DATEIEN:
        datei = wurzel / name
        if datei.is_file():
            yield datei, name
    for ordner in ERLAUBTE_ORDNER:
        basis = wurzel / ordner
        if not basis.is_dir():
            continue
        for pfad in sorted(basis.rglob("*")):
            if not pfad.is_file() or pfad.is_symlink():
                # Ein Symlink im Profil koennte auf /etc/shadow zeigen; er
                # wuerde beim Packen dereferenziert. Also gar nicht erst.
                continue
            relativ = pfad.resolve().relative_to(wurzel).as_posix()
            if _erlaubt(relativ) is None:
                yield pfad, relativ


def manifest(profil_slug: str, dateien: int) -> dict[str, object]:
    """Beschreibung des Archivs. Reine Auskunft - der Import liest sie nicht."""
    return {
        "erzeugt_von": "Anzeigen-Studio",
        "erzeugt_am": datetime.now(UTC).isoformat(timespec = "seconds"),
        "profil": profil_slug,
        "dateien": dateien,
        "enthaelt": list(ERLAUBTE_ORDNER) + list(ERLAUBTE_DATEIEN),
        "enthaelt_nicht": [
            "Zugangsdaten und LLM-Schlüssel (liegen verschlüsselt in der Datenbank)",
            "Browserprofil (.temp/browser-profile - angemeldete Sitzung)",
            "Diagnoseartefakte (.temp/diagnostics)",
            "config.yaml (wird vor jedem Lauf neu erzeugt)",
            "Protokolle",
        ],
    }


def exportieren(profil_wurzel: Path, ziel: Path, *, profil_slug: str) -> int:
    """Schreibt das Profilarchiv nach `ziel`. Gibt die Dateizahl zurueck."""
    import json  # noqa: PLC0415 - nur fuer das Manifest gebraucht

    gepackt = list(_sammeln(profil_wurzel))
    ziel.parent.mkdir(parents = True, exist_ok = True)
    with zipfile.ZipFile(ziel, "w", compression = zipfile.ZIP_DEFLATED) as archiv:
        for quelle, name in gepackt:
            archiv.write(quelle, name)
        archiv.writestr(
            MANIFEST, json.dumps(manifest(profil_slug, len(gepackt)), ensure_ascii = False, indent = 2),
        )
    LOG.info("Profil %s exportiert: %d Datei(en) nach %s", profil_slug, len(gepackt), ziel.name)
    return len(gepackt)


def archivname(profil_slug: str) -> str:
    stempel = datetime.now(UTC).strftime("%Y-%m-%d")
    return f"anzeigen-studio_{profil_slug}_{stempel}.zip"


# -- Import -------------------------------------------------------------------

def _pruefbar(info: zipfile.ZipInfo) -> bool:
    """Nur die Konfigurationsdatei wird zur Pruefung ausgepackt, nichts sonst."""
    return (
        PurePosixPath(info.filename).name == "nutzer.yaml"
        and info.file_size <= _PRUEFBAR_BYTES
    )


def _eintraege_lesen(archiv: zipfile.ZipFile) -> tuple[list[Eintrag], list[str]]:
    """Trennt die brauchbaren Eintraege von den abgewiesenen."""
    gut: list[Eintrag] = []
    schlecht: list[str] = []
    gesamt = 0
    for info in archiv.infolist():
        if info.is_dir():
            continue
        if info.filename == MANIFEST:
            continue
        grund = _erlaubt(info.filename)
        if grund is not None:
            schlecht.append(f"{info.filename}: {grund}")
            continue
        if info.file_size > MAX_EINZELDATEI_BYTES:
            schlecht.append(f"{info.filename}: Datei ist zu groß.")
            continue
        gesamt += info.file_size
        if gesamt > MAX_ENTPACKT_BYTES:
            raise FachlicherFehler(
                "Das Archiv ist entpackt zu groß. Abgebrochen, bevor die Platte volläuft.",
                status = 413,
            )
        inhalt_grund = _inhalt_pruefen(
            info.filename, archiv.read(info) if _pruefbar(info) else b"",
        )
        if inhalt_grund is not None:
            schlecht.append(f"{info.filename}: {inhalt_grund}")
            continue
        gut.append(Eintrag(
            pfad = info.filename,
            bytes_gross = info.file_size,
            ist_anzeige = _ist_anzeige(info.filename),
        ))
    return gut, schlecht


def _oeffnen(archiv_datei: Path) -> zipfile.ZipFile:
    if not zipfile.is_zipfile(archiv_datei):
        raise FachlicherFehler("Das ist keine lesbare Archivdatei.", status = 400, feld = "datei")
    geoeffnet = zipfile.ZipFile(archiv_datei)
    if len(geoeffnet.infolist()) > MAX_EINTRAEGE:
        geoeffnet.close()
        raise FachlicherFehler("Das Archiv enthält zu viele Dateien.", status = 413, feld = "datei")
    return geoeffnet


def vorschau(archiv_datei: Path, profil_wurzel: Path) -> Vorschau:
    """Was ein Import tun wuerde. Schreibt nichts.

    `EXPECTATIONS.md` Paragraph 2 verlangt fuer Massenvorgaenge Vorschau,
    Duplikatbehandlung und ein Ergebnisprotokoll. Das hier ist die Vorschau -
    und sie benutzt exakt dieselbe Positivliste wie der Import darunter, sonst
    zeigte sie etwas anderes, als spaeter passiert.
    """
    wurzel = profil_wurzel.resolve()
    with _oeffnen(archiv_datei) as archiv:
        eintraege, abgewiesen = _eintraege_lesen(archiv)

    neu, doppelt = [], []
    for eintrag in eintraege:
        if (wurzel / eintrag.pfad).exists():
            doppelt.append(eintrag.pfad)
        else:
            neu.append(eintrag.pfad)

    return Vorschau(
        dateien = len(eintraege),
        anzeigen = sum(1 for e in eintraege if e.ist_anzeige),
        bilder = sum(1 for e in eintraege if _ist_bild(e.pfad)),
        neu = sorted(neu),
        doppelt = sorted(doppelt),
        abgewiesen = sorted(abgewiesen),
    )


def importieren(
    archiv_datei: Path, profil_wurzel: Path, *, vorhandene_ersetzen: bool = False,
) -> Ergebnis:
    """Spielt ein Archiv in ein Profil ein.

    Vorgabe ist, vorhandene Dateien NICHT zu ersetzen: Der haeufige Fall ist
    das Zurueckholen einzelner Anzeigen in einen bestehenden Bestand, und ein
    Import, der dabei stillschweigend lokale Aenderungen ueberschreibt, ist ein
    Datenverlust, den niemand bemerkt. Wer ersetzen will, sagt es ausdruecklich.
    """
    wurzel = profil_wurzel.resolve()
    geschrieben, uebersprungen, ersetzt = [], [], []

    with _oeffnen(archiv_datei) as archiv:
        eintraege, abgewiesen = _eintraege_lesen(archiv)
        for eintrag in eintraege:
            ziel = (wurzel / eintrag.pfad).resolve()
            # Dritte Gegenprobe, nach `_erlaubt` und der Pfadpruefung: Erst
            # hier steht fest, wo die Datei wirklich landet.
            if not ziel.is_relative_to(wurzel):
                abgewiesen.append(f"{eintrag.pfad}: Ziel läge außerhalb des Profils.")
                continue
            existiert = ziel.exists()
            if existiert and not vorhandene_ersetzen:
                uebersprungen.append(eintrag.pfad)
                continue
            ziel.parent.mkdir(parents = True, exist_ok = True)
            with archiv.open(eintrag.pfad) as quelle:
                ziel.write_bytes(quelle.read(MAX_EINZELDATEI_BYTES + 1))
            if existiert:
                ersetzt.append(eintrag.pfad)
            else:
                geschrieben.append(eintrag.pfad)

    ergebnis = Ergebnis(
        geschrieben = sorted(geschrieben),
        uebersprungen = sorted(uebersprungen),
        ersetzt = sorted(ersetzt),
        abgewiesen = sorted(abgewiesen),
    )
    LOG.info("Import nach %s: %s", wurzel.name, ergebnis.zusammenfassung)
    return ergebnis
