# SPDX-FileCopyrightText: © Anzeigen-Studio contributors
# SPDX-ArtifactOfProjectHomePage: https://github.com/TingelTangelBob/Kleinanzeigen.de-botUI/
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# Tests der Einstellungen (AP-2.9). Kein volles Qualitaetstor - aber die
# Sperrfelder aus AP-1.11 muessen nachweislich abgewiesen werden.

from __future__ import annotations

import base64
from typing import TYPE_CHECKING

import pytest
from fastapi.testclient import TestClient

from anzeigen_studio.core.settings import Settings
from anzeigen_studio.main import create_app

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path

SCHLUESSEL = base64.b64encode(b"0123456789abcdef0123456789abcdef").decode()
PASSWORT = "ein-ausreichend-langes-Passwort"
PROFIL = "testprofil"


@pytest.fixture
def client(tmp_path: Path) -> Iterator[TestClient]:
    cfg = Settings(data_dir = tmp_path, secret_key = SCHLUESSEL, dev_mode = True,
                   chromium = "/usr/bin/chromium")
    cfg.profiles_dir.mkdir(parents = True, exist_ok = True)
    with TestClient(create_app(cfg)) as c:
        c.post("/api/auth/einrichten", json = {"name": "steffen", "passwort": PASSWORT})
        c.post("/api/profile", json = {"slug": PROFIL, "anzeigename": "Testprofil"})
        yield c


def _get(client: TestClient) -> dict:
    antwort = client.get(f"/api/einstellungen?profil={PROFIL}")
    assert antwort.status_code == 200, antwort.text
    return antwort.json()


class TestLesenUndSpeichern:

    def test_leer_ohne_datei(self, client: TestClient) -> None:
        daten = _get(client)
        assert daten["profil"] == PROFIL
        assert daten["werte"] == {}
        pfade = [feld["pfad"] for gruppe in daten["gruppen"] for feld in gruppe["felder"]]
        assert pfade
        for gesperrt in (
            "ad_files", "browser.binary_location", "browser.extensions",
            "browser.arguments", "login.username", "login.password",
        ):
            assert gesperrt not in pfade

    def test_speichern_und_lesen(self, client: TestClient, tmp_path: Path) -> None:
        antwort = client.put(
            f"/api/einstellungen?profil={PROFIL}",
            json = {"werte": {"ad_defaults": {"republication_interval": 14}}},
        )
        assert antwort.status_code == 200, antwort.text
        assert antwort.json()["werte"]["ad_defaults"]["republication_interval"] == 14
        assert _get(client)["werte"]["ad_defaults"]["republication_interval"] == 14
        datei = tmp_path / "profiles" / PROFIL / "nutzer.yaml"
        assert datei.is_file()
        assert "14" in datei.read_text(encoding = "utf-8")


class TestSperrfelder:

    @pytest.mark.parametrize("werte", [
        {"ad_files": ["./ads/**/*.yaml"]},
        {"browser": {"binary_location": "/bin/sh"}},
        {"browser": {"extensions": ["/tmp/x.crx"]}},
        {"browser": {"arguments": ["--load-extension=/tmp"]}},
        {"login": {"username": "x", "password": "GEHEIM"}},
    ])
    def test_gesperrte_werden_abgewiesen(self, client: TestClient, werte: dict, tmp_path: Path) -> None:
        antwort = client.put(f"/api/einstellungen?profil={PROFIL}", json = {"werte": werte})
        assert antwort.status_code == 400, antwort.text
        meldung = antwort.json()["fehler"]["meldung"]
        assert "darf nicht gesetzt werden" in meldung
        datei = tmp_path / "profiles" / PROFIL / "nutzer.yaml"
        assert not datei.exists()

    def test_unbekanntes_feld_wird_abgewiesen(self, client: TestClient) -> None:
        antwort = client.put(
            f"/api/einstellungen?profil={PROFIL}",
            json = {"werte": {"kein_bot_feld": True}},
        )
        assert antwort.status_code == 400, antwort.text
        assert "unbekannt" in antwort.json()["fehler"]["meldung"]


class TestBrowserprofil:

    def test_zuruecksetzen_ohne_ordner_ist_ok(self, client: TestClient) -> None:
        antwort = client.post(
            f"/api/einstellungen/browserprofil-zuruecksetzen?profil={PROFIL}",
        )
        assert antwort.status_code == 204

    def test_loescht_nur_das_browserprofil(self, client: TestClient, tmp_path: Path) -> None:
        wurzel = tmp_path / "profiles" / PROFIL
        browser = wurzel / ".temp" / "browser-profile"
        browser.mkdir(parents = True)
        (browser / "Cookies").write_text("x", encoding = "utf-8")
        ads = wurzel / "ads"
        ads.mkdir(parents = True, exist_ok = True)
        (ads / "ad_1.yaml").write_text("title: bleibt", encoding = "utf-8")
        antwort = client.post(
            f"/api/einstellungen/browserprofil-zuruecksetzen?profil={PROFIL}",
        )
        assert antwort.status_code == 204
        assert not browser.exists()
        assert (ads / "ad_1.yaml").is_file()
