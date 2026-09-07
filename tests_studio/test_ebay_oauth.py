# SPDX-FileCopyrightText: © Anzeigen-Studio contributors
# SPDX-ArtifactOfProjectHomePage: https://github.com/TingelTangelBob/Kleinanzeigen.de-botUI/
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# Tests eBay OAuth Sandbox + Refresh (AP-E-03) mit Fake-Transport.
#
# Abgedeckt: state (falsch/ablauf/einmalig/sitzung), Callback, Refresh
# serialisiert, Widerruf, HTTP-Timeout, Production gesperrt. Kein Netz.

from __future__ import annotations

import base64
import threading
import time
from typing import TYPE_CHECKING
from urllib.parse import parse_qs, urlparse

import pytest

from anzeigen_studio.core import db
from anzeigen_studio.core import profile as profile_dienst
from anzeigen_studio.core.errors import FachlicherFehler
from anzeigen_studio.marketplaces.ebay import credentials, oauth
from anzeigen_studio.marketplaces.ebay.models import (
    MVP_SCOPES,
    EbayUmgebung,
    EbayVerbindung,
)
from anzeigen_studio.marketplaces.ebay.oauth import TokenHttpAntwort

if TYPE_CHECKING:
    import sqlite3
    from pathlib import Path as PathType

SCHLUESSEL = base64.b64encode(b"0123456789abcdef0123456789abcdef").decode()
APP_ID = "EbayAppId-Sandbox-Client"
APP_SECRET = "EbayCertId-Sandbox-Secret"
RUNAME = "Anzeigen_Studio_RuName"
SITZUNG_A = "sitzung-token-profil-a-aaaaaaaa"
SITZUNG_B = "sitzung-token-profil-b-bbbbbbbb"


class FakeTransport:
    """Steuerbarer Token-Transport ohne Netzwerk."""

    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []
        self.antworten: list[TokenHttpAntwort | BaseException] = []
        self.block_bis: threading.Event | None = None
        self.betreten: threading.Event | None = None

    def queuee(self, antwort: TokenHttpAntwort | BaseException) -> None:
        self.antworten.append(antwort)

    def post_form(
        self,
        url: str,
        *,
        headers: dict[str, str],
        data: dict[str, str],
        timeout: float,
    ) -> TokenHttpAntwort:
        self.calls.append({"url": url, "headers": headers, "data": data, "timeout": timeout})
        if self.betreten is not None:
            self.betreten.set()
        if self.block_bis is not None:
            self.block_bis.wait(timeout = 5)
        if not self.antworten:
            raise AssertionError("FakeTransport ohne Antwort")
        antwort = self.antworten.pop(0)
        if isinstance(antwort, BaseException):
            raise antwort
        return antwort


@pytest.fixture(autouse = True)
def _state_reset() -> None:
    oauth.state_zuruecksetzen_fuer_tests()


@pytest.fixture
def db_pfad(tmp_path: PathType) -> PathType:
    return tmp_path / "app.db"


@pytest.fixture
def conn(db_pfad: PathType) -> sqlite3.Connection:
    verbindung = db.connect(db_pfad)
    db.migrate(verbindung)
    return verbindung


@pytest.fixture
def profil_id(conn: sqlite3.Connection, tmp_path: PathType) -> int:
    verzeichnis = tmp_path / "profiles"
    verzeichnis.mkdir(exist_ok = True)
    return profile_dienst.anlegen(conn, verzeichnis, "haushalt", "Haushalt").id


def _app_hinterlegen(conn: sqlite3.Connection, profil_id: int) -> None:
    credentials.speichern(
        conn, profil_id, EbayUmgebung.SANDBOX,
        schluessel = SCHLUESSEL,
        app_id = APP_ID,
        app_secret = APP_SECRET,
        scopes = MVP_SCOPES,
    )


def _start(conn: sqlite3.Connection, profil_id: int, *, sitzung: str = SITZUNG_A,
           redirect_uri: str = RUNAME) -> oauth.AutorisierungStart:
    return oauth.autorisierung_starten(
        conn,
        profil_id = profil_id,
        umgebung = EbayUmgebung.SANDBOX,
        sitzungs_token = sitzung,
        schluessel = SCHLUESSEL,
        redirect_uri = redirect_uri,
    )


