# SPDX-FileCopyrightText: © Anzeigen-Studio contributors
# SPDX-ArtifactOfProjectHomePage: https://github.com/TingelTangelBob/Kleinanzeigen.de-botUI/
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# Sicherung, Export und Import (AP-3.6).
#
# Der wichtigste Test dieser Datei ist `test_kein_geheimnis_im_archiv`: Er ist
# die Gegenprobe, die der Projektplan fuer dieses Paket ausdruecklich verlangt -
# im Archiv findet ein `grep` weder Passwort noch API-Schluessel noch die
# Kekse einer angemeldeten Browsersitzung.
#
# Danach kommen die Einbruchsversuche (`TestBoesesArchiv`). Ein Importweg, der
# Dateien aus fremder Hand auf die Platte schreibt, ist die gefaehrlichste
# Stelle dieses Pakets.

from __future__ import annotations

import base64
import zipfile
from typing import TYPE_CHECKING

import pytest

from anzeigen_studio.bestand import archiv
from anzeigen_studio.core.errors import FachlicherFehler

if TYPE_CHECKING:
    from pathlib import Path

SCHLUESSEL = base64.b64encode(b"0123456789abcdef0123456789abcdef").decode()

ANZEIGE = """active: true
type: OFFER
title: {titel}
description: Unbenutzt
price: 10
images:
  - {bild}
id: {nummer}
"""


def _profil_aufbauen(wurzel: Path) -> None:
    """Ein Profil, wie es im Betrieb aussieht - samt allem, was NICHT mitdarf."""
    anzeige = wurzel / "downloaded-ads" / "ad_1_tisch"
    anzeige.mkdir(parents = True)
    (anzeige / "ad_1.yaml").write_text(
        ANZEIGE.format(titel = "Tisch", bild = "bild1.jpg", nummer = "111"), encoding = "utf-8")
    (anzeige / "bild1.jpg").write_bytes(b"\xff\xd8\xff\xe0JPEG")

    vorlage = wurzel / "vorlagen" / "standard"
    vorlage.mkdir(parents = True)
    (vorlage / "vorlage_standard.yaml").write_text("title: Vorlage\n", encoding = "utf-8")

    (wurzel / "nutzer.yaml").write_text("publishing:\n  delete_old_ads: BEFORE_PUBLISH\n",
                                        encoding = "utf-8")

    # --- und jetzt das, was auf keinen Fall mitgehen darf ---------------------
    (wurzel / "config.yaml").write_text(
        "login:\n  username: ${KLEINANZEIGEN_BOT_USERNAME}\n"
        "  password: ${KLEINANZEIGEN_BOT_PASSWORD}\n", encoding = "utf-8")
    browser = wurzel / ".temp" / "browser-profile" / "Default"
    browser.mkdir(parents = True)
    (browser / "Cookies").write_bytes(b"SESSIONKEKS-GEHEIM-abcdef123456")
    diagnose = wurzel / ".temp" / "diagnostics"
    diagnose.mkdir(parents = True)
    (diagnose / "seite.html").write_text("Klarname Musterstrasse 1", encoding = "utf-8")
    (wurzel / "kleinanzeigen_bot.log").write_text(
        "Anmeldung mit Passwort HOCHGEHEIM123\n", encoding = "utf-8")


class TestExport:

    def test_nimmt_anzeigen_bilder_vorlagen_und_nutzerconfig(self, tmp_path: Path) -> None:
        wurzel = tmp_path / "profil"
        wurzel.mkdir()
        _profil_aufbauen(wurzel)
        ziel = tmp_path / "aus.zip"

        anzahl = archiv.exportieren(wurzel, ziel, profil_slug = "haushalt")

        with zipfile.ZipFile(ziel) as z:
            namen = set(z.namelist())
        assert anzahl == 4
        assert "downloaded-ads/ad_1_tisch/ad_1.yaml" in namen
        assert "downloaded-ads/ad_1_tisch/bild1.jpg" in namen
        assert "vorlagen/standard/vorlage_standard.yaml" in namen
        assert "nutzer.yaml" in namen
        assert archiv.MANIFEST in namen

    def test_kein_geheimnis_im_archiv(self, tmp_path: Path) -> None:
        """Die Gegenprobe aus dem Projektplan, wörtlich genommen.

        Gesucht wird im ROHEN Archivbytes, nicht in der Dateiliste: Ein
        Geheimnis, das in einer mitgepackten Datei steckt, taucht in keiner
        Namensliste auf.
        """
        wurzel = tmp_path / "profil"
        wurzel.mkdir()
        _profil_aufbauen(wurzel)
        ziel = tmp_path / "aus.zip"

        archiv.exportieren(wurzel, ziel, profil_slug = "haushalt")

        roh = ziel.read_bytes()
        for geheimnis in (b"SESSIONKEKS", b"HOCHGEHEIM123", b"KLEINANZEIGEN_BOT_PASSWORD",
                          b"Musterstrasse"):
            assert geheimnis not in roh, f"{geheimnis!r} steht im Archiv"

        with zipfile.ZipFile(ziel) as z:
            namen = z.namelist()
        assert not any(n.startswith(".temp") for n in namen)
        assert "config.yaml" not in namen
        assert "kleinanzeigen_bot.log" not in namen

    def test_symlink_geht_nicht_mit(self, tmp_path: Path) -> None:
        # Sonst wuerde er beim Packen dereferenziert - ein Link auf
        # /etc/passwd landete als echte Datei im Archiv.
        wurzel = tmp_path / "profil"
        (wurzel / "downloaded-ads").mkdir(parents = True)
        geheim = tmp_path / "geheim.yaml"
        geheim.write_text("passwort: PETERSILIE\n", encoding = "utf-8")
        (wurzel / "downloaded-ads" / "ad_x.yaml").symlink_to(geheim)
        ziel = tmp_path / "aus.zip"

        archiv.exportieren(wurzel, ziel, profil_slug = "haushalt")

        assert b"PETERSILIE" not in ziel.read_bytes()


