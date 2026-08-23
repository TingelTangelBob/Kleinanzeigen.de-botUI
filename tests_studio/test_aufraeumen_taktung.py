# SPDX-FileCopyrightText: © Anzeigen-Studio contributors
# SPDX-ArtifactOfProjectHomePage: https://github.com/TingelTangelBob/Kleinanzeigen.de-botUI/
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# Tests des Aufraeumens (AP-1.9) und der Taktung (AP-1.12).

from __future__ import annotations

import subprocess
import sys
import time as zeitmodul
from datetime import datetime, time
from typing import TYPE_CHECKING

import psutil
import pytest

from anzeigen_studio.jobs import aufraeumen
from anzeigen_studio.jobs.taktung import Taktung

if TYPE_CHECKING:
    from pathlib import Path


class TestSperrenEntfernen:

    def test_entfernt_bekannte_sperrdateien(self, tmp_path:Path) -> None:
        profil = tmp_path / "browser-profile"
        profil.mkdir()
        (profil / "SingletonCookie").write_text("x", encoding = "utf-8")
        (profil / "SingletonSocket").write_text("x", encoding = "utf-8")
        # SingletonLock ist bei Chromium eine symbolische Verknuepfung, deren
        # Ziel oft gar nicht existiert - exists() meldet dann False.
        (profil / "SingletonLock").symlink_to("nicht-vorhanden")

        entfernt = aufraeumen.sperren_entfernen(profil)

        assert set(entfernt) == {"SingletonLock", "SingletonCookie", "SingletonSocket"}
        assert not (profil / "SingletonLock").is_symlink()
        assert not (profil / "SingletonCookie").exists()

    def test_fehlendes_verzeichnis_ist_kein_fehler(self, tmp_path:Path) -> None:
        assert aufraeumen.sperren_entfernen(tmp_path / "gibtesnicht") == []

    def test_leeres_verzeichnis_ist_kein_fehler(self, tmp_path:Path) -> None:
        profil = tmp_path / "leer"
        profil.mkdir()
        assert aufraeumen.sperren_entfernen(profil) == []


class TestVerwaisteBrowser:

    def test_ohne_treffer_passiert_nichts(self, tmp_path:Path) -> None:
        assert aufraeumen.verwaiste_browser_beenden(tmp_path / "kein-profil") == 0

    def test_beendet_nur_den_passenden_prozess(self, tmp_path:Path) -> None:
        meins = tmp_path / "profil-a"
        fremdes = tmp_path / "profil-b"

        # Zwei langlaufende Prozesse, die sich nur im Profilpfad unterscheiden.
        # Der Schalter steht als EIGENES Argument - so uebergibt ihn auch das
        # echte Chromium, und genau darauf prueft verwaiste_browser_beenden().
        a = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)",
                              f"--user-data-dir={meins}"])
        b = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)",
                              f"--user-data-dir={fremdes}"])
        try:
            # Kurz warten, bis die Befehlszeilen sichtbar sind.
            zeitmodul.sleep(0.3)
            beendet = aufraeumen.verwaiste_browser_beenden(meins)

            assert beendet == 1
            # Der fremde Lauf darf NICHT mitgerissen werden - sonst zerstoerte
            # das Aufraeumen eines Profils den Lauf eines anderen.
            assert psutil.pid_exists(b.pid)
            assert b.poll() is None
        finally:
            for prozess in (a, b):
                prozess.kill()
                prozess.wait(timeout = 5)


class TestTaktung:

    def test_pause_liegt_ueber_der_mindestpause(self) -> None:
        t = Taktung(mindestpause_s = 60, streuung = 0.5)
        werte = [t.pause_nach_lauf() for _ in range(50)]
        assert all(60.0 <= w <= 90.0 for w in werte)
        # Streuung nach oben, nicht um die Mitte: ein exakt gleichmaessiger
        # Abstand waere selbst ein Muster.
        assert len(set(werte)) > 1

    def test_pause_null_schaltet_ab(self) -> None:
        assert Taktung(mindestpause_s = 0).pause_nach_lauf() == 0.0

    @pytest.mark.parametrize(("stunde", "erwartet"), [
        (6, False), (7, True), (12, True), (22, True), (23, False), (3, False),
    ])
    def test_zeitfenster(self, stunde:int, erwartet:bool) -> None:
        t = Taktung(fenster_von = time(7, 0), fenster_bis = time(23, 0))
        jetzt = datetime(2026, 8, 23, stunde, 30).astimezone()
        assert t.im_fenster(jetzt) is erwartet

    def test_fenster_ueber_mitternacht(self) -> None:
        t = Taktung(fenster_von = time(22, 0), fenster_bis = time(6, 0))
        assert t.im_fenster(datetime(2026, 8, 23, 23, 0).astimezone()) is True
        assert t.im_fenster(datetime(2026, 8, 23, 3, 0).astimezone()) is True
        assert t.im_fenster(datetime(2026, 8, 23, 12, 0).astimezone()) is False

    def test_fenster_abschaltbar(self) -> None:
        t = Taktung(fenster_aktiv = False)
        assert t.im_fenster(datetime(2026, 8, 23, 3, 0).astimezone()) is True

    def test_wartezeit_bis_fenster(self) -> None:
        t = Taktung(fenster_von = time(7, 0), fenster_bis = time(23, 0))
        # Um 3 Uhr sind es vier Stunden bis sieben.
        wartezeit = t.wartezeit_bis_fenster(datetime(2026, 8, 23, 3, 0).astimezone())
        assert wartezeit == pytest.approx(4 * 3600, abs = 60)
        # Innerhalb des Fensters gar keine.
        assert t.wartezeit_bis_fenster(datetime(2026, 8, 23, 12, 0).astimezone()) == 0.0

    def test_wartezeit_geht_auf_den_naechsten_tag(self) -> None:
        t = Taktung(fenster_von = time(7, 0), fenster_bis = time(23, 0))
        # Um 23:30 ist der naechste Fensterbeginn morgen frueh.
        wartezeit = t.wartezeit_bis_fenster(datetime(2026, 8, 23, 23, 30).astimezone())
        assert wartezeit == pytest.approx(7.5 * 3600, abs = 60)
