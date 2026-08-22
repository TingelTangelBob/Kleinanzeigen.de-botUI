# SPDX-FileCopyrightText: © Anzeigen-Studio contributors
# SPDX-ArtifactOfProjectHomePage: https://github.com/TingelTangelBob/Kleinanzeigen.de-botUI/
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# Tests der Zugangsdatenverwaltung (AP-1.4).
#
# Der wichtigste Test ist test_passwort_steht_nirgends_im_klartext: Er
# durchsucht die tatsaechliche Datenbankdatei byteweise. Alles andere prueft
# Verhalten - dieser prueft die Zusage.

from __future__ import annotations

import base64
import os
import sqlite3
from typing import TYPE_CHECKING

import pytest

from anzeigen_studio.core import db
from anzeigen_studio.core import profile as profile_dienst
from anzeigen_studio.core import zugang
from anzeigen_studio.core.crypto import Tresor, SchluesselUngueltig, tresor_oder_fehler
from anzeigen_studio.core.errors import FachlicherFehler

if TYPE_CHECKING:
    from pathlib import Path

GEHEIMES_PASSWORT = "Hunter2-sehr-geheim-!§$%"
SCHLUESSEL = base64.b64encode(b"0123456789abcdef0123456789abcdef").decode()


@pytest.fixture
def db_pfad(tmp_path:Path) -> Path:
    return tmp_path / "app.db"


@pytest.fixture
def conn(db_pfad:Path) -> sqlite3.Connection:
    verbindung = db.connect(db_pfad)
    db.migrate(verbindung)
    return verbindung


@pytest.fixture
def profil_id(conn:sqlite3.Connection, tmp_path:Path) -> int:
    verzeichnis = tmp_path / "profiles"
    verzeichnis.mkdir(exist_ok = True)
    return profile_dienst.anlegen(conn, verzeichnis, "haushalt", "Haushalt").id


class TestTresor:

    def test_rundlauf(self) -> None:
        tresor = Tresor.aus_text(SCHLUESSEL)
        assert tresor.entschluesseln(tresor.verschluesseln(GEHEIMES_PASSWORT)) == GEHEIMES_PASSWORT

    def test_gleicher_klartext_ergibt_verschiedene_chiffrate(self) -> None:
        # Zufaellige Nonce je Vorgang. Sonst liesse sich an gleichen Chiffraten
        # ablesen, dass zwei Profile dasselbe Passwort benutzen.
        tresor = Tresor.aus_text(SCHLUESSEL)
        assert tresor.verschluesseln(GEHEIMES_PASSWORT) != tresor.verschluesseln(GEHEIMES_PASSWORT)

    def test_manipulation_faellt_auf(self) -> None:
        tresor = Tresor.aus_text(SCHLUESSEL)
        chiffre = bytearray(tresor.verschluesseln(GEHEIMES_PASSWORT))
        chiffre[-1] ^= 0x01
        with pytest.raises(FachlicherFehler):
            tresor.entschluesseln(bytes(chiffre))

    def test_falscher_schluessel_meldet_verstaendlich(self) -> None:
        chiffre = Tresor.aus_text(SCHLUESSEL).verschluesseln(GEHEIMES_PASSWORT)
        anderer = base64.b64encode(os.urandom(32)).decode()
        with pytest.raises(FachlicherFehler) as fehler:
            Tresor.aus_text(anderer).entschluesseln(chiffre)
        assert "ANZEIGEN_STUDIO_SECRET_KEY" in fehler.value.meldung

    @pytest.mark.parametrize("text", ["", "kein-base64!!", base64.b64encode(b"zu-kurz").decode()])
    def test_ungueltiger_schluessel(self, text:str) -> None:
        with pytest.raises((SchluesselUngueltig, FachlicherFehler)):
            Tresor.aus_text(text)

    def test_ohne_schluessel_kein_klartext_rueckfall(self) -> None:
        # Entscheidend: Fehlt der Schluessel, wird abgebrochen - NICHT
        # unverschluesselt gespeichert.
        with pytest.raises(FachlicherFehler) as fehler:
            tresor_oder_fehler(None)
        assert fehler.value.status == 503


