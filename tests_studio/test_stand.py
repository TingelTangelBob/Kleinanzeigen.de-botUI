# SPDX-FileCopyrightText: © Anzeigen-Studio contributors
# SPDX-ArtifactOfProjectHomePage: https://github.com/TingelTangelBob/Kleinanzeigen.de-botUI/
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# Vorher-Nachher-Vergleich (AP-3.5).
#
# Der wichtigste Fall in dieser Datei ist der leere: Ohne bekannten Abgleich
# darf kein Unterschied behauptet werden - und "kein Abgleich bekannt" muss
# vom Aufrufer von "nichts geaendert" unterschieden werden koennen.

from __future__ import annotations

import textwrap
import time
from datetime import UTC, datetime
from typing import TYPE_CHECKING

import pytest

from anzeigen_studio.bestand import stand
from anzeigen_studio.bestand.bearbeiten import AENDERBAR
from anzeigen_studio.core import db

if TYPE_CHECKING:
    import sqlite3
    from pathlib import Path

ANZEIGE = """
    active: true
    type: OFFER
    title: 1CH Wi-Fi Dimmer Module
    description: Unbenutzt! Nagelneu
    category: 161/168
    price: 10.0
    price_type: NEGOTIABLE
    shipping_type: SHIPPING
    shipping_options: []
    sell_directly: true
    images:
      - ad_1__img1.jpg
      - ad_1__img2.jpg
    id: 3310837392
    content_hash: abc123
    updated_on: '2026-08-01T10:00:00'
"""


@pytest.fixture
def verbindung(tmp_path:Path) -> sqlite3.Connection:
    conn = db.connect(tmp_path / "test.db")
    db.migrate(conn)
    conn.execute(
        "INSERT INTO profil (id, slug, anzeigename, angelegt_am, geaendert_am) "
        "VALUES (1, 'test', 'Test', '2026-08-27', '2026-08-27')",
    )
    conn.commit()
    return conn


def _anzeige_schreiben(wurzel:Path, inhalt:str = ANZEIGE) -> Path:
    ziel = wurzel / "downloaded-ads" / "ad_1"
    ziel.mkdir(parents = True, exist_ok = True)
    datei = ziel / "ad_1.yaml"
    datei.write_text(textwrap.dedent(inhalt), encoding = "utf-8")
    return datei


class TestSchnappschuss:
    def test_nimmt_nur_die_aenderbaren_felder(self) -> None:
        """Kennung, Pruefsumme und Zeitstempel gehoeren dem Bot.

        Sie mitzunehmen hiesse, bei jedem Vergleich Unterschiede zu melden,
        die niemanden interessieren - der Bot schreibt sie bei jedem Lauf neu.
        """
        kurz = stand.schnappschuss({
            "title": "Titel", "price": 9.0, "id": 123,
            "content_hash": "abc", "updated_on": "2026-08-01", "repost_count": 3,
        })
        assert kurz == {"title": "Titel", "price": 9.0}

    def test_jedes_aenderbare_feld_hat_eine_beschriftung(self) -> None:
        """Sonst faellt ein Feld stillschweigend aus dem Vergleich."""
        assert stand.FEHLENDE_BESCHRIFTUNGEN == frozenset()
        assert frozenset(stand.BESCHRIFTUNGEN) >= frozenset(AENDERBAR)


class TestVergleich:
    def test_ohne_gemerkten_stand_keine_unterschiede(self) -> None:
        """Nichts zu wissen ist nicht dasselbe wie zu wissen, dass nichts ist."""
        assert stand.vergleichen(None, {"title": "Neu"}) == []

    def test_gleicher_stand_ergibt_nichts(self) -> None:
        daten = {"title": "Titel", "price": 10.0}
        assert stand.vergleichen(stand.schnappschuss(daten), daten) == []

    def test_geaenderter_preis_wird_gemeldet(self) -> None:
        vorher = stand.schnappschuss({"title": "T", "price": 10.0})
        unterschiede = stand.vergleichen(vorher, {"title": "T", "price": 9.0})
        assert len(unterschiede) == 1
        assert unterschiede[0].feld == "price"
        assert unterschiede[0].beschriftung == "Preis"
        assert unterschiede[0].vorher == "10,00 €"
        assert unterschiede[0].jetzt == "9,00 €"

    def test_lange_texte_werden_nicht_ausgeschrieben(self) -> None:
        """Eine Beschreibung darf 4000 Zeichen haben - der Dialog nicht."""
        vorher = stand.schnappschuss({"description": "kurz"})
        unterschiede = stand.vergleichen(vorher, {"description": "x" * 300})
        assert unterschiede[0].jetzt == "300 Zeichen"

    def test_bilder_werden_gezaehlt_nicht_aufgezaehlt(self) -> None:
        vorher = stand.schnappschuss({"images": ["a.jpg", "b.jpg"]})
        unterschiede = stand.vergleichen(vorher, {"images": ["a.jpg"]})
        assert unterschiede[0].vorher == "2 Bilder"
        assert unterschiede[0].jetzt == "1 Bild"

    def test_leer_und_fehlend_sind_dasselbe(self) -> None:
        """Sonst meldet jede Datei, die ein Feld nicht kennt, einen Unterschied."""
        vorher = stand.schnappschuss({"title": "T", "shipping_options": []})
        assert stand.vergleichen(vorher, {"title": "T"}) == []

    def test_versandpakete_werden_benannt(self) -> None:
        vorher = stand.schnappschuss({"shipping_options": []})
        unterschiede = stand.vergleichen(vorher, {"shipping_options": ["Hermes_Päckchen"]})
        assert unterschiede[0].beschriftung == "Versandpakete"
        assert unterschiede[0].vorher == "keine"
        assert unterschiede[0].jetzt == "Hermes_Päckchen"


