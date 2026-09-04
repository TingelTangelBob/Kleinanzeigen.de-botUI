# SPDX-FileCopyrightText: © Anzeigen-Studio contributors
# SPDX-ArtifactOfProjectHomePage: https://github.com/TingelTangelBob/Kleinanzeigen.de-botUI/
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# Vorlagen (AP-3.3).
#
# EINE VORLAGE IST KEINE ANZEIGE. Das ist die ganze Schwierigkeit dieses
# Moduls, und es ist keine begriffliche Feinheit: Der Bot veroeffentlicht,
# was er unter `./ads/**/ad_*.{yaml,yml,json}` findet. Eine Vorlage, die dort
# laege, ginge beim naechsten `publish`-Lauf mit online - ein Geruest mit
# Platzhaltertitel und ohne fertige Beschreibung, oeffentlich sichtbar unter
# echtem Namen.
#
# Deshalb zwei Trennungen statt einer:
#
#   1. Vorlagen liegen unter `vorlagen/`, nicht unter `ads/`.
#   2. Ihre Dateien heissen `vorlage_*`, nicht `ad_*`.
#
# Jede fuer sich genuegt schon, um den Bot fernzuhalten. Zusammen ueberleben
# sie auch den Fall, dass jemand einen Vorlagenordner spaeter nach `ads/`
# kopiert oder das Glob-Muster erweitert wird. Bei einer Datei, deren
# versehentliche Veroeffentlichung oeffentlich sichtbar waere, ist die zweite
# Sperre ihren Satz Code wert.
#
# `bestand_lesen` sieht Vorlagen ebenfalls nicht: Es liest `downloaded-ads`
# und `ads`. Vorlagen tauchen also nicht in der Anzeigenliste auf, koennen
# nicht hochgeladen, verlaengert oder geloescht werden wie Anzeigen - sie
# haben ihre eigene Liste und genau zwei Verben: anwenden und entfernen.

from __future__ import annotations

import logging
import shutil
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Final

from ruamel.yaml import YAML

from anzeigen_studio.bestand.anlegen import anlegen, kopierbares_lesen, schreiben
from anzeigen_studio.core.errors import FachlicherFehler

if TYPE_CHECKING:
    from pathlib import Path

    from anzeigen_studio.bestand.lesen import BestandsAnzeige

LOG = logging.getLogger(__name__)

#: Wo Vorlagen liegen - bewusst neben `ads/`, nicht darin.
ORDNER: Final[str] = "vorlagen"

#: Dateipraefix. Siehe Kopfkommentar: die zweite Sperre.
PRAEFIX: Final[str] = "vorlage"

_yaml = YAML(typ = "safe")

#: Was eine Vorlage niemals traegt. `id` ist der gefaehrlichste Eintrag: Eine
#: Vorlage mit Anzeigennummer wuerde beim Anwenden eine Kopie erzeugen, die
#: der Bot fuer die bereits online stehende Anzeige haelt - und die er beim
#: naechsten Lauf ueberschreibt, statt sie einzustellen.
_VERBOTEN: Final[frozenset[str]] = frozenset({"id", "content_hash"})


@dataclass(frozen = True, slots = True)
class Vorlage:
    """Eine Vorlage, wie sie auf der Platte liegt."""

    datei: str
    """Pfad der YAML, relativ zum Profilverzeichnis - zugleich der Schluessel."""

    ordner: str
    titel: str
    bilder: int = 0
    vorschaubild: str | None = None
    erstellt_am: str | None = None
    unlesbar: str | None = None


def _dateien(profil_wurzel: Path) -> list[Path]:
    wurzel = profil_wurzel / ORDNER
    if not wurzel.is_dir():
        return []
    return sorted(wurzel.glob(f"*/{PRAEFIX}_*.yaml"))


def _lesen(pfad: Path, profil_wurzel: Path) -> Vorlage:
    relativ = pfad.relative_to(profil_wurzel).as_posix()
    try:
        daten: Any = _yaml.load(pfad.read_text(encoding = "utf-8"))
    except Exception as fehler:  # noqa: BLE001 - eine kaputte Vorlage darf die Liste nicht sprengen
        grund = str(fehler).splitlines()[0].strip()
        return Vorlage(
            datei = relativ, ordner = pfad.parent.name, titel = pfad.parent.name,
            unlesbar = grund,
        )
    if not isinstance(daten, dict):
        return Vorlage(
            datei = relativ, ordner = pfad.parent.name, titel = pfad.parent.name,
            unlesbar = "Die Datei enthält keine Anzeige.",
        )

    bilder = [name for name in (daten.get("images") or []) if isinstance(name, str)]
    return Vorlage(
        datei = relativ,
        ordner = pfad.parent.name,
        titel = str(daten.get("title") or pfad.parent.name),
        bilder = len(bilder),
        vorschaubild = bilder[0] if bilder else None,
        erstellt_am = (str(daten["created_on"]) if daten.get("created_on") else None),
    )


