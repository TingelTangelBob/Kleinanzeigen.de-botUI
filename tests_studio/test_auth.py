# SPDX-FileCopyrightText: © Anzeigen-Studio contributors
# SPDX-ArtifactOfProjectHomePage: https://github.com/TingelTangelBob/Kleinanzeigen.de-botUI/
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# Tests der Anmeldung (AP-1.10).

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from anzeigen_studio.core import auth, db
from anzeigen_studio.core.errors import FachlicherFehler

if TYPE_CHECKING:
    import sqlite3
    from pathlib import Path

PASSWORT = "ein-ausreichend-langes-Passwort"


@pytest.fixture
def conn(tmp_path:Path) -> sqlite3.Connection:
    verbindung = db.connect(tmp_path / "auth.db")
    db.migrate(verbindung)
    return verbindung


class TestPasswortHash:

    def test_rundlauf(self) -> None:
        h = auth.passwort_hashen(PASSWORT)
        assert auth.passwort_pruefen(PASSWORT, h)
        assert not auth.passwort_pruefen("falsch", h)

    def test_hash_enthaelt_das_passwort_nicht(self) -> None:
        h = auth.passwort_hashen(PASSWORT)
        assert PASSWORT not in h
        assert h.startswith("scrypt$")

    def test_gleiches_passwort_ergibt_verschiedene_hashes(self) -> None:
        # Zufaelliges Salz. Sonst liesse sich an gleichen Hashes ablesen, dass
        # zwei Konten dasselbe Passwort benutzen.
        assert auth.passwort_hashen(PASSWORT) != auth.passwort_hashen(PASSWORT)

    @pytest.mark.parametrize("kaputt", ["", "kein-format", "scrypt$a$b$c$d$e", "md5$1$2$3$aa$bb"])
    def test_kaputter_hash_wird_abgelehnt(self, kaputt:str) -> None:
        # Darf nicht werfen und schon gar nicht True liefern.
        assert auth.passwort_pruefen(PASSWORT, kaputt) is False


class TestEinrichtung:

    def test_erster_benutzer(self, conn:sqlite3.Connection) -> None:
        assert auth.gibt_es_benutzer(conn) is False
        b = auth.ersten_benutzer_anlegen(conn, "steffen", PASSWORT)
        assert b.name == "steffen"
        assert auth.gibt_es_benutzer(conn) is True

    def test_kein_zweiter_benutzer(self, conn:sqlite3.Connection) -> None:
        auth.ersten_benutzer_anlegen(conn, "steffen", PASSWORT)
        # Keine Selbstregistrierung: bei einer Anwendung, die fremde
        # Zugangsdaten haelt, waere das ein Einfallstor.
        with pytest.raises(FachlicherFehler) as fehler:
            auth.ersten_benutzer_anlegen(conn, "fremder", PASSWORT)
        assert fehler.value.status == 409

    def test_zu_kurzes_passwort(self, conn:sqlite3.Connection) -> None:
        with pytest.raises(FachlicherFehler):
            auth.ersten_benutzer_anlegen(conn, "steffen", "kurz")


