# SPDX-FileCopyrightText: © Anzeigen-Studio contributors
# SPDX-ArtifactOfProjectHomePage: https://github.com/TingelTangelBob/Kleinanzeigen.de-botUI/
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# Tests der Nachschlagewerke fuer den Editor (AP-2.7).

from __future__ import annotations

import pytest

from anzeigen_studio.katalog import daten


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
        assert groessen == sorted(groessen, key = {"Klein": 0, "Mittel": 1, "Groß": 2}.get)

    def test_ohne_preisliste_bleibt_die_auswahl(self) -> None:
        """Ist die Plattform nicht erreichbar, gibt es die Liste ohne Preise."""
        pytest.importorskip("kleinanzeigen_bot")
        pakete = daten.versandpakete()
        assert pakete
        assert all(p.preis is None for p in pakete)
