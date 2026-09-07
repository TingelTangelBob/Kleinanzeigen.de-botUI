# SPDX-FileCopyrightText: © Anzeigen-Studio contributors
# SPDX-ArtifactOfProjectHomePage: https://github.com/TingelTangelBob/Kleinanzeigen.de-botUI/
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# HTTP-Endpunkte fuer eBay-OAuth (AP-E-03). Nur Sandbox-Verbindung.
# Keine Tokens in Antworten. Callback ist oeffentlich, prueft aber state.

from __future__ import annotations

import sqlite3
from typing import TYPE_CHECKING, Annotated, Literal

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from pydantic import BaseModel, Field

from anzeigen_studio.core import auth, db
from anzeigen_studio.core import profile as profile_dienst
from anzeigen_studio.core.errors import FachlicherFehler
from anzeigen_studio.core.settings import Settings
from anzeigen_studio.marketplaces.ebay import credentials, oauth
from anzeigen_studio.marketplaces.ebay.models import (
    MVP_SCOPES,
    EbayUmgebung,
    EbayZugangStatus,
)

if TYPE_CHECKING:
    from collections.abc import Iterator

router = APIRouter(prefix = "/api/ebay", tags = ["eBay"])

#: Browser-Callback von eBay – ohne Sitzungs-Whitelist waere der Redirect 401.
CALLBACK_PFAD = "/api/ebay/oauth/callback"


def _verbindung(request: Request) -> Iterator[sqlite3.Connection]:
    cfg: Settings = request.app.state.settings
    conn = db.connect(cfg.database_path)
    try:
        yield conn
    finally:
        conn.close()


def _einstellungen(request: Request) -> Settings:
    return request.app.state.settings


Verbindung = Annotated[sqlite3.Connection, Depends(_verbindung)]
Konfiguration = Annotated[Settings, Depends(_einstellungen)]
ProfilSlug = Annotated[str, Query(min_length = 1, max_length = 32, description = "Aktives Profil")]
UmgebungParam = Annotated[
    Literal["sandbox", "production"],
    Query(description = "eBay-Umgebung (Verbinden nur Sandbox)"),
]


def _profil_id(conn: sqlite3.Connection, slug: str) -> int:
    p = profile_dienst.nach_slug(conn, slug)
    if p is None:
        raise FachlicherFehler("Profil nicht gefunden.", status = 404, feld = "profil")
    return p.id


def _status_ausgabe(st: EbayZugangStatus) -> "StatusAusgabe":
    return StatusAusgabe(
        profil_id = st.profil_id,
        umgebung = st.umgebung.value,
        verbindung = st.verbindung.value,
        konto_id = st.konto_id,
        app_id = st.app_id,
        scopes = list(st.scopes),
        schema_version = st.schema_version,
        access_token_hinterlegt = st.access_token_hinterlegt,
        refresh_token_hinterlegt = st.refresh_token_hinterlegt,
        app_secret_hinterlegt = st.app_secret_hinterlegt,
        access_token_laeuft_ab = st.access_token_laeuft_ab,
        refresh_token_laeuft_ab = st.refresh_token_laeuft_ab,
        verbunden_am = st.verbunden_am,
        geaendert_am = st.geaendert_am,
    )


class StatusAusgabe(BaseModel):
    profil_id: int
    umgebung: str
    verbindung: str
    konto_id: str | None = None
    app_id: str | None = None
    scopes: list[str] = Field(default_factory = list)
    schema_version: int
    access_token_hinterlegt: bool
    refresh_token_hinterlegt: bool
    app_secret_hinterlegt: bool
    access_token_laeuft_ab: str | None = None
    refresh_token_laeuft_ab: str | None = None
    verbunden_am: str | None = None
    geaendert_am: str | None = None


class AppEingabe(BaseModel):
    app_id: str = Field(min_length = 1, max_length = 200)
    app_secret: str = Field(min_length = 1, max_length = 400)
    #: Optional – RuName kann auch per EBAY_SANDBOX_RUNAME kommen.
    redirect_uri: str | None = Field(default = None, min_length = 1, max_length = 400)


class StartEingabe(BaseModel):
    redirect_uri: str | None = Field(default = None, min_length = 1, max_length = 400)
    app_id: str | None = Field(default = None, min_length = 1, max_length = 200)
    app_secret: str | None = Field(default = None, min_length = 1, max_length = 400)


class StartAusgabe(BaseModel):
    authorize_url: str
    state: str
    laeuft_ab: str
    umgebung: str
    profil_id: int


@router.get("/status", response_model = StatusAusgabe)
def status_lesen(
    conn: Verbindung,
    profil: ProfilSlug,
    umgebung: UmgebungParam = "sandbox",
) -> StatusAusgabe:
    return _status_ausgabe(credentials.status(conn, _profil_id(conn, profil), umgebung))


