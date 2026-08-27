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

from anzeigen_studio.bestand.lesen import BestandsAnzeige, bestand_lesen
from anzeigen_studio.core.errors import FachlicherFehler

if TYPE_CHECKING:
    from pathlib import Path

LOG = logging.getLogger(__name__)

#: Wie viele Bilder eine neu angelegte Anzeige hoechstens bekommt.
#: Kleinanzeigen erlaubt 20; mehr als das anzunehmen waere sinnlos.
MAX_BILDER: Final[int] = 20

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


def anlegen(
    profil_wurzel: Path,
    felder: dict[str, Any],
    bilder: list[bytes],
) -> BestandsAnzeige:
    """Schreibt eine neue Anzeigendatei samt Bildern und gibt sie zurueck.

    `felder` sind bereits geprueft (Titel, Beschreibung, ggf. Preis und
    Zustand). Was hier dazukommt, ist das Geruest, das jede Anzeigendatei
    braucht.
    """
    titel = str(felder.get("title") or "").strip()
    if not titel:
        raise FachlicherFehler("Ohne Titel lässt sich keine Anzeige anlegen.", feld = "titel")
    if len(bilder) > MAX_BILDER:
        raise FachlicherFehler(
            f"Mehr als {MAX_BILDER} Bilder nimmt Kleinanzeigen nicht.", feld = "bilder",
        )

    stamm = kurzname(titel)
    ordner = _freier_ordner(profil_wurzel / "ads", stamm)
    ordner.mkdir(parents = True)

    bildnamen: list[str] = []
    for nummer, inhalt in enumerate(bilder, start = 1):
        name = f"ad_{ordner.name}__img{nummer}{_endung(inhalt)}"
        (ordner / name).write_bytes(inhalt)
        bildnamen.append(name)

    daten: dict[str, Any] = {
        "active": True,
        "type": "OFFER",
        "title": titel,
        "description": str(felder.get("description") or ""),
        "category": felder.get("category"),
        "special_attributes": felder.get("special_attributes") or {},
        "price": felder.get("price"),
        "price_type": felder.get("price_type") or "NEGOTIABLE",
        # Versand bleibt offen. Ein geratener Versandweg waere teuer im
        # Wortsinn - und die Wahl haengt an Groesse und Gewicht, die auf
        # keinem Foto stehen.
        "shipping_type": None,
        "shipping_options": [],
        "sell_directly": False,
        "images": bildnamen,
        "created_on": datetime.now(UTC).isoformat(timespec = "seconds"),
    }

    pfad = ordner / f"ad_{ordner.name}.yaml"
    yaml = YAML()
    yaml.default_flow_style = False
    yaml.allow_unicode = True
    with pfad.open("w", encoding = "utf-8") as datei:
        datei.write(_SCHEMA_ZEILE + "\n")
        yaml.dump(daten, datei)

    relativ = pfad.relative_to(profil_wurzel).as_posix()
    LOG.info("Neue Anzeige angelegt: %s (%d Bilder)", relativ, len(bildnamen))

    for anzeige in bestand_lesen(profil_wurzel):
        if anzeige.datei == relativ:
            return anzeige
    # Kann nur passieren, wenn das Lesen die eben geschriebene Datei verwirft.
    raise FachlicherFehler("Die Anzeige wurde angelegt, ließ sich aber nicht lesen.", status = 500)
