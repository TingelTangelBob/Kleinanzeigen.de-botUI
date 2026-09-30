# SPDX-FileCopyrightText: © Anzeigen-Studio contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# HTTP-Nachweis fuer den gehosteten KI-Zugang.

from __future__ import annotations

import base64
import time
from typing import TYPE_CHECKING

import pytest
from fastapi.testclient import TestClient

from anzeigen_studio.ai import entwurf_lauf
from anzeigen_studio.ai.entwurf import Entwurf
from anzeigen_studio.core.settings import Settings
from anzeigen_studio.main import create_app

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path


SCHLUESSEL = base64.b64encode(b"0123456789abcdef0123456789abcdef").decode()
PASSWORT = "ein-ausreichend-langes-Passwort"


@pytest.fixture
def test_client(tmp_path: Path) -> Iterator[TestClient]:
    cfg = Settings(
        data_dir = tmp_path,
        secret_key = SCHLUESSEL,
        dev_mode = True,
        chromium = "/usr/bin/chromium",
        hosted = True,
        openai_api_schluessel = "sk-gehostet-nicht-ausgeben",
        ki_max_bilder = 2,
    )
    with TestClient(create_app(cfg)) as test_client:
        antwort = test_client.post(
            "/api/auth/einrichten",
            json = {"name": "steffen", "passwort": PASSWORT},
        )
        assert antwort.status_code == 201, antwort.text
        yield test_client


def test_status_zeigt_gehosteten_modus_ohne_schluessel(test_client: TestClient) -> None:
    antwort = test_client.get("/api/ki/status")

    assert antwort.status_code == 200, antwort.text
    daten = antwort.json()
    assert daten["modus"] == "gehostet"
    assert daten["hinterlegt"] is True
    assert daten["schluessel_selbst_setzbar"] is False
    assert daten["max_bilder"] == 2
    assert "sk-gehostet-nicht-ausgeben" not in antwort.text


def test_gehostete_installation_verweigert_schluesselverwaltung(test_client: TestClient) -> None:
    setzen = test_client.put("/api/ki/schluessel", json = {"api_schluessel": "sk-eigener"})
    entfernen = test_client.delete("/api/ki/schluessel")

    assert setzen.status_code == 403, setzen.text
    assert entfernen.status_code == 403, entfernen.text


def test_gehostete_installation_begrenzt_bildanzahl_vor_dem_anbieteraufruf(
    test_client: TestClient,
) -> None:
    test_client.post("/api/profile", json = {"slug": "test", "anzeigename": "Testprofil"})
    dateien = [
        ("bilder", (f"bild-{nummer}.jpg", b"kein Bild", "image/jpeg"))
        for nummer in range(3)
    ]

    antwort = test_client.post(
        "/api/ki/entwurf", data = {"profil": "test"}, files = dateien,
    )

    assert antwort.status_code == 413, antwort.text
    assert "höchstens 2 Bilder" in antwort.json()["fehler"]["meldung"]


def test_erkennung_laeuft_hintergrund_und_bleibt_zur_pruefung_liegen(
    test_client: TestClient, monkeypatch: pytest.MonkeyPatch,
) -> None:
    test_client.post("/api/profile", json = {"slug": "test", "anzeigename": "Testprofil"})

    async def fake_erzeugen(*_args: object, **_kwargs: object) -> entwurf_lauf.Ergebnis:
        return entwurf_lauf.Ergebnis(
            entwurf = Entwurf(
                titel = "Schwarzer Akkuschrauber",
                beschreibung = "Akkuschrauber mit Ladegerät.",
                zustand = "gut",
                kategorie = None,
                preis_von_euro = 20,
                preis_bis_euro = 35,
                preis_begruendung = "Grobe Einordnung.",
                fragen = [],
            ),
            kosten = entwurf_lauf.Kosten(
                modell = "testmodell", token_eingabe = 10, token_ausgabe = 5,
                usd = 0.001, bilder_gesendet = 1, bytes_gesendet = 42,
                stil_eigene_texte = 0, verbrauch_usd = 0.001, budget_usd = 5,
            ),
        )

    monkeypatch.setattr(entwurf_lauf, "erzeugen", fake_erzeugen)
    start = test_client.post(
        "/api/ki/erkennungen",
        data = {"profil": "test"},
        files = [("bilder", ("bild.jpg", b"nicht wichtig", "image/jpeg"))],
    )
    assert start.status_code == 202, start.text
    erkennung_id = start.json()["id"]
    assert start.json()["zustand"] == "wartet"

    for _ in range(30):
        gelesen = test_client.get(f"/api/ki/erkennungen/{erkennung_id}?profil=test")
        assert gelesen.status_code == 200, gelesen.text
        if gelesen.json()["zustand"] == "pruefen":
            break
        time.sleep(0.01)
    else:
        pytest.fail("Die Hintergrund-Erkennung wurde nicht fertig.")

    daten = gelesen.json()
    assert daten["entwurf"]["titel"] == "Schwarzer Akkuschrauber"
    assert daten["kosten"]["bilder_gesendet"] == 1


def test_hintergrundentwurf_wird_lokal_gespeichert_ohne_neuen_ki_aufruf(
    test_client: TestClient, monkeypatch: pytest.MonkeyPatch,
) -> None:
    test_client.post("/api/profile", json = {"slug": "test", "anzeigename": "Testprofil"})

    async def fake_erzeugen(*_args: object, **_kwargs: object) -> entwurf_lauf.Ergebnis:
        return entwurf_lauf.Ergebnis(
            entwurf = Entwurf(
                titel = "Lampe",
                beschreibung = "Lampe aus dem Haushalt.",
                zustand = "gut",
                kategorie = None,
                preis_von_euro = None,
                preis_bis_euro = None,
                preis_begruendung = None,
                fragen = [],
            ),
            kosten = entwurf_lauf.Kosten(
                modell = "testmodell", token_eingabe = 1, token_ausgabe = 1,
                usd = 0.001, bilder_gesendet = 1, bytes_gesendet = 42,
                stil_eigene_texte = 0, verbrauch_usd = 0.001, budget_usd = 5,
            ),
        )

    monkeypatch.setattr(entwurf_lauf, "erzeugen", fake_erzeugen)
    start = test_client.post(
        "/api/ki/erkennungen",
        data = {"profil": "test"},
        files = [("bilder", ("bild.jpg", b"\xff\xd8\xffbild", "image/jpeg"))],
    )
    erkennung_id = start.json()["id"]
    for _ in range(30):
        if test_client.get(f"/api/ki/erkennungen/{erkennung_id}?profil=test").json()["zustand"] == "pruefen":
            break
        time.sleep(0.01)

    gespeichert = test_client.post(
        f"/api/ki/erkennungen/{erkennung_id}/anlegen?profil=test",
        json = {"antworten": {}, "beschreibung": "Lampe, funktioniert."},
    )
    assert gespeichert.status_code == 201, gespeichert.text
    assert gespeichert.json()["titel"] == "Lampe"
    assert test_client.get("/api/ki/erkennungen?profil=test").json() == []
