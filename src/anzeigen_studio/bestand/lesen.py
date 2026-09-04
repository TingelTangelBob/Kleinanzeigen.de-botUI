# SPDX-FileCopyrightText: © Anzeigen-Studio contributors
# SPDX-ArtifactOfProjectHomePage: https://github.com/TingelTangelBob/Kleinanzeigen.de-botUI/
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# Den lokalen Anzeigenbestand von der Platte lesen (AP-3.2).
#
# Grundsatz aus dem Projektplan: Die Platte ist die Wahrheit, eine Datenbank
# waere nur ein Index. Deshalb wird hier bei jeder Anfrage gelesen. Bei einem
# Bestand in der Groessenordnung eines privaten Kontos - Dutzende Anzeigen, nicht
# Zehntausende - ist das schnell genug, und es kann nichts veralten. Ein Index
# kommt, wenn er gebraucht wird, nicht vorher.

from __future__ import annotations

import logging
import re
import shutil
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Literal

from ruamel.yaml import YAML

from anzeigen_studio.core.errors import FachlicherFehler
from anzeigen_studio.katalog.daten import gemischte_versandgroessen

LOG = logging.getLogger(__name__)

#: Unterverzeichnisse eines Profils, in denen Anzeigen liegen koennen.
#:
#: `downloaded-ads` fuellt der Bot beim Konto-Download, `ads` ist das
#: Verzeichnis, auf das die erzeugte config.yaml zeigt (selbst angelegte
#: Anzeigen). `fremde-ads` nimmt Anzeigen auf, die per Link geholt wurden
#: (nicht aus dem eigenen Konto). Herkunft folgt dem Ordner, nicht einem
#: Marker in der YAML - bestehende Dateien ohne Marker bleiben eigene.
#: Oeffentlich seit AP-2.20: `loeschen` muss dieselbe Liste pruefen, sonst
#: liesse sich ueber den Loeschendpunkt eine Vorlage oder die Datenbank
#: erwischen. Zwei Kopien derselben Wahrheit waeren genau die Art Fehler, die
#: erst auffaellt, wenn jemand einen vierten Ordner ergaenzt.
ANZEIGEN_ORDNER = ("downloaded-ads", "ads", "fremde-ads")
_ANZEIGEN_ORDNER = ANZEIGEN_ORDNER
_FREMDE_ORDNER = "fremde-ads"
_EIGENE_ZIEL = "downloaded-ads"
Herkunft = Literal["eigene", "fremde"]

#: Bildendungen, die der Bot herunterlaedt - und zugleich die, die er beim
#: Hochladen wieder lesen kann (`ad_loading.resolve_ad_images`). WebP steht
#: bewusst nicht dabei, siehe `bilder.ERLAUBTE_FORMATE`.
BILD_ENDUNGEN = {".jpg", ".jpeg", ".png", ".gif"}
_BILD_ENDUNGEN = BILD_ENDUNGEN

_yaml = YAML(typ = "safe")


#: Die Dekoration, die kleinanzeigen.de dem Titel einer nicht mehr aktiven
#: Anzeige voranstellt. Sie ist kein Teil des Titels, sondern ein Statusbefund -
#: siehe `BestandsAnzeige.geloescht` und `webui/src/titel.ts`.
_GELOESCHT_PRAEFIX = re.compile(r"^Gel\u00f6scht\s*[\u2022\u00b7]\s*")


