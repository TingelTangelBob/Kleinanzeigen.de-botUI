# SPDX-FileCopyrightText: © Anzeigen-Studio contributors
# SPDX-ArtifactOfProjectHomePage: https://github.com/TingelTangelBob/Kleinanzeigen.de-botUI/
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# eBay OAuth Authorization-Code + Refresh (AP-E-03), zuerst Sandbox.
#
# Keine Browserautomatisierung: Der Kontoinhaber oeffnet die Autorisierungs-
# URL selbst. Kurzlebiger, einmaliger `state` ist an Sitzung, Profil und
# Umgebung gebunden. Refresh je Profil/Umgebung serialisiert. HTTP ist
# austauschbar (Fakes in Tests) – keine Verkaufs-API-Aufrufe hier.

from __future__ import annotations

import base64
import hashlib
import logging
import os
import secrets
import threading
import time
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Final, Protocol, Sequence
from urllib.parse import urlencode

from anzeigen_studio.core.errors import FachlicherFehler
from anzeigen_studio.marketplaces.ebay import credentials
from anzeigen_studio.marketplaces.ebay.models import (
    MVP_SCOPES,
    EbayUmgebung,
    EbayVerbindung,
    EbayZugangStatus,
)

if TYPE_CHECKING:
    import sqlite3

LOG = logging.getLogger(__name__)

#: Kurzlebig – CSRF-Schutz, kein Dauerzustand.
STATE_TTL: Final[timedelta] = timedelta(minutes = 10)

#: HTTP-Frist fuer Token-Endpunkt (Austausch und Refresh).
HTTP_TIMEOUT_S: Final[float] = 20.0

#: eBay Scope-Basis (Sandbox und Production gleich laut Docs).
_SCOPE_BASIS: Final[str] = "https://api.ebay.com/oauth/api_scope/"

_AUTH_URL: Final[dict[EbayUmgebung, str]] = {
    EbayUmgebung.SANDBOX: "https://auth.sandbox.ebay.com/oauth2/authorize",
    EbayUmgebung.PRODUCTION: "https://auth.ebay.com/oauth2/authorize",
}

_TOKEN_URL: Final[dict[EbayUmgebung, str]] = {
    EbayUmgebung.SANDBOX: "https://api.sandbox.ebay.com/identity/v1/oauth2/token",
    EbayUmgebung.PRODUCTION: "https://api.ebay.com/identity/v1/oauth2/token",
}

# Umgebungsvariablen fuer Sandbox-App (keine Secrets ins Repo).
ENV_SANDBOX_APP_ID: Final[str] = "EBAY_SANDBOX_APP_ID"
ENV_SANDBOX_CERT_ID: Final[str] = "EBAY_SANDBOX_CERT_ID"
ENV_SANDBOX_RUNAME: Final[str] = "EBAY_SANDBOX_RUNAME"


@dataclass(frozen = True, slots = True)
class TokenHttpAntwort:
    """Ergebnis eines Token-HTTP-Aufrufs – absichtlich ohne Request-Echo."""

    status_code: int
    body: dict[str, object] | None
    text: str


class TokenTransport(Protocol):
    """Austauschbarer HTTP-Transport fuer Tests mit Fakes."""

    def post_form(
        self,
        url: str,
        *,
        headers: dict[str, str],
        data: dict[str, str],
        timeout: float,
    ) -> TokenHttpAntwort:
        ...


class HttpxTokenTransport:
    """Echter httpx-Transport. Lazy-Import wie im KI-Modul."""

    def post_form(
        self,
        url: str,
        *,
        headers: dict[str, str],
        data: dict[str, str],
        timeout: float,
    ) -> TokenHttpAntwort:
        import httpx  # noqa: PLC0415 - nur hier gebraucht

        try:
            with httpx.Client(timeout = timeout) as klient:
                antwort = klient.post(url, headers = headers, data = data)
        except httpx.TimeoutException as fehler:
            raise FachlicherFehler(
                "eBay hat nicht rechtzeitig geantwortet. Bitte später erneut versuchen.",
                status = 504,
            ) from fehler
        except httpx.HTTPError as fehler:
            LOG.warning("eBay-Token-Endpunkt nicht erreichbar: %s", type(fehler).__name__)
            raise FachlicherFehler(
                "Der eBay-Token-Endpunkt ist nicht erreichbar.",
                status = 502,
            ) from fehler

        body: dict[str, object] | None
        try:
            gelesen = antwort.json()
            body = gelesen if isinstance(gelesen, dict) else None
        except ValueError:
            body = None
        return TokenHttpAntwort(status_code = antwort.status_code, body = body, text = antwort.text)