def _archiv_bauen(pfad: Path, eintraege: dict[str, bytes]) -> Path:
    with zipfile.ZipFile(pfad, "w") as z:
        for name, inhalt in eintraege.items():
            z.writestr(name, inhalt)
    return pfad


class TestVorschau:

    def test_trennt_neu_von_doppelt(self, tmp_path: Path) -> None:
        wurzel = tmp_path / "profil"
        (wurzel / "downloaded-ads" / "ad_1_tisch").mkdir(parents = True)
        (wurzel / "downloaded-ads" / "ad_1_tisch" / "ad_1.yaml").write_text("x", encoding = "utf-8")
        quelle = _archiv_bauen(tmp_path / "ein.zip", {
            "downloaded-ads/ad_1_tisch/ad_1.yaml": b"neu",
            "downloaded-ads/ad_2_stuhl/ad_2.yaml": b"neu",
            "downloaded-ads/ad_2_stuhl/bild.jpg": b"\xff\xd8",
        })

        gesehen = archiv.vorschau(quelle, wurzel)

        assert gesehen.dateien == 3
        assert gesehen.anzeigen == 2
        assert gesehen.bilder == 1
        assert gesehen.doppelt == ["downloaded-ads/ad_1_tisch/ad_1.yaml"]
        assert len(gesehen.neu) == 2

    def test_schreibt_nichts(self, tmp_path: Path) -> None:
        wurzel = tmp_path / "profil"
        wurzel.mkdir()
        quelle = _archiv_bauen(tmp_path / "ein.zip", {"downloaded-ads/a/ad_1.yaml": b"x"})

        archiv.vorschau(quelle, wurzel)

        assert list(wurzel.iterdir()) == []

    def test_nennt_abgewiesenes_mit_grund(self, tmp_path: Path) -> None:
        wurzel = tmp_path / "profil"
        wurzel.mkdir()
        quelle = _archiv_bauen(tmp_path / "ein.zip", {
            ".temp/browser-profile/Cookies": b"KEKS",
            "downloaded-ads/a/schadcode.sh": b"rm -rf /",
        })

        gesehen = archiv.vorschau(quelle, wurzel)

        assert gesehen.dateien == 0
        assert len(gesehen.abgewiesen) == 2