class TestAnmeldung:

    def test_anmelden_und_sitzung(self, conn:sqlite3.Connection) -> None:
        auth.ersten_benutzer_anlegen(conn, "steffen", PASSWORT)
        token = auth.anmelden(conn, "steffen", PASSWORT)
        assert token
        benutzer = auth.sitzung_pruefen(conn, token)
        assert benutzer is not None
        assert benutzer.name == "steffen"

    def test_falsches_passwort(self, conn:sqlite3.Connection) -> None:
        auth.ersten_benutzer_anlegen(conn, "steffen", PASSWORT)
        with pytest.raises(FachlicherFehler) as fehler:
            auth.anmelden(conn, "steffen", "falsch")
        assert fehler.value.status == 401

    def test_gleiche_meldung_bei_unbekanntem_benutzer(self, conn:sqlite3.Connection) -> None:
        auth.ersten_benutzer_anlegen(conn, "steffen", PASSWORT)
        with pytest.raises(FachlicherFehler) as a:
            auth.anmelden(conn, "steffen", "falsch")
        with pytest.raises(FachlicherFehler) as b:
            auth.anmelden(conn, "gibtesnicht", "falsch")
        # Verraet nicht, ob der Benutzername existiert.
        assert a.value.meldung == b.value.meldung

    def test_token_steht_nicht_in_der_datenbank(self, conn:sqlite3.Connection, tmp_path:Path) -> None:
        auth.ersten_benutzer_anlegen(conn, "steffen", PASSWORT)
        token = auth.anmelden(conn, "steffen", PASSWORT)
        conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        # Gespeichert wird nur der Hash - ein Blick in die Datei verschafft
        # keine gueltige Sitzung.
        assert token.encode() not in (tmp_path / "auth.db").read_bytes()

    def test_unbekanntes_token(self, conn:sqlite3.Connection) -> None:
        assert auth.sitzung_pruefen(conn, "erfunden") is None
        assert auth.sitzung_pruefen(conn, None) is None

    def test_abmelden_beendet_die_sitzung(self, conn:sqlite3.Connection) -> None:
        auth.ersten_benutzer_anlegen(conn, "steffen", PASSWORT)
        token = auth.anmelden(conn, "steffen", PASSWORT)
        auth.abmelden(conn, token)
        assert auth.sitzung_pruefen(conn, token) is None

    def test_sperre_nach_zu_vielen_fehlversuchen(self, conn:sqlite3.Connection) -> None:
        auth.ersten_benutzer_anlegen(conn, "steffen", PASSWORT)
        for _ in range(auth.MAX_FEHLVERSUCHE):
            with pytest.raises(FachlicherFehler):
                auth.anmelden(conn, "steffen", "falsch")
        # Jetzt auch mit RICHTIGEM Passwort gesperrt - sonst waere die Bremse
        # wirkungslos.
        with pytest.raises(FachlicherFehler) as fehler:
            auth.anmelden(conn, "steffen", PASSWORT)
        assert fehler.value.status == 429

    def test_erfolgreiche_anmeldung_loescht_fehlversuche(self, conn:sqlite3.Connection) -> None:
        auth.ersten_benutzer_anlegen(conn, "steffen", PASSWORT)
        for _ in range(auth.MAX_FEHLVERSUCHE - 1):
            with pytest.raises(FachlicherFehler):
                auth.anmelden(conn, "steffen", "falsch")
        auth.anmelden(conn, "steffen", PASSWORT)
        # Zaehler zurueckgesetzt, sonst sperrte sich der Nutzer nach und nach
        # selbst aus.
        for _ in range(auth.MAX_FEHLVERSUCHE - 1):
            with pytest.raises(FachlicherFehler) as fehler:
                auth.anmelden(conn, "steffen", "falsch")
            assert fehler.value.status == 401


class TestPasswortAendern:

    def test_aendern_und_alte_sitzungen_beenden(self, conn:sqlite3.Connection) -> None:
        b = auth.ersten_benutzer_anlegen(conn, "steffen", PASSWORT)
        alte_sitzung = auth.anmelden(conn, "steffen", PASSWORT)
        neu = "ein-anderes-langes-Passwort"

        auth.passwort_aendern(conn, b.id, PASSWORT, neu)

        # Wer sein Passwort aendert, will ueblicherweise fremde Sitzungen los.
        assert auth.sitzung_pruefen(conn, alte_sitzung) is None
        assert auth.anmelden(conn, "steffen", neu)

    def test_falsches_altes_passwort(self, conn:sqlite3.Connection) -> None:
        b = auth.ersten_benutzer_anlegen(conn, "steffen", PASSWORT)
        with pytest.raises(FachlicherFehler) as fehler:
            auth.passwort_aendern(conn, b.id, "falsch", "ein-anderes-langes-Passwort")
        assert fehler.value.status == 401