@dataclass(frozen = True, slots = True)
class PendingOAuth:
    state: str
    sitzung_hash: str
    profil_id: int
    umgebung: EbayUmgebung
    redirect_uri: str
    app_id: str
    laeuft_ab: float  # time.monotonic()


@dataclass(frozen = True, slots = True)
class AutorisierungStart:
    authorize_url: str
    state: str
    laeuft_ab: str
    umgebung: EbayUmgebung
    profil_id: int


@dataclass(frozen = True, slots = True)
class EbayAppZugang:
    app_id: str
    app_secret: str
    redirect_uri: str


_state_lock = threading.Lock()
_pending: dict[str, PendingOAuth] = {}
_refresh_guards: dict[tuple[int, str], threading.Lock] = {}
_refresh_guards_meta = threading.Lock()




def _umgebung(wert: EbayUmgebung | str) -> EbayUmgebung:
    try:
        return wert if isinstance(wert, EbayUmgebung) else EbayUmgebung(wert)
    except ValueError as fehler:
        raise FachlicherFehler(
            "Unbekannte eBay-Umgebung. Erlaubt sind „sandbox“ und „production“.",
            feld = "umgebung",
        ) from fehler


def sitzung_hash(token: str | None) -> str:
    """Fingerprint der Studio-Sitzung – gebunden an OAuth-state, nie loggen."""
    if not token:
        raise FachlicherFehler("Nicht angemeldet.", status = 401)
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def scopes_als_urls(scopes: Sequence[str] | None = None) -> tuple[str, ...]:
    """Kurzform (`sell.inventory`) → volle eBay-Scope-URL."""
    roh = tuple(scopes) if scopes is not None else MVP_SCOPES
    urls: list[str] = []
    gesehen: set[str] = set()
    for teil in roh:
        if not teil or not str(teil).strip():
            continue
        wert = str(teil).strip()
        if not wert.startswith("http"):
            wert = _SCOPE_BASIS + wert.lstrip("/")
        if wert not in gesehen:
            gesehen.add(wert)
            urls.append(wert)
    if not urls:
        raise FachlicherFehler("Mindestens ein OAuth-Scope ist erforderlich.", feld = "scopes")
    return tuple(urls)


def sandbox_app_aus_env() -> tuple[str | None, str | None, str | None]:
    """Liest optionale Sandbox-App-Werte aus der Umgebung (ohne Defaults)."""
    def _opt(name: str) -> str | None:
        roh = os.environ.get(name)
        if roh is None:
            return None
        wert = roh.strip()
        return wert or None

    return (
        _opt(ENV_SANDBOX_APP_ID),
        _opt(ENV_SANDBOX_CERT_ID),
        _opt(ENV_SANDBOX_RUNAME),
    )


def app_zugang_aufloesen(
    conn: sqlite3.Connection,
    profil_id: int,
    umgebung: EbayUmgebung | str,
    *,
    schluessel: str | None,
    app_id: str | None = None,
    app_secret: str | None = None,
    redirect_uri: str | None = None,
) -> EbayAppZugang:
    """App-ID/Secret/RuName: Argumente → Store → Sandbox-Env."""
    umg = _umgebung(umgebung)
    if umg is not EbayUmgebung.SANDBOX:
        # Production-Verbindung ist in AP-E-03 bewusst gesperrt.
        raise FachlicherFehler(
            "Produktive eBay-Verbindung ist noch gesperrt. Bitte die Sandbox nutzen.",
            status = 409,
            feld = "umgebung",
        )

    store_id: str | None = None
    store_secret: str | None = None
    try:
        geheim = credentials.lesen(conn, profil_id, umg, schluessel = schluessel)
        store_id = geheim.app_id
        store_secret = geheim.app_secret
    except FachlicherFehler:
        pass

    env_id, env_secret, env_runame = sandbox_app_aus_env()
    fertig_id = (app_id or store_id or env_id or "").strip()
    fertig_secret = (app_secret or store_secret or env_secret or "").strip()
    fertig_runame = (redirect_uri or env_runame or "").strip()

    if not fertig_id:
        raise FachlicherFehler(
            "eBay App ID fehlt. Bitte hinterlegen oder EBAY_SANDBOX_APP_ID setzen.",
            feld = "app_id",
        )
    if not fertig_secret:
        raise FachlicherFehler(
            "eBay Cert ID (App Secret) fehlt. Bitte hinterlegen oder EBAY_SANDBOX_CERT_ID setzen.",
            feld = "app_secret",
        )
    if not fertig_runame:
        raise FachlicherFehler(
            "eBay RuName (redirect_uri) fehlt. Bitte angeben oder EBAY_SANDBOX_RUNAME setzen.",
            feld = "redirect_uri",
        )
    return EbayAppZugang(app_id = fertig_id, app_secret = fertig_secret, redirect_uri = fertig_runame)


