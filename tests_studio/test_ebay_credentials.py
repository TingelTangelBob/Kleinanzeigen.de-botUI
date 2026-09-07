# SPDX-FileCopyrightText: © Anzeigen-Studio contributors
# SPDX-ArtifactOfProjectHomePage: https://github.com/TingelTangelBob/Kleinanzeigen.de-botUI/
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# Tests des eBay-Credential-Stores (AP-E-02).
#
# Kernzusagen: Speichern/Lesen/Loeschen, Profil-/Umgebungstrennung,
# fehlender/falscher Schluessel blockiert, Status und Repr ohne Klartext.

from __future__ import annotations

import base64
import dataclasses
import os
import sqlite3
from typing import TYPE_CHECKING

import pytest

from anzeigen_studio.core import db
from anzeigen_studio.core import profile as profile_dienst
from anzeigen_studio.core.errors import FachlicherFehler
from anzeigen_studio.marketplaces.ebay import credentials
from anzeigen_studio.marketplaces.ebay.models import (
    MVP_SCOPES,
    SCHEMA_VERSION,
    EbayUmgebung,
    EbayVerbindung,
)

if TYPE_CHECKING:
    from pathlib import Path

ACCESS = "v^1.1#i^1#AccessToken-sehr-geheim-xyz"
REFRESH = "v^1.1#i^1#RefreshToken-noch-geheimer-abc"
APP_SECRET = "CertId-AppSecret-niemals-zeigen-12345"
SCHLUESSEL = base64.b64encode(b"0123456789abcdef0123456789abcdef").decode()
ANDERS = base64.b64encode(os.urandom(32)).decode()


@pytest.fixture
def db_pfad(tmp_path: Path) -> Path:
    return tmp_path / "app.db"


@pytest.fixture
def conn(db_pfad: Path) -> sqlite3.Connection:
    verbindung = db.connect(db_pfad)
    db.migrate(verbindung)
    return verbindung


@pytest.fixture
def profil_id(conn: sqlite3.Connection, tmp_path: Path) -> int:
    verzeichnis = tmp_path / "profiles"
    verzeichnis.mkdir(exist_ok = True)
    return profile_dienst.anlegen(conn, verzeichnis, "haushalt", "Haushalt").id


@pytest.fixture
def profil_b(conn: sqlite3.Connection, tmp_path: Path) -> int:
    verzeichnis = tmp_path / "profiles"
    verzeichnis.mkdir(exist_ok = True)
    return profile_dienst.anlegen(conn, verzeichnis, "garage", "Garage").id


class TestMigration:

    def test_ebay_zugang_existiert(self, conn: sqlite3.Connection) -> None:
        row = conn.execute(
            "SELECT bezeichnung FROM schema_migration WHERE nummer = 15",
        ).fetchone()
        assert row is not None
        assert row["bezeichnung"] == "ebay-zugang"
        spalten = {
            r["name"]
            for r in conn.execute("PRAGMA table_info(ebay_zugang)").fetchall()
        }
        assert {
            "profil_id", "umgebung", "konto_id", "schema_version", "scopes",
            "app_id", "app_secret_chiffre", "access_token_chiffre",
            "refresh_token_chiffre", "access_token_laeuft_ab",
            "refresh_token_laeuft_ab", "verbindung", "verbunden_am", "geaendert_am",
        } <= spalten


