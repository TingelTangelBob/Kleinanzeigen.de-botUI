# SPDX-FileCopyrightText: © Anzeigen-Studio contributors
# SPDX-ArtifactOfProjectHomePage: https://github.com/TingelTangelBob/Kleinanzeigen.de-botUI/
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# Tests des Bot-Adapters (AP-1.5).
#
# Statt des echten Bots laeuft ein Ersatzskript. Damit sind die Tests schnell,
# brauchen weder Browser noch Konto und pruefen genau das, was diese Schicht
# leistet: Prozessfuehrung, Ausgabeauswertung, Abbruch, Eingabe.

from __future__ import annotations

import textwrap
from typing import TYPE_CHECKING

import pytest

from anzeigen_studio.botbridge import konfiguration
from anzeigen_studio.botbridge.events import (
    Aufmerksamkeit,
    Eingriff,
    LaufErgebnis,
    Stufe,
    zeile_auswerten,
)
from anzeigen_studio.botbridge.runner import BotLauf, LaufAuftrag
from anzeigen_studio.core.errors import FachlicherFehler

if TYPE_CHECKING:
    from pathlib import Path


def _ersatzbot(tmp_path:Path, koerper:str) -> tuple[str, str]:
    """Legt ein Ersatzmodul an und gibt (python, modulname) zurueck."""
    paket = tmp_path / "fakebot"
    paket.mkdir(exist_ok = True)
    (paket / "__init__.py").write_text("", encoding = "utf-8")
    (paket / "__main__.py").write_text(textwrap.dedent(koerper), encoding = "utf-8")
    return ("python3", "fakebot")


async def _lauf_durchfuehren(lauf:BotLauf) -> list[str]:
    await lauf.starten()
    return [e.text async for e in lauf.ereignisse()]


class TestZeileAuswerten:

    def test_stufen(self) -> None:
        assert zeile_auswerten("INFO alles gut").stufe is Stufe.INFO
        assert zeile_auswerten("2026-01-01 ERROR kaputt").stufe is Stufe.FEHLER
        assert zeile_auswerten("WARNING Vorsicht").stufe is Stufe.WARNUNG
        assert zeile_auswerten("DEBUG Details").stufe is Stufe.DEBUG

    @pytest.mark.parametrize(("name", "erwartet"), [
        ("PostPublishPersistenceError", Aufmerksamkeit.VEROEFFENTLICHT_NICHT_GESPEICHERT),
        ("PublishSubmissionUncertainError", Aufmerksamkeit.ABSENDEN_UNGEWISS),
        ("CategoryResolutionError", Aufmerksamkeit.KATEGORIE_UNAUFLOESBAR),
    ])
    def test_aufmerksamkeit_wird_erkannt(self, name:str, erwartet:Aufmerksamkeit) -> None:
        assert zeile_auswerten(f"ERROR {name}: etwas ist passiert").aufmerksamkeit is erwartet

    def test_ansi_farbcodes_werden_entfernt(self) -> None:
        # Der Bot faerbt seine Ausgabe ein. Ohne Entfernung kaemen die Codes in
        # der Oberflaeche als Zeichensalat an - und die Stufenerkennung
        # scheiterte an eingefaerbten Schluesselwoertern.
        roh = "\x1b[33m[WARNING]\x1b[0m \x1b[33mnodriver patch not found"
        e = zeile_auswerten(roh)
        assert "\x1b[" not in e.text
        assert e.text == "[WARNING] nodriver patch not found"
        assert e.stufe is Stufe.WARNUNG

    def test_gewoehnliche_zeile_ohne_zusatz(self) -> None:
        e = zeile_auswerten("Lade Anzeige 12345 herunter")
        assert e.aufmerksamkeit is None
        assert e.eingriff is None
        assert e.braucht_menschen is False

    @pytest.mark.parametrize(("text", "erwartet"), [
        ("Captcha detected, please solve", Eingriff.CAPTCHA),
        ("Wir haben dir gerade einen 6-stelligen Code für die Telefonnummer", Eingriff.SMS_CODE),
        ("Um dein Konto zu schützen haben wir dir eine E-Mail geschickt", Eingriff.EMAIL_BESTAETIGUNG),
        ("Press ENTER when done...", Eingriff.UNBEKANNT),
    ])
    def test_wartepunkte_werden_erkannt(self, text:str, erwartet:Eingriff) -> None:
        e = zeile_auswerten(text)
        assert e.eingriff is erwartet
        assert e.braucht_menschen is True


