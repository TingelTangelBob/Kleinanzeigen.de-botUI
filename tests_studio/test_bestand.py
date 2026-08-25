# SPDX-FileCopyrightText: © Anzeigen-Studio contributors
# SPDX-ArtifactOfProjectHomePage: https://github.com/TingelTangelBob/Kleinanzeigen.de-botUI/
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# Tests des lokalen Anzeigenbestands (AP-3.2) und der Warnung vor dem
# Ueberschreiben lokaler Aenderungen (AP-3.1).

from __future__ import annotations

import textwrap
from datetime import UTC, datetime
from typing import TYPE_CHECKING

import pytest

from anzeigen_studio.bestand import bearbeiten, bestand_lesen, bildpfad, lokal_geaenderte
from anzeigen_studio.core.errors import FachlicherFehler

if TYPE_CHECKING:
    from pathlib import Path

JETZT = datetime(2026, 8, 24, 12, 0, tzinfo = UTC)


def _anzeige_schreiben(wurzel: Path, ordner: str, name: str, inhalt: str) -> Path:
    ziel = wurzel / "downloaded-ads" / ordner
    ziel.mkdir(parents = True, exist_ok = True)
    datei = ziel / f"{name}.yaml"
    datei.write_text(textwrap.dedent(inhalt), encoding = "utf-8")
    return datei


VOLLSTAENDIG = """
    active: true
    type: OFFER
    title: 1CH Wi-Fi Dimmer Module
    description: Unbenutzt
    category: 161/168
    price: 10
    price_type: NEGOTIABLE
    shipping_type: SHIPPING
    shipping_costs: 3.0
    shipping_options:
    sell_directly: true
    images:
      - ad_1__img1.jpg
    republication_interval: 30
    id: 3310837392
    created_on: '2026-01-27T00:00:00+01:00'
    updated_on:
    """


class TestLesen:

    def test_leeres_profil_ist_kein_fehler(self, tmp_path:Path) -> None:
        assert bestand_lesen(tmp_path) == []
        assert bestand_lesen(tmp_path / "gibtesnicht") == []

    def test_anzeige_wird_gelesen(self, tmp_path:Path) -> None:
        _anzeige_schreiben(tmp_path, "ad_1_dimmer", "ad_1", VOLLSTAENDIG)
        (tmp_path / "downloaded-ads" / "ad_1_dimmer" / "ad_1__img1.jpg").write_bytes(b"x")

        (anzeige,) = bestand_lesen(tmp_path, jetzt = JETZT)

        assert anzeige.titel == "1CH Wi-Fi Dimmer Module"
        assert anzeige.id == 3310837392
        assert anzeige.preis == 10
        assert anzeige.preistyp == "NEGOTIABLE"
        assert anzeige.versandkosten == 3.0
        assert anzeige.versandpakete == []
        assert anzeige.direkt_kaufen is True
        assert anzeige.bilder == 1
        assert anzeige.vorschaubild == "ad_1__img1.jpg"
        assert anzeige.datei.startswith("downloaded-ads/")

    def test_fehlendes_bild_verschweigt_die_anzeige_nicht(self, tmp_path:Path) -> None:
        """Die YAML nennt ein Bild, das nicht daliegt - die Anzeige bleibt sichtbar."""
        _anzeige_schreiben(tmp_path, "ad_1_dimmer", "ad_1", VOLLSTAENDIG)

        (anzeige,) = bestand_lesen(tmp_path, jetzt = JETZT)

        assert anzeige.vorschaubild is None
        assert anzeige.bilder == 1

    def test_kaputte_datei_kippt_die_liste_nicht(self, tmp_path:Path) -> None:
        """Dieselbe Lehre wie beim Download: ein Grenzfall kostet nicht den Rest."""
        _anzeige_schreiben(tmp_path, "ad_1_dimmer", "ad_1", VOLLSTAENDIG)
        _anzeige_schreiben(tmp_path, "ad_2_kaputt", "ad_2", "title: [unvollstaendig\n")

        anzeigen = bestand_lesen(tmp_path, jetzt = JETZT)

        assert len(anzeigen) == 2
        kaputt = [a for a in anzeigen if a.unlesbar]
        assert len(kaputt) == 1
        assert kaputt[0].titel == "ad_2"

    def test_faellige_stehen_oben(self, tmp_path:Path) -> None:
        _anzeige_schreiben(tmp_path, "ad_1_frisch", "ad_1", """
            title: Zzz frisch
            republication_interval: 30
            created_on: '2026-08-20T00:00:00+00:00'
            """)
        _anzeige_schreiben(tmp_path, "ad_2_alt", "ad_2", """
            title: Aaa alt
            republication_interval: 7
            created_on: '2026-01-01T00:00:00+00:00'
            """)

        titel = [a.titel for a in bestand_lesen(tmp_path, jetzt = JETZT)]

        assert titel == ["Aaa alt", "Zzz frisch"]

    def test_naechste_neueinstellung_wird_berechnet(self, tmp_path:Path) -> None:
        _anzeige_schreiben(tmp_path, "ad_1", "ad_1", """
            title: Test
            republication_interval: 10
            created_on: '2026-08-20T00:00:00+00:00'
            """)

        (anzeige,) = bestand_lesen(tmp_path, jetzt = JETZT)

        assert anzeige.neueinstellung_am == "2026-08-30"
        assert anzeige.faellig is False


