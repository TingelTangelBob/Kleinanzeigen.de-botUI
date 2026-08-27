# SPDX-FileCopyrightText: © Anzeigen-Studio contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# Stilbeispiele aus dem eigenen Anzeigenbestand (AP-4.2).
#
# Die Texte werden nicht durch einen zweiten KI-Aufruf zusammengefasst.
# Einige kurze, lokal gelesene Beispiele reichen als Stilreferenz und sparen
# Kosten. Es werden nur Beschreibungstexte gelesen - keine Nachrichten,
# Zugangsdaten oder Kontaktfelder.
#
# GELESEN WIRD NUR, WAS EINE ANZEIGENNUMMER HAT. Das ist keine Kleinigkeit,
# sondern der Punkt, an dem das Stilprofil sonst kippt: Entwuerfe aus diesem
# Modul liegen ebenfalls im Bestand, tragen aber keine `id`, weil sie nie
# online waren. Ohne diese Schranke naehme das Modell nach wenigen Entwuerfen
# seine eigenen Texte als Vorlage fuer den Stil des Nutzers - eine
# Rueckkopplung, die den Zweck von AP-4.2 in sein Gegenteil verkehrt. Eine
# Anzeige mit `id` stand dagegen nachweislich auf der Plattform; ihr Text
# stammt vom Nutzer.

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Final

from ruamel.yaml import YAML

from anzeigen_studio.bestand.lesen import anzeigendateien

if TYPE_CHECKING:
    from pathlib import Path

#: Nie mehr als diese Zahl eigener Texte an einen Anbieter schicken.
MAX_BEISPIELE: Final[int] = 5

#: Ein einzelner Text soll den Prompt nicht unverhaeltnismaessig aufblasen.
MAX_ZEICHEN_PRO_BEISPIEL: Final[int] = 900

#: Obergrenze fuer alle Stilbeispiele zusammen.
MAX_ZEICHEN_GESAMT: Final[int] = 3600

_yaml = YAML(typ = "safe")
_E_MAIL = re.compile(r"\b[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}\b")
_TELEFON = re.compile(r"(?<!\w)(?:(?:\+|00)49|0)(?:[\s()/.-]*\d){6,}(?!\w)")


#: Stilvorgabe ohne eigene Vorlagen (AP-4.3).
#:
#: Wer das Studio gerade erst eingerichtet hat, hat noch keine
#: veroeffentlichte Anzeige - und bekaeme sonst gar keine Stilvorgabe. Dann
#: schreibt das Modell in seinem eigenen Ton, und der ist fuer eine private
#: Kleinanzeige regelmaessig zu glatt und zu lang.
#:
#: Bewusst als Regeln formuliert und nicht als erfundene Beispielanzeige: Ein
#: ausgedachter Beispieltext waere ein fremder Stil, den niemand gewaehlt hat,
#: und er wuerde mit Sachangaben locken, die nicht zum Foto gehoeren.
STANDARDSTIL: Final[str] = (
    "Fuer den Ton gilt, solange keine eigenen Anzeigen als Vorlage vorliegen: "
    "Schreibe wie ein Privatmensch, der einen Gegenstand aus dem eigenen Haushalt "
    "abgibt. Kurze Hauptsaetze, kein Marketing, keine Superlative, keine "
    "Aufzaehlung technischer Daten, die nicht auf den Fotos stehen. Nenne "
    "Gebrauchsspuren offen - sie schaffen Vertrauen und ersparen Rueckfragen. "
    "Duze nicht und sieze nicht; schreibe ueber den Gegenstand, nicht ueber den "
    "Leser."
)


@dataclass(frozen = True, slots = True)
class Stilprofil:
    """Woran sich der Ton des Entwurfs ausrichtet.

    Entweder an eigenen Texten (AP-4.2) oder, wenn es keine gibt, an einer
    festen Vorgabe (AP-4.3). Beides ist eine Stilreferenz - nie eine Quelle
    fuer Sachangaben.
    """

    beispiele: tuple[str, ...]

    @property
    def aus_eigenen_texten(self) -> bool:
        """Ob eigene Anzeigen die Vorlage sind. Fuer Protokoll und Oberflaeche."""
        return bool(self.beispiele)

    def anweisungsteil(self) -> str:
        """Formuliert die Stilvorgabe fuer den Prompt des einzigen KI-Aufrufs."""
        if not self.beispiele:
            return STANDARDSTIL

        texte = "\n\n".join(
            f"Beispiel {nummer}:\n{beispiel}"
            for nummer, beispiel in enumerate(self.beispiele, start = 1)
        )
        return (
            "Nutze die folgenden Beschreibungstexte aus den eigenen lokalen Anzeigen "
            "ausschließlich als Stilreferenz. Übernimm daraus Ton, Satzlänge, Detailgrad "
            "und die natürliche private Sprache - niemals Sachangaben, Namen, Preise, "
            "Maße oder Zustände in die neue Anzeige.\n\n"
            f"{texte}"
        )


def _kontakt_entfernen(text: str) -> str:
    text = _E_MAIL.sub("[E-Mail entfernt]", text)
    return _TELEFON.sub("[Telefonnummer entfernt]", text)


def _beschreibung_lesen(datei: Path) -> str | None:
    try:
        daten: Any = _yaml.load(datei.read_text(encoding = "utf-8"))
    except Exception:  # noqa: BLE001 - eine kaputte Anzeige darf den Entwurf nicht verhindern
        return None
    if not isinstance(daten, dict):
        return None

    # Ohne Anzeigennummer war der Text nie auf der Plattform - er kann also aus
    # diesem Modul selbst stammen. Siehe Kopfkommentar.
    if not isinstance(daten.get("id"), int):
        return None

    beschreibung = daten.get("description")
    if not isinstance(beschreibung, str) or not beschreibung.strip():
        return None

    # Zeilenumbrueche aus YAML werden fuer den Prompt zu normalem Fliesstext.
    # Kontaktangaben sind fuer die Stilimitation nicht noetig und sollen nicht
    # mit den Beispielen zum Anbieter wandern.
    sauber = _kontakt_entfernen(" ".join(beschreibung.split()))
    sauber = sauber[:MAX_ZEICHEN_PRO_BEISPIEL].rstrip()
    return sauber or None


def aus_bestand(profil_wurzel: Path) -> Stilprofil:
    """Liest wenige eigene Beschreibungstexte fuer eine Stilreferenz."""
    beispiele: list[str] = []
    gesamt = 0

    for datei in anzeigendateien(profil_wurzel):
        beispiel = _beschreibung_lesen(datei)
        if not beispiel:
            continue

        verbleibend = MAX_ZEICHEN_GESAMT - gesamt
        if verbleibend <= 0:
            break
        if len(beispiel) > verbleibend:
            beispiel = beispiel[:verbleibend].rstrip()
        if not beispiel:
            break

        beispiele.append(beispiel)
        gesamt += len(beispiel)
        if len(beispiele) >= MAX_BEISPIELE:
            break

    return Stilprofil(tuple(beispiele))