class TestLaufErgebnis:

    def test_erfolg_nur_ohne_aufmerksamkeit(self) -> None:
        assert LaufErgebnis("publish", 0).erfolgreich is True
        assert LaufErgebnis("publish", 1).erfolgreich is False
        assert LaufErgebnis("publish", 0, abgebrochen = True).erfolgreich is False
        # Entscheidend: Rueckgabecode 0 plus Aufmerksamkeitsfall ist KEIN Erfolg.
        # Sonst meldete die Oberflaeche "fertig", waehrend eine Anzeige online
        # ist, die lokal nicht gespeichert wurde.
        mit_fall = LaufErgebnis("publish", 0, aufmerksamkeit = [Aufmerksamkeit.ABSENDEN_UNGEWISS])
        assert mit_fall.erfolgreich is False


class TestKonfiguration:

    def test_gesperrte_felder_werden_verworfen(self, tmp_path:Path) -> None:
        boese = {
            "browser": {"binary_location": "/bin/sh", "arguments": ["--load-extension=/tmp/x"],
                        "extensions": ["/tmp/b.crx"], "use_private_window": True},
            "ad_files": ["../../../**/*.yaml"],
            "publishing": {"delete_old_ads": "NEVER"},
        }
        ziel = tmp_path / "config.yaml"
        entfernt = konfiguration.schreiben(ziel, boese, anzeigen_glob = "./ads/**/ad_*.yaml")

        assert set(entfernt) == konfiguration.GESPERRTE_FELDER
        inhalt = ziel.read_text(encoding = "utf-8")
        assert "/bin/sh" not in inhalt
        assert "b.crx" not in inhalt
        assert "load-extension" not in inhalt
        assert "../../../" not in inhalt
        # Nicht gesperrte Nachbarfelder bleiben erhalten.
        assert "use_private_window" in inhalt
        assert "NEVER" in inhalt

    def test_chromium_pfad_kommt_vom_server(self, tmp_path:Path) -> None:
        ziel = tmp_path / "config.yaml"
        konfiguration.schreiben(ziel, {"browser": {"binary_location": "/bin/sh"}},
                                anzeigen_glob = "./ads/**/ad_*.yaml",
                                chromium = "/usr/bin/chromium")
        inhalt = ziel.read_text(encoding = "utf-8")
        assert "/usr/bin/chromium" in inhalt
        assert "/bin/sh" not in inhalt

    def test_zugangsdaten_nur_als_platzhalter(self, tmp_path:Path) -> None:
        ziel = tmp_path / "config.yaml"
        konfiguration.schreiben(ziel, {"login": {"password": "GEHEIM123"}},
                                anzeigen_glob = "./ads/**/ad_*.yaml")
        inhalt = ziel.read_text(encoding = "utf-8")
        # Selbst ein mitgeliefertes Passwort landet nicht in der Datei: die
        # Basis wird UEBER die Nutzerkonfiguration gelegt.
        assert "GEHEIM123" not in inhalt
        assert "${KLEINANZEIGEN_BOT_PASSWORD}" in inhalt
        assert "${KLEINANZEIGEN_BOT_USERNAME}" in inhalt


