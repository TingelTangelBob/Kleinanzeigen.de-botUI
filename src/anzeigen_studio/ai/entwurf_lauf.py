# SPDX-FileCopyrightText: © Anzeigen-Studio contributors
# SPDX-ArtifactOfProjectHomePage: https://github.com/TingelTangelBob/Kleinanzeigen.de-botUI/
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# Gemeinsamer KI-Aufruf fuer den direkten und den wartenden Entwurfsweg.
# Neue Datei, Anzeigen-Studio, 2026-09-13.
#
# Die HTTP-Schnittstelle darf nicht die einzige Stelle sein, die Kosten- und
# Datenschutzregeln kennt: Der Hintergrundlauf braucht denselben Weg. Hier
# liegt deshalb genau ein Ablauf fuer Schluessel, Budget, Bildverkleinerung,
# Anbieteraufruf und Verbrauchsbuch.

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import TYPE_CHECKING, Any

from anzeigen_studio.ai import anbieter as anbieter_dienst
from anzeigen_studio.ai import bilder as ki_bilder
from anzeigen_studio.ai import budget as budget_dienst
from anzeigen_studio.ai import entwurf as entwurf_dienst
from anzeigen_studio.ai import stil as stil_dienst
from anzeigen_studio.core import ki_zugang
from anzeigen_studio.core.errors import FachlicherFehler

if TYPE_CHECKING:
    import sqlite3
    from pathlib import Path

    from anzeigen_studio.core.settings import Settings


# Preise des eingestellten Modells in USD je 1 Mio. Token, Stand 2026-08-27.
# Die Werte sind nur eine Schaetzung fuer die Anzeige; abgerechnet wird beim
# Anbieter. Die Quelle liegt in 00_Agentenordner/04_Serververwaltung.
_PREIS_EINGABE_USD_JE_TOKEN = 0.20 / 1_000_000
_PREIS_AUSGABE_USD_JE_TOKEN = 1.20 / 1_000_000


@dataclass(frozen = True, slots = True)
class Kosten:
    """Die sichtbaren Verbrauchsdaten eines Entwurfs."""

    modell: str
    token_eingabe: int
    token_ausgabe: int
    usd: float
    bilder_gesendet: int
    bytes_gesendet: int
    stil_eigene_texte: int
    verbrauch_usd: float
    budget_usd: float


@dataclass(frozen = True, slots = True)
class Ergebnis:
    """Gepruefter Entwurf plus Verbrauchsdaten."""

    entwurf: entwurf_dienst.Entwurf
    kosten: Kosten


def _schluessel(conn: sqlite3.Connection, cfg: Settings) -> str:
    """Holt den aktiven Anbieter-Schluessel, ohne ihn nach aussen zu geben."""
    if cfg.hosted:
        if not cfg.openai_api_schluessel:
            raise FachlicherFehler(
                "Der KI-Zugang ist noch nicht eingerichtet. Öffne die Ersteinrichtung.",
                status = 409,
            )
        return cfg.openai_api_schluessel
    return ki_zugang.lesen(conn, schluessel = cfg.secret_key)