class TestHinweise:

    def test_versand_ohne_paket(self, tmp_path:Path) -> None:
        _anzeige_schreiben(tmp_path, "ad_1", "ad_1", VOLLSTAENDIG)
        (anzeige,) = bestand_lesen(tmp_path, jetzt = JETZT)
        assert "versand_ohne_paket" in anzeige.hinweise
        assert "direktkauf_ohne_paket" in anzeige.hinweise

    def test_paket_vorhanden_gibt_keinen_hinweis(self, tmp_path:Path) -> None:
        _anzeige_schreiben(tmp_path, "ad_1", "ad_1", """
            title: Test
            shipping_type: SHIPPING
            shipping_costs: 0.49
            shipping_options:
              - Hermes_Päckchen
            sell_directly: true
            images:
              - a.jpg
            """)
        (anzeige,) = bestand_lesen(tmp_path, jetzt = JETZT)
        assert anzeige.hinweise == []


class TestLokaleAenderungen:

    def _mit_stempel(self, tmp_path:Path, *, stempel:str) -> None:
        _anzeige_schreiben(tmp_path, "ad_1", "ad_1", f"""
            active: true
            type: OFFER
            title: Testanzeige mit gueltiger Laenge
            description: Text
            category: 161/168
            price: 10
            price_type: FIXED
            shipping_type: PICKUP
            republication_interval: 30
            id: 4711
            content_hash: '{stempel}'
            """)

    def test_falscher_stempel_gilt_als_geaendert(self, tmp_path:Path) -> None:
        pytest.importorskip("kleinanzeigen_bot.model.ad_model")
        self._mit_stempel(tmp_path, stempel = "passt-nicht")

        geaendert = lokal_geaenderte(tmp_path)

        assert [a.titel for a in geaendert] == ["Testanzeige mit gueltiger Laenge"]

    def test_ungueltige_datei_mit_stempel_gilt_als_geaendert(self, tmp_path:Path) -> None:
        """Nicht mehr pruefbar heisst im Zweifel geaendert - lieber fragen als ueberschreiben."""
        pytest.importorskip("kleinanzeigen_bot.model.ad_model")
        _anzeige_schreiben(tmp_path, "ad_1", "ad_1", """
            title: Zu kurz
            id: 4711
            content_hash: 'irgendwas'
            """)

        assert len(lokal_geaenderte(tmp_path)) == 1

    def test_ohne_stempel_gilt_als_unveraendert(self, tmp_path:Path) -> None:
        """Ein fehlender Stempel ist keine Aenderung - nur eine Anzeige ohne Stempel."""
        _anzeige_schreiben(tmp_path, "ad_1", "ad_1", VOLLSTAENDIG)
        assert lokal_geaenderte(tmp_path) == []


class TestBildpfad:

    def test_bild_wird_gefunden(self, tmp_path:Path) -> None:
        datei = _anzeige_schreiben(tmp_path, "ad_1", "ad_1", VOLLSTAENDIG)
        bild = datei.parent / "ad_1__img1.jpg"
        bild.write_bytes(b"x")

        gefunden = bildpfad(tmp_path, datei.relative_to(tmp_path).as_posix(), "ad_1__img1.jpg")

        assert gefunden == bild.resolve()

    @pytest.mark.parametrize("boese", [
        "../../app.db",
        "../../../etc/passwd",
        "/etc/passwd",
    ])
    def test_ausbruch_wird_abgewiesen(self, tmp_path:Path, boese:str) -> None:
        datei = _anzeige_schreiben(tmp_path, "ad_1", "ad_1", VOLLSTAENDIG)
        (tmp_path / "app.db").write_bytes(b"geheim")

        with pytest.raises(FachlicherFehler):
            bildpfad(tmp_path, datei.relative_to(tmp_path).as_posix(), boese)

    def test_nur_bilder(self, tmp_path:Path) -> None:
        datei = _anzeige_schreiben(tmp_path, "ad_1", "ad_1", VOLLSTAENDIG)
        (datei.parent / "notiz.txt").write_text("x", encoding = "utf-8")

        with pytest.raises(FachlicherFehler):
            bildpfad(tmp_path, datei.relative_to(tmp_path).as_posix(), "notiz.txt")


