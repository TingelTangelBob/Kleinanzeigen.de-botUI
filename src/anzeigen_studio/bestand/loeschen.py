# SPDX-FileCopyrightText: © Anzeigen-Studio contributors
# SPDX-ArtifactOfProjectHomePage: https://github.com/TingelTangelBob/Kleinanzeigen.de-botUI/
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# Anzeigen lokal loeschen (AP-2.20).
#
# WAS HIER NICHT PASSIERT: Es wird nichts auf kleinanzeigen.de geloescht.
# Der Upstream kann das (`delete`-Kommando), und genau deshalb steht es hier
# geschrieben: Dieser Dienst ruft es nicht auf, reiht keinen Lauf ein und
# spricht mit keinem Browser. Er entfernt Dateien von der Platte, mehr nicht.
# Eine Anzeige, die online steht, steht nach diesem Aufruf weiter online -
# nur ohne lokale Kopie.
#
# Die Trennung ist keine Vorsicht, sondern Produktentscheidung aus
# EXPECTATIONS.md: Kein Lauf gegen ein echtes Konto ohne ausdrueckliche
# Freigabe. Ein Loeschknopf, der stillschweigend die Plattform mit erwischt,
# waere genau der Unfall, den diese Regel verhindern soll.

from __future__ import annotations

import logging
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

from ruamel.yaml import YAML

from anzeigen_studio.bestand.lesen import ANZEIGEN_ORDNER, BILD_ENDUNGEN
from anzeigen_studio.core.errors import FachlicherFehler

if TYPE_CHECKING:
    from collections.abc import Sequence

LOG = logging.getLogger(__name__)

_yaml = YAML(typ = "safe")


@dataclass(frozen = True, slots = True)
class Geloescht:
    """Was ein Loeschaufruf tatsaechlich von der Platte genommen hat."""

    datei: str
    """Pfad der YAML, relativ zum Profil - derselbe Schluessel wie im Bestand."""

    titel: str
    """Titel aus der YAML, oder der Dateiname, wenn sie unlesbar war."""

    bilder: int
    """Wie viele Bilddateien mitgegangen sind."""

    ordner_entfernt: bool
    """Ob der ganze Anzeigenordner weg ist oder nur einzelne Dateien."""


def _pfad(profil_wurzel: Path, datei: str) -> Path:
    """Loest den Pfad einer Anzeigendatei auf - mit Gegenprobe gegen Ausbruch.

    Dieselben Schranken wie in `lesen.herkunft_setzen`, und aus demselben
    Grund: `datei` kommt aus einer Anfrage. Zusaetzlich muss die Datei in
    einem der drei Bestandsordner liegen. Ohne diese Bedingung liesse sich
    ueber diesen Endpunkt eine Vorlage oder die Datenbank loeschen.
    """
    wurzel = profil_wurzel.resolve()
    ziel = (wurzel / datei).resolve()
    if not ziel.is_relative_to(wurzel):
        raise FachlicherFehler("Ungültiger Pfad.", status = 400, feld = "datei")
    if ziel.suffix.lower() not in {".yaml", ".yml"}:
        raise FachlicherFehler("Das ist keine Anzeigendatei.", status = 400, feld = "datei")

    relativ = ziel.relative_to(wurzel).as_posix()
    teile = Path(relativ).parts
    if len(teile) < 2 or teile[0] not in ANZEIGEN_ORDNER:
        raise FachlicherFehler(
            "Anzeige liegt in keinem Bestandsordner.", status = 400, feld = "datei",
        )
    if not ziel.is_file():
        raise FachlicherFehler("Anzeige nicht gefunden.", status = 404, feld = "datei")
    return ziel


def _titel_und_bilder(pfad: Path) -> tuple[str, list[str]]:
    """Titel und Bildnamen aus der YAML. Eine kaputte Datei ist kein Fehler.

    Wer eine unlesbare Anzeige loeschen will, hat meist genau deshalb den
    Knopf gedrueckt. Ein Parserfehler darf das nicht verhindern - dann gehen
    eben nur die Dateien, die ohne die YAML zu finden sind.
    """
    try:
        daten: Any = _yaml.load(pfad.read_text(encoding = "utf-8")) or {}
    except Exception as fehler:  # noqa: BLE001 - eine kaputte Datei muss loeschbar bleiben
        LOG.warning("Anzeigendatei %s ist beim Löschen nicht lesbar: %s", pfad.name, fehler)
        return pfad.stem, []
    if not isinstance(daten, dict):
        return pfad.stem, []
    bilder = [Path(str(b)).name for b in (daten.get("images") or [])]
    return str(daten.get("title") or pfad.stem), bilder