class TestZugangsdaten:

    def test_setzen_und_status(self, conn:sqlite3.Connection, profil_id:int) -> None:
        st = zugang.setzen(conn, profil_id, benutzername = "a@b.de",
                           passwort = GEHEIMES_PASSWORT, schluessel = SCHLUESSEL)
        assert st.benutzername == "a@b.de"
        assert st.passwort_hinterlegt is True

    def test_benutzername_aendern_ohne_passwort(self, conn:sqlite3.Connection, profil_id:int) -> None:
        zugang.setzen(conn, profil_id, benutzername = "alt@b.de",
                      passwort = GEHEIMES_PASSWORT, schluessel = SCHLUESSEL)
        st = zugang.setzen(conn, profil_id, benutzername = "neu@b.de",
                           passwort = None, schluessel = SCHLUESSEL)
        assert st.benutzername == "neu@b.de"
        assert st.passwort_hinterlegt is True
        # Das alte Passwort muss weiterhin entschluesselbar sein.
        umgebung = zugang.umgebung_fuer_lauf(conn, profil_id, schluessel = SCHLUESSEL)
        assert umgebung[zugang.ENV_PASSWORT] == GEHEIMES_PASSWORT

    def test_ohne_vorhandenes_passwort_ist_none_ein_fehler(self, conn:sqlite3.Connection, profil_id:int) -> None:
        with pytest.raises(FachlicherFehler):
            zugang.setzen(conn, profil_id, benutzername = "a@b.de",
                          passwort = None, schluessel = SCHLUESSEL)

    def test_leeres_passwort_wird_abgewiesen(self, conn:sqlite3.Connection, profil_id:int) -> None:
        with pytest.raises(FachlicherFehler):
            zugang.setzen(conn, profil_id, benutzername = "a@b.de",
                          passwort = "", schluessel = SCHLUESSEL)

    def test_speichern_ohne_schluessel_scheitert(self, conn:sqlite3.Connection, profil_id:int) -> None:
        with pytest.raises(FachlicherFehler) as fehler:
            zugang.setzen(conn, profil_id, benutzername = "a@b.de",
                          passwort = GEHEIMES_PASSWORT, schluessel = None)
        assert fehler.value.status == 503

    def test_umgebung_enthaelt_die_erwarteten_variablen(self, conn:sqlite3.Connection, profil_id:int) -> None:
        zugang.setzen(conn, profil_id, benutzername = "a@b.de",
                      passwort = GEHEIMES_PASSWORT, schluessel = SCHLUESSEL)
        umgebung = zugang.umgebung_fuer_lauf(conn, profil_id, schluessel = SCHLUESSEL)
        # Die Namen muessen zu den Platzhaltern passen, die der Bot ersetzt.
        assert umgebung == {
            zugang.ENV_BENUTZER: "a@b.de",
            zugang.ENV_PASSWORT: GEHEIMES_PASSWORT,
        }
        assert zugang.PLATZHALTER_PASSWORT == "${KLEINANZEIGEN_BOT_PASSWORD}"

    def test_ohne_zugangsdaten_kein_lauf(self, conn:sqlite3.Connection, profil_id:int) -> None:
        with pytest.raises(FachlicherFehler) as fehler:
            zugang.umgebung_fuer_lauf(conn, profil_id, schluessel = SCHLUESSEL)
        assert fehler.value.status == 409

    def test_entfernen(self, conn:sqlite3.Connection, profil_id:int) -> None:
        zugang.setzen(conn, profil_id, benutzername = "a@b.de",
                      passwort = GEHEIMES_PASSWORT, schluessel = SCHLUESSEL)
        zugang.entfernen(conn, profil_id)
        assert zugang.status(conn, profil_id) is None

    def test_profil_loeschen_nimmt_zugangsdaten_mit(
        self, conn:sqlite3.Connection, profil_id:int, tmp_path:Path,
    ) -> None:
        zugang.setzen(conn, profil_id, benutzername = "a@b.de",
                      passwort = GEHEIMES_PASSWORT, schluessel = SCHLUESSEL)
        profile_dienst.loeschen(conn, tmp_path / "profiles", "haushalt", mit_daten = True)
        # Haengt am ON DELETE CASCADE. Ohne aktive Fremdschluessel bliebe hier
        # ein verwaistes Chiffrat zurueck.
        rest = conn.execute("SELECT COUNT(*) AS n FROM profil_zugang").fetchone()
        assert rest["n"] == 0


class TestKeinKlartext:

    def test_passwort_steht_nirgends_im_klartext(
        self, conn:sqlite3.Connection, profil_id:int, db_pfad:Path,
    ) -> None:
        """Der eigentliche Nachweis von AP-1.4.

        Nicht "wir verschluesseln schon", sondern: die Datenbankdatei wird
        byteweise durchsucht, einschliesslich WAL-Datei.
        """
        zugang.setzen(conn, profil_id, benutzername = "a@b.de",
                      passwort = GEHEIMES_PASSWORT, schluessel = SCHLUESSEL)
        # WAL in die Hauptdatei zwingen, damit wirklich alles geprueft wird.
        conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")

        gesucht = GEHEIMES_PASSWORT.encode("utf-8")
        geprueft = 0
        for pfad in (db_pfad, db_pfad.with_suffix(".db-wal"), db_pfad.with_suffix(".db-shm")):
            if not pfad.exists():
                continue
            geprueft += 1
            assert gesucht not in pfad.read_bytes(), f"Passwort im Klartext in {pfad.name}"
        assert geprueft >= 1

    def test_status_gibt_das_passwort_nicht_heraus(self, conn:sqlite3.Connection, profil_id:int) -> None:
        zugang.setzen(conn, profil_id, benutzername = "a@b.de",
                      passwort = GEHEIMES_PASSWORT, schluessel = SCHLUESSEL)
        st = zugang.status(conn, profil_id)
        assert st is not None
        # Auch nicht mittelbar, etwa ueber eine Laengenangabe.
        assert GEHEIMES_PASSWORT not in repr(st)
        assert str(len(GEHEIMES_PASSWORT)) not in repr(st)