@dataclass(frozen = True, slots = True)
class BestandsAnzeige:
    """Eine Anzeige, wie sie auf der Platte liegt."""

    datei: str
    """Pfad der YAML, relativ zum Profilverzeichnis - zugleich der Schluessel."""

    ordner: str
    titel: str
    id: int | None = None
    art: str = "OFFER"
    aktiv: bool = True
    kategorie: str | None = None
    preis: float | None = None
    preistyp: str | None = None
    versandart: str | None = None
    versandkosten: float | None = None
    versandpakete: list[str] = field(default_factory = list)
    direkt_kaufen: bool = False
    bilder: int = 0
    vorschaubild: str | None = None
    erstellt_am: str | None = None
    aktualisiert_am: str | None = None
    neueinstellung_am: str | None = None
    faellig: bool = False
    lokal_geaendert: bool = False
    hinweise: list[str] = field(default_factory = list)
    unlesbar: str | None = None
    herkunft: Herkunft = "eigene"

    @property
    def geloescht(self) -> bool:
        """Eigene Anzeige, die auf der Plattform nicht mehr aktiv ist (AP-3.10).

        Klassifiziert wird ueber das bestehende YAML-Feld `active` - kein neues
        Feld. Der Bot setzt es beim Herunterladen aus der Profiluebersicht
        (`state == "active"`, siehe `docs/RUNDLAUF.md` Abschnitt 3). Geloescht,
        pausiert und "in Pruefung" fallen dort alle auf `active: false` zusammen;
        die Oberflaeche darf also nicht behaupten, die Anzeige sei sicher
        geloescht - nur, dass sie nicht mehr online ist.

        Drei Bedingungen zusammen, damit ein harmloser Entwurf nicht als
        geloescht erscheint:

        * `herkunft == "eigene"` - fremde Anzeigen aus `fremde-ads/` sind kein
          Konto-Bestand; ihr Status geht uns nichts an.
        * `id is not None` - die Anzeige hatte eine Anzeigennummer, war also
          einmal online. Ein lokal angelegter Entwurf ohne Nummer ist nichts
          "Geloeschtes".
        * `not aktiv` - `active: false` in der Datei.

        **Zweiter Weg ueber den Titel (AP-2.35).** Kleinanzeigen.de stellt dem
        Titel einer nicht mehr aktiven Anzeige in der Uebersicht "Geloescht \u2022"
        voran, und `extract.py` uebernimmt ihn woertlich. Das Praefix ist damit
        ein Befund der Plattform - genauso belastbar wie `active: false` und in
        manchen Faellen der einzige, den wir haben. Es zaehlt deshalb mit, und
        zwar auch fuer FREMDE Anzeigen: Bei denen kennen wir `active` oft nicht,
        aber wenn die Plattform den Titel so ausliefert, ist die Anzeige weg.
        Die Oberflaeche zeigt das Praefix nicht mehr an (`titel.ts`) - ohne
        diese Auswertung waere die Auskunft also ersatzlos verloren.
        """
        ueber_titel = _GELOESCHT_PRAEFIX.match(self.titel) is not None
        if ueber_titel:
            return True
        return self.herkunft == "eigene" and self.id is not None and not self.aktiv


def _als_text(wert: Any) -> str | None:
    if wert is None:
        return None
    if isinstance(wert, datetime):
        return wert.isoformat()
    return str(wert)


def _zeitpunkt(wert: Any) -> datetime | None:
    if isinstance(wert, datetime):
        return wert
    if isinstance(wert, str):
        try:
            return datetime.fromisoformat(wert)
        except ValueError:
            return None
    return None


def _hinweise_sammeln(daten: dict[str, Any]) -> list[str]:
    """Benennt, was beim Wieder-Hochladen Aerger macht.

    Die Faelle stammen aus der Verlustanalyse (`docs/RUNDLAUF.md`, AP-3.4). Sie
    hier zu erheben statt in der Oberflaeche hat den Grund, dass die Oberflaeche
    sonst dieselbe Regel ein zweites Mal kennen muesste.
    """
    hinweise: list[str] = []
    versandart = daten.get("shipping_type")
    kosten = daten.get("shipping_costs")
    pakete = daten.get("shipping_options") or []

    if versandart == "SHIPPING" and kosten is not None and not pakete:
        hinweise.append("versand_ohne_paket")
    if daten.get("sell_directly") and not pakete and daten.get("type") != "WANTED":
        hinweise.append("direktkauf_ohne_paket")
    if isinstance(pakete, list) and gemischte_versandgroessen(pakete):
        hinweise.append("versand_gemischte_groessen")
    if not (daten.get("images") or []):
        hinweise.append("ohne_bild")
    return hinweise


def _lokal_geaendert(daten: dict[str, Any]) -> bool:
    """Vergleicht den gespeicherten Inhaltsstempel mit dem der Datei.

    Gleiche Rechnung wie im Bot (`ad_loading.is_ad_changed`): Fehlt der
    gespeicherte Stempel, gilt die Anzeige als unveraendert - ein fehlender
    Stempel ist keine Aenderung, sondern eine Anzeige, die nie einen hatte.
    """
    gespeichert = daten.get("content_hash")
    if not gespeichert:
        return False
    try:
        from kleinanzeigen_bot.model.ad_model import AdPartial  # noqa: PLC0415 - Bot-Import bewusst lokal

        aktuell = AdPartial.model_validate(daten).update_content_hash().content_hash
    except Exception as fehler:  # noqa: BLE001 - eine unlesbare Anzeige darf die Liste nicht kippen
        # Die Datei hat einen Stempel, laesst sich aber nicht mehr pruefen -
        # jemand hat sie von Hand in einen ungueltigen Zustand gebracht. Im
        # Zweifel warnen: Das schlimmste Ergebnis eines Fehlalarms ist eine
        # Rueckfrage, das schlimmste Ergebnis des Schweigens ist eine
        # ueberschriebene Aenderung.
        LOG.debug("Inhaltsstempel nicht berechenbar, gilt als geaendert: %s", fehler)
        return True
    return aktuell is not None and aktuell != gespeichert


