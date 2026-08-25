# SPDX-FileCopyrightText: © Anzeigen-Studio contributors
# SPDX-ArtifactOfProjectHomePage: https://github.com/TingelTangelBob/Kleinanzeigen.de-botUI/
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# Bilder einer Anzeige verwalten (AP-2.6).
#
# Die Bilder liegen als Dateien neben der YAML, und die YAML fuehrt ihre
# Reihenfolge. Beides gehoert zusammen: Eine Datei ohne Eintrag laedt der Bot
# nie hoch, ein Eintrag ohne Datei laesst ihn scheitern. Alle Aenderungen hier
# fassen deshalb immer beides an.
#
# Der Dateiname folgt dem Muster des Bots (`<stamm>__img<N>.<endung>`). Nicht
# aus Aehnlichkeitsliebe: Der Bot benennt beim Herunterladen genau so, und wer
# den Bestand auf der Kommandozeile ansieht, soll nicht zwei Sorten Namen
# vorfinden.

from __future__ import annotations

import logging
import re
from typing import TYPE_CHECKING

from anzeigen_studio.bestand.bearbeiten import _pfad, rohdaten_lesen, speichern  # noqa: PLC2701 - dieselbe Schicht
from anzeigen_studio.core.errors import FachlicherFehler

if TYPE_CHECKING:
    from pathlib import Path

    from anzeigen_studio.bestand.lesen import BestandsAnzeige

LOG = logging.getLogger(__name__)

#: Groesse je Bild. Kleinanzeigen selbst nimmt deutlich weniger an; die Grenze
#: hier soll vor allem verhindern, dass ein Fehlgriff das Datenverzeichnis
#: fuellt.
MAX_BYTES = 15 * 1024 * 1024

#: Erkannt wird am Inhalt, nicht an der Endung. Eine `.jpg`, die keine ist,
#: faellt sonst erst beim Hochladen auf - dann aber mitten in einem Lauf.
_SIGNATUREN: tuple[tuple[bytes, str], ...] = (
    (b"\xff\xd8\xff", ".jpg"),
    (b"\x89PNG\r\n\x1a\n", ".png"),
    (b"GIF87a", ".gif"),
    (b"GIF89a", ".gif"),
)

_NUMMER = re.compile(r"__img(\d+)\.", re.IGNORECASE)


def _endung(inhalt: bytes) -> str:
    for signatur, endung in _SIGNATUREN:
        if inhalt.startswith(signatur):
            return endung
    if inhalt[:4] == b"RIFF" and inhalt[8:12] == b"WEBP":
        return ".webp"
    raise FachlicherFehler(
        "Das ist kein Bild. Erlaubt sind JPEG, PNG, WebP und GIF.",
        status = 415, feld = "bild",
    )


def _naechste_nummer(ordner: Path, stamm: str) -> int:
    """Die naechste freie Nummer - auch wenn zwischendrin geloescht wurde."""
    hoechste = 0
    for vorhanden in ordner.glob(f"{stamm}__img*"):
        treffer = _NUMMER.search(vorhanden.name)
        if treffer:
            hoechste = max(hoechste, int(treffer.group(1)))
    return hoechste + 1


def _bilder(daten: dict[str, object]) -> list[str]:
    roh = daten.get("images") or []
    return [str(b) for b in roh] if isinstance(roh, list) else []


def bild_hinzufuegen(
    profil_wurzel: Path,
    datei: str,
    inhalt: bytes,
) -> tuple[str, BestandsAnzeige]:
    """Legt ein Bild neben die Anzeige und traegt es hinten ein."""
    if not inhalt:
        raise FachlicherFehler("Die Datei ist leer.", status = 400, feld = "bild")
    if len(inhalt) > MAX_BYTES:
        raise FachlicherFehler(
            f"Das Bild ist größer als {MAX_BYTES // (1024 * 1024)} MB.",
            status = 413, feld = "bild",
        )

    pfad = _pfad(profil_wurzel, datei)
    ordner = pfad.parent
    stamm = pfad.stem
    name = f"{stamm}__img{_naechste_nummer(ordner, stamm)}{_endung(inhalt)}"

    (ordner / name).write_bytes(inhalt)

    daten = rohdaten_lesen(profil_wurzel, datei)
    kopf, _ = speichern(profil_wurzel, datei, {"images": [*_bilder(daten), name]})
    LOG.info("Bild %s zu %s hinzugefügt", name, datei)
    return name, kopf


def bild_entfernen(profil_wurzel: Path, datei: str, name: str) -> BestandsAnzeige:
    """Nimmt ein Bild aus der Anzeige und loescht die Datei.

    Geloescht wird nur, was auch in der Anzeige steht. Ein Name, der dort nicht
    vorkommt, wird abgewiesen - damit ist der Weg zu fremden Dateien zu, ohne
    sich auf die Pfadpruefung allein zu verlassen.
    """
    pfad = _pfad(profil_wurzel, datei)
    daten = rohdaten_lesen(profil_wurzel, datei)
    vorhanden = _bilder(daten)

    if name not in vorhanden:
        raise FachlicherFehler("Dieses Bild gehört nicht zur Anzeige.", status = 404, feld = "bild")

    kopf, _ = speichern(profil_wurzel, datei, {"images": [b for b in vorhanden if b != name] or None})

    ziel = pfad.parent / name
    try:
        ziel.unlink(missing_ok = True)
    except OSError as fehler:
        # Der Eintrag ist raus, die Datei nicht - das ist der harmlosere von
        # beiden Zustaenden und kein Grund, den Vorgang scheitern zu lassen.
        LOG.warning("Bilddatei %s ließ sich nicht löschen: %s", ziel, fehler)
    return kopf


def reihenfolge_pruefen(profil_wurzel: Path, datei: str, bilder: list[str]) -> None:
    """Stellt sicher, dass eine neue Reihenfolge nur vorhandene Bilder nennt."""
    pfad = _pfad(profil_wurzel, datei)
    daten = rohdaten_lesen(profil_wurzel, datei)
    vorher = set(_bilder(daten))
    neu = set(bilder)

    if neu - vorher:
        raise FachlicherFehler(
            "Die Reihenfolge nennt Bilder, die nicht zur Anzeige gehören.",
            status = 400, feld = "images",
        )
    if vorher - neu:
        raise FachlicherFehler(
            "Beim Sortieren darf kein Bild verschwinden. Zum Entfernen gibt es einen eigenen Weg.",
            status = 400, feld = "images",
        )
    fehlend = [b for b in bilder if not (pfad.parent / b).is_file()]
    if fehlend:
        raise FachlicherFehler(
            f"Diese Bilddateien fehlen: {', '.join(fehlend)}", status = 404, feld = "images",
        )
