# SPDX-FileCopyrightText: © Anzeigen-Studio contributors
# SPDX-ArtifactOfProjectHomePage: https://github.com/TingelTangelBob/Kleinanzeigen.de-botUI/
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# Tests der Vorlagen (AP-3.3).
#
# Der wichtigste Test dieser Datei ist nicht das Anlegen oder Anwenden,
# sondern `test_der_bot_findet_keine_vorlage`. Alles andere waere Komfort;
# diese eine Zusage ist der Grund, warum Vorlagen nicht einfach ein Feld in
# der Anzeigendatei sind.

from __future__ import annotations

import fnmatch
from pathlib import Path

import pytest
from ruamel.yaml import YAML

from anzeigen_studio.bestand import anlegen as anlegen_dienst
from anzeigen_studio.bestand import bearbeiten as bearbeiten_dienst
from anzeigen_studio.bestand import lesen as lesen_dienst
from anzeigen_studio.bestand import vorlagen as vorlagen_dienst
from anzeigen_studio.core.errors import FachlicherFehler

#: Genau das Muster, mit dem der Bot seine Anzeigen sucht.
#: Siehe `jobs/warteschlange.py`: "./ads/**/ad_*.{yaml,yml,json}".
BOT_MUSTER = ("ads/**/ad_*.yaml", "ads/**/ad_*.yml", "ads/**/ad_*.json")

_JPEG = b"\xff\xd8\xff" + b"0" * 40


@pytest.fixture
def profil(tmp_path: Path) -> Path:
    return tmp_path


def _anzeige(profil_wurzel: Path, titel: str = "Bosch Akkuschrauber") -> str:
    anzeige = anlegen_dienst.anlegen(
        profil_wurzel,
        {"title": titel, "description": "Beschreibung.", "category": "161/168",
         "price": 35.0, "shipping_type": "SHIPPING"},
        [_JPEG],
    )
    return anzeige.datei


def _wie_der_bot_sucht(profil_wurzel: Path) -> list[str]:
    """Sammelt, was der Bot unter seinem Glob-Muster faende."""
    alle = [
        p.relative_to(profil_wurzel).as_posix()
        for p in profil_wurzel.rglob("*") if p.is_file()
    ]
    return [
        pfad for pfad in alle
        if any(fnmatch.fnmatch(pfad, muster) for muster in BOT_MUSTER)
    ]


def test_der_bot_findet_keine_vorlage(profil: Path) -> None:
    """Die Zusage, an der das ganze Modul haengt.

    Eine Vorlage, die der Bot faende, ginge beim naechsten `publish`-Lauf mit
    online - ein Geruest, oeffentlich sichtbar unter echtem Namen.
    """
    datei = _anzeige(profil)
    vorlagen_dienst.aus_anzeige(profil, datei)

    gefunden = _wie_der_bot_sucht(profil)
    assert gefunden == [datei], f"Der Bot faende zu viel: {gefunden}"


def test_beide_sperren_greifen_einzeln(profil: Path) -> None:
    """Ordner UND Praefix - jede Sperre genuegt fuer sich."""
    datei = _anzeige(profil)
    vorlage = vorlagen_dienst.aus_anzeige(profil, datei)

    assert vorlage.datei.startswith("vorlagen/")
    assert Path(vorlage.datei).name.startswith("vorlage_")


def test_eine_vorlage_taucht_nicht_im_bestand_auf(profil: Path) -> None:
    """Sie ist keine Anzeige - also gehoert sie nicht in die Anzeigenliste."""
    datei = _anzeige(profil)
    vorlagen_dienst.aus_anzeige(profil, datei)

    bestand = lesen_dienst.bestand_lesen(profil)
    assert [a.datei for a in bestand] == [datei]


def test_die_vorlage_traegt_nie_eine_anzeigennummer(profil: Path) -> None:
    """Mit `id` hielte der Bot die angewendete Kopie fuer die Anzeige selbst
    und wuerde sie beim naechsten Lauf ueberschreiben, statt sie einzustellen."""
    datei = _anzeige(profil)
    roh = bearbeiten_dienst.rohdaten_lesen(profil, datei)
    roh["id"] = 3310837392
    with (profil / datei).open("w", encoding = "utf-8") as ziel:
        YAML().dump(roh, ziel)

    vorlage = vorlagen_dienst.aus_anzeige(profil, datei)
    inhalt = bearbeiten_dienst.rohdaten_lesen(profil, vorlage.datei)
    assert "id" not in inhalt
    assert "content_hash" not in inhalt


def test_anwenden_erzeugt_eine_anzeige_und_verbraucht_die_vorlage_nicht(profil: Path) -> None:
    """Der Unterschied zum Entwurf: Eine Vorlage wird benutzt, nicht aufgebraucht."""
    vorlage = vorlagen_dienst.aus_anzeige(profil, _anzeige(profil))

    erste = vorlagen_dienst.anwenden(profil, vorlage.datei)
    zweite = vorlagen_dienst.anwenden(profil, vorlage.datei)

    assert erste.datei != zweite.datei
    assert erste.datei.startswith("ads/")
    assert vorlagen_dienst.lesen(profil), "die Vorlage ist verschwunden"


def test_die_neue_anzeige_uebernimmt_die_felder(profil: Path) -> None:
    """Der ganze Sinn einer Vorlage: Kategorie und Versand stehen schon."""
    vorlage = vorlagen_dienst.aus_anzeige(profil, _anzeige(profil))
    neu = vorlagen_dienst.anwenden(profil, vorlage.datei)

    assert neu.kategorie == "161/168"
    assert neu.bilder == 1
    assert neu.id is None


def test_kein_kopie_zusatz_im_titel(profil: Path) -> None:
    """Anders als beim Duplizieren. Die Anzeige ist keine Kopie einer Anzeige."""
    vorlage = vorlagen_dienst.aus_anzeige(profil, _anzeige(profil, "Kinderwagen"))
    neu = vorlagen_dienst.anwenden(profil, vorlage.datei)
    assert neu.titel == "Kinderwagen"


def test_entfernen_nimmt_die_bilder_mit(profil: Path) -> None:
    vorlage = vorlagen_dienst.aus_anzeige(profil, _anzeige(profil))
    ordner = (profil / vorlage.datei).parent

    vorlagen_dienst.entfernen(profil, vorlage.datei)

    assert not ordner.exists()
    assert vorlagen_dienst.lesen(profil) == []


def test_ueber_die_vorlagen_wege_laesst_sich_keine_anzeige_anfassen(profil: Path) -> None:
    """Sonst waere `DELETE /vorlagen` ein Loeschweg fuer echte Anzeigen."""
    datei = _anzeige(profil)

    for weg in (vorlagen_dienst.entfernen, vorlagen_dienst.anwenden):
        with pytest.raises(FachlicherFehler):
            weg(profil, datei)

    assert (profil / datei).is_file()


def test_ausbruch_aus_dem_profil_wird_abgewiesen(profil: Path) -> None:
    with pytest.raises(FachlicherFehler):
        vorlagen_dienst.entfernen(profil, "../../etc/passwd.yaml")


def test_eine_kaputte_vorlage_sprengt_die_liste_nicht(profil: Path) -> None:
    vorlage = vorlagen_dienst.aus_anzeige(profil, _anzeige(profil))
    (profil / vorlage.datei).write_text("das: ist: kein: yaml:\n[", encoding = "utf-8")

    liste = vorlagen_dienst.lesen(profil)
    assert len(liste) == 1
    assert liste[0].unlesbar
