# SPDX-FileCopyrightText: © Anzeigen-Studio contributors
# SPDX-ArtifactOfProjectHomePage: https://github.com/TingelTangelBob/Kleinanzeigen.de-botUI/
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# Eine einzelne Anzeige lesen und speichern (AP-2.5).
#
# Zwei Entscheidungen, die den Rest erklaeren:
#
# 1. Gespeichert wird mit ruamel im Rundlauf-Modus. Die Datei behaelt damit
#    Reihenfolge, Kommentare und Blockschreibweise der Beschreibung. Eine
#    Anzeigendatei ist auch fuer die Kommandozeile da - sie soll nach einer
#    Bearbeitung nicht neu sortiert aussehen.
#
# 2. Der `content_hash` bleibt unangetastet. Er haelt fest, wie die Anzeige
#    zuletzt veroeffentlicht war. Wuerde er beim Speichern neu berechnet, waere
#    die Aenderung sofort unsichtbar - und genau daran erkennt die Oberflaeche,
#    dass ein Download etwas ueberschreiben wuerde (AP-3.1).

from __future__ import annotations

import io
import logging
from typing import TYPE_CHECKING, Any

from ruamel.yaml import YAML

from anzeigen_studio.bestand.lesen import BestandsAnzeige, _anzeige_lesen  # noqa: PLC2701 - dieselbe Schicht
from anzeigen_studio.core.errors import FachlicherFehler
from anzeigen_studio.katalog.daten import gemischte_versandgroessen

if TYPE_CHECKING:
    from datetime import datetime
    from pathlib import Path

LOG = logging.getLogger(__name__)

#: Felder, die der Editor setzen darf.
#:
#: Positivliste statt Sperrliste: Was hier nicht steht, kann die Oberflaeche
#: nicht veraendern - auch nicht durch einen zurechtgebogenen Aufruf. `id`,
#: `content_hash`, `created_on` und `updated_on` gehoeren dem Bot; sie zu
#: veraendern hiesse, ihm etwas Falsches ueber die Plattform zu erzaehlen.
AENDERBAR = frozenset({
    "active", "type", "title", "description", "category", "price", "price_type",
    "shipping_type", "shipping_costs", "shipping_options", "sell_directly",
    "republication_interval", "contact", "special_attributes", "images",
})

_yaml_rund = YAML()
_yaml_rund.preserve_quotes = True
_yaml_rund.width = 4096  # Zeilen nicht umbrechen - der Bot liest die Datei auch.


def _pfad(profil_wurzel: Path, datei: str) -> Path:
    """Loest den Pfad einer Anzeigendatei auf - mit Gegenprobe gegen Ausbruch."""
    wurzel = profil_wurzel.resolve()
    ziel = (wurzel / datei).resolve()
    if not ziel.is_relative_to(wurzel):
        raise FachlicherFehler("Ungültiger Pfad.", status = 400, feld = "datei")
    if ziel.suffix.lower() not in {".yaml", ".yml"}:
        raise FachlicherFehler("Das ist keine Anzeigendatei.", status = 400, feld = "datei")
    if not ziel.is_file():
        raise FachlicherFehler("Anzeige nicht gefunden.", status = 404)
    return ziel


def rohdaten_lesen(profil_wurzel: Path, datei: str) -> dict[str, Any]:
    """Liest eine Anzeigendatei als Wörterbuch."""
    pfad = _pfad(profil_wurzel, datei)
    try:
        daten = _yaml_rund.load(pfad.read_text(encoding = "utf-8"))
    except Exception as fehler:  # noqa: BLE001 - der Grund gehoert dem Nutzer gesagt
        # Nur die erste Zeile: Der Parser haengt Zeilennummern, Spaltenmarken
        # und einen Ausschnitt der Datei an. Das hilft beim Debuggen, nicht
        # aber jemandem, der wissen will, was mit seiner Anzeige ist.
        grund = str(fehler).splitlines()[0].strip()
        raise FachlicherFehler(
            f"Die Anzeigendatei ist nicht lesbar ({grund}). "
            "Am ehesten hilft, sie neu herunterzuladen.",
            status = 422,
        ) from fehler
    if not isinstance(daten, dict):
        raise FachlicherFehler("Die Datei enthält keine Anzeige.", status = 422)
    return daten


def _lesbar(fehler: Exception) -> list[str]:
    """Macht aus einer Pydantic-Meldung einen Satz, den man lesen kann.

    Roh sieht eine Meldung so aus:

        1 validation error for Ad
          Value error, sell_directly erfordert shipping_type: SHIPPING
          [type=value_error, input_value={...}, input_type=dict]
          For further information visit https://errors.pydantic.dev/...

    Der brauchbare Teil ist eine Zeile davon. Der Rest ist fuer Entwickler
    gedacht und gehoert nicht in eine Oberflaeche - samt der eingebetteten
    Anzeigendaten, die dort nichts zu suchen haben.
    """
    saetze: list[str] = []
    einzelne = getattr(fehler, "errors", None)
    if callable(einzelne):
        try:
            for eintrag in einzelne():
                text = str(eintrag.get("msg", "")).removeprefix("Value error, ").strip()
                ort = ".".join(str(t) for t in eintrag.get("loc", ()))
                if text:
                    saetze.append(f"{ort}: {text}" if ort else text)
        except Exception:  # noqa: BLE001 - dann eben die Rohfassung
            saetze = []
    if not saetze:
        saetze = [str(fehler).splitlines()[0].strip() or "Die Anzeige ist nicht gültig."]
    return saetze


