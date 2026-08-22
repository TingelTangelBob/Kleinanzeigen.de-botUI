# SPDX-FileCopyrightText: © Anzeigen-Studio contributors
# SPDX-ArtifactOfProjectHomePage: https://github.com/TingelTangelBob/Kleinanzeigen.de-botUI/
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# Anmeldeendpunkte und der Schutz aller uebrigen Pfade (AP-1.10).

from __future__ import annotations

import sqlite3
from typing import TYPE_CHECKING, Annotated

from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel, Field

from anzeigen_studio.core import auth, db
from anzeigen_studio.core.errors import FachlicherFehler

if TYPE_CHECKING:
    from collections.abc import Iterator

    from anzeigen_studio.core.settings import Settings

router = APIRouter(prefix = "/api/auth", tags = ["Anmeldung"])

#: Pfade, die ohne Sitzung erreichbar sein muessen. Bewusst kurz und
#: vollstaendig aufgezaehlt statt ueber Praefixe - eine zu weite Regel hier
#: oeffnet unbemerkt die ganze Anwendung.
OEFFENTLICH = frozenset({
    "/api/health",
    "/api/auth/status",
    "/api/auth/einrichten",
    "/api/auth/anmelden",
})


def _verbindung(request: Request) -> Iterator[sqlite3.Connection]:
    cfg: Settings = request.app.state.settings
    conn = db.connect(cfg.database_path)
    try:
        yield conn
    finally:
        conn.close()


Verbindung = Annotated[sqlite3.Connection, Depends(_verbindung)]


class AnmeldeEingabe(BaseModel):
    name: str = Field(min_length = 1, max_length = 100)
    passwort: str = Field(min_length = 1, max_length = 400)


class EinrichtenEingabe(BaseModel):
    name: str = Field(min_length = 1, max_length = 100)
    passwort: str = Field(min_length = auth.MIN_PASSWORTLAENGE, max_length = 400)


class PasswortAendern(BaseModel):
    alt: str = Field(min_length = 1, max_length = 400)
    neu: str = Field(min_length = auth.MIN_PASSWORTLAENGE, max_length = 400)


class StatusAusgabe(BaseModel):
    eingerichtet: bool
    angemeldet: bool
    name: str | None = None


def _cookie_setzen(response: Response, token: str, *, sicher: bool) -> None:
    response.set_cookie(
        auth.COOKIE_NAME,
        token,
        # HttpOnly: kein Zugriff aus JavaScript, damit ein XSS-Fehler nicht
        # sofort die Sitzung verschenkt.
        httponly = True,
        # Lax statt Strict: Strict wuerde den Zugriff ueber einen Verweis von
        # aussen brechen, ohne hier Sicherheit hinzuzufuegen.
        samesite = "lax",
        # Nur bei HTTPS - sonst schickt der Browser das Cookie gar nicht erst,
        # und die Anwendung waere im Heimnetz unbenutzbar.
        secure = sicher,
        max_age = int(auth.SITZUNGSDAUER.total_seconds()),
        path = "/",
    )


@router.get("/status", response_model = StatusAusgabe)
def status(request: Request, conn: Verbindung) -> StatusAusgabe:
    """Sagt der Oberflaeche, ob eingerichtet und ob angemeldet."""
    benutzer = auth.sitzung_pruefen(conn, request.cookies.get(auth.COOKIE_NAME))
    return StatusAusgabe(
        eingerichtet = auth.gibt_es_benutzer(conn),
        angemeldet = benutzer is not None,
        name = benutzer.name if benutzer else None,
    )


@router.post("/einrichten", response_model = StatusAusgabe, status_code = 201)
def einrichten(daten: EinrichtenEingabe, request: Request, conn: Verbindung,
               response: Response) -> StatusAusgabe:
    """Legt das erste und einzige Konto an.

    Danach gibt es keine Selbstregistrierung mehr - bei einer Anwendung, die
    fremde Zugangsdaten haelt, waere eine offene Registrierung ein Einfallstor.
    """
    benutzer = auth.ersten_benutzer_anlegen(conn, daten.name, daten.passwort)
    token = auth.anmelden(conn, daten.name, daten.passwort)
    ueber_https = request.url.scheme == "https" or \
        request.headers.get("x-forwarded-proto", "").lower() == "https"
    _cookie_setzen(response, token, sicher = ueber_https)
    return StatusAusgabe(eingerichtet = True, angemeldet = True, name = benutzer.name)


@router.post("/anmelden", response_model = StatusAusgabe)
def anmelden(daten: AnmeldeEingabe, request: Request, conn: Verbindung, response: Response) -> StatusAusgabe:
    token = auth.anmelden(conn, daten.name, daten.passwort)
    # Secure nur setzen, wenn die Anfrage tatsaechlich ueber HTTPS kam - sonst
    # verwirft der Browser das Cookie und niemand kommt mehr hinein.
    ueber_https = request.url.scheme == "https" or \
        request.headers.get("x-forwarded-proto", "").lower() == "https"
    _cookie_setzen(response, token, sicher = ueber_https)
    return StatusAusgabe(eingerichtet = True, angemeldet = True, name = daten.name.strip())


@router.post("/abmelden", status_code = 204)
def abmelden(request: Request, conn: Verbindung, response: Response) -> None:
    auth.abmelden(conn, request.cookies.get(auth.COOKIE_NAME))
    response.delete_cookie(auth.COOKIE_NAME, path = "/")


@router.post("/passwort", status_code = 204)
def passwort_aendern(daten: PasswortAendern, request: Request, conn: Verbindung) -> None:
    benutzer = auth.sitzung_pruefen(conn, request.cookies.get(auth.COOKIE_NAME))
    if benutzer is None:
        raise FachlicherFehler("Nicht angemeldet.", status = 401)
    auth.passwort_aendern(conn, benutzer.id, daten.alt, daten.neu)


@router.get("/pruefen", status_code = 204)
def pruefen() -> None:
    """Antwortet 204, wenn eine gültige Sitzung besteht - sonst 401.

    Wird von nginx über auth_request abgefragt, bevor die Browsersicht aus
    AP-1.8 durchgelassen wird. Dass hier nichts steht, ist Absicht: Die
    eigentliche Prüfung macht die Middleware, und dieser Pfad ist bewusst
    NICHT in OEFFENTLICH eingetragen.
    """