def _neueinstellung(daten: dict[str, Any], *, jetzt: datetime) -> tuple[str | None, bool]:
    """Wann die Anzeige laut eigener Einstellung neu eingestellt wird.

    Nachgebaut statt importiert: `ad_loading.is_ad_due_for_republication` ist
    keine Datenklasse, und der Upstream sagt nur fuer Dateiformate und CLI
    Stabilitaet zu (siehe NOTICE.md). Die Rechnung ist drei Zeilen lang - die
    Kopie ist billiger als die Abhaengigkeit.
    """
    intervall = daten.get("republication_interval")
    letzte = _zeitpunkt(daten.get("updated_on")) or _zeitpunkt(daten.get("created_on"))
    if letzte is None:
        # Nie veroeffentlicht: der Bot wuerde sofort einstellen.
        return None, True
    if not isinstance(intervall, int) or intervall <= 0:
        return None, False
    if letzte.tzinfo is None:
        letzte = letzte.replace(tzinfo = UTC)
    faellig_am = letzte + timedelta(days = intervall)
    return faellig_am.date().isoformat(), (jetzt - letzte).days >= intervall


def _vorschaubild(ordner: Path, daten: dict[str, Any]) -> tuple[str | None, int]:
    bilder = [str(b) for b in (daten.get("images") or [])]
    if not bilder:
        return None, 0
    erstes = Path(bilder[0]).name
    if (ordner / erstes).is_file():
        return erstes, len(bilder)
    # Die YAML nennt Dateien, die nicht (mehr) daliegen. Kein Grund, die
    # Anzeige zu verschweigen - aber auch kein Vorschaubild.
    return None, len(bilder)


def _herkunft_von(relativ: str) -> Herkunft:
    """Herkunft aus dem Bestandsordner, nicht aus der YAML."""
    kopf = relativ.split("/", 1)[0]
    return "fremde" if kopf == _FREMDE_ORDNER else "eigene"


def _anzeige_lesen(pfad: Path, profil_wurzel: Path, *, jetzt: datetime) -> BestandsAnzeige:
    relativ = pfad.relative_to(profil_wurzel).as_posix()
    ordner = pfad.parent.name
    herkunft = _herkunft_von(relativ)
    try:
        daten = _yaml.load(pfad.read_text(encoding = "utf-8")) or {}
    except Exception as fehler:  # noqa: BLE001 - eine kaputte Datei darf die Liste nicht kippen
        LOG.warning("Anzeigendatei %s ist nicht lesbar: %s", relativ, fehler)
        return BestandsAnzeige(
            datei = relativ, ordner = ordner, titel = pfad.stem,
            unlesbar = "Die Datei ist nicht lesbar.",
            herkunft = herkunft,
        )
    if not isinstance(daten, dict):
        return BestandsAnzeige(
            datei = relativ, ordner = ordner, titel = pfad.stem,
            unlesbar = "Die Datei enthält keine Anzeige.",
            herkunft = herkunft,
        )

    vorschau, bilder = _vorschaubild(pfad.parent, daten)
    neueinstellung_am, faellig = _neueinstellung(daten, jetzt = jetzt)
    kennung = daten.get("id")

    return BestandsAnzeige(
        datei = relativ,
        ordner = ordner,
        titel = str(daten.get("title") or pfad.stem),
        id = kennung if isinstance(kennung, int) else None,
        art = str(daten.get("type") or "OFFER"),
        aktiv = bool(daten.get("active", True)),
        kategorie = _als_text(daten.get("category")),
        preis = daten.get("price") if isinstance(daten.get("price"), (int, float)) else None,
        preistyp = _als_text(daten.get("price_type")),
        versandart = _als_text(daten.get("shipping_type")),
        versandkosten = daten.get("shipping_costs") if isinstance(daten.get("shipping_costs"), (int, float)) else None,
        versandpakete = [str(p) for p in (daten.get("shipping_options") or [])],
        direkt_kaufen = bool(daten.get("sell_directly")),
        bilder = bilder,
        vorschaubild = vorschau,
        erstellt_am = _als_text(daten.get("created_on")),
        aktualisiert_am = _als_text(daten.get("updated_on")),
        neueinstellung_am = neueinstellung_am,
        faellig = faellig,
        lokal_geaendert = _lokal_geaendert(daten),
        hinweise = _hinweise_sammeln(daten),
        herkunft = herkunft,
    )


def _dateien(profil_wurzel: Path) -> list[Path]:
    gefunden: list[Path] = []
    for name in _ANZEIGEN_ORDNER:
        ordner = profil_wurzel / name
        if not ordner.is_dir():
            continue
        gefunden.extend(sorted(ordner.rglob("*.yaml")))
        gefunden.extend(sorted(ordner.rglob("*.yml")))
    return gefunden


