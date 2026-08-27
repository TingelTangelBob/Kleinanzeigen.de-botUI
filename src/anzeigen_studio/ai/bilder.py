# SPDX-FileCopyrightText: © Anzeigen-Studio contributors
# SPDX-ArtifactOfProjectHomePage: https://github.com/TingelTangelBob/Kleinanzeigen.de-botUI/
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# Bilder fuer den Versand an den KI-Anbieter vorbereiten (AP-4.7).
#
# Zwei Gruende, warum hier ueberhaupt etwas passiert, und der zweite ist der
# wichtigere:
#
# 1. KOSTEN. Ein Bild wird beim Anbieter in Token umgerechnet, kachelweise:
#    70 Grundtoken plus 140 je 512-px-Kachel. 768 px ergeben vier Kacheln, also
#    630 Token. Ein Handyfoto mit 4032 px waere ein Vielfaches davon, ohne fuer
#    die Erkennung eines Verkaufsgegenstands mehr zu liefern.
#
# 2. DATENSCHUTZ. Fotos von Verkaufsgegenstaenden zeigen oft mehr als den
#    Gegenstand - die Wohnung, ein Kennzeichen, Papiere im Hintergrund. Und sie
#    tragen EXIF-Daten: Aufnahmezeit, Kameramodell, bei Handys regelmaessig die
#    GPS-Koordinaten des Aufnahmeorts, also in aller Regel die Wohnadresse.
#    Diese Daten haben beim Anbieter nichts zu suchen. Das Verkleinern loest
#    das Problem nicht mit; EXIF ueberlebt eine Groessenaenderung.
#
# Der Weg ueber `Image.new` und `paste` statt `save` auf dem geladenen Bild ist
# Absicht: Ein frisch angelegtes Bild traegt keine Metadaten, die versehentlich
# mitwandern koennten. Nichts mitzunehmen ist sicherer, als Bekanntes zu
# entfernen - eine Liste zu pflegen, was alles weg muss, geht irgendwann schief.

from __future__ import annotations

import base64
import io
import logging
from dataclasses import dataclass
from typing import Final

from anzeigen_studio.core.errors import FachlicherFehler

LOG = logging.getLogger(__name__)

#: Qualitaet des erzeugten JPEG. 82 ist der uebliche Kompromiss - darunter
#: werden Kanten sichtbar weich, darueber waechst nur die Datei.
_JPEG_QUALITAET: Final[int] = 82

#: Wie viele Bilder hoechstens in eine Anfrage gehen. Jedes weitere kostet
#: Token, ohne viel beizutragen: Was auf dem vierten Foto steht und auf keinem
#: der ersten drei, entscheidet selten ueber Titel und Zustand.
MAX_BILDER: Final[int] = 4

#: Groesse, ab der eine hochgeladene Datei gar nicht erst geoeffnet wird.
#: Vor dem Dekodieren geprueft, nicht danach - ein absichtlich praepariertes
#: Bild soll keinen Speicher belegen duerfen.
MAX_EINGABE_BYTES: Final[int] = 20 * 1024 * 1024


@dataclass(frozen = True, slots = True)
class VorbereitetesBild:
    """Ein Bild, wie es den Rechner verlaesst."""

    #: Als data-URL, direkt in die Anfrage einsetzbar.
    daten_url: str
    breite: int
    hoehe: int
    bytes_vorher: int
    bytes_nachher: int


def vorbereiten(inhalt: bytes, *, kante: int) -> VorbereitetesBild:
    """Verkleinert ein Bild, entfernt alle Metadaten und gibt es als data-URL zurueck.

    `kante` ist die laengste zulaessige Seite. Kleinere Bilder werden NICHT
    vergroessert - das kostet Token, ohne Bildinformation hinzuzufuegen.
    """
    if len(inhalt) > MAX_EINGABE_BYTES:
        raise FachlicherFehler(
            f"Das Bild ist größer als {MAX_EINGABE_BYTES // (1024 * 1024)} MB.",
            status = 413, feld = "bilder",
        )

    try:
        from PIL import Image  # noqa: PLC0415 - nur hier gebraucht
    except ImportError as fehler:  # pragma: no cover - im Abbild liegt Pillow
        raise FachlicherFehler(
            "Die Bildbibliothek fehlt in dieser Installation.", status = 500,
        ) from fehler

    try:
        with Image.open(io.BytesIO(inhalt)) as geoeffnet:
            # Ausrichtung anwenden, solange die EXIF-Angabe noch da ist. Danach
            # ist sie weg - ein hochkant aufgenommenes Foto laege sonst quer.
            from PIL import ImageOps  # noqa: PLC0415 - nur hier gebraucht
            gedreht = ImageOps.exif_transpose(geoeffnet) or geoeffnet
            gedreht = gedreht.convert("RGB")

            breite, hoehe = gedreht.size
            faktor = min(1.0, kante / max(breite, hoehe))
            if faktor < 1.0:
                gedreht = gedreht.resize(
                    (max(1, round(breite * faktor)), max(1, round(hoehe * faktor))),
                    Image.Resampling.LANCZOS,
                )

            # Neues, leeres Bild: Es traegt keine Metadaten, die mitwandern
            # koennten. Siehe Kopfkommentar.
            sauber = Image.new("RGB", gedreht.size)
            sauber.paste(gedreht)
    except FachlicherFehler:
        raise
    except Exception as fehler:  # noqa: BLE001 - jedes kaputte Bild landet hier
        raise FachlicherFehler(
            "Das Bild ließ sich nicht lesen. Erlaubt sind JPEG, PNG und GIF.",
            status = 415, feld = "bilder",
        ) from fehler

    puffer = io.BytesIO()
    sauber.save(puffer, format = "JPEG", quality = _JPEG_QUALITAET, optimize = True)
    roh = puffer.getvalue()

    return VorbereitetesBild(
        daten_url = "data:image/jpeg;base64," + base64.b64encode(roh).decode("ascii"),
        breite = sauber.width,
        hoehe = sauber.height,
        bytes_vorher = len(inhalt),
        bytes_nachher = len(roh),
    )


def alle_vorbereiten(inhalte: list[bytes], *, kante: int) -> list[VorbereitetesBild]:
    """Bereitet mehrere Bilder vor und begrenzt ihre Zahl.

    Ueberzaehlige werden weggelassen, nicht abgelehnt: Wer sechs Fotos
    hochlaedt, will einen Entwurf und keine Fehlermeldung.
    """
    if not inhalte:
        raise FachlicherFehler("Ohne Bild gibt es nichts zu erkennen.", status = 400, feld = "bilder")

    ausgewaehlt = inhalte[:MAX_BILDER]
    if len(inhalte) > MAX_BILDER:
        LOG.info("Nur die ersten %d von %d Bildern gehen an den Anbieter", MAX_BILDER, len(inhalte))
    return [vorbereiten(inhalt, kante = kante) for inhalt in ausgewaehlt]