class TestBotLauf:

    def test_unbekannter_befehl_wird_abgewiesen(self, tmp_path:Path) -> None:
        with pytest.raises(FachlicherFehler):
            BotLauf(LaufAuftrag(befehl = "rm-rf", config_datei = tmp_path / "c.yaml"))

    def test_kommando_enthaelt_workspace_mode(self, tmp_path:Path) -> None:
        lauf = BotLauf(LaufAuftrag(befehl = "verify", config_datei = tmp_path / "c.yaml"))
        kommando = lauf._kommando()  # noqa: SLF001 - bewusst geprueft, das ist der Vertrag
        assert "--workspace-mode=portable" in kommando
        assert f"--config={tmp_path / 'c.yaml'}" in kommando
        assert kommando[-1] == "verify"

    @pytest.mark.asyncio
    async def test_ausgabe_wird_zu_ereignissen(self, tmp_path:Path, monkeypatch:pytest.MonkeyPatch) -> None:
        python, modul = _ersatzbot(tmp_path, """
            print("INFO Start")
            print("ERROR PostPublishPersistenceError: ad is live")
            print("INFO Ende")
        """)
        monkeypatch.chdir(tmp_path)
        lauf = BotLauf(LaufAuftrag(befehl = "publish", config_datei = tmp_path / "c.yaml"),
                       python = python, modul = modul)
        zeilen = await _lauf_durchfuehren(lauf)

        assert "INFO Start" in zeilen
        assert lauf.ergebnis.rueckgabecode == 0
        # Trotz Rueckgabecode 0 kein Erfolg - der Aufmerksamkeitsfall zaehlt.
        assert lauf.ergebnis.aufmerksamkeit == [Aufmerksamkeit.VEROEFFENTLICHT_NICHT_GESPEICHERT]
        assert lauf.ergebnis.erfolgreich is False

    @pytest.mark.asyncio
    async def test_rueckgabecode_wird_uebernommen(self, tmp_path:Path, monkeypatch:pytest.MonkeyPatch) -> None:
        python, modul = _ersatzbot(tmp_path, """
            import sys
            print("INFO etwas lief schief")
            sys.exit(2)
        """)
        monkeypatch.chdir(tmp_path)
        lauf = BotLauf(LaufAuftrag(befehl = "verify", config_datei = tmp_path / "c.yaml"),
                       python = python, modul = modul)
        await _lauf_durchfuehren(lauf)
        # sys.exit im Bot wird zum Rueckgabecode, statt einen Serverprozess zu
        # beenden - genau der Grund fuer das Unterprozessmodell.
        assert lauf.ergebnis.rueckgabecode == 2
        assert lauf.ergebnis.erfolgreich is False

    @pytest.mark.asyncio
    async def test_eingabe_beantwortet_wartepunkt(self, tmp_path:Path, monkeypatch:pytest.MonkeyPatch) -> None:
        python, modul = _ersatzbot(tmp_path, """
            import sys
            print("Press ENTER when done...", flush=True)
            sys.stdin.readline()
            print("INFO weiter", flush=True)
        """)
        monkeypatch.chdir(tmp_path)
        lauf = BotLauf(LaufAuftrag(befehl = "publish", config_datei = tmp_path / "c.yaml"),
                       python = python, modul = modul)
        await lauf.starten()

        gesehen:list[str] = []
        async for ereignis in lauf.ereignisse():
            gesehen.append(ereignis.text)
            if ereignis.braucht_menschen:
                # Genau das ist die Naht fuer AP-1.8: kein Upstream-Patch noetig.
                await lauf.eingabe_senden()

        assert "INFO weiter" in gesehen
        assert lauf.ergebnis.rueckgabecode == 0

    @pytest.mark.asyncio
    async def test_abbruch_beendet_den_prozess(self, tmp_path:Path, monkeypatch:pytest.MonkeyPatch) -> None:
        python, modul = _ersatzbot(tmp_path, """
            import time
            print("INFO laeuft", flush=True)
            time.sleep(60)
        """)
        monkeypatch.chdir(tmp_path)
        lauf = BotLauf(LaufAuftrag(befehl = "download", config_datei = tmp_path / "c.yaml"),
                       python = python, modul = modul)
        await lauf.starten()
        await lauf.eingabe_senden("")  # Prozess sicher gestartet
        await lauf.abbrechen()

        assert lauf.ergebnis.abgebrochen is True
        assert lauf.ergebnis.rueckgabecode is not None
        assert lauf.ergebnis.erfolgreich is False