class TestAutorisierungStart:

    def test_url_und_state_gebunden(
        self, conn: sqlite3.Connection, profil_id: int, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.delenv(oauth.ENV_SANDBOX_APP_ID, raising = False)
        monkeypatch.delenv(oauth.ENV_SANDBOX_CERT_ID, raising = False)
        monkeypatch.delenv(oauth.ENV_SANDBOX_RUNAME, raising = False)
        _app_hinterlegen(conn, profil_id)
        start = _start(conn, profil_id)
        assert start.state
        assert "auth.sandbox.ebay.com" in start.authorize_url
        parsed = urlparse(start.authorize_url)
        qs = parse_qs(parsed.query)
        assert qs["client_id"] == [APP_ID]
        assert qs["redirect_uri"] == [RUNAME]
        assert qs["response_type"] == ["code"]
        assert qs["state"] == [start.state]
        scope = qs["scope"][0]
        assert "sell.inventory" in scope
        assert "sell.account" in scope
        assert "https://api.ebay.com/oauth/api_scope/" in scope

    def test_production_gesperrt(self, conn: sqlite3.Connection, profil_id: int) -> None:
        with pytest.raises(FachlicherFehler) as fehler:
            oauth.autorisierung_starten(
                conn,
                profil_id = profil_id,
                umgebung = EbayUmgebung.PRODUCTION,
                sitzungs_token = SITZUNG_A,
                schluessel = SCHLUESSEL,
                app_id = APP_ID,
                app_secret = APP_SECRET,
                redirect_uri = RUNAME,
            )
        assert fehler.value.status == 409


class TestCallback:

    def test_erfolgreicher_code_tausch(
        self, conn: sqlite3.Connection, profil_id: int,
    ) -> None:
        _app_hinterlegen(conn, profil_id)
        start = _start(conn, profil_id)
        fake = FakeTransport()
        fake.queuee(TokenHttpAntwort(
            status_code = 200,
            body = {
                "access_token": "access-neu",
                "expires_in": 7200,
                "refresh_token": "refresh-neu",
                "refresh_token_expires_in": 47304000,
                "token_type": "User Access Token",
            },
            text = "{}",
        ))
        st = oauth.callback_abschliessen(
            conn,
            code = "auth-code-1",
            state = start.state,
            sitzungs_token = SITZUNG_A,
            schluessel = SCHLUESSEL,
            transport = fake,
        )
        assert st.verbindung == EbayVerbindung.VERBUNDEN
        assert st.access_token_hinterlegt and st.refresh_token_hinterlegt
        geheim = credentials.lesen(conn, profil_id, "sandbox", schluessel = SCHLUESSEL)
        assert geheim.access_token == "access-neu"
        assert geheim.refresh_token == "refresh-neu"
        assert fake.calls[0]["data"]["grant_type"] == "authorization_code"  # type: ignore[index]

    def test_falscher_state(self, conn: sqlite3.Connection, profil_id: int) -> None:
        _app_hinterlegen(conn, profil_id)
        _start(conn, profil_id)
        with pytest.raises(FachlicherFehler) as fehler:
            oauth.callback_abschliessen(
                conn,
                code = "x",
                state = "nicht-dieser-state",
                sitzungs_token = SITZUNG_A,
                schluessel = SCHLUESSEL,
                transport = FakeTransport(),
            )
        assert fehler.value.status == 400
        assert "state" in (fehler.value.feld or "")

    def test_state_einmalig(self, conn: sqlite3.Connection, profil_id: int) -> None:
        _app_hinterlegen(conn, profil_id)
        start = _start(conn, profil_id)
        fake = FakeTransport()
        fake.queuee(TokenHttpAntwort(
            status_code = 200,
            body = {
                "access_token": "a1", "expires_in": 100,
                "refresh_token": "r1", "refresh_token_expires_in": 1000,
            },
            text = "{}",
        ))
        oauth.callback_abschliessen(
            conn, code = "c1", state = start.state,
            sitzungs_token = SITZUNG_A, schluessel = SCHLUESSEL, transport = fake,
        )
        with pytest.raises(FachlicherFehler) as fehler:
            oauth.callback_abschliessen(
                conn, code = "c2", state = start.state,
                sitzungs_token = SITZUNG_A, schluessel = SCHLUESSEL, transport = FakeTransport(),
            )
        assert fehler.value.status == 400

    def test_falsche_sitzung(self, conn: sqlite3.Connection, profil_id: int) -> None:
        _app_hinterlegen(conn, profil_id)
        start = _start(conn, profil_id, sitzung = SITZUNG_A)
        with pytest.raises(FachlicherFehler) as fehler:
            oauth.callback_abschliessen(
                conn, code = "c", state = start.state,
                sitzungs_token = SITZUNG_B, schluessel = SCHLUESSEL,
                transport = FakeTransport(),
            )
        assert fehler.value.status == 400

    def test_ablauf(self, conn: sqlite3.Connection, profil_id: int, monkeypatch: pytest.MonkeyPatch) -> None:
        _app_hinterlegen(conn, profil_id)
        monkeypatch.setattr(oauth, "STATE_TTL", __import__("datetime").timedelta(milliseconds = 1))
        start = _start(conn, profil_id)
        time.sleep(0.02)
        with pytest.raises(FachlicherFehler) as fehler:
            oauth.callback_abschliessen(
                conn, code = "c", state = start.state,
                sitzungs_token = SITZUNG_A, schluessel = SCHLUESSEL,
                transport = FakeTransport(),
            )
        assert fehler.value.status == 400

    def test_ebay_error_query(self, conn: sqlite3.Connection, profil_id: int) -> None:
        _app_hinterlegen(conn, profil_id)
        start = _start(conn, profil_id)
        with pytest.raises(FachlicherFehler) as fehler:
            oauth.callback_abschliessen(
                conn, code = None, state = start.state,
                sitzungs_token = SITZUNG_A, schluessel = SCHLUESSEL,
                error = "access_denied",
                error_description = "user refused",
            )
        assert fehler.value.status == 400


class TestRefresh:

    def _verbunden(self, conn: sqlite3.Connection, profil_id: int) -> None:
        credentials.speichern(
            conn, profil_id, EbayUmgebung.SANDBOX,
            schluessel = SCHLUESSEL,
            app_id = APP_ID,
            app_secret = APP_SECRET,
            access_token = "access-alt",
            refresh_token = "refresh-alt",
            scopes = MVP_SCOPES,
            access_token_laeuft_ab = "2026-09-07T10:00:00+00:00",
        )

    def test_refresh_erneuert_access(self, conn: sqlite3.Connection, profil_id: int) -> None:
        self._verbunden(conn, profil_id)
        fake = FakeTransport()
        fake.queuee(TokenHttpAntwort(
            status_code = 200,
            body = {"access_token": "access-frisch", "expires_in": 7200, "token_type": "User Access Token"},
            text = "{}",
        ))
        st = oauth.tokens_auffrischen(
            conn, profil_id, "sandbox", schluessel = SCHLUESSEL, transport = fake,
        )
        assert st.verbindung == EbayVerbindung.VERBUNDEN
        geheim = credentials.lesen(conn, profil_id, "sandbox", schluessel = SCHLUESSEL)
        assert geheim.access_token == "access-frisch"
        assert geheim.refresh_token == "refresh-alt"
        assert fake.calls[0]["data"]["grant_type"] == "refresh_token"  # type: ignore[index]

    def test_widerruf_bei_ablehnung(self, conn: sqlite3.Connection, profil_id: int) -> None:
        self._verbunden(conn, profil_id)
        fake = FakeTransport()
        fake.queuee(TokenHttpAntwort(
            status_code = 401,
            body = {"error": "invalid_grant"},
            text = "{}",
        ))
        with pytest.raises(FachlicherFehler) as fehler:
            oauth.tokens_auffrischen(
                conn, profil_id, "sandbox", schluessel = SCHLUESSEL, transport = fake,
            )
        assert fehler.value.status == 409
        st = credentials.status(conn, profil_id, "sandbox")
        assert st.verbindung == EbayVerbindung.ERNEUT_VERBINDEN
        assert st.access_token_hinterlegt is False

    def test_timeout(self, conn: sqlite3.Connection, profil_id: int) -> None:
        self._verbunden(conn, profil_id)
        fake = FakeTransport()
        fake.queuee(FachlicherFehler(
            "eBay hat nicht rechtzeitig geantwortet. Bitte später erneut versuchen.",
            status = 504,
        ))
        with pytest.raises(FachlicherFehler) as fehler:
            oauth.tokens_auffrischen(
                conn, profil_id, "sandbox", schluessel = SCHLUESSEL, transport = fake,
            )
        assert fehler.value.status == 504

    def test_refresh_serialisiert(self, db_pfad: PathType, profil_id: int) -> None:
        # Eigene Verbindungen je Thread – SQLite-Connection ist nicht parallel nutzbar.
        vorbereitung = db.connect(db_pfad)
        try:
            self._verbunden(vorbereitung, profil_id)
        finally:
            vorbereitung.close()

        fake = FakeTransport()
        fake.betreten = threading.Event()
        fake.block_bis = threading.Event()
        fake.queuee(TokenHttpAntwort(
            status_code = 200,
            body = {"access_token": "t1", "expires_in": 100},
            text = "{}",
        ))
        fake.queuee(TokenHttpAntwort(
            status_code = 200,
            body = {"access_token": "t2", "expires_in": 100},
            text = "{}",
        ))

        ergebnisse: list[str] = []
        fehler: list[BaseException] = []

        def lauf(marke: str) -> None:
            eigene = db.connect(db_pfad)
            try:
                st = oauth.tokens_auffrischen(
                    eigene, profil_id, "sandbox", schluessel = SCHLUESSEL, transport = fake,
                )
                geheim = credentials.lesen(eigene, profil_id, "sandbox", schluessel = SCHLUESSEL)
                ergebnisse.append(f"{marke}:{geheim.access_token}")
                _ = st
            except BaseException as exc:  # noqa: BLE001 - Test sammelt
                fehler.append(exc)
            finally:
                eigene.close()

        t1 = threading.Thread(target = lauf, args = ("a",))
        t1.start()
        assert fake.betreten.wait(2)
        t2 = threading.Thread(target = lauf, args = ("b",))
        t2.start()
        time.sleep(0.05)
        # Zweiter Aufruf darf noch nicht in den Transport gelangt sein.
        assert len(fake.calls) == 1
        fake.block_bis.set()
        t1.join(timeout = 3)
        t2.join(timeout = 3)
        assert not fehler, fehler
        assert len(fake.calls) == 2
        assert len(ergebnisse) == 2


class TestWiderrufLokal:

    def test_widerrufen(self, conn: sqlite3.Connection, profil_id: int) -> None:
        credentials.speichern(
            conn, profil_id, "sandbox",
            schluessel = SCHLUESSEL,
            access_token = "a", refresh_token = "r", app_secret = APP_SECRET, app_id = APP_ID,
        )
        st = oauth.widerrufen(conn, profil_id, "sandbox")
        assert st.verbindung == EbayVerbindung.ERNEUT_VERBINDEN
        assert st.access_token_hinterlegt is False


class TestEnvAufloesung:

    def test_runame_aus_env(self, conn: sqlite3.Connection, profil_id: int, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv(oauth.ENV_SANDBOX_APP_ID, APP_ID)
        monkeypatch.setenv(oauth.ENV_SANDBOX_CERT_ID, APP_SECRET)
        monkeypatch.setenv(oauth.ENV_SANDBOX_RUNAME, "Env_RuName")
        start = oauth.autorisierung_starten(
            conn,
            profil_id = profil_id,
            umgebung = "sandbox",
            sitzungs_token = SITZUNG_A,
            schluessel = SCHLUESSEL,
        )
        assert "Env_RuName" in start.authorize_url


class TestSitzungHash:

    def test_ohne_token(self) -> None:
        with pytest.raises(FachlicherFehler) as fehler:
            oauth.sitzung_hash(None)
        assert fehler.value.status == 401

    def test_stabil(self) -> None:
        assert oauth.sitzung_hash("abc") == oauth.sitzung_hash("abc")
        assert oauth.sitzung_hash("abc") != oauth.sitzung_hash("abd")


class TestScopes:

    def test_urls(self) -> None:
        urls = oauth.scopes_als_urls(("sell.inventory", "sell.account"))
        assert urls == (
            "https://api.ebay.com/oauth/api_scope/sell.inventory",
            "https://api.ebay.com/oauth/api_scope/sell.account",
        )
