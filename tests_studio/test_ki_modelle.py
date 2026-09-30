# SPDX-FileCopyrightText: © Anzeigen-Studio contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# Modellauswahl und Stapel-Erkennung (2026-09-30).

from __future__ import annotations

import asyncio
import base64
import sqlite3
import time
from typing import TYPE_CHECKING, Any

import httpx
import pytest
from fastapi.testclient import TestClient

from anzeigen_studio.ai import anbieter, entwurf_lauf, erkennungswarteschlange
from anzeigen_studio.ai import modelle as modell_katalog
from anzeigen_studio.ai.entwurf import Entwurf
from anzeigen_studio.core import db
from anzeigen_studio.core.errors import FachlicherFehler
from anzeigen_studio.core.settings import Settings
from anzeigen_studio.main import create_app

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path


SCHLUESSEL = base64.b64encode(b"0123456789abcdef0123456789abcdef").decode()
PASSWORT = "ein-ausreichend-langes-Passwort"


def _cfg(tmp_path: Path, **extra: Any) -> Settings:
    return Settings(
        data_dir = tmp_path, secret_key = SCHLUESSEL, dev_mode = True,
        chromium = "/usr/bin/chromium", **extra,
    )


@pytest.fixture
def conn(tmp_path: Path) -> Iterator[sqlite3.Connection]:
    verbindung = db.connect(tmp_path / "app.db")
    db.migrate(verbindung)
    try:
        yield verbindung
    finally:
        verbindung.close()


# ------------------------------------------------------------------ Katalog

def test_vorgabe_ist_gpt_6_luna(tmp_path: Path, conn: sqlite3.Connection) -> None:
    assert modell_katalog.STANDARD == "gpt-6-luna"
    assert modell_katalog.aktiv(conn, _cfg(tmp_path)).kennung == "gpt-6-luna"


def test_jedes_katalogmodell_hat_einen_preis() -> None:
    for modell in modell_katalog.MODELLE:
        assert modell.preis_eingabe_usd > 0
        assert modell.preis_ausgabe_usd > 0


def test_auswahl_wird_gespeichert_und_gilt(tmp_path: Path, conn: sqlite3.Connection) -> None:
    cfg = _cfg(tmp_path)
    modell_katalog.waehlen(conn, cfg, "gpt-5.6-luna")
    assert modell_katalog.aktiv(conn, cfg).kennung == "gpt-5.6-luna"
    modell_katalog.waehlen(conn, cfg, "gpt-6-luna")
    assert modell_katalog.aktiv(conn, cfg).kennung == "gpt-6-luna"


def test_unbekanntes_modell_wird_abgewiesen(tmp_path: Path, conn: sqlite3.Connection) -> None:
    with pytest.raises(FachlicherFehler) as fehler:
        modell_katalog.waehlen(conn, _cfg(tmp_path), "gpt-irgendwas")
    assert fehler.value.status == 422


def test_gehostet_entscheidet_der_betreiber(tmp_path: Path, conn: sqlite3.Connection) -> None:
    offen = _cfg(tmp_path)
    modell_katalog.waehlen(conn, offen, "gpt-5.6-luna")
    gehostet = _cfg(tmp_path, hosted = True, openai_api_schluessel = "sk-x", ki_modell = "gpt-6-luna")

    assert modell_katalog.aktiv(conn, gehostet).kennung == "gpt-6-luna"
    with pytest.raises(FachlicherFehler) as fehler:
        modell_katalog.waehlen(conn, gehostet, "gpt-5.6-luna")
    assert fehler.value.status == 403


def test_unbekanntes_servermodell_rechnet_mit_dem_hoechsten_preis(
    tmp_path: Path, conn: sqlite3.Connection,
) -> None:
    modell = modell_katalog.aktiv(conn, _cfg(tmp_path, ki_modell = "eigenes-modell"))
    assert modell.kennung == "eigenes-modell"
    assert modell.preis_ausgabe_usd == max(m.preis_ausgabe_usd for m in modell_katalog.MODELLE)


# ------------------------------------------------------------------ Anfrage

class _FalscherKlient:
    gesendet: dict[str, Any] = {}

    def __init__(self, **_kwargs: object) -> None:
        pass

    async def __aenter__(self) -> _FalscherKlient:
        return self

    async def __aexit__(self, *_args: object) -> None:
        return None

    async def post(self, _url: str, *, headers: dict[str, str], json: dict[str, Any]) -> httpx.Response:
        del headers
        _FalscherKlient.gesendet = json
        return httpx.Response(200, json = {
            "output_text": '{"titel": "x"}', "usage": {"input_tokens": 1, "output_tokens": 1},
        })