async def erzeugen(
    conn: sqlite3.Connection,
    cfg: Settings,
    *,
    profil_slug: str,
    profil_wurzel: Path,
    inhalte: list[bytes],
) -> Ergebnis:
    """Erzeugt genau einen KI-Entwurf aus bereits gelesenen Bildbytes.

    Die Bytes werden vom Aufrufer auf Anzahl und Dateigroesse geprueft. Die
    letzte Bildpruefung steckt trotzdem in `alle_vorbereiten`, damit auch ein
    interner Aufrufer nicht versehentlich zu grosse oder unlesbare Daten an den
    Anbieter schickt.
    """
    if not inhalte:
        raise FachlicherFehler("Ohne Bild kann kein Entwurf erkannt werden.", status = 400, feld = "bilder")

    api_schluessel = _schluessel(conn, cfg)
    # Vor dem Anbieteraufruf, nicht danach: Der Monatsdeckel soll eine Schleife
    # stoppen, bevor sie den naechsten kostenpflichtigen Aufruf startet.
    budget_dienst.pruefen(conn, grenze_usd = cfg.ki_budget_usd)

    vorbereitet = ki_bilder.alle_vorbereiten(
        inhalte, kante = cfg.ki_bildkante, max_bilder = cfg.ki_max_bilder,
    )
    stilprofil = stil_dienst.aus_bestand(profil_wurzel)
    dienst = anbieter_dienst.OpenAI(api_schluessel = api_schluessel, modell = cfg.ki_modell)
    antwort = await dienst.erkennen(
        vorbereitet,
        anweisung = entwurf_dienst.anweisung(stilprofil.anweisungsteil()),
        schema = entwurf_dienst.schema(),
        schema_name = "anzeigenentwurf",
    )

    usd = (
        antwort.token_eingabe * _PREIS_EINGABE_USD_JE_TOKEN
        + antwort.token_ausgabe * _PREIS_AUSGABE_USD_JE_TOKEN
    )
    # Gebucht wird auch bei einer unbrauchbaren strukturierten Antwort: Der
    # Anbieter hat den Aufruf verarbeitet und berechnet ihn moeglicherweise.
    budget_dienst.buchen(
        conn,
        profil_slug = profil_slug,
        modell = antwort.modell,
        token_eingabe = antwort.token_eingabe,
        token_ausgabe = antwort.token_ausgabe,
        mikro_usd = round(usd * budget_dienst.MIKRO_JE_USD),
    )
    stand = budget_dienst.verbrauch(conn, grenze_usd = cfg.ki_budget_usd)
    ergebnis = entwurf_dienst.aus_antwort(antwort.daten)

    return Ergebnis(
        entwurf = ergebnis,
        kosten = Kosten(
            modell = antwort.modell,
            token_eingabe = antwort.token_eingabe,
            token_ausgabe = antwort.token_ausgabe,
            usd = round(usd, 6),
            bilder_gesendet = len(vorbereitet),
            bytes_gesendet = sum(bild.bytes_nachher for bild in vorbereitet),
            stil_eigene_texte = len(stilprofil.beispiele),
            verbrauch_usd = round(stand.usd, 4),
            budget_usd = round(stand.grenze_usd, 2),
        ),
    )


def entwurf_zu_dict(entwurf: entwurf_dienst.Entwurf) -> dict[str, Any]:
    """Serialisiert nur den geprueften Entwurf fuer die Warteschlange."""
    return {
        "titel": entwurf.titel,
        "beschreibung": entwurf.beschreibung,
        "zustand": entwurf.zustand,
        "kategorie": entwurf.kategorie,
        "preis_von_euro": entwurf.preis_von_euro,
        "preis_bis_euro": entwurf.preis_bis_euro,
        "preis_begruendung": entwurf.preis_begruendung,
        "preis_euro": entwurf.preis_euro,
        "versandgroesse": entwurf.versandgroesse,
        "sicherheit": entwurf.sicherheit,
        "fragen": [
            {
                "id": frage.id,
                "frage": frage.frage,
                "feld": frage.feld,
                "freitext_erlaubt": frage.freitext_erlaubt,
                "optionen": [
                    {"text": option.text, "wert": option.wert}
                    for option in frage.optionen
                ],
            }
            for frage in entwurf.fragen
        ],
    }


def entwurf_aus_dict(daten: dict[str, Any]) -> entwurf_dienst.Entwurf:
    """Liest einen in der Datenbank abgelegten Entwurf erneut sicher ein."""
    return entwurf_dienst.aus_antwort(daten)


def kosten_zu_dict(kosten: Kosten) -> dict[str, Any]:
    """Serialisiert Kosten ohne Rundungs- oder JSON-Sonderweg."""
    return asdict(kosten)


def kosten_aus_dict(daten: dict[str, Any]) -> Kosten:
    """Liest gespeicherte Kosten mit festen Typen ein."""
    try:
        return Kosten(
            modell = str(daten["modell"]),
            token_eingabe = int(daten["token_eingabe"]),
            token_ausgabe = int(daten["token_ausgabe"]),
            usd = float(daten["usd"]),
            bilder_gesendet = int(daten["bilder_gesendet"]),
            bytes_gesendet = int(daten["bytes_gesendet"]),
            stil_eigene_texte = int(daten.get("stil_eigene_texte", 0)),
            verbrauch_usd = float(daten.get("verbrauch_usd", 0.0)),
            budget_usd = float(daten.get("budget_usd", 0.0)),
        )
    except (KeyError, TypeError, ValueError) as fehler:
        raise FachlicherFehler("Die gespeicherten KI-Kosten sind unlesbar.", status = 500) from fehler