def _andere_anzeigen_im_ordner(ordner: Path, ausser: Path) -> bool:
    """Liegt in diesem Ordner noch eine zweite Anzeige?

    `bestand_lesen` sucht mit `rglob`, ein Anzeigenordner darf also mehr als
    eine YAML enthalten. Der uebliche Fall ist eine - dann geht der ganze
    Ordner weg, wie bei Vorlagen. Gibt es eine zweite, waere `rmtree` ein
    stiller Datenverlust: Der Nutzer hat eine Anzeige zum Loeschen ausgewaehlt
    und zwei verloren.
    """
    for endung in ("*.yaml", "*.yml"):
        for gefunden in ordner.rglob(endung):
            if gefunden.resolve() != ausser.resolve():
                return True
    return False


def entfernen(profil_wurzel: Path, datei: str) -> Geloescht:
    """Loescht eine Anzeige von der Platte. Die Plattform bleibt unberuehrt.

    Im Normalfall geht der ganze Anzeigenordner - er enthaelt ausschliesslich
    diese Anzeige und ihre Bilder, und eine zurueckgelassene Bildhalde waere
    Muell, den niemand mehr zuordnen kann. Teilt sich der Ordner mit einer
    zweiten Anzeige, gehen nur die YAML und die Bilder, die sie nennt.
    """
    pfad = _pfad(profil_wurzel, datei)
    relativ = pfad.relative_to(profil_wurzel.resolve()).as_posix()
    titel, bildnamen = _titel_und_bilder(pfad)
    ordner = pfad.parent

    # Gegenprobe vor einem rekursiven Loeschen: Der Ordner muss selbst noch
    # unter einem Bestandsordner liegen und darf nicht der Bestandsordner sein.
    wurzel = profil_wurzel.resolve()
    bestandsordner = {(wurzel / name).resolve() for name in ANZEIGEN_ORDNER}
    ordner_loeschbar = (
        ordner.resolve() not in bestandsordner
        and not _andere_anzeigen_im_ordner(ordner, pfad)
    )

    if ordner_loeschbar:
        anzahl = sum(
            1 for p in ordner.rglob("*") if p.is_file() and p.suffix.lower() in BILD_ENDUNGEN
        )
        shutil.rmtree(ordner)
        LOG.info("Anzeige lokal entfernt: %s samt Ordner (%d Bilder)", relativ, anzahl)
        return Geloescht(datei = relativ, titel = titel, bilder = anzahl, ordner_entfernt = True)

    entfernte = 0
    for name in bildnamen:
        bild = (ordner / Path(name).name).resolve()
        # Auch hier: Der Name kommt aus einer Datei, die jemand von Hand
        # geschrieben haben kann.
        if not bild.is_relative_to(wurzel) or bild.suffix.lower() not in BILD_ENDUNGEN:
            continue
        if bild.is_file():
            bild.unlink()
            entfernte += 1
    pfad.unlink()
    LOG.info(
        "Anzeige lokal entfernt: %s (%d Bilder; Ordner bleibt, er trägt noch eine Anzeige)",
        relativ, entfernte,
    )
    return Geloescht(datei = relativ, titel = titel, bilder = entfernte, ordner_entfernt = False)


def mehrere_entfernen(profil_wurzel: Path, dateien: Sequence[str]) -> list[Geloescht]:
    """Loescht mehrere Anzeigen. Bricht beim ersten Fehler ab.

    Kein Weiterlaufen ueber Fehler hinweg: Wer fuenf Anzeigen ausgewaehlt hat
    und eine Fehlermeldung bekommt, muss wissen, was jetzt noch da ist. Der
    Aufrufer bekommt die Liste der bereits geloeschten mit - was dahinter
    kam, liegt unveraendert auf der Platte.
    """
    fertig: list[Geloescht] = []
    for datei in dateien:
        try:
            fertig.append(entfernen(profil_wurzel, datei))
        except FachlicherFehler as fehler:
            raise FachlicherFehler(
                f"{len(fertig)} von {len(dateien)} gelöscht, dann: {fehler.meldung}",
                status = fehler.status, feld = fehler.feld,
            ) from fehler
    return fertig
