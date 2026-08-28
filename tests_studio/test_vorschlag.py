# SPDX-FileCopyrightText: © Anzeigen-Studio contributors
# SPDX-ArtifactOfProjectHomePage: https://github.com/TingelTangelBob/Kleinanzeigen.de-botUI/
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# Tests des Kategorie- und Versandvorschlags (AP-4.5).

from __future__ import annotations

from anzeigen_studio.ai import entwurf as entwurf_dienst
from anzeigen_studio.ai import vorschlag
from anzeigen_studio.katalog import daten as katalog


def test_klartext_wird_zu_einem_pfad_der_wirklich_existiert() -> None:
    """Der Kern von AP-4.5: geraten wird nicht, abgeglichen schon."""
    treffer = vorschlag.kategorie_treffer("Elektronik > Weitere Elektronik")

    assert treffer, "kein Treffer für eine Kategorie, die es gibt"
    bekannt = {k.wert for k in katalog.kategorien()}
    assert all(t.wert in bekannt for t in treffer)


def test_der_beste_treffer_steht_vorn() -> None:
    """Der Katalog nennt 161/168 schlicht "Elektronik" - und genau die trägt
    die echte Dimmer-Anzeige, an der dieses Projekt seinen Rundlauf geprüft
    hat. Ein Vorschlag "Elektronik > Weitere Elektronik" muss also dort landen
    und nicht bei einer der 30 Unterkategorien."""
    treffer = vorschlag.kategorie_treffer("Elektronik > Weitere Elektronik")
    assert treffer[0].wert == "161/168"


def test_unsinn_ergibt_keinen_vorschlag() -> None:
    """Ein schwacher Vorschlag ist schlechter als keiner - er verleitet zum Klicken."""
    assert vorschlag.kategorie_treffer("Xyzzy Plughbert Frobnitz") == []


def test_leerer_vorschlag_ist_kein_fehler() -> None:
    assert vorschlag.kategorie_treffer(None) == []
    assert vorschlag.kategorie_treffer("   ") == []


def test_hoechstens_drei_vorschlaege() -> None:
    treffer = vorschlag.kategorie_treffer("Elektronik")
    assert len(treffer) <= vorschlag.MAX_KATEGORIEN


def test_umlaute_stehen_der_erkennung_nicht_im_weg() -> None:
    mit = vorschlag.kategorie_treffer("Zubehör für Büro")
    ohne = vorschlag.kategorie_treffer("Zubehoer fuer Buero")
    assert [t.wert for t in mit] == [t.wert for t in ohne]


def test_versandvorschlaege_haben_alle_dieselbe_groesse() -> None:
    """Gemischte Größen lässt Kleinanzeigen nicht zu - der Lauf bräche sonst ab."""
    for groesse in ("klein", "mittel", "gross"):
        treffer = vorschlag.versand_treffer(groesse)
        assert treffer, f"keine Pakete für {groesse}"
        assert len({v.groesse for v in treffer}) == 1


def test_guenstigstes_paket_steht_vorn() -> None:
    treffer = vorschlag.versand_treffer("klein")
    preise = [v.preis for v in treffer if v.preis is not None]
    assert preise == sorted(preise)


def test_sperrgut_bekommt_keinen_versandvorschlag() -> None:
    """Was nicht in ein Paket passt, wird abgeholt. Das ist eine Entscheidung."""
    assert vorschlag.versand_treffer("sperrgut") == []


def test_unbekannte_groesse_ergibt_keinen_vorschlag() -> None:
    assert vorschlag.versand_treffer(None) == []
    assert vorschlag.versand_treffer("riesig") == []


def test_die_groessenliste_stimmt_mit_dem_schema_ueberein() -> None:
    """Zwei Listen an zwei Orten laufen sonst auseinander, ohne dass es auffällt."""
    schema_groessen = entwurf_dienst.schema()["properties"]["versandgroesse"]["enum"]
    assert [g for g in schema_groessen if g is not None] == list(vorschlag.GROESSEN)