class TestImport:

    def test_schreibt_und_meldet(self, tmp_path: Path) -> None:
        wurzel = tmp_path / "profil"
        wurzel.mkdir()
        quelle = _archiv_bauen(tmp_path / "ein.zip", {
            "downloaded-ads/ad_1_tisch/ad_1.yaml": b"title: Tisch\n",
            "downloaded-ads/ad_1_tisch/bild.jpg": b"\xff\xd8",
            "nutzer.yaml": b"publishing: {}\n",
        })

        ergebnis = archiv.importieren(quelle, wurzel)

        assert len(ergebnis.geschrieben) == 3
        assert (wurzel / "downloaded-ads" / "ad_1_tisch" / "ad_1.yaml").read_text() == "title: Tisch\n"
        assert "3 übernommen" in ergebnis.zusammenfassung

    def test_vorhandenes_bleibt_unangetastet(self, tmp_path: Path) -> None:
        # Der Vorgabefall: Zurueckholen einzelner Anzeigen in einen Bestand,
        # an dem lokal gearbeitet wurde.
        wurzel = tmp_path / "profil"
        (wurzel / "downloaded-ads" / "a").mkdir(parents = True)
        vorhanden = wurzel / "downloaded-ads" / "a" / "ad_1.yaml"
        vorhanden.write_text("meine Fassung", encoding = "utf-8")
        quelle = _archiv_bauen(tmp_path / "ein.zip", {"downloaded-ads/a/ad_1.yaml": b"aus dem Archiv"})

        ergebnis = archiv.importieren(quelle, wurzel)

        assert vorhanden.read_text(encoding = "utf-8") == "meine Fassung"
        assert ergebnis.uebersprungen == ["downloaded-ads/a/ad_1.yaml"]
        assert ergebnis.geschrieben == []

    def test_ersetzen_nur_auf_ansage(self, tmp_path: Path) -> None:
        wurzel = tmp_path / "profil"
        (wurzel / "downloaded-ads" / "a").mkdir(parents = True)
        vorhanden = wurzel / "downloaded-ads" / "a" / "ad_1.yaml"
        vorhanden.write_text("meine Fassung", encoding = "utf-8")
        quelle = _archiv_bauen(tmp_path / "ein.zip", {"downloaded-ads/a/ad_1.yaml": b"aus dem Archiv"})

        ergebnis = archiv.importieren(quelle, wurzel, vorhandene_ersetzen = True)

        assert vorhanden.read_text(encoding = "utf-8") == "aus dem Archiv"
        assert ergebnis.ersetzt == ["downloaded-ads/a/ad_1.yaml"]

    def test_rundlauf_export_import(self, tmp_path: Path) -> None:
        """Der Nachweis aus dem Plan: Export, frische Ablage, Import, vollständig."""
        alt = tmp_path / "alt"
        alt.mkdir()
        _profil_aufbauen(alt)
        paket = tmp_path / "aus.zip"
        archiv.exportieren(alt, paket, profil_slug = "haushalt")

        neu = tmp_path / "neu"
        neu.mkdir()
        ergebnis = archiv.importieren(paket, neu)

        assert len(ergebnis.geschrieben) == 4
        assert (neu / "downloaded-ads" / "ad_1_tisch" / "ad_1.yaml").exists()
        assert (neu / "downloaded-ads" / "ad_1_tisch" / "bild1.jpg").read_bytes().startswith(b"\xff\xd8")
        assert (neu / "vorlagen" / "standard" / "vorlage_standard.yaml").exists()
        assert (neu / "nutzer.yaml").exists()
        # Und was nicht mitdurfte, ist auch nach dem Import nicht da.
        assert not (neu / ".temp").exists()
        assert not (neu / "config.yaml").exists()


