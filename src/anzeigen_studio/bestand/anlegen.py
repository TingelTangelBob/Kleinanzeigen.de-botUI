# SPDX-FileCopyrightText: © Anzeigen-Studio contributors
# SPDX-ArtifactOfProjectHomePage: https://github.com/TingelTangelBob/Kleinanzeigen.de-botUI/
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# Eine neue Anzeige im Bestand anlegen (AP-3.3, AP-4.6).
#
# Der Ordner ist `ads/`, nicht `downloaded-ads/`. Das ist keine Kosmetik: Der
# Bot sucht zum Veroeffentlichen unter `./ads/**/ad_*.{yaml,yml,json}`. Eine
# selbst angelegte Anzeige, die dort nicht liegt, waere fuer `publish`
# unsichtbar - genau der Fehler, an dem der Rundlauf am 2026-08-25 schon einmal
# gescheitert ist.
#
# Ohne `id` und ohne `content_hash`. Beide setzt der Bot nach dem ersten
# erfolgreichen Veroeffentlichen selbst. Eine erfundene Nummer waere schlimmer
# als keine: Der Bot haelt eine Anzeige mit `id` fuer bereits online.

from __future__ import annotations

import logging
import re
import unicodedata
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, Final

from ruamel.yaml import YAML

from anzeigen_studio.bestand.bearbeiten import rohdaten_lesen
from anzeigen_studio.bestand.lesen import BestandsAnzeige, bestand_lesen, bildpfad
from anzeigen_studio.core.errors import FachlicherFehler

if TYPE_CHECKING:
    from pathlib import Path

LOG = logging.getLogger(__name__)

#: Wie viele Bilder eine neu angelegte Anzeige hoechstens bekommt.
#: Kleinanzeigen erlaubt 20; mehr als das anzunehmen waere sinnlos.
MAX_BILDER: Final[int] = 20

#: Kleinanzeigen begrenzt den Titel. Gleiche Zahl wie im KI-Modul.
_TITEL_MAX: Final[int] = 65

#: Kopfzeile, die auch die heruntergeladenen Dateien tragen. Sie schaltet in
#: Editoren die Schemapruefung ein und ist der einzige Grund, warum hier
#: ueberhaupt von Hand geschrieben wird statt nur `yaml.dump`.
_SCHEMA_ZEILE: Final[str] = (
    "# yaml-language-server: $schema=https://raw.githubusercontent.com/"
    "Second-Hand-Friends/kleinanzeigen-bot/refs/heads/main/schemas/ad.schema.json"
)

#: Endungen, die der Bot beim Hochladen wieder lesen kann
#: (`ad_loading.resolve_ad_images`). Siehe `bestand/bilder.py`.
_ENDUNG_ZU_SIGNATUR: Final[tuple[tuple[bytes, str], ...]] = (
    (b"\xff\xd8\xff", ".jpg"),
    (b"\x89PNG\r\n\x1a\n", ".png"),
    (b"GIF87a", ".gif"),
    (b"GIF89a", ".gif"),
)


def _endung(inhalt: bytes) -> str:
    for signatur, endung in _ENDUNG_ZU_SIGNATUR:
        if inhalt.startswith(signatur):
            return endung
    raise FachlicherFehler(
        "Das ist kein Bild. Erlaubt sind JPEG, PNG und GIF.", status = 415, feld = "bilder",
    )


def kurzname(titel: str) -> str:
    """Macht aus einem Titel einen Ordnernamen ohne Ueberraschungen.

    Umlaute werden ausgeschrieben statt zerlegt: `ae` ist lesbar, das
    zerlegte `a` mit kombinierendem Trema waere es nicht - und je nach
    Dateisystem kaeme es unterschiedlich zurueck.
    """
    ersetzt = (titel.lower()
               .replace("ä", "ae").replace("ö", "oe").replace("ü", "ue")
               .replace("ß", "ss"))
    ohne_zeichen = unicodedata.normalize("NFKD", ersetzt).encode("ascii", "ignore").decode("ascii")
    gesaeubert = re.sub(r"[^a-z0-9]+", "-", ohne_zeichen).strip("-")
    return gesaeubert[:60] or "anzeige"