class TestSpeichernLesenLoeschen:

    def test_rundlauf(self, conn: sqlite3.Connection, profil_id: int) -> None:
        st = credentials.speichern(
            conn, profil_id, EbayUmgebung.SANDBOX,
            schluessel = SCHLUESSEL,
            access_token = ACCESS,
            refresh_token = REFRESH,
            app_secret = APP_SECRET,
            app_id = "AppId-Client",
            konto_id = "ebay-user-1",
            scopes = MVP_SCOPES,
            access_token_laeuft_ab = "2026-09-07T20:00:00+00:00",
            refresh_token_laeuft_ab = "2027-09-07T20:00:00+00:00",
        )
        assert st.verbindung == EbayVerbindung.VERBUNDEN
        assert st.access_token_hinterlegt is True
        assert st.refresh_token_hinterlegt is True
        assert st.app_secret_hinterlegt is True
        assert st.konto_id == "ebay-user-1"
        assert st.app_id == "AppId-Client"
        assert st.scopes == MVP_SCOPES
        assert st.schema_version == SCHEMA_VERSION
        assert ACCESS not in repr(st)
        assert REFRESH not in repr(st)
        assert APP_SECRET not in repr(st)

        geheim = credentials.lesen(conn, profil_id, EbayUmgebung.SANDBOX, schluessel = SCHLUESSEL)
        assert geheim.access_token == ACCESS
        assert geheim.refresh_token == REFRESH
        assert geheim.app_secret == APP_SECRET
        assert "***" in repr(geheim)
        assert ACCESS not in repr(geheim)
        assert REFRESH not in repr(geheim)
        assert APP_SECRET not in repr(geheim)

        credentials.entfernen(conn, profil_id, EbayUmgebung.SANDBOX)
        st2 = credentials.status(conn, profil_id, EbayUmgebung.SANDBOX)
        assert st2.verbindung == EbayVerbindung.NICHT_VERBUNDEN
        assert st2.access_token_hinterlegt is False
        with pytest.raises(FachlicherFehler) as fehler:
            credentials.lesen(conn, profil_id, EbayUmgebung.SANDBOX, schluessel = SCHLUESSEL)
        assert fehler.value.status == 409

    def test_teilupdate_behaelt_refresh(self, conn: sqlite3.Connection, profil_id: int) -> None:
        credentials.speichern(
            conn, profil_id, "sandbox",
            schluessel = SCHLUESSEL,
            access_token = ACCESS,
            refresh_token = REFRESH,
            scopes = MVP_SCOPES,
        )
        neu = "v^1.1#i^1#AccessToken-erneuert"
        st = credentials.tokens_erneuern(
            conn, profil_id, EbayUmgebung.SANDBOX,
            schluessel = SCHLUESSEL,
            access_token = neu,
            access_token_laeuft_ab = "2026-09-08T12:00:00+00:00",
        )
        assert st.access_token_hinterlegt and st.refresh_token_hinterlegt
        geheim = credentials.lesen(conn, profil_id, "sandbox", schluessel = SCHLUESSEL)
        assert geheim.access_token == neu
        assert geheim.refresh_token == REFRESH

    def test_als_erneut_verbinden_loescht_tokens(
        self, conn: sqlite3.Connection, profil_id: int,
    ) -> None:
        credentials.speichern(
            conn, profil_id, EbayUmgebung.SANDBOX,
            schluessel = SCHLUESSEL,
            access_token = ACCESS,
            refresh_token = REFRESH,
            app_secret = APP_SECRET,
            app_id = "AppId",
        )
        st = credentials.als_erneut_verbinden(conn, profil_id, EbayUmgebung.SANDBOX)
        assert st.verbindung == EbayVerbindung.ERNEUT_VERBINDEN
        assert st.access_token_hinterlegt is False
        assert st.refresh_token_hinterlegt is False
        # App-Secret darf fuer erneutes Verbinden erhalten bleiben.
        assert st.app_secret_hinterlegt is True
        assert st.app_id == "AppId"
        geheim = credentials.lesen(conn, profil_id, EbayUmgebung.SANDBOX, schluessel = SCHLUESSEL)
        assert geheim.access_token is None
        assert geheim.refresh_token is None
        assert geheim.app_secret == APP_SECRET


