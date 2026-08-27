# SPDX-FileCopyrightText: © Anzeigen-Studio contributors
# SPDX-ArtifactOfProjectHomePage: https://github.com/TingelTangelBob/Kleinanzeigen.de-botUI/
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# Anbieterabstraktion fuer das KI-Entwurfsmodul (AP-4.1).
#
# Ein Anbieter bekommt Bilder und eine Anweisung und liefert ein Woerterbuch
# zurueck, das einem festen Schema entspricht. Mehr weiss diese Schicht nicht -
# was in den Feldern steht, entscheidet `entwurf.py`.
#
# Umgesetzt ist OpenAI ueber die Responses-Schnittstelle mit "Structured
# Outputs": Das Schema geht mit der Anfrage hinaus, und der Anbieter garantiert
# eine Antwort, die dazu passt. Das erspart das Erraten von JSON aus Fliesstext
# und damit die haeufigste Fehlerquelle solcher Anbindungen.
#
# Bewusst ueber rohes HTTP statt ueber das SDK des Anbieters. Roomverse nimmt
# das SDK (`openai@^6`), und fuer dessen Bilderzeugung ist das richtig. Hier
# geht es um einen einzigen Endpunkt mit einem dokumentierten Rumpf; ein SDK
# waere eine weitere Abhaengigkeit, die sich unabhaengig von uns aendert - und
# der Grund, warum diese Anwendung sich vom Upstream-Bot per Unterprozess
# trennt, gilt hier sinngemaess auch.

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from http import HTTPStatus
from typing import TYPE_CHECKING, Any, Final, Protocol

from anzeigen_studio.core.errors import FachlicherFehler

if TYPE_CHECKING:
    from anzeigen_studio.ai.bilder import VorbereitetesBild

LOG = logging.getLogger(__name__)

_ENDPUNKT: Final[str] = "https://api.openai.com/v1/responses"

#: Wie lange auf eine Antwort gewartet wird. Grosszuegig, weil mehrere Bilder
#: ausgewertet werden - aber endlich, damit ein haengender Anbieter nicht eine
#: Anfrage der Oberflaeche fuer immer festhaelt.
_FRIST_S: Final[float] = 90.0

#: Aufloesungsstufe je Bild. "high" statt "low": Der Unterschied sind rund
#: 560 Token je Bild, also etwa 0,03 Cent bei drei Bildern. Der Zustand eines
#: Gegenstands - Kratzer, Abnutzung, Vollstaendigkeit - ist genau das, was auf
#: einem 512er-Vorschaubild verschwindet.
_BILD_STUFE: Final[str] = "high"


@dataclass(frozen = True, slots = True)
class Antwort:
    """Was ein Anbieter zurueckgibt."""

    daten: dict[str, Any]
    modell: str
    token_eingabe: int
    token_ausgabe: int

    def kosten_mikro_usd(self, *, preis_eingabe: float, preis_ausgabe: float) -> int:
        """Kosten in Mikro-Dollar, wie in Roomverse gezaehlt.

        Preise sind USD je 1 Mio. Token. Ganzzahlig, weil Fliesskomma fuer
        Geldbetraege ueber viele Summanden hinweg driftet.
        """
        gesamt = (self.token_eingabe * preis_eingabe + self.token_ausgabe * preis_ausgabe)
        return round(gesamt)


class Anbieter(Protocol):
    """Was ein KI-Anbieter koennen muss."""

    async def erkennen(
        self,
        bilder: list[VorbereitetesBild],
        *,
        anweisung: str,
        schema: dict[str, Any],
        schema_name: str,
    ) -> Antwort:
        ...


