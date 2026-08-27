# SPDX-FileCopyrightText: © Anzeigen-Studio contributors
# SPDX-ArtifactOfProjectHomePage: https://github.com/TingelTangelBob/Kleinanzeigen.de-botUI/
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# Tests der Nachschlagewerke fuer den Editor (AP-2.7).

from __future__ import annotations

import json
import urllib.request

import pytest

from anzeigen_studio.katalog import daten

#: Vor der autouse-Fixture festgehalten. Sie ersetzt `_preise` fuer alle
#: uebrigen Tests - hier wird aber genau diese Funktion geprueft.
_ECHTES_PREISE = daten._preise  # noqa: SLF001 - Absicht, siehe oben


@pytest.fixture(autouse = True)
def _ohne_netz(monkeypatch:pytest.MonkeyPatch) -> None:
    """Kein Test greift auf die Plattform zu.

    Die Preisliste ist eine Bequemlichkeit, keine Voraussetzung - genau das
    soll hier auch geprueft werden.
    """
    monkeypatch.setattr(daten, "_preise", lambda: {})


class TestKategorien:

    def test_liste_ist_gefuellt(self) -> None:
        pytest.importorskip("kleinanzeigen_bot")
        alle = daten.kategorien()
        assert len(alle) > 100

    def test_eintraege_haben_pfad_und_nummer(self) -> None:
        pytest.importorskip("kleinanzeigen_bot")
        alle = daten.kategorien()
        treffer = [k for k in alle if k.wert == "161/278"]
        assert treffer, "Notebooks sollten in der Liste stehen"
        assert treffer[0].name == "Elektronik > Notebooks"

    def test_name_zu_bekanntem_wert(self) -> None:
        pytest.importorskip("kleinanzeigen_bot")
        assert daten.kategorie_name("161/278") == "Elektronik > Notebooks"

    def test_unbekannter_wert_gibt_none(self) -> None:
        """Kein Fehler, sondern ein normaler Fall.

        Heruntergeladene Anzeigen tragen mitunter Werte, die
        `categories.yaml` nicht kennt - beobachtet an `161/278/laptop`,
        während die Liste nur `161/278` führt. Die Oberfläche muss so einen
        Wert zeigen können, ohne ihn stillschweigend zu ersetzen.
        """
        pytest.importorskip("kleinanzeigen_bot")
        assert daten.kategorie_name("161/278/gibt-es-nicht") is None
        assert daten.kategorie_name(None) is None


class TestVersandpakete:

    def test_alle_neun_pakete(self) -> None:
        pytest.importorskip("kleinanzeigen_bot")
        pakete = daten.versandpakete()
        assert len(pakete) == 9
        assert {p.wert for p in pakete} >= {"Hermes_Päckchen", "DHL_2", "Hermes_L"}

    def test_nach_groesse_sortiert(self) -> None:
        pytest.importorskip("kleinanzeigen_bot")
        groessen = [p.groesse for p in daten.versandpakete()]
        # Eigene Rangfolge statt `dict.get` als Schluessel: `.get` liefert fuer
        # eine unbekannte Groesse None, und None laesst sich nicht sortieren -
        # der Test waere dann nicht falsch, sondern kaputt.
        rang = {"Klein": 0, "Mittel": 1, "Groß": 2}
        assert groessen == sorted(groessen, key = lambda g: rang.get(g, 99))

    def test_ohne_preisliste_bleibt_die_auswahl(self) -> None:
        """Ist die Plattform nicht erreichbar, gibt es die Liste ohne Preise."""
        pytest.importorskip("kleinanzeigen_bot")
        pakete = daten.versandpakete()
        assert pakete
        assert all(p.preis is None for p in pakete)


class _Antwort:
    """Minimaler Ersatz fuer das Ergebnis von `urlopen`."""

    def __init__(self, rohtext:str) -> None:
        self._roh = rohtext.encode("utf-8")

    def read(self) -> bytes:
        return self._roh

    def __enter__(self) -> _Antwort:
        return self

    def __exit__(self, *_:object) -> None:
        return