class TestSchluesselUndTrennung:

    def test_ohne_schluessel_kein_speichern(
        self, conn: sqlite3.Connection, profil_id: int,
    ) -> None:
        with pytest.raises(FachlicherFehler) as fehler:
            credentials.speichern(
                conn, profil_id, EbayUmgebung.SANDBOX,
                schluessel = None,
                access_token = ACCESS,
            )
        assert fehler.value.status == 503

    def test_falscher_schluessel_blockiert_lesen(
        self, conn: sqlite3.Connection, profil_id: int,
    ) -> None:
        credentials.speichern(
            conn, profil_id, EbayUmgebung.SANDBOX,
            schluessel = SCHLUESSEL,
            access_token = ACCESS,
            refresh_token = REFRESH,
        )
        with pytest.raises(FachlicherFehler) as fehler:
            credentials.lesen(conn, profil_id, EbayUmgebung.SANDBOX, schluessel = ANDERS)
        assert "ANZEIGEN_STUDIO_SECRET_KEY" in fehler.value.meldung or fehler.value.status == 500

    def test_profiltrennung(
        self, conn: sqlite3.Connection, profil_id: int, profil_b: int,
    ) -> None:
        credentials.speichern(
            conn, profil_id, EbayUmgebung.SANDBOX,
            schluessel = SCHLUESSEL,
            access_token = ACCESS,
            refresh_token = REFRESH,
            konto_id = "A",
        )
        credentials.speichern(
            conn, profil_b, EbayUmgebung.SANDBOX,
            schluessel = SCHLUESSEL,
            access_token = "other-access",
            refresh_token = "other-refresh",
            konto_id = "B",
        )
        assert credentials.status(conn, profil_id, "sandbox").konto_id == "A"
        assert credentials.status(conn, profil_b, "sandbox").konto_id == "B"
        assert credentials.lesen(conn, profil_id, "sandbox", schluessel = SCHLUESSEL).access_token == ACCESS

    def test_umgebungstrennung(self, conn: sqlite3.Connection, profil_id: int) -> None:
        credentials.speichern(
            conn, profil_id, EbayUmgebung.SANDBOX,
            schluessel = SCHLUESSEL,
            access_token = ACCESS,
            refresh_token = REFRESH,
            konto_id = "sandbox-user",
        )
        credentials.speichern(
            conn, profil_id, EbayUmgebung.PRODUCTION,
            schluessel = SCHLUESSEL,
            access_token = "prod-access",
            refresh_token = "prod-refresh",
            konto_id = "prod-user",
        )
        sb = credentials.status(conn, profil_id, EbayUmgebung.SANDBOX)
        pr = credentials.status(conn, profil_id, EbayUmgebung.PRODUCTION)
        assert sb.konto_id == "sandbox-user"
        assert pr.konto_id == "prod-user"
        assert sb.umgebung == EbayUmgebung.SANDBOX
        assert pr.umgebung == EbayUmgebung.PRODUCTION
        credentials.entfernen(conn, profil_id, EbayUmgebung.SANDBOX)
        assert credentials.status(conn, profil_id, EbayUmgebung.PRODUCTION).konto_id == "prod-user"
        assert credentials.status(conn, profil_id, EbayUmgebung.SANDBOX).verbindung == EbayVerbindung.NICHT_VERBUNDEN

    def test_ungueltige_umgebung(self, conn: sqlite3.Connection, profil_id: int) -> None:
        with pytest.raises(FachlicherFehler) as fehler:
            credentials.status(conn, profil_id, "staging")
        assert fehler.value.feld == "umgebung"

    def test_profil_loeschen_nimmt_ebay_zugang_mit(
        self, conn: sqlite3.Connection, profil_id: int, tmp_path: Path,
    ) -> None:
        credentials.speichern(
            conn, profil_id, EbayUmgebung.SANDBOX,
            schluessel = SCHLUESSEL,
            access_token = ACCESS,
            refresh_token = REFRESH,
        )
        profile_dienst.loeschen(conn, tmp_path / "profiles", "haushalt", mit_daten = True)
        rest = conn.execute("SELECT COUNT(*) AS n FROM ebay_zugang").fetchone()
        assert rest["n"] == 0


class TestKeinKlartext:

    def test_tokens_stehen_nirgends_im_klartext(
        self, conn: sqlite3.Connection, profil_id: int, db_pfad: Path,
    ) -> None:
        credentials.speichern(
            conn, profil_id, EbayUmgebung.SANDBOX,
            schluessel = SCHLUESSEL,
            access_token = ACCESS,
            refresh_token = REFRESH,
            app_secret = APP_SECRET,
        )
        conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")

        for geheim in (ACCESS, REFRESH, APP_SECRET):
            gesucht = geheim.encode("utf-8")
            geprueft = 0
            for pfad in (db_pfad, db_pfad.with_suffix(".db-wal"), db_pfad.with_suffix(".db-shm")):
                if not pfad.exists():
                    continue
                geprueft += 1
                assert gesucht not in pfad.read_bytes(), f"{geheim[:12]}… im Klartext in {pfad.name}"
            assert geprueft >= 1

    def test_status_gibt_keine_tokens_heraus(
        self, conn: sqlite3.Connection, profil_id: int,
    ) -> None:
        credentials.speichern(
            conn, profil_id, EbayUmgebung.SANDBOX,
            schluessel = SCHLUESSEL,
            access_token = ACCESS,
            refresh_token = REFRESH,
            app_secret = APP_SECRET,
            konto_id = "user-x",
        )
        st = credentials.status(conn, profil_id, EbayUmgebung.SANDBOX)
        felder = {f.name: getattr(st, f.name) for f in dataclasses.fields(st)}
        verboten = {"access_token", "refresh_token", "app_secret", "token", "secret", "chiffre"}
        assert not (set(felder) & verboten)
        # Zeitstempel ausklammern (Zufallstreffer mit Tokenlaengen, vgl. test_zugang).
        geprueft = {k: v for k, v in felder.items() if k not in {"geaendert_am", "verbunden_am", "access_token_laeuft_ab", "refresh_token_laeuft_ab"}}
        text = repr(geprueft)
        assert ACCESS not in text
        assert REFRESH not in text
        assert APP_SECRET not in text
        assert "access_token_hinterlegt" in geprueft
