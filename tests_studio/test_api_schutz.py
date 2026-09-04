# SPDX-FileCopyrightText: © Anzeigen-Studio contributors
# SPDX-ArtifactOfProjectHomePage: https://github.com/TingelTangelBob/Kleinanzeigen.de-botUI/
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# Tests des Zugriffsschutzes auf HTTP-Ebene (AP-1.10, AP-1.8).
#
# Bewusst gegen die echte Anwendung statt gegen einzelne Funktionen: Der Schutz
# ist eine Middleware, und was zaehlt, ist was am Endpunkt ankommt. Ein Test
# der Middleware-Funktion allein wuerde nicht auffangen, dass eine Route
# versehentlich in die Positivliste geraet.

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

#: Pfade, die ohne Sitzung NICHT erreichbar sein duerfen.
GESCHUETZT = [
    ("GET", "/api/profile"),
    ("POST", "/api/profile"),
    ("GET", "/api/jobs"),
    ("POST", "/api/jobs"),
    ("GET", "/api/jobs/1"),
    ("GET", "/api/jobs/1/log"),
    ("GET", "/api/profile/x/zugang"),
    ("PUT", "/api/profile/x/zugang"),
    ("GET", "/api/auth/pruefen"),
    ("GET", "/api/einstellungen"),
    ("PUT", "/api/einstellungen"),
    ("POST", "/api/einstellungen/browserprofil-zuruecksetzen"),
]


@pytest.fixture
def client(tmp_path:Path) -> Iterator[TestClient]:
    cfg = Settings(data_dir = tmp_path, secret_key = SCHLUESSEL, dev_mode = True,
                   chromium = "/usr/bin/chromium")
    cfg.profiles_dir.mkdir(parents = True, exist_ok = True)
    with TestClient(create_app(cfg)) as c:
        yield c


def _einrichten(client:TestClient) -> None:
    antwort = client.post("/api/auth/einrichten",
                          json = {"name": "steffen", "passwort": PASSWORT})
    assert antwort.status_code == 201


class TestOhneEinrichtung:

    def test_health_bleibt_offen(self, client:TestClient) -> None:
        # Muss ohne alles erreichbar sein, sonst kann kein Healthcheck greifen.
        assert client.get("/api/health").status_code == 200

    def test_status_bleibt_offen(self, client:TestClient) -> None:
        # Die Oberflaeche muss erfahren duerfen, ob sie zur Einrichtung fuehrt.
        antwort = client.get("/api/auth/status")
        assert antwort.status_code == 200
        assert antwort.json()["eingerichtet"] is False

    def test_pruefen_liefert_401_statt_409(self, client:TestClient) -> None:
        # Wichtig fuer nginx: auth_request macht aus allem ausser 401/403 einen
        # 500. "Noch nicht eingerichtet" ist fuer eine Sitzungspruefung
        # schlicht "nicht angemeldet".
        assert client.get("/api/auth/pruefen").status_code == 401


class TestOhneAnmeldung:

    @pytest.mark.parametrize(("methode", "pfad"), GESCHUETZT)
    def test_geschuetzte_pfade_liefern_401(self, client:TestClient, methode:str, pfad:str) -> None:
        _einrichten(client)
        client.post("/api/auth/abmelden")
        antwort = client.request(methode, pfad, json = {})
        assert antwort.status_code == 401, f"{methode} {pfad} war ohne Sitzung erreichbar"

    def test_kein_zweites_konto(self, client:TestClient) -> None:
        _einrichten(client)
        antwort = client.post("/api/auth/einrichten",
                              json = {"name": "fremd", "passwort": PASSWORT})
        assert antwort.status_code == 409


class TestMitAnmeldung:

    def test_zugriff_nach_anmeldung(self, client:TestClient) -> None:
        _einrichten(client)
        assert client.get("/api/profile").status_code == 200
        assert client.get("/api/auth/pruefen").status_code == 204

    def test_abmelden_und_wieder_anmelden(self, client:TestClient) -> None:
        _einrichten(client)
        assert client.post("/api/auth/abmelden").status_code == 204
        assert client.get("/api/profile").status_code == 401

        antwort = client.post("/api/auth/anmelden",
                              json = {"name": "steffen", "passwort": PASSWORT})
        assert antwort.status_code == 200
        assert client.get("/api/profile").status_code == 200

    def test_cookie_ist_httponly(self, client:TestClient) -> None:
        antwort = client.post("/api/auth/einrichten",
                              json = {"name": "steffen", "passwort": PASSWORT})
        gesetzt = antwort.headers.get("set-cookie", "")
        # Ohne HttpOnly wuerde ein XSS-Fehler die Sitzung sofort verschenken.
        assert "httponly" in gesetzt.lower()
        assert "samesite=lax" in gesetzt.lower()

    def test_passwort_kommt_nie_zurueck(self, client:TestClient) -> None:
        _einrichten(client)
        client.post("/api/profile", json = {"slug": "haushalt", "anzeigename": "Haushalt"})
        client.put("/api/profile/haushalt/zugang",
                   json = {"benutzername": "u@example.org", "passwort": "GEHEIM-XYZZY"})
        antwort = client.get("/api/profile/haushalt/zugang")
        assert antwort.status_code == 200
        assert "GEHEIM-XYZZY" not in antwort.text
        assert antwort.json()["passwort_hinterlegt"] is True