def _freier_ordner(ads: Path, stamm: str) -> Path:
    """Findet einen noch unbenutzten Ordnernamen.

    Zwei Anzeigen duerfen denselben Titel haben - zwei Ordner nicht. Gezaehlt
    wird bis 100; wer so weit kommt, hat ein anderes Problem als den Namen.
    """
    kandidat = ads / stamm
    if not kandidat.exists():
        return kandidat
    for nummer in range(2, 101):
        kandidat = ads / f"{stamm}-{nummer}"
        if not kandidat.exists():
            return kandidat
    raise FachlicherFehler(
        "Es gibt schon zu viele Anzeigen mit diesem Titel.", status = 409, feld = "titel",
    )


def schreiben(
    profil_wurzel: Path,
    felder: dict[str, Any],
    bilder: list[bytes],
    *,
    unterordner: str = "ads",
    praefix: str = "ad",
) -> str:
    """Schreibt eine Anzeigendatei samt Bildern und gibt ihren relativen Pfad.

    `felder` sind bereits geprueft (Titel, Beschreibung, ggf. Preis und
    Zustand). Was hier dazukommt, ist das Geruest, das jede Anzeigendatei
    braucht.

    `unterordner` und `praefix` gibt es wegen der Vorlagen (AP-3.3). Eine
    Vorlage ist dateiformatgleich zu einer Anzeige - deshalb schreibt sie
    dieselbe Funktion -, darf aber vom Bot nicht gefunden werden. Sie landet
    unter `vorlagen/` und heisst `vorlage_*`. Beides einzeln reicht schon:
    Der Bot sucht unter `./ads/**/ad_*.{yaml,yml,json}`. Zusammen ueberlebt
    die Trennung auch, dass jemand den Ordner spaeter woanders hin kopiert.
    """
    titel = str(felder.get("title") or "").strip()
    if not titel:
        raise FachlicherFehler("Ohne Titel lässt sich keine Anzeige anlegen.", feld = "titel")
    if len(bilder) > MAX_BILDER:
        raise FachlicherFehler(
            f"Mehr als {MAX_BILDER} Bilder nimmt Kleinanzeigen nicht.", feld = "bilder",
        )

    stamm = kurzname(titel)
    ordner = _freier_ordner(profil_wurzel / unterordner, stamm)
    ordner.mkdir(parents = True)

    bildnamen: list[str] = []
    for nummer, inhalt in enumerate(bilder, start = 1):
        name = f"{praefix}_{ordner.name}__img{nummer}{_endung(inhalt)}"
        (ordner / name).write_bytes(inhalt)
        bildnamen.append(name)

    # Was der Aufrufer mitgibt, bleibt stehen; das Geruest fuellt nur, was
    # fehlt. Der Unterschied ist beim Duplizieren wesentlich: Dort sollen
    # Versand, Kontakt und Kategorie mitkommen - das ist der ganze Sinn einer
    # Kopie. Beim KI-Entwurf werden diese Felder gar nicht erst mitgegeben und
    # bleiben deshalb leer: Ein geratener Versandweg waere teuer im Wortsinn,
    # und die Wahl haengt an Groesse und Gewicht, die auf keinem Foto stehen.
    daten: dict[str, Any] = dict(felder)
    daten["title"] = titel
    daten["description"] = str(felder.get("description") or "")
    daten["images"] = bildnamen
    daten["created_on"] = datetime.now(UTC).isoformat(timespec = "seconds")

    for schluessel, vorgabe in (
        ("active", True),
        ("type", "OFFER"),
        ("category", None),
        ("special_attributes", {}),
        ("price", None),
        ("price_type", "NEGOTIABLE"),
        ("shipping_type", None),
        ("shipping_options", []),
        ("sell_directly", False),
    ):
        daten.setdefault(schluessel, vorgabe)

    pfad = ordner / f"{praefix}_{ordner.name}.yaml"
    yaml = YAML()
    yaml.default_flow_style = False
    yaml.allow_unicode = True
    with pfad.open("w", encoding = "utf-8") as datei:
        datei.write(_SCHEMA_ZEILE + "\n")
        yaml.dump(daten, datei)

    relativ = pfad.relative_to(profil_wurzel).as_posix()
    LOG.info("Datei angelegt: %s (%d Bilder)", relativ, len(bildnamen))
    return relativ