class TestMerken:
    def test_merken_und_lesen(self, verbindung:sqlite3.Connection) -> None:
        stand.merken(verbindung, 1, "a.yaml", {"title": "T", "price": 10.0},
                     quelle = "download", zeitpunkt = "2026-08-27T10:00:00+00:00")
        gemerkt = stand.gemerkt(verbindung, 1, "a.yaml")
        assert gemerkt is not None
        daten, quelle, zeitpunkt = gemerkt
        assert daten == {"title": "T", "price": 10.0}
        assert quelle == "download"
        assert zeitpunkt == "2026-08-27T10:00:00+00:00"

    def test_zweites_merken_ersetzt_das_erste(self, verbindung:sqlite3.Connection) -> None:
        for preis, quelle in ((10.0, "download"), (9.0, "update")):
            stand.merken(verbindung, 1, "a.yaml", {"price": preis},
                         quelle = quelle, zeitpunkt = "2026-08-27T10:00:00+00:00")
        gemerkt = stand.gemerkt(verbindung, 1, "a.yaml")
        assert gemerkt is not None
        assert gemerkt[0] == {"price": 9.0}
        assert gemerkt[1] == "update"

    def test_unbekannte_datei_ergibt_none(self, verbindung:sqlite3.Connection) -> None:
        assert stand.gemerkt(verbindung, 1, "gibtsnicht.yaml") is None

    def test_unlesbarer_schnappschuss_ist_wie_keiner(self, verbindung:sqlite3.Connection) -> None:
        """Ein Vergleich ist Zusatzauskunft und darf nie ein Fehler werden."""
        verbindung.execute(
            "INSERT INTO anzeige_stand (profil_id, datei, stand, quelle, zeitpunkt) "
            "VALUES (1, 'a.yaml', 'kein json', 'download', '2026-08-27T10:00:00+00:00')",
        )
        assert stand.gemerkt(verbindung, 1, "a.yaml") is None


class TestAbgleichNachLauf:
    def test_merkt_nur_waehrend_des_laufs_geschriebene_dateien(
        self, verbindung:sqlite3.Connection, tmp_path:Path,
    ) -> None:
        """Die Aenderungszeit der Datei entscheidet - sie weiss es genau."""
        alt = _anzeige_schreiben(tmp_path)
        # Sicherstellen, dass die zweite Datei messbar spaeter entsteht.
        time.sleep(0.02)
        seit = datetime.now(UTC).isoformat(timespec = "milliseconds")
        time.sleep(0.02)

        neu_ordner = tmp_path / "downloaded-ads" / "ad_2"
        neu_ordner.mkdir(parents = True, exist_ok = True)
        (neu_ordner / "ad_2.yaml").write_text(textwrap.dedent(ANZEIGE), encoding = "utf-8")

        anzahl = stand.abgleich_nach_lauf(verbindung, 1, tmp_path, seit = seit, quelle = "download")

        assert anzahl == 1
        assert stand.gemerkt(verbindung, 1, "downloaded-ads/ad_2/ad_2.yaml") is not None
        assert stand.gemerkt(verbindung, 1, alt.relative_to(tmp_path).as_posix()) is None

    def test_kaputte_datei_bricht_den_abgleich_nicht_ab(
        self, verbindung:sqlite3.Connection, tmp_path:Path,
    ) -> None:
        """Ein erfolgreicher Lauf darf nicht nachtraeglich am Vergleich scheitern."""
        seit = datetime.now(UTC).isoformat(timespec = "milliseconds")
        time.sleep(0.02)
        ordner = tmp_path / "downloaded-ads" / "ad_1"
        ordner.mkdir(parents = True, exist_ok = True)
        (ordner / "kaputt.yaml").write_text("das: ist: kein: yaml:", encoding = "utf-8")
        (ordner / "ad_1.yaml").write_text(textwrap.dedent(ANZEIGE), encoding = "utf-8")

        assert stand.abgleich_nach_lauf(verbindung, 1, tmp_path, seit = seit, quelle = "update") == 1

    def test_unbrauchbarer_zeitpunkt_merkt_nichts(
        self, verbindung:sqlite3.Connection, tmp_path:Path,
    ) -> None:
        _anzeige_schreiben(tmp_path)
        assert stand.abgleich_nach_lauf(
            verbindung, 1, tmp_path, seit = "keine zeit", quelle = "download",
        ) == 0