def pruefen_zum_veroeffentlichen(daten: dict[str, Any]) -> list[str]:
    """Prueft die Anzeige gegen die Modelle des Bots.

    Zwei Stufen, und der Unterschied ist Absicht:

    * Was `AdPartial` ablehnt, ist strukturell falsch (Titel zu kurz, Preis
      keine Zahl). Das wird als Fehler geworfen - so etwas gehoert nicht in
      eine Datei, die der Bot spaeter liest.
    * Was erst die vollstaendige `Ad`-Pruefung bemaengelt, betrifft das
      Veroeffentlichen. Das kommt als Hinweis zurueck, nicht als Fehler: Ein
      halbfertiger Entwurf muss sich speichern lassen.
    """
    try:
        from kleinanzeigen_bot.model.ad_model import AdDefaults, AdPartial  # noqa: PLC0415 - Bot-Import bewusst lokal
    except ImportError:  # pragma: no cover - im Betrieb liegt der Bot daneben
        LOG.warning("Bot-Modelle nicht verfügbar, Anzeige wird ungeprüft gespeichert.")
        return []

    try:
        teil = AdPartial.model_validate(dict(daten))
    except Exception as fehler:  # noqa: BLE001 - Pydantic wirft eigene Klassen
        raise FachlicherFehler(" · ".join(_lesbar(fehler)), status = 422) from fehler

    try:
        teil.to_ad(AdDefaults())
    except Exception as fehler:  # noqa: BLE001
        return _lesbar(fehler)
    return []


#: Fehlertext fuer gemischte Versandgroessen. Steht hier, weil ihn zwei Wege
#: brauchen: das Speichern und das Hochladen (`api/bestand.py`).
GEMISCHTE_GROESSEN_MELDUNG = (
    "Die Versandpakete gehören zu mehreren Größen. Kleinanzeigen lässt nur eine Größe zu – "
    "beim Veröffentlichen bricht der Lauf im Versanddialog ab. Wähle Pakete einer Größe."
)


def versandgroessen_pruefen(daten: dict[str, Any]) -> None:
    """Weist gemischte Versandgroessen ab, bevor irgendetwas geschrieben wird.

    Bewusst ein Fehler und kein Hinweis, anders als bei den uebrigen
    Veroeffentlichungsregeln: Ein halbfertiger Entwurf soll sich speichern
    lassen, aber diese Kombination ist nicht halbfertig, sondern unmoeglich.
    `publishing_form.set_shipping_options` bricht damit ab - und zwar erst im
    bereits geoeffneten Versanddialog, mit halb ausgefuelltem Formular. Weder
    `AdPartial` noch `Ad` pruefen die Regel, es gibt sonst also keine Stelle,
    die sie durchsetzt.

    Die Oberflaeche verhindert den Zustand schon beim Anklicken. Das genuegt
    nicht: Die API ist selbst eine Schnittstelle, und heruntergeladene oder von
    Hand bearbeitete Dateien kommen an ihr vorbei.
    """
    pakete = daten.get("shipping_options") or []
    if isinstance(pakete, list) and gemischte_versandgroessen(pakete):
        raise FachlicherFehler(
            GEMISCHTE_GROESSEN_MELDUNG, status = 422, feld = "shipping_options",
        )


def speichern(
    profil_wurzel: Path,
    datei: str,
    aenderungen: dict[str, Any],
    *,
    jetzt: datetime | None = None,
) -> tuple[BestandsAnzeige, list[str]]:
    """Schreibt geänderte Felder in die Anzeigendatei.

    Gibt die neu gelesene Anzeige und die Hinweise der Pruefung zurueck.
    """
    pfad = _pfad(profil_wurzel, datei)
    daten = rohdaten_lesen(profil_wurzel, datei)

    unerlaubt = sorted(set(aenderungen) - AENDERBAR)
    if unerlaubt:
        raise FachlicherFehler(
            f"Diese Felder lassen sich hier nicht ändern: {', '.join(unerlaubt)}",
            status = 400,
        )

    for feld, wert in aenderungen.items():
        daten[feld] = wert

    # Vor dem Schreiben, nicht danach: Eine abgelehnte Aenderung darf die Datei
    # nicht angefasst haben.
    versandgroessen_pruefen(daten)

    hinweise = pruefen_zum_veroeffentlichen(daten)

    # Erst in den Speicher schreiben, dann in einem Zug auf die Platte. Ein
    # Fehler beim Serialisieren darf keine halbe Datei hinterlassen.
    puffer = io.StringIO()
    _yaml_rund.dump(daten, puffer)
    pfad.write_text(puffer.getvalue(), encoding = "utf-8")

    return _anzeige_lesen(pfad, profil_wurzel.resolve(), jetzt = jetzt or _jetzt()), hinweise


def _jetzt() -> datetime:
    from datetime import UTC, datetime  # noqa: PLC0415 - nur hier gebraucht

    return datetime.now(UTC)
