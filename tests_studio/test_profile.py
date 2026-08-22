# SPDX-FileCopyrightText: © Anzeigen-Studio contributors
# SPDX-ArtifactOfProjectHomePage: https://github.com/TingelTangelBob/Kleinanzeigen.de-botUI/
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# Tests der Profilverwaltung (AP-1.3).
#
# Schwerpunkt liegt auf dem Ausbruch aus dem Profilverzeichnis: Das Kuerzel wird
# zu einem Pfad, und genau dort entstehen Traversal-Luecken. Der Upstream hat
# beim Glob-Muster genau diesen Fehler (siehe Upstream-Codepruefung, D.2) - der
# soll sich hier nicht wiederholen.

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    import sqlite3
    from pathlib import Path

from anzeigen_studio.core import db
from anzeigen_studio.core import profile as p
from anzeigen_studio.core.errors import FachlicherFehler


@pytest.fixture
def conn(tmp_path:Path) -> sqlite3.Connection:
    verbindung = db.connect(tmp_path / "test.db")
    db.migrate(verbindung)
    return verbindung


@pytest.fixture
def profiles_dir(tmp_path:Path) -> Path:
    d = tmp_path / "profiles"
    d.mkdir()
    return d


class TestSlugPruefung:

    @pytest.mark.parametrize("slug", ["a", "haushalt", "konto-2", "x1", "a" * 32])
    def test_gueltige_kuerzel(self, slug:str) -> None:
        assert p.slug_pruefen(slug) == slug

    @pytest.mark.parametrize("slug", [
        "",                 # leer
        "-start",           # Bindestrich am Anfang
        "ende-",            # Bindestrich am Ende
        "Gross",            # Grossbuchstaben
        "mit punkt",        # Leerzeichen
        "umlaut-ä",         # Nicht-ASCII
        "a" * 33,           # zu lang
        "..",               # Traversal
        "../etc",           # Traversal
        "a/b",              # Pfadtrenner
        "a\\b",             # Pfadtrenner Windows
        "con",              # reservierter Name
    ])
    def test_ungueltige_kuerzel_werden_abgewiesen(self, slug:str) -> None:
        with pytest.raises(FachlicherFehler):
            p.slug_pruefen(slug)


class TestPfadIsolation:

    def test_pfade_liegen_im_profilverzeichnis(self, profiles_dir:Path) -> None:
        pfade = p.pfade_fuer(profiles_dir, "haushalt")
        assert pfade.wurzel.is_relative_to(profiles_dir.resolve())
        assert pfade.anzeigen_verzeichnis.is_relative_to(pfade.wurzel)
        assert pfade.browser_profil.is_relative_to(pfade.wurzel)

    @pytest.mark.parametrize("boeses_kuerzel", ["..", "../..", "../anderes"])
    def test_ausbruch_wird_abgewiesen(self, profiles_dir:Path, boeses_kuerzel:str) -> None:
        # Auch wenn ein solcher Wert die Slug-Pruefung umginge - etwa direkt aus
        # der Datenbank - darf daraus kein Pfad ausserhalb entstehen.
        with pytest.raises(FachlicherFehler):
            p.pfade_fuer(profiles_dir, boeses_kuerzel)