def _pending_aufraeumen(jetzt: float | None = None) -> None:
    marke = time.monotonic() if jetzt is None else jetzt
    abgelaufen = [k for k, v in _pending.items() if v.laeuft_ab <= marke]
    for k in abgelaufen:
        _pending.pop(k, None)


def state_zuruecksetzen_fuer_tests() -> None:
    """Leert den In-Memory-State – nur fuer Tests."""
    with _state_lock:
        _pending.clear()


def _refresh_lock(profil_id: int, umgebung: EbayUmgebung) -> threading.Lock:
    schluessel = (profil_id, umgebung.value)
    with _refresh_guards_meta:
        sperre = _refresh_guards.get(schluessel)
        if sperre is None:
            sperre = threading.Lock()
            _refresh_guards[schluessel] = sperre
        return sperre


def autorisierung_starten(
    conn: sqlite3.Connection,
    *,
    profil_id: int,
    umgebung: EbayUmgebung | str,
    sitzungs_token: str | None,
    schluessel: str | None,
    app_id: str | None = None,
    app_secret: str | None = None,
    redirect_uri: str | None = None,
    scopes: Sequence[str] | None = None,
) -> AutorisierungStart:
    """Erzeugt einmaligen state und die Sandbox-Autorisierungs-URL."""
    umg = _umgebung(umgebung)
    if umg is not EbayUmgebung.SANDBOX:
        raise FachlicherFehler(
            "Produktive eBay-Verbindung ist noch gesperrt. Bitte die Sandbox nutzen.",
            status = 409,
            feld = "umgebung",
        )

    zugang = app_zugang_aufloesen(
        conn, profil_id, umg,
        schluessel = schluessel,
        app_id = app_id,
        app_secret = app_secret,
        redirect_uri = redirect_uri,
    )
    # App-Secret/ID im Store halten (ohne Tokens), damit Refresh später greift.
    credentials.speichern(
        conn, profil_id, umg,
        schluessel = schluessel,
        app_id = zugang.app_id,
        app_secret = zugang.app_secret,
        scopes = scopes if scopes is not None else MVP_SCOPES,
    )

    fingerprint = sitzung_hash(sitzungs_token)
    state = secrets.token_urlsafe(32)
    laeuft_ab_mono = time.monotonic() + STATE_TTL.total_seconds()
    laeuft_ab_iso = (datetime.now(UTC) + STATE_TTL).isoformat(timespec = "seconds")

    with _state_lock:
        _pending_aufraeumen()
        _pending[state] = PendingOAuth(
            state = state,
            sitzung_hash = fingerprint,
            profil_id = profil_id,
            umgebung = umg,
            redirect_uri = zugang.redirect_uri,
            app_id = zugang.app_id,
            laeuft_ab = laeuft_ab_mono,
        )

    scope_text = " ".join(scopes_als_urls(scopes))
    query = urlencode({
        "client_id": zugang.app_id,
        "redirect_uri": zugang.redirect_uri,
        "response_type": "code",
        "scope": scope_text,
        "state": state,
    })
    return AutorisierungStart(
        authorize_url = f"{_AUTH_URL[umg]}?{query}",
        state = state,
        laeuft_ab = laeuft_ab_iso,
        umgebung = umg,
        profil_id = profil_id,
    )