@router.put("/app", response_model = StatusAusgabe)
def app_setzen(
    daten: AppEingabe,
    conn: Verbindung,
    cfg: Konfiguration,
    profil: ProfilSlug,
    umgebung: UmgebungParam = "sandbox",
) -> StatusAusgabe:
    if umgebung != EbayUmgebung.SANDBOX.value:
        raise FachlicherFehler(
            "Produktive eBay-Verbindung ist noch gesperrt. Bitte die Sandbox nutzen.",
            status = 409,
            feld = "umgebung",
        )
    st = credentials.speichern(
        conn, _profil_id(conn, profil), umgebung,
        schluessel = cfg.secret_key,
        app_id = daten.app_id.strip(),
        app_secret = daten.app_secret,
        scopes = MVP_SCOPES,
    )
    # RuName ist kein Geheimnis; wird nur fuer den naechsten Start gebraucht.
    # Persistenz ueber Env – siehe docs/EBAY-OAUTH-SANDBOX.md.
    _ = daten.redirect_uri
    return _status_ausgabe(st)


@router.post("/oauth/start", response_model = StartAusgabe)
def oauth_starten(
    request: Request,
    conn: Verbindung,
    cfg: Konfiguration,
    profil: ProfilSlug,
    umgebung: UmgebungParam = "sandbox",
    daten: StartEingabe | None = None,
) -> StartAusgabe:
    daten = daten or StartEingabe()
    start = oauth.autorisierung_starten(
        conn,
        profil_id = _profil_id(conn, profil),
        umgebung = umgebung,
        sitzungs_token = request.cookies.get(auth.COOKIE_NAME),
        schluessel = cfg.secret_key,
        app_id = daten.app_id,
        app_secret = daten.app_secret,
        redirect_uri = daten.redirect_uri,
    )
    return StartAusgabe(
        authorize_url = start.authorize_url,
        state = start.state,
        laeuft_ab = start.laeuft_ab,
        umgebung = start.umgebung.value,
        profil_id = start.profil_id,
    )


@router.get("/oauth/callback", response_model = None)
def oauth_callback(
    request: Request,
    conn: Verbindung,
    cfg: Konfiguration,
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
    error_description: str | None = None,
) -> RedirectResponse | HTMLResponse:
    """eBay Redirect. Oeffentlich, aber state an Sitzung gebunden."""
    try:
        st = oauth.callback_abschliessen(
            conn,
            code = code,
            state = state,
            sitzungs_token = request.cookies.get(auth.COOKIE_NAME),
            schluessel = cfg.secret_key,
            error = error,
            error_description = error_description,
        )
    except FachlicherFehler as fehler:
        return HTMLResponse(
            _callback_html(ok = False, meldung = fehler.meldung),
            status_code = fehler.status if fehler.status >= 400 else 400,
        )

    # Hash-Route der Oberflaeche; UI fuer eBay folgt in AP-E-09.
    ziel = "/#einstellungen?ebay=verbunden&umgebung=" + st.umgebung.value
    return RedirectResponse(url = ziel, status_code = 303)


@router.post("/oauth/refresh", response_model = StatusAusgabe)
def oauth_refresh(
    conn: Verbindung,
    cfg: Konfiguration,
    profil: ProfilSlug,
    umgebung: UmgebungParam = "sandbox",
) -> StatusAusgabe:
    st = oauth.tokens_auffrischen(
        conn, _profil_id(conn, profil), umgebung,
        schluessel = cfg.secret_key,
    )
    return _status_ausgabe(st)


@router.post("/oauth/widerrufen", response_model = StatusAusgabe)
def oauth_widerrufen(
    conn: Verbindung,
    profil: ProfilSlug,
    umgebung: UmgebungParam = "sandbox",
) -> StatusAusgabe:
    st = oauth.widerrufen(conn, _profil_id(conn, profil), umgebung)
    return _status_ausgabe(st)


@router.delete("/verbindung", status_code = 204)
def verbindung_entfernen(
    conn: Verbindung,
    profil: ProfilSlug,
    umgebung: UmgebungParam = "sandbox",
) -> None:
    credentials.entfernen(conn, _profil_id(conn, profil), umgebung)


def _callback_html(*, ok: bool, meldung: str) -> str:
    titel = "eBay verbunden" if ok else "eBay-Verbindung fehlgeschlagen"
    return (
        "<!DOCTYPE html><html lang=\"de\"><head><meta charset=\"utf-8\">"
        f"<title>{titel}</title></head><body>"
        f"<h1>{titel}</h1><p>{meldung}</p>"
        "<p><a href=\"/#einstellungen\">Zurück zu den Einstellungen</a></p>"
        "</body></html>"
    )