def lesen(profil_wurzel: Path) -> list[Vorlage]:
    """Alle Vorlagen eines Profils, nach Titel sortiert."""
    vorlagen = [_lesen(pfad, profil_wurzel) for pfad in _dateien(profil_wurzel)]
    return sorted(vorlagen, key = lambda v: v.titel.casefold())


def _pfad(profil_wurzel: Path, datei: str) -> Path:
    """Loest den Pfad einer Vorlage auf - mit Gegenprobe gegen Ausbruch.

    Strenger als `bestand._pfad`: Dort genuegt es, unter dem Profil zu
    bleiben. Hier muss die Datei zusaetzlich unter `vorlagen/` liegen und das
    Vorlagenpraefix tragen. Sonst liesse sich ueber die Vorlagen-Endpunkte
    eine echte Anzeige loeschen.
    """
    wurzel = profil_wurzel.resolve()
    ziel = (wurzel / datei).resolve()
    if not ziel.is_relative_to(wurzel / ORDNER):
        raise FachlicherFehler("Das ist keine Vorlage.", status = 400, feld = "datei")
    if not ziel.name.startswith(f"{PRAEFIX}_") or ziel.suffix.lower() not in {".yaml", ".yml"}:
        raise FachlicherFehler("Das ist keine Vorlage.", status = 400, feld = "datei")
    if not ziel.is_file():
        raise FachlicherFehler("Vorlage nicht gefunden.", status = 404)
    return ziel


def aus_anzeige(profil_wurzel: Path, datei: str) -> Vorlage:
    """Macht aus einer vorhandenen Anzeige eine Vorlage.

    Die Anzeige selbst bleibt unangetastet - markiert wird nichts, kopiert
    wird. Eine Markierung an der Anzeigendatei waere der naheliegende Weg und
    der falsche: Sie laege weiter unter `ads/`, der Bot faende sie weiter, und
    die Sperre haette nur aus einem Feld bestanden, das er nicht liest.
    """
    felder, bilder, titel = kopierbares_lesen(profil_wurzel, datei)
    felder["title"] = titel

    # Gegenprobe, obwohl `kopierbares_lesen` das schon leistet: Diese Zusage
    # ist zu wichtig, um sie an einer anderen Funktion haengen zu lassen.
    for schluessel in _VERBOTEN:
        felder.pop(schluessel, None)

    relativ = schreiben(
        profil_wurzel, felder, bilder, unterordner = ORDNER, praefix = PRAEFIX,
        # Vorlagen sehen die Faelligkeitslogik des Bots nie (AP-3.9); ihr
        # `created_on` ist rein lokal das "angelegt am" fuer die Vorlagenliste.
        mit_erstellzeit = True,
    )
    LOG.info("Vorlage aus %s angelegt: %s (%d Bilder)", datei, relativ, len(bilder))

    for vorlage in lesen(profil_wurzel):
        if vorlage.datei == relativ:
            return vorlage
    raise FachlicherFehler("Die Vorlage wurde angelegt, ließ sich aber nicht lesen.", status = 500)


def anwenden(profil_wurzel: Path, datei: str) -> BestandsAnzeige:
    """Erzeugt aus einer Vorlage eine neue Anzeige unter `ads/`.

    Die Vorlage bleibt liegen. Genau das unterscheidet sie vom Entwurf: Sie
    wird angewendet, nicht verbraucht.

    Kein "(Kopie)" im Titel, anders als beim Duplizieren. Dort ist der Zusatz
    eine Warnung - zwei fast gleiche Anzeigen im Bestand sind sonst nicht
    auseinanderzuhalten. Hier waere er Unsinn: Die neue Anzeige ist keine
    Kopie einer Anzeige, sondern die erste ihrer Art.
    """
    _pfad(profil_wurzel, datei)
    felder, bilder, titel = kopierbares_lesen(profil_wurzel, datei)
    felder["title"] = titel

    LOG.info("Vorlage %s wird angewendet (%d Bilder)", datei, len(bilder))
    return anlegen(profil_wurzel, felder, bilder)


def entfernen(profil_wurzel: Path, datei: str) -> None:
    """Loescht eine Vorlage samt ihrem Ordner.

    Der ganze Ordner geht, nicht nur die YAML: Er enthaelt ausschliesslich die
    Bilder dieser Vorlage, und eine zurueckgelassene Bildhalde waere Muell,
    den niemand mehr zuordnen kann.
    """
    pfad = _pfad(profil_wurzel, datei)
    ordner = pfad.parent

    # Gegenprobe vor einem rekursiven Loeschen: Der Ordner muss ein direktes
    # Kind von `vorlagen/` sein. Ohne sie haenge das `rmtree` an einem Pfad,
    # den `_pfad` zwar geprueft hat, dessen Elternteil aber ein anderer ist.
    if ordner.parent.resolve() != (profil_wurzel / ORDNER).resolve():
        raise FachlicherFehler("Das ist keine Vorlage.", status = 400, feld = "datei")

    shutil.rmtree(ordner)
    LOG.info("Vorlage entfernt: %s", datei)