def _state_nehmen(
    state: str,
    *,
    sitzungs_token: str | None,
) -> PendingOAuth:
    if not state or not state.strip():
        raise FachlicherFehler("OAuth-State fehlt.", status = 400, feld = "state")

    fingerprint = sitzung_hash(sitzungs_token)
    jetzt = time.monotonic()
    with _state_lock:
        _pending_aufraeumen(jetzt)
        eintrag = _pending.pop(state, None)

    if eintrag is None:
        raise FachlicherFehler(
            "OAuth-State ist ungültig, abgelaufen oder bereits verwendet.",
            status = 400,
            feld = "state",
        )
    if eintrag.laeuft_ab <= jetzt:
        raise FachlicherFehler(
            "OAuth-State ist abgelaufen. Bitte die Verbindung erneut starten.",
            status = 400,
            feld = "state",
        )
    if not secrets.compare_digest(eintrag.sitzung_hash, fingerprint):
        raise FachlicherFehler(
            "OAuth-State passt nicht zur aktuellen Sitzung.",
            status = 400,
            feld = "state",
        )
    return eintrag


def _basic_auth(app_id: str, app_secret: str) -> str:
    roh = f"{app_id}:{app_secret}".encode("utf-8")
    return "Basic " + base64.b64encode(roh).decode("ascii")


def _ablauf_aus_expires_in(expires_in: object) -> str | None:
    try:
        sekunden = int(expires_in)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    if sekunden <= 0:
        return None
    return (datetime.now(UTC) + timedelta(seconds = sekunden)).isoformat(timespec = "seconds")


def _token_fehler(status: int, body: dict[str, object] | None, text: str) -> FachlicherFehler:
    kurz = ""
    if body:
        for schluessel in ("error_description", "error", "message"):
            wert = body.get(schluessel)
            if isinstance(wert, str) and wert.strip():
                kurz = wert.strip()[:200]
                break
    LOG.warning("eBay-Token-Antwort %s: %s", status, kurz or text[:200])
    if status in {400, 401}:
        return FachlicherFehler(
            "eBay hat die OAuth-Anfrage abgelehnt. Bitte App-Daten und Zustimmung prüfen.",
            status = 502,
        )
    return FachlicherFehler(
        f"eBay-Token-Endpunkt meldet einen Fehler ({status}).",
        status = 502,
    )


def _tokens_aus_antwort(body: dict[str, object]) -> tuple[str, str | None, str | None, str | None]:
    access = body.get("access_token")
    if not isinstance(access, str) or not access.strip():
        raise FachlicherFehler("eBay lieferte keinen Access-Token.", status = 502)
    refresh = body.get("refresh_token")
    refresh_s = refresh.strip() if isinstance(refresh, str) and refresh.strip() else None
    access_ablauf = _ablauf_aus_expires_in(body.get("expires_in"))
    refresh_ablauf = _ablauf_aus_expires_in(body.get("refresh_token_expires_in"))
    return access.strip(), refresh_s, access_ablauf, refresh_ablauf


def callback_abschliessen(
    conn: sqlite3.Connection,
    *,
    code: str | None,
    state: str | None,
    sitzungs_token: str | None,
    schluessel: str | None,
    error: str | None = None,
    error_description: str | None = None,
    transport: TokenTransport | None = None,
    scopes: Sequence[str] | None = None,
) -> EbayZugangStatus:
    """Tauscht den Autorisierungscode und speichert Tokens verschluesselt."""
    if error:
        beschreibung = (error_description or error).strip()[:200]
        raise FachlicherFehler(
            f"eBay-Zustimmung abgebrochen oder verweigert ({beschreibung}).",
            status = 400,
        )
    if not code or not code.strip():
        raise FachlicherFehler("OAuth-Code fehlt.", status = 400, feld = "code")

    pending = _state_nehmen(state or "", sitzungs_token = sitzungs_token)
    zugang = app_zugang_aufloesen(
        conn, pending.profil_id, pending.umgebung,
        schluessel = schluessel,
        app_id = pending.app_id,
        redirect_uri = pending.redirect_uri,
    )

    transport = transport or HttpxTokenTransport()
    antwort = transport.post_form(
        _TOKEN_URL[pending.umgebung],
        headers = {
            "Authorization": _basic_auth(zugang.app_id, zugang.app_secret),
            "Content-Type": "application/x-www-form-urlencoded",
        },
        data = {
            "grant_type": "authorization_code",
            "code": code.strip(),
            "redirect_uri": pending.redirect_uri,
        },
        timeout = HTTP_TIMEOUT_S,
    )
    if antwort.status_code != 200 or not antwort.body:
        raise _token_fehler(antwort.status_code, antwort.body, antwort.text)

    access, refresh, access_ablauf, refresh_ablauf = _tokens_aus_antwort(antwort.body)
    if not refresh:
        raise FachlicherFehler(
            "eBay lieferte keinen Refresh-Token. Bitte Scopes und App-Zustimmung prüfen.",
            status = 502,
        )

    return credentials.speichern(
        conn, pending.profil_id, pending.umgebung,
        schluessel = schluessel,
        access_token = access,
        refresh_token = refresh,
        app_id = zugang.app_id,
        app_secret = zugang.app_secret,
        scopes = scopes if scopes is not None else MVP_SCOPES,
        access_token_laeuft_ab = access_ablauf,
        refresh_token_laeuft_ab = refresh_ablauf,
        verbindung = EbayVerbindung.VERBUNDEN,
    )