class TestBoesesArchiv:
    """Ein Archiv kommt aus fremder Hand. Es wird wie eine Eingabe behandelt."""

    @pytest.mark.parametrize("name", [
        "../../../etc/cron.d/uebernahme",
        "/etc/passwd",
        "downloaded-ads/../../ausbruch.yaml",
        ".temp/browser-profile/Cookies",
        "kleinanzeigen_bot.log",
        "config.yaml",
        "downloaded-ads/a/skript.sh",
        "fremdes-verzeichnis/a.yaml",
    ])
    def test_wird_abgewiesen_und_schreibt_nichts(self, tmp_path: Path, name: str) -> None:
        wurzel = tmp_path / "profil"
        wurzel.mkdir()
        quelle = _archiv_bauen(tmp_path / "ein.zip", {name: b"boese"})

        ergebnis = archiv.importieren(quelle, wurzel)

        assert ergebnis.geschrieben == []
        assert len(ergebnis.abgewiesen) == 1
        # Nichts ausserhalb UND nichts innerhalb des Profils angelegt.
        assert list(wurzel.rglob("*")) == []
        assert not (tmp_path / "ausbruch.yaml").exists()

    def test_keine_zipdatei(self, tmp_path: Path) -> None:
        wurzel = tmp_path / "profil"
        wurzel.mkdir()
        keine = tmp_path / "ein.zip"
        keine.write_bytes(b"das ist kein zip")

        with pytest.raises(FachlicherFehler) as fehler:
            archiv.vorschau(keine, wurzel)
        assert fehler.value.status == 400

    def test_zu_viele_eintraege(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(archiv, "MAX_EINTRAEGE", 3)
        wurzel = tmp_path / "profil"
        wurzel.mkdir()
        quelle = _archiv_bauen(tmp_path / "ein.zip", {
            f"downloaded-ads/a/ad_{i}.yaml": b"x" for i in range(5)
        })

        with pytest.raises(FachlicherFehler) as fehler:
            archiv.vorschau(quelle, wurzel)
        assert fehler.value.status == 413

    def test_zu_gross_entpackt(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        # Die klassische Zip-Bombe: klein im Archiv, riesig auf der Platte.
        monkeypatch.setattr(archiv, "MAX_ENTPACKT_BYTES", 100)
        wurzel = tmp_path / "profil"
        wurzel.mkdir()
        quelle = _archiv_bauen(tmp_path / "ein.zip", {
            "downloaded-ads/a/ad_1.yaml": b"x" * 1000,
        })

        with pytest.raises(FachlicherFehler) as fehler:
            archiv.vorschau(quelle, wurzel)
        assert fehler.value.status == 413


class TestInhaltspruefung:
    """Der Dateiname allein entscheidet nicht (Befund 2026-09-05).

    Fuer Anzeigen reicht die Pfadpruefung - eine kaputte Anzeigendatei zeigt
    die Bestandsliste als "unlesbar" an, mehr kann sie nicht anrichten. Fuer
    `nutzer.yaml` reicht sie nicht: Darin stehen die Felder aus AP-1.11, die
    einen Codeausfuehrungspfad oeffnen.
    """

    @pytest.mark.parametrize("inhalt", [
        b"browser:\n  binary_location: /bin/sh\n",
        b"browser:\n  arguments:\n    - --load-extension=/tmp\n",
        b"browser:\n  extensions:\n    - /tmp/x.crx\n",
        b"ad_files:\n  - /etc/passwd\n",
        b"login:\n  username: x\n  password: GEHEIM\n",
    ])
    def test_gesperrte_felder_kommen_nicht_ins_profil(
        self, tmp_path: Path, inhalt: bytes,
    ) -> None:
        wurzel = tmp_path / "profil"
        wurzel.mkdir()
        quelle = _archiv_bauen(tmp_path / "ein.zip", {"nutzer.yaml": inhalt})

        ergebnis = archiv.importieren(quelle, wurzel)

        assert ergebnis.geschrieben == []
        assert len(ergebnis.abgewiesen) == 1
        assert "nutzer.yaml" in ergebnis.abgewiesen[0]
        assert not (wurzel / "nutzer.yaml").exists()

    def test_unbekanntes_feld_wird_abgewiesen(self, tmp_path: Path) -> None:
        # Dieselbe Regel wie im Einstellungen-Endpunkt: Was das Formular nicht
        # kennt, wird nicht gespeichert.
        wurzel = tmp_path / "profil"
        wurzel.mkdir()
        quelle = _archiv_bauen(tmp_path / "ein.zip", {"nutzer.yaml": b"erfunden: 1\n"})

        ergebnis = archiv.importieren(quelle, wurzel)

        assert ergebnis.geschrieben == []
        assert len(ergebnis.abgewiesen) == 1

    def test_gueltige_nutzerconfig_geht_durch(self, tmp_path: Path) -> None:
        wurzel = tmp_path / "profil"
        wurzel.mkdir()
        quelle = _archiv_bauen(tmp_path / "ein.zip", {
            "nutzer.yaml": b"publishing:\n  delete_old_ads: BEFORE_PUBLISH\n",
        })

        ergebnis = archiv.importieren(quelle, wurzel)

        assert ergebnis.geschrieben == ["nutzer.yaml"]

    def test_leere_nutzerconfig_ist_in_ordnung(self, tmp_path: Path) -> None:
        wurzel = tmp_path / "profil"
        wurzel.mkdir()
        quelle = _archiv_bauen(tmp_path / "ein.zip", {"nutzer.yaml": b"\n"})

        assert archiv.importieren(quelle, wurzel).geschrieben == ["nutzer.yaml"]

    def test_kaputte_yaml_wird_benannt(self, tmp_path: Path) -> None:
        wurzel = tmp_path / "profil"
        wurzel.mkdir()
        quelle = _archiv_bauen(tmp_path / "ein.zip", {"nutzer.yaml": b"a: [1,\n  b: 2\n"})

        ergebnis = archiv.importieren(quelle, wurzel)

        assert ergebnis.geschrieben == []
        assert "lesbare YAML" in ergebnis.abgewiesen[0]

    def test_eigenes_archiv_bleibt_importierbar(self, tmp_path: Path) -> None:
        """Export und Import muessen zueinander passen - sonst ist der Rundlauf kaputt."""
        alt = tmp_path / "alt"
        alt.mkdir()
        _profil_aufbauen(alt)
        paket = tmp_path / "aus.zip"
        archiv.exportieren(alt, paket, profil_slug = "haushalt")

        neu = tmp_path / "neu"
        neu.mkdir()
        ergebnis = archiv.importieren(paket, neu)

        assert ergebnis.abgewiesen == []
        assert "nutzer.yaml" in ergebnis.geschrieben