def test_denkstufe_geht_nur_mit_wenn_das_modell_sie_hat(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(httpx, "AsyncClient", _FalscherKlient)

    asyncio.run(anbieter.OpenAI(api_schluessel = "sk-test", modell = "gpt-6-luna", denkstufe = "low")
                .erkennen([], anweisung = "a", schema = {}, schema_name = "s"))
    assert _FalscherKlient.gesendet["reasoning"] == {"effort": "low"}

    asyncio.run(anbieter.OpenAI(api_schluessel = "sk-test", modell = "gpt-5.6-luna")
                .erkennen([], anweisung = "a", schema = {}, schema_name = "s"))
    assert "reasoning" not in _FalscherKlient.gesendet


# ------------------------------------------------------------------ HTTP

@pytest.fixture
def klient(tmp_path: Path) -> Iterator[TestClient]:
    with TestClient(create_app(_cfg(tmp_path, ki_parallel = 3))) as test_client:
        antwort = test_client.post(
            "/api/auth/einrichten", json = {"name": "steffen", "passwort": PASSWORT},
        )
        assert antwort.status_code == 201, antwort.text
        test_client.post("/api/profile", json = {"slug": "test", "anzeigename": "Testprofil"})
        yield test_client


def test_status_nennt_auswahl_und_parallelitaet(klient: TestClient) -> None:
    daten = klient.get("/api/ki/status").json()

    assert daten["modell"] == "gpt-6-luna"
    assert daten["modell_waehlbar"] is True
    assert [m["kennung"] for m in daten["modelle"]] == ["gpt-6-luna", "gpt-5.6-luna"]
    assert daten["parallel"] == 3
    assert daten["max_offen"] == erkennungswarteschlange.MAX_OFFEN_JE_PROFIL


def test_modell_waehlen_ueber_http(klient: TestClient) -> None:
    antwort = klient.put("/api/ki/modell", json = {"modell": "gpt-5.6-luna"})
    assert antwort.status_code == 200, antwort.text
    assert antwort.json()["modell"] == "gpt-5.6-luna"
    assert klient.get("/api/ki/status").json()["modell"] == "gpt-5.6-luna"

    abgewiesen = klient.put("/api/ki/modell", json = {"modell": "https://boese.example/x"})
    assert abgewiesen.status_code == 422


def _warten_auf(klient: TestClient, erkennung_id: int, zustand: str) -> dict[str, Any]:
    for _ in range(100):
        daten: dict[str, Any] = klient.get(f"/api/ki/erkennungen/{erkennung_id}?profil=test").json()
        if daten["zustand"] == zustand:
            return daten
        time.sleep(0.01)
    pytest.fail(f"Zustand {zustand} nicht erreicht, zuletzt {daten['zustand']}")


def test_gescheiterte_analyse_laesst_sich_wiederholen_und_verwerfen(
    klient: TestClient, monkeypatch: pytest.MonkeyPatch,
) -> None:
    versuche: list[int] = []

    async def erst_fehler_dann_entwurf(*_args: object, **_kwargs: object) -> entwurf_lauf.Ergebnis:
        versuche.append(1)
        if len(versuche) == 1:
            raise FachlicherFehler("Der KI-Anbieter bremst gerade.", status = 502)
        return entwurf_lauf.Ergebnis(
            entwurf = Entwurf(
                titel = "Lampe", beschreibung = "Lampe.", zustand = "gut", kategorie = None,
                preis_von_euro = None, preis_bis_euro = None, preis_begruendung = None, fragen = [],
            ),
            kosten = entwurf_lauf.Kosten(
                modell = "gpt-6-luna", token_eingabe = 1, token_ausgabe = 1, usd = 0.0,
                bilder_gesendet = 1, bytes_gesendet = 1, stil_eigene_texte = 0,
                verbrauch_usd = 0.0, budget_usd = 5,
            ),
        )

    monkeypatch.setattr(entwurf_lauf, "erzeugen", erst_fehler_dann_entwurf)
    start = klient.post(
        "/api/ki/erkennungen", data = {"profil": "test"},
        files = [("bilder", ("bild.jpg", b"\xff\xd8\xffbild", "image/jpeg"))],
    )
    erkennung_id = start.json()["id"]
    assert _warten_auf(klient, erkennung_id, "gescheitert")["meldung"] == "Der KI-Anbieter bremst gerade."

    # Verwerfen geht erst nach dem Lauf, wiederholen nur nach einem Fehler.
    wieder = klient.post(f"/api/ki/erkennungen/{erkennung_id}/wiederholen?profil=test")
    assert wieder.status_code == 202, wieder.text
    assert _warten_auf(klient, erkennung_id, "pruefen")["entwurf"]["titel"] == "Lampe"
    assert klient.post(f"/api/ki/erkennungen/{erkennung_id}/wiederholen?profil=test").status_code == 409

    verworfen = klient.delete(f"/api/ki/erkennungen/{erkennung_id}?profil=test")
    assert verworfen.status_code == 204, verworfen.text
    assert klient.get("/api/ki/erkennungen?profil=test").json() == []


def test_zu_viele_offene_analysen_werden_abgewiesen(
    klient: TestClient, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(erkennungswarteschlange, "MAX_OFFEN_JE_PROFIL", 2)
    haengt = asyncio.Event()

    async def haengt_fest(*_args: object, **_kwargs: object) -> entwurf_lauf.Ergebnis:
        await haengt.wait()
        raise AssertionError("nicht erreicht")

    monkeypatch.setattr(entwurf_lauf, "erzeugen", haengt_fest)
    datei = [("bilder", ("bild.jpg", b"\xff\xd8\xffbild", "image/jpeg"))]
    ergebnisse = [
        klient.post("/api/ki/erkennungen", data = {"profil": "test"}, files = datei).status_code
        for _ in range(3)
    ]
    assert ergebnisse == [202, 202, 429]