def tokens_auffrischen(
    conn: sqlite3.Connection,
    profil_id: int,
    umgebung: EbayUmgebung | str,
    *,
    schluessel: str | None,
    transport: TokenTransport | None = None,
    scopes: Sequence[str] | None = None,
) -> EbayZugangStatus:
    """Erneuert den Access-Token serialisiert je Profil/Umgebung."""
    umg = _umgebung(umgebung)
    if umg is not EbayUmgebung.SANDBOX:
        raise FachlicherFehler(
            "Produktive eBay-Verbindung ist noch gesperrt. Bitte die Sandbox nutzen.",
            status = 409,
            feld = "umgebung",
        )

    sperre = _refresh_lock(profil_id, umg)
    with sperre:
        geheim = credentials.lesen(conn, profil_id, umg, schluessel = schluessel)
        if not geheim.refresh_token:
            raise FachlicherFehler(
                "Für dieses Profil/diese Umgebung ist kein Refresh-Token hinterlegt.",
                status = 409,
            )
        if not geheim.app_id or not geheim.app_secret:
            raise FachlicherFehler(
                "App ID oder Cert ID fehlen für die Token-Erneuerung.",
                status = 409,
            )

        scope_seq = scopes if scopes is not None else (geheim.scopes or MVP_SCOPES)
        transport = transport or HttpxTokenTransport()
        antwort = transport.post_form(
            _TOKEN_URL[umg],
            headers = {
                "Authorization": _basic_auth(geheim.app_id, geheim.app_secret),
                "Content-Type": "application/x-www-form-urlencoded",
            },
            data = {
                "grant_type": "refresh_token",
                "refresh_token": geheim.refresh_token,
                "scope": " ".join(scopes_als_urls(scope_seq)),
            },
            timeout = HTTP_TIMEOUT_S,
        )
        if antwort.status_code != 200 or not antwort.body:
            # Widerruf / ungueltiger Refresh → lokal als erneut verbinden markieren.
            if antwort.status_code in {400, 401}:
                credentials.als_erneut_verbinden(conn, profil_id, umg)
                raise FachlicherFehler(
                    "eBay hat den Refresh abgelehnt. Bitte erneut verbinden.",
                    status = 409,
                )
            raise _token_fehler(antwort.status_code, antwort.body, antwort.text)

        access, refresh_neu, access_ablauf, refresh_ablauf = _tokens_aus_antwort(antwort.body)
        if refresh_neu is not None:
            return credentials.tokens_erneuern(
                conn, profil_id, umg,
                schluessel = schluessel,
                access_token = access,
                access_token_laeuft_ab = access_ablauf,
                refresh_token = refresh_neu,
                refresh_token_laeuft_ab = refresh_ablauf,
            )
        return credentials.tokens_erneuern(
            conn, profil_id, umg,
            schluessel = schluessel,
            access_token = access,
            access_token_laeuft_ab = access_ablauf,
        )


def widerrufen(
    conn: sqlite3.Connection,
    profil_id: int,
    umgebung: EbayUmgebung | str,
) -> EbayZugangStatus:
    """Lokaler Widerruf: Tokens entfernen, Status „erneut verbinden“."""
    return credentials.als_erneut_verbinden(conn, profil_id, umgebung)