class TestLebenszyklus:

    def test_anlegen_und_finden(self, conn:sqlite3.Connection, profiles_dir:Path) -> None:
        angelegt = p.anlegen(conn, profiles_dir, "haushalt", "Haushaltsauflösung")
        assert angelegt.slug == "haushalt"
        assert angelegt.anzeigename == "Haushaltsauflösung"

        gefunden = p.nach_slug(conn, "haushalt")
        assert gefunden is not None
        assert gefunden.id == angelegt.id
        # Das Anzeigenverzeichnis muss existieren, sonst scheitert der erste
        # Download mit einem unverstaendlichen Fehler.
        assert p.pfade_fuer(profiles_dir, "haushalt").anzeigen_verzeichnis.is_dir()

    def test_doppeltes_kuerzel_wird_abgewiesen(self, conn:sqlite3.Connection, profiles_dir:Path) -> None:
        p.anlegen(conn, profiles_dir, "haushalt", "Erstes")
        with pytest.raises(FachlicherFehler) as fehler:
            p.anlegen(conn, profiles_dir, "haushalt", "Zweites")
        assert fehler.value.status == 409

    def test_leerer_anzeigename_wird_abgewiesen(self, conn:sqlite3.Connection, profiles_dir:Path) -> None:
        with pytest.raises(FachlicherFehler):
            p.anlegen(conn, profiles_dir, "haushalt", "   ")

    def test_zwei_profile_sind_getrennt(self, conn:sqlite3.Connection, profiles_dir:Path) -> None:
        p.anlegen(conn, profiles_dir, "eins", "Eins")
        p.anlegen(conn, profiles_dir, "zwei", "Zwei")
        a = p.pfade_fuer(profiles_dir, "eins")
        b = p.pfade_fuer(profiles_dir, "zwei")
        assert a.wurzel != b.wurzel
        assert len(p.alle(conn)) == 2

    def test_umbenennen_aendert_nur_den_anzeigenamen(self, conn:sqlite3.Connection, profiles_dir:Path) -> None:
        p.anlegen(conn, profiles_dir, "haushalt", "Alt")
        geaendert = p.umbenennen(conn, "haushalt", "Neu")
        assert geaendert.anzeigename == "Neu"
        assert geaendert.slug == "haushalt"

    def test_loeschen_ohne_daten_laesst_die_dateien_stehen(self, conn:sqlite3.Connection, profiles_dir:Path) -> None:
        p.anlegen(conn, profiles_dir, "haushalt", "Haushalt")
        pfade = p.pfade_fuer(profiles_dir, "haushalt")
        (pfade.anzeigen_verzeichnis / "ad_1.yaml").write_text("titel: Test\n", encoding = "utf-8")

        p.loeschen(conn, profiles_dir, "haushalt", mit_daten = False)

        assert p.nach_slug(conn, "haushalt") is None
        # Bewusst: Der Anzeigenbestand bleibt, bis jemand ihn ausdruecklich
        # mitloescht. Datenverlust darf kein Nebeneffekt sein.
        assert (pfade.anzeigen_verzeichnis / "ad_1.yaml").exists()

    def test_loeschen_mit_daten_raeumt_ab(self, conn:sqlite3.Connection, profiles_dir:Path) -> None:
        p.anlegen(conn, profiles_dir, "haushalt", "Haushalt")
        pfade = p.pfade_fuer(profiles_dir, "haushalt")
        (pfade.anzeigen_verzeichnis / "ad_1.yaml").write_text("titel: Test\n", encoding = "utf-8")

        p.loeschen(conn, profiles_dir, "haushalt", mit_daten = True)

        assert p.nach_slug(conn, "haushalt") is None
        assert not pfade.wurzel.exists()

    def test_loeschen_beruehrt_andere_profile_nicht(self, conn:sqlite3.Connection, profiles_dir:Path) -> None:
        p.anlegen(conn, profiles_dir, "eins", "Eins")
        p.anlegen(conn, profiles_dir, "zwei", "Zwei")

        p.loeschen(conn, profiles_dir, "eins", mit_daten = True)

        assert p.nach_slug(conn, "zwei") is not None
        assert p.pfade_fuer(profiles_dir, "zwei").anzeigen_verzeichnis.is_dir()

    def test_unbekanntes_profil_loeschen_meldet_404(self, conn:sqlite3.Connection, profiles_dir:Path) -> None:
        with pytest.raises(FachlicherFehler) as fehler:
            p.loeschen(conn, profiles_dir, "gibtesnicht", mit_daten = False)
        assert fehler.value.status == 404


class TestMigrationen:

    def test_migration_ist_wiederholbar(self, tmp_path:Path) -> None:
        pfad = tmp_path / "wiederholt.db"
        erste = db.connect(pfad)
        assert db.migrate(erste) == len(db.MIGRATIONS)
        erste.close()

        # Zweiter Start derselben Datenbank darf nichts erneut anwenden.
        zweite = db.connect(pfad)
        assert db.migrate(zweite) == 0
        zweite.close()

    def test_fremdschluessel_sind_aktiv(self, conn:sqlite3.Connection) -> None:
        # Ohne aktive Fremdschluessel liefe das ON DELETE CASCADE ins Leere und
        # Zugangsdaten blieben nach dem Loeschen eines Profils zurueck.
        assert conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1