class TestPreisAbruf:
    """Eine beschaedigte Antwort darf die Auswahl nicht mitreissen.

    Der Modulkopf von `daten.py` sagt zu: schlaegt der Abruf fehl, gibt es die
    Liste ohne Preise statt gar keine. Eine Ausnahme aus dem Auswerten wuerde
    daraus einen 500 machen - und die Oberflaeche zeigt dann eine leere
    Paketliste, also das Gegenteil der Zusage.
    """

    @pytest.fixture(autouse = True)
    def _leerer_zwischenspeicher(self, monkeypatch:pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(daten, "_preise_zwischenspeicher", None)

    def _antworten_mit(self, monkeypatch:pytest.MonkeyPatch, rohtext:str) -> list[int]:
        aufrufe:list[int] = []

        def _urlopen(*_args:object, **_kwargs:object) -> _Antwort:
            aufrufe.append(1)
            return _Antwort(rohtext)

        # Direkt an urllib.request, nicht ueber `daten.urllib`: dasselbe
        # Modulobjekt, aber ohne den Umweg ueber ein Attribut, das `daten`
        # nicht ausdruecklich weiterreicht.
        monkeypatch.setattr(urllib.request, "urlopen", _urlopen)
        return aufrufe

    def test_gesunde_antwort_wird_gelesen(self, monkeypatch:pytest.MonkeyPatch) -> None:
        self._antworten_mit(monkeypatch, json.dumps({"data": {"shippingOptionsResponse": {"options": [
            {"id": "DHL_001", "priceInEuroCent": 549},
            {"id": "HERMES_002", "priceInEuroCent": 439},
        ]}}}))
        assert _ECHTES_PREISE() == {"DHL_001": 5.49, "HERMES_002": 4.39}

    @pytest.mark.parametrize("optionen", [
        '["DHL_001", "HERMES_002"]',   # Liste aus Zeichenketten statt Objekten
        '{"DHL_001": 549}',            # Objekt statt Liste
        "[1, 2, 3]",
        "null",
        '[{"priceInEuroCent": 549}]',  # Eintrag ohne id
    ])
    def test_beschaedigte_antwort_gibt_leere_preise(
        self, monkeypatch:pytest.MonkeyPatch, optionen:str,
    ) -> None:
        self._antworten_mit(
            monkeypatch,
            f'{{"data": {{"shippingOptionsResponse": {{"options": {optionen}}}}}}}',
        )
        assert _ECHTES_PREISE() == {}

    def test_ein_kaputter_eintrag_kostet_nicht_die_ganze_liste(
        self, monkeypatch:pytest.MonkeyPatch,
    ) -> None:
        self._antworten_mit(monkeypatch, json.dumps({"data": {"shippingOptionsResponse": {"options": [
            {"id": "DHL_001", "priceInEuroCent": 549},
            "muell",
            None,
        ]}}}))
        assert _ECHTES_PREISE() == {"DHL_001": 5.49}

    def test_fehlschlag_wird_gemerkt(self, monkeypatch:pytest.MonkeyPatch) -> None:
        """Sonst zahlt jede Anfrage erneut die volle Frist von vier Sekunden."""
        aufrufe = self._antworten_mit(monkeypatch, "kein json")

        assert _ECHTES_PREISE() == {}
        assert _ECHTES_PREISE() == {}

        assert len(aufrufe) == 1, "der zweite Aufruf hätte aus dem Zwischenspeicher kommen müssen"


class TestGroessengruppen:
    """Kleinanzeigen laesst nur Pakete einer Groesse zu.

    Der Upstream setzt die Regel erst im Veroeffentlichen-Formular durch
    (`publishing_form.py`), und zwar mit einem Abbruch im bereits geoeffneten
    Versanddialog. Weder `AdPartial` noch `Ad` pruefen sie.
    """

    def test_eine_groesse_ist_in_ordnung(self) -> None:
        pytest.importorskip("kleinanzeigen_bot")
        assert daten.gemischte_versandgroessen(["Hermes_Päckchen", "Hermes_S", "DHL_2"]) is False

    def test_zwei_groessen_werden_erkannt(self) -> None:
        pytest.importorskip("kleinanzeigen_bot")
        assert daten.gemischte_versandgroessen(["Hermes_Päckchen", "Hermes_L"]) is True

    def test_leere_und_einzelne_auswahl(self) -> None:
        pytest.importorskip("kleinanzeigen_bot")
        assert daten.gemischte_versandgroessen([]) is False
        assert daten.gemischte_versandgroessen(["DHL_10"]) is False

    def test_unbekannte_namen_schlagen_nicht_an(self) -> None:
        """Ein falscher Alarm waere schlimmer als ein fehlender.

        Heruntergeladene Anzeigen koennen Namen tragen, die der Katalog nicht
        kennt. Ueber deren Groesse laesst sich nichts sagen.
        """
        pytest.importorskip("kleinanzeigen_bot")
        assert daten.gemischte_versandgroessen(["Hermes_L", "Gibt_Es_Nicht"]) is False

    def test_jedes_bekannte_paket_hat_eine_groesse(self) -> None:
        pytest.importorskip("kleinanzeigen_bot")
        tabelle = daten.groesse_je_paket()
        assert len(tabelle) == 9
        assert set(tabelle.values()) == {"Klein", "Mittel", "Groß"}
