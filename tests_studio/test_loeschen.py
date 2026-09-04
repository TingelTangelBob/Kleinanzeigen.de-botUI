# SPDX-FileCopyrightText: © Anzeigen-Studio contributors
# SPDX-ArtifactOfProjectHomePage: https://github.com/TingelTangelBob/Kleinanzeigen.de-botUI/
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# Anzeigen lokal loeschen (AP-2.20).
#
# Der wichtigste Test dieser Datei ist `test_kein_bot_aufruf_und_kein_job`:
# Loeschen darf die Platte anfassen und sonst nichts. Alle anderen pruefen,
# dass es die richtigen Dateien erwischt - und vor allem, welche nicht.

from __future__ import annotations

import textwrap
from typing import TYPE_CHECKING

import pytest

from anzeigen_studio.bestand import bestand_lesen, loeschen
from anzeigen_studio.core.errors import FachlicherFehler

if TYPE_CHECKING:
    from pathlib import Path

ANZEIGE = """
    active: true
    type: OFFER
    title: {titel}
    description: Unbenutzt
    price: 10
    images:
      - {bild}
    id: 3310837392
    """


def _anzeige(wurzel: Path, bucket: str, ordner: str, name: str, *, titel: str = "Dimmer") -> Path:
    ziel = wurzel / bucket / ordner
    ziel.mkdir(parents = True, exist_ok = True)
    datei = ziel / f"{name}.yaml"
    bild = f"{name}__img1.jpg"
    datei.write_text(textwrap.dedent(ANZEIGE.format(titel = titel, bild = bild)), encoding = "utf-8")
    (ziel / bild).write_bytes(b"x")
    return datei


class TestEntfernen:

    def test_yaml_und_bild_gehen_mit(self, tmp_path: Path) -> None:
        datei = _anzeige(tmp_path, "downloaded-ads", "ad_1_dimmer", "ad_1")
        ordner = datei.parent

        ergebnis = loeschen.entfernen(tmp_path, "downloaded-ads/ad_1_dimmer/ad_1.yaml")

        assert not datei.exists()
        assert not ordner.exists()
        assert ergebnis.titel == "Dimmer"
        assert ergebnis.bilder == 1
        assert ergebnis.ordner_entfernt is True
        assert bestand_lesen(tmp_path) == []

    def test_andere_anzeigen_bleiben(self, tmp_path: Path) -> None:
        _anzeige(tmp_path, "downloaded-ads", "ad_1_dimmer", "ad_1", titel = "Erste")
        zweite = _anzeige(tmp_path, "downloaded-ads", "ad_2_lampe", "ad_2", titel = "Zweite")

        loeschen.entfernen(tmp_path, "downloaded-ads/ad_1_dimmer/ad_1.yaml")

        assert zweite.exists()
        assert [a.titel for a in bestand_lesen(tmp_path)] == ["Zweite"]

    def test_geteilter_ordner_verliert_nur_die_eine_anzeige(self, tmp_path: Path) -> None:
        """Zwei Anzeigen in einem Ordner: `rmtree` waere stiller Datenverlust."""
        ordner = tmp_path / "downloaded-ads" / "gemeinsam"
        ordner.mkdir(parents = True)
        for name, titel in (("ad_1", "Erste"), ("ad_2", "Zweite")):
            (ordner / f"{name}.yaml").write_text(
                textwrap.dedent(ANZEIGE.format(titel = titel, bild = f"{name}__img1.jpg")),
                encoding = "utf-8",
            )
            (ordner / f"{name}__img1.jpg").write_bytes(b"x")

        ergebnis = loeschen.entfernen(tmp_path, "downloaded-ads/gemeinsam/ad_1.yaml")

        assert ergebnis.ordner_entfernt is False
        assert ergebnis.bilder == 1
        assert not (ordner / "ad_1.yaml").exists()
        assert not (ordner / "ad_1__img1.jpg").exists()
        assert (ordner / "ad_2.yaml").exists()
        assert (ordner / "ad_2__img1.jpg").exists()
        assert [a.titel for a in bestand_lesen(tmp_path)] == ["Zweite"]

    def test_unlesbare_anzeige_laesst_sich_loeschen(self, tmp_path: Path) -> None:
        """Wer eine kaputte Datei loescht, drueckt oft genau deshalb den Knopf."""
        ordner = tmp_path / "downloaded-ads" / "kaputt"
        ordner.mkdir(parents = True)
        (ordner / "ad_1.yaml").write_text("title: [unbalanciert\n", encoding = "utf-8")

        ergebnis = loeschen.entfernen(tmp_path, "downloaded-ads/kaputt/ad_1.yaml")

        assert ergebnis.titel == "ad_1"
        assert not ordner.exists()

    def test_yaml_im_bestandsordner_reisst_ihn_nicht_mit(self, tmp_path: Path) -> None:
        """`bestand_lesen` sucht mit `rglob` und zeigt auch eine YAML direkt im
        Bestandsordner an. Was die Liste zeigt, muss loeschbar sein - aber
        `rmtree` haette hier den ganzen Bestand genommen.
        """
        ordner = tmp_path / "downloaded-ads"
        ordner.mkdir()
        (ordner / "ad_1.yaml").write_text("title: x\n", encoding = "utf-8")
        (ordner / "ad_1__img1.jpg").write_bytes(b"x")

        ergebnis = loeschen.entfernen(tmp_path, "downloaded-ads/ad_1.yaml")

        assert ergebnis.ordner_entfernt is False
        assert ordner.is_dir()
        assert not (ordner / "ad_1.yaml").exists()

    def test_fremde_anzeige_geht_auch(self, tmp_path: Path) -> None:
        _anzeige(tmp_path, "fremde-ads", "ad_9_fremd", "ad_9")
        loeschen.entfernen(tmp_path, "fremde-ads/ad_9_fremd/ad_9.yaml")
        assert bestand_lesen(tmp_path) == []