class TestBearbeiten:
    """Tests des Editors (AP-2.5)."""

    def _profil(self, tmp_path:Path) -> tuple[Path, str]:
        datei = _anzeige_schreiben(tmp_path, "ad_1", "ad_1", VOLLSTAENDIG)
        return tmp_path, datei.relative_to(tmp_path).as_posix()

    def test_rohdaten_lesen(self, tmp_path:Path) -> None:
        wurzel, datei = self._profil(tmp_path)
        daten = bearbeiten.rohdaten_lesen(wurzel, datei)
        assert daten["title"] == "1CH Wi-Fi Dimmer Module"
        assert daten["price"] == 10

    def test_speichern_aendert_nur_gegebene_felder(self, tmp_path:Path) -> None:
        wurzel, datei = self._profil(tmp_path)

        kopf, _ = bearbeiten.speichern(wurzel, datei, {"price": 12, "title": "Neuer Titel für alles"})

        assert kopf.preis == 12
        assert kopf.titel == "Neuer Titel für alles"
        danach = bearbeiten.rohdaten_lesen(wurzel, datei)
        assert danach["category"] == "161/168"
        assert danach["id"] == 3310837392

    def test_inhaltsstempel_bleibt_stehen(self, tmp_path:Path) -> None:
        """Sonst wäre die Änderung sofort unsichtbar - und die Warnung vor dem
        Download (AP-3.1) hätte nichts mehr zu melden."""
        pytest.importorskip("kleinanzeigen_bot.model.ad_model")
        _anzeige_schreiben(tmp_path, "ad_2", "ad_2", """
            active: true
            type: OFFER
            title: Testanzeige mit gueltiger Laenge
            description: Text
            category: 161/168
            price: 10
            price_type: FIXED
            shipping_type: PICKUP
            republication_interval: 30
            id: 4711
            content_hash: 'alter-stempel'
            """)
        datei = "downloaded-ads/ad_2/ad_2.yaml"

        bearbeiten.speichern(tmp_path, datei, {"price": 15})

        danach = bearbeiten.rohdaten_lesen(tmp_path, datei)
        assert danach["content_hash"] == "alter-stempel"
        assert len(lokal_geaenderte(tmp_path)) == 1

    def test_gesperrte_felder_werden_abgewiesen(self, tmp_path:Path) -> None:
        wurzel, datei = self._profil(tmp_path)
        with pytest.raises(FachlicherFehler):
            bearbeiten.speichern(wurzel, datei, {"id": 1, "content_hash": "x"})

    def test_strukturfehler_wird_abgewiesen(self, tmp_path:Path) -> None:
        pytest.importorskip("kleinanzeigen_bot.model.ad_model")
        wurzel, datei = self._profil(tmp_path)

        with pytest.raises(FachlicherFehler):
            bearbeiten.speichern(wurzel, datei, {"title": "zu kurz"})

        # Die Datei darf dabei unberührt bleiben.
        assert bearbeiten.rohdaten_lesen(wurzel, datei)["title"] == "1CH Wi-Fi Dimmer Module"

    def test_veroeffentlichungsfehler_ist_nur_ein_hinweis(self, tmp_path:Path) -> None:
        """Ein halbfertiger Entwurf muss sich speichern lassen.

        Direkt kaufen mit Abholung ist eine Kombination, die das Modell erst
        beim vollstaendigen Zusammenbau ablehnt - also beim Veroeffentlichen,
        nicht beim Tippen.
        """
        pytest.importorskip("kleinanzeigen_bot.model.ad_model")
        wurzel, datei = self._profil(tmp_path)

        _, hinweise = bearbeiten.speichern(wurzel, datei, {"shipping_type": "PICKUP"})

        assert hinweise, "Direkt kaufen mit Abholung gehört gemeldet"
        assert bearbeiten.rohdaten_lesen(wurzel, datei)["shipping_type"] == "PICKUP"

    def test_saubere_aenderung_erzeugt_keinen_hinweis(self, tmp_path:Path) -> None:
        """Sonst waere der Hinweiskanal dauerhaft laut und damit wertlos."""
        pytest.importorskip("kleinanzeigen_bot.model.ad_model")
        wurzel, datei = self._profil(tmp_path)

        _, hinweise = bearbeiten.speichern(wurzel, datei, {"price": 12})

        assert hinweise == []

    def test_ausbruch_wird_abgewiesen(self, tmp_path:Path) -> None:
        wurzel, _ = self._profil(tmp_path)
        (tmp_path / "app.db").write_bytes(b"geheim")
        with pytest.raises(FachlicherFehler):
            bearbeiten.rohdaten_lesen(wurzel, "../app.db")