@dataclass(frozen = True, slots = True)
class OpenAI:
    """Anbindung an OpenAI. Der Schluessel wird nie protokolliert."""

    api_schluessel: str
    modell: str

    async def erkennen(
        self,
        bilder: list[VorbereitetesBild],
        *,
        anweisung: str,
        schema: dict[str, Any],
        schema_name: str,
    ) -> Antwort:
        import httpx  # noqa: PLC0415 - nur hier gebraucht

        inhalt: list[dict[str, Any]] = [{"type": "input_text", "text": anweisung}]
        inhalt.extend(
            {"type": "input_image", "image_url": bild.daten_url, "detail": _BILD_STUFE}
            for bild in bilder
        )

        rumpf = {
            "model": self.modell,
            "input": [{"role": "user", "content": inhalt}],
            "text": {
                "format": {
                    "type": "json_schema",
                    "name": schema_name,
                    "schema": schema,
                    "strict": True,
                },
            },
        }

        LOG.info(
            "KI-Anfrage: Modell %s, %d Bilder, %d Byte Bilddaten",
            self.modell, len(bilder), sum(len(b.daten_url) for b in bilder),
        )

        try:
            async with httpx.AsyncClient(timeout = _FRIST_S) as klient:
                antwort = await klient.post(
                    _ENDPUNKT,
                    headers = {
                        "Authorization": f"Bearer {self.api_schluessel}",
                        "Content-Type": "application/json",
                    },
                    json = rumpf,
                )
        except httpx.TimeoutException as fehler:
            raise FachlicherFehler(
                "Der KI-Anbieter hat nicht rechtzeitig geantwortet. Bitte noch einmal versuchen.",
                status = 504,
            ) from fehler
        except httpx.HTTPError as fehler:
            # Absichtlich ohne die Ausnahme im Text: httpx nimmt die
            # angefragte Adresse mit auf, und in den Kopfzeilen steht der
            # Schluessel. Der Grund gehoert ins Protokoll, nicht in die Antwort.
            LOG.warning("KI-Anbieter nicht erreichbar: %s", type(fehler).__name__)
            raise FachlicherFehler(
                "Der KI-Anbieter ist nicht erreichbar.", status = 502,
            ) from fehler

        if antwort.status_code != HTTPStatus.OK:
            raise _fehler_aus_antwort(antwort.status_code, antwort.text)

        return _antwort_lesen(antwort.json(), self.modell)


def _fehler_aus_antwort(status: int, rohtext: str) -> FachlicherFehler:
    """Uebersetzt eine Fehlerantwort des Anbieters in etwas Lesbares.

    Die Meldung des Anbieters ist englisch und technisch; die haeufigen Faelle
    bekommen deshalb einen eigenen Satz, der sagt, was zu tun ist.
    """
    meldung = ""
    try:
        meldung = str(json.loads(rohtext).get("error", {}).get("message", ""))[:200]
    except (ValueError, AttributeError, TypeError):
        meldung = ""

    LOG.warning("KI-Anbieter antwortete mit %d: %s", status, meldung or rohtext[:200])

    if status == HTTPStatus.UNAUTHORIZED:
        return FachlicherFehler(
            "Der hinterlegte OpenAI-Schlüssel wurde abgelehnt. Bitte prüfen und neu eintragen.",
            status = 502,
        )
    if status == HTTPStatus.TOO_MANY_REQUESTS:
        return FachlicherFehler(
            "Der KI-Anbieter bremst gerade oder das Guthaben ist aufgebraucht. "
            "Später noch einmal versuchen.",
            status = 502,
        )
    if status == HTTPStatus.BAD_REQUEST and "model" in meldung.lower():
        return FachlicherFehler(
            f"Der Anbieter kennt das eingestellte Modell nicht ({meldung}).", status = 502,
        )
    return FachlicherFehler(
        f"Der KI-Anbieter meldet einen Fehler ({status}).", status = 502,
    )


def _antwort_lesen(nutzlast: dict[str, Any], modell: str) -> Antwort:
    """Holt den JSON-Text aus der Antwort und wandelt ihn in ein Woerterbuch.

    Die Responses-Schnittstelle liefert eine verschachtelte Struktur; manche
    Antworten tragen zusaetzlich ein bequemes `output_text`. Beide Wege werden
    versucht, damit eine Formataenderung an einer Stelle nicht alles bricht.
    """
    text = nutzlast.get("output_text")
    if not isinstance(text, str) or not text.strip():
        stuecke: list[str] = []
        for eintrag in nutzlast.get("output") or []:
            if not isinstance(eintrag, dict):
                continue
            stuecke.extend(
                teil["text"]
                for teil in eintrag.get("content") or []
                if isinstance(teil, dict) and isinstance(teil.get("text"), str)
            )
        text = "".join(stuecke)

    if not text.strip():
        raise FachlicherFehler(
            "Der KI-Anbieter hat nichts Verwertbares zurückgegeben.", status = 502,
        )

    try:
        daten = json.loads(text)
    except ValueError as fehler:
        # Sollte mit strict=true nicht vorkommen. Wenn doch, ist die Anbindung
        # kaputt und nicht die Anzeige - das gehoert unterschieden.
        LOG.warning("Antwort des Anbieters war kein JSON: %s", text[:200])
        raise FachlicherFehler(
            "Die Antwort des KI-Anbieters war unlesbar.", status = 502,
        ) from fehler

    if not isinstance(daten, dict):
        raise FachlicherFehler("Die Antwort des KI-Anbieters hatte die falsche Form.", status = 502)

    verbrauch = nutzlast.get("usage") or {}
    return Antwort(
        daten = daten,
        modell = modell,
        token_eingabe = int(verbrauch.get("input_tokens") or 0),
        token_ausgabe = int(verbrauch.get("output_tokens") or 0),
    )