class TestSchranken:
    """Was der Endpunkt NICHT loeschen darf. `datei` kommt aus einer Anfrage."""

    def test_ausbruch_aus_dem_profil(self, tmp_path: Path) -> None:
        profil = tmp_path / "profil"
        profil.mkdir()
        fremd = tmp_path / "geheim.yaml"
        fremd.write_text("title: x\n", encoding = "utf-8")

        with pytest.raises(FachlicherFehler) as fehler:
            loeschen.entfernen(profil, "../geheim.yaml")

        assert fehler.value.status == 400
        assert fremd.exists()

    def test_vorlage_ist_keine_anzeige(self, tmp_path: Path) -> None:
        vorlage = tmp_path / "vorlagen" / "v1" / "vorlage_1.yaml"
        vorlage.parent.mkdir(parents = True)
        vorlage.write_text("title: x\n", encoding = "utf-8")

        with pytest.raises(FachlicherFehler) as fehler:
            loeschen.entfernen(tmp_path, "vorlagen/v1/vorlage_1.yaml")

        assert fehler.value.status == 400
        assert vorlage.exists()

    def test_datenbank_ist_keine_anzeige(self, tmp_path: Path) -> None:
        db = tmp_path / "app.db"
        db.write_bytes(b"sqlite")

        with pytest.raises(FachlicherFehler):
            loeschen.entfernen(tmp_path, "app.db")

        assert db.exists()

    def test_fehlende_datei(self, tmp_path: Path) -> None:
        (tmp_path / "downloaded-ads" / "leer").mkdir(parents = True)
        with pytest.raises(FachlicherFehler) as fehler:
            loeschen.entfernen(tmp_path, "downloaded-ads/leer/ad_1.yaml")
        assert fehler.value.status == 404


class TestMehrere:

    def test_zwei_auf_einmal(self, tmp_path: Path) -> None:
        _anzeige(tmp_path, "downloaded-ads", "ad_1_dimmer", "ad_1", titel = "Erste")
        _anzeige(tmp_path, "downloaded-ads", "ad_2_lampe", "ad_2", titel = "Zweite")
        _anzeige(tmp_path, "downloaded-ads", "ad_3_tisch", "ad_3", titel = "Dritte")

        fertig = loeschen.mehrere_entfernen(tmp_path, [
            "downloaded-ads/ad_1_dimmer/ad_1.yaml",
            "downloaded-ads/ad_2_lampe/ad_2.yaml",
        ])

        assert [g.titel for g in fertig] == ["Erste", "Zweite"]
        assert [a.titel for a in bestand_lesen(tmp_path)] == ["Dritte"]

    def test_fehler_sagt_wie_viele_schon_weg_sind(self, tmp_path: Path) -> None:
        _anzeige(tmp_path, "downloaded-ads", "ad_1_dimmer", "ad_1")

        with pytest.raises(FachlicherFehler) as fehler:
            loeschen.mehrere_entfernen(tmp_path, [
                "downloaded-ads/ad_1_dimmer/ad_1.yaml",
                "downloaded-ads/gibtesnicht/ad_9.yaml",
            ])

        assert "1 von 2 gelöscht" in fehler.value.meldung
        assert bestand_lesen(tmp_path) == []


def test_kein_bot_aufruf_und_kein_job(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Loeschen fasst die Platte an und sonst nichts.

    Der Bot hat ein `delete`-Kommando. Wuerde es hier je aufgerufen, gingen
    Anzeigen auf kleinanzeigen.de mit - unwiederbringlich und ohne Freigabe.
    Deshalb wird `subprocess` scharf gestellt: Ein Prozessstart in diesem
    Pfad laesst den Test fallen.
    """
    import subprocess

    def _verboten(*args: object, **kwargs: object) -> None:
        msg = f"Löschen darf keinen Prozess starten: {args!r}"
        raise AssertionError(msg)

    monkeypatch.setattr(subprocess, "run", _verboten)
    monkeypatch.setattr(subprocess, "Popen", _verboten)

    _anzeige(tmp_path, "downloaded-ads", "ad_1_dimmer", "ad_1")
    loeschen.entfernen(tmp_path, "downloaded-ads/ad_1_dimmer/ad_1.yaml")

    assert bestand_lesen(tmp_path) == []