def anlegen(
    profil_wurzel: Path,
    felder: dict[str, Any],
    bilder: list[bytes],
) -> BestandsAnzeige:
    """Legt eine neue Anzeige unter `ads/` an und gibt sie zurueck.

    Der Ordner ist `ads/`, nicht `downloaded-ads/` - siehe Kopfkommentar.
    """
    relativ = schreiben(profil_wurzel, felder, bilder)

    for anzeige in bestand_lesen(profil_wurzel):
        if anzeige.datei == relativ:
            return anzeige
    # Kann nur passieren, wenn das Lesen die eben geschriebene Datei verwirft.
    raise FachlicherFehler("Die Anzeige wurde angelegt, ließ sich aber nicht lesen.", status = 500)


#: Was beim Duplizieren NICHT mitkommt.
#:
#: Jedes dieser Felder beschreibt die Anzeige auf der Plattform, nicht den
#: Gegenstand. `id` waere der schlimmste Mitreisende: Der Bot haelt eine
#: Anzeige mit Nummer fuer bereits online und wuerde beim naechsten Lauf das
#: ORIGINAL ueberschreiben, statt die Kopie einzustellen.
_NICHT_KOPIEREN: Final[frozenset[str]] = frozenset({
    "id",
    "created_on",
    "updated_on",
    "content_hash",
})

#: Zaehler, die bei einer Kopie wieder bei null anfangen.
_ZURUECKSETZEN: Final[dict[str, Any]] = {
    "repost_count": 0,
    "price_reduction_count": 0,
}

#: Damit die Kopie in der Liste nicht mit dem Original zu verwechseln ist.
KOPIE_ZUSATZ: Final[str] = " (Kopie)"


def duplizieren(profil_wurzel: Path, datei: str) -> BestandsAnzeige:
    """Legt eine Kopie einer vorhandenen Anzeige als neuen Entwurf an (AP-3.3).

    Gedacht fuer den haeufigen Fall, dass jemand mehrere aehnliche Gegenstaende
    verkauft: Kategorie, Versand, Zustand und Beschreibungsgeruest stehen dann
    schon, geaendert werden nur Titel, Bilder und Preis.

    Die Kopie landet wie jeder Entwurf unter `ads/` und ohne Anzeigennummer.
    """
    felder, bilder, titel = kopierbares_lesen(profil_wurzel, datei)
    felder["title"] = (titel + KOPIE_ZUSATZ)[:_TITEL_MAX]

    LOG.info("Anzeige %s wird dupliziert (%d Bilder)", datei, len(bilder))
    return anlegen(profil_wurzel, felder, bilder)


def kopierbares_lesen(
    profil_wurzel: Path, datei: str,
) -> tuple[dict[str, Any], list[bytes], str]:
    """Liest aus einer vorhandenen Datei, was in eine Kopie gehoert.

    Gibt Felder, Bildinhalte und den Titel zurueck - ohne alles, was die
    Anzeige auf der Plattform beschreibt statt den Gegenstand. Gemeinsame
    Grundlage von `duplizieren` und der Vorlagen (AP-3.3): Beide sind
    "aus dieser Datei wird eine neue", sie unterscheiden sich nur im Ziel.
    """
    daten = rohdaten_lesen(profil_wurzel, datei)

    titel = str(daten.get("title") or "").strip()
    if not titel:
        raise FachlicherFehler("Die Anzeige hat keinen Titel.", status = 422, feld = "titel")

    # Die Bilder werden mitkopiert, nicht verlinkt: Wer das Original spaeter
    # loescht, soll die Kopie nicht mit entwerten.
    bilder: list[bytes] = []
    for name in daten.get("images") or []:
        if not isinstance(name, str):
            continue
        quelle = bildpfad(profil_wurzel, datei, name)
        if quelle.is_file():
            bilder.append(quelle.read_bytes())

    felder = {
        schluessel: wert
        for schluessel, wert in daten.items()
        if schluessel not in _NICHT_KOPIEREN and schluessel != "images"
    }
    felder.update(_ZURUECKSETZEN)
    return felder, bilder, titel