def anzeigendateien(profil_wurzel: Path) -> list[Path]:
    """Alle Anzeigendateien eines Profils. Oeffentlich fuer AP-3.5."""
    return _dateien(profil_wurzel)


def bestand_lesen(profil_wurzel: Path, *, jetzt: datetime | None = None) -> list[BestandsAnzeige]:
    """Liest alle Anzeigen eines Profils von der Platte."""
    if not profil_wurzel.is_dir():
        return []
    zeitpunkt = jetzt or datetime.now(UTC)
    anzeigen = [_anzeige_lesen(p, profil_wurzel, jetzt = zeitpunkt) for p in _dateien(profil_wurzel)]
    # Faellige zuerst, dann nach Titel - die Liste soll oben zeigen, was Arbeit
    # macht, nicht was zufaellig zuerst im Verzeichnis stand.
    return sorted(anzeigen, key = lambda a: (not a.faellig, a.titel.casefold()))


def lokal_geaenderte(profil_wurzel: Path) -> list[BestandsAnzeige]:
    """Anzeigen mit lokalen Aenderungen, die ein Download ueberschreiben wuerde."""
    return [a for a in bestand_lesen(profil_wurzel) if a.lokal_geaendert]


def herkunft_setzen(profil_wurzel: Path, datei: str, ziel: Herkunft) -> BestandsAnzeige:
    """Verschiebt eine Anzeige zwischen eigenen und fremden Ordnern.

    Nur der Bestandsordner wechselt. YAML und Bilder bleiben zusammen.
    Kein Massen-Umsortieren: nur dieser eine Aufruf.
    """
    if ziel not in ("eigene", "fremde"):
        raise FachlicherFehler("Herkunft muss eigene oder fremde sein.", status = 400, feld = "herkunft")

    wurzel = profil_wurzel.resolve()
    yaml_pfad = (wurzel / datei).resolve()
    if not yaml_pfad.is_relative_to(wurzel):
        raise FachlicherFehler("Ungültiger Pfad.", status = 400, feld = "datei")
    if yaml_pfad.suffix.lower() not in {".yaml", ".yml"}:
        raise FachlicherFehler("Das ist keine Anzeigendatei.", status = 400, feld = "datei")
    if not yaml_pfad.is_file():
        raise FachlicherFehler("Anzeige nicht gefunden.", status = 404)

    relativ = yaml_pfad.relative_to(wurzel).as_posix()
    teile = Path(relativ).parts
    if not teile or teile[0] not in _ANZEIGEN_ORDNER:
        raise FachlicherFehler("Anzeige liegt in keinem Bestandsordner.", status = 400, feld = "datei")

    bisher = _herkunft_von(relativ)
    if bisher == ziel:
        return _anzeige_lesen(yaml_pfad, wurzel, jetzt = datetime.now(UTC))

    quellordner = yaml_pfad.parent
    bucket = _FREMDE_ORDNER if ziel == "fremde" else _EIGENE_ZIEL
    zielordner = wurzel / bucket / quellordner.name
    if not zielordner.is_relative_to(wurzel):
        raise FachlicherFehler("Ungültiger Zielpfad.", status = 400)
    if zielordner.exists():
        raise FachlicherFehler(
            "Unter diesem Namen liegt dort schon eine Anzeige.",
            status = 409, feld = "datei",
        )
    zielordner.parent.mkdir(parents = True, exist_ok = True)
    shutil.move(str(quellordner), str(zielordner))
    neu = zielordner / yaml_pfad.name
    return _anzeige_lesen(neu, wurzel, jetzt = datetime.now(UTC))


def bildpfad(profil_wurzel: Path, datei: str, bild: str) -> Path:
    """Loest den Pfad eines Anzeigenbildes auf - mit Gegenprobe gegen Ausbruch.

    `datei` und `bild` kommen aus einer Anfrage. Beide werden zusammengesetzt
    und danach geprueft: Was nach dem Aufloesen nicht mehr unter dem Profil
    liegt, wird abgelehnt. Ein `..` im Namen soll nicht die Datenbank ausliefern.
    """
    wurzel = profil_wurzel.resolve()
    ziel = (wurzel / datei).resolve().parent / Path(bild).name
    ziel = ziel.resolve()
    if not ziel.is_relative_to(wurzel):
        raise FachlicherFehler("Ungültiger Bildpfad.", status = 400, feld = "bild")
    if ziel.suffix.lower() not in _BILD_ENDUNGEN:
        raise FachlicherFehler("Das ist kein Anzeigenbild.", status = 400, feld = "bild")
    if not ziel.is_file():
        raise FachlicherFehler("Bild nicht gefunden.", status = 404)
    return ziel
