# SPDX-FileCopyrightText: © Anzeigen-Studio contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# Read-only Gegenprobe nach dem Plattform-Delete (AP-3.13).

from __future__ import annotations

import email.message
import io
import urllib.error
from typing import TYPE_CHECKING

from scripts.pruefe_kleinanzeigen_loeschung import anbieterliste_pruefen, main, pruefen

if TYPE_CHECKING:
    import pytest

URL = "https://www.kleinanzeigen.de/s-anzeige/test/3310837392"


class Antwort:
    def __init__(self, status: int, text: str, *, url: str = URL) -> None:
        self.status = status
        self._text = text.encode()
        self._url = url

    def __enter__(self) -> Antwort:
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def read(self, limit: int = -1) -> bytes:
        return self._text[:limit] if limit >= 0 else self._text

    def geturl(self) -> str:
        return self._url


def test_http_404_ist_eindeutig_geloescht(monkeypatch: pytest.MonkeyPatch) -> None:
    def _urlopen(*args: object, **kwargs: object) -> None:
        raise urllib.error.HTTPError(
            URL, 404, "nicht gefunden", email.message.Message(), io.BytesIO(),
        )

    monkeypatch.setattr("urllib.request.urlopen", _urlopen)

    ergebnis = pruefen(URL)

    assert ergebnis.status == "geloescht"
    assert ergebnis.rueckgabecode == 0


def test_loeschhinweis_in_einer_200_seite_reicht(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "urllib.request.urlopen",
        lambda *args, **kwargs: Antwort(200, "Diese Anzeige ist nicht mehr verfügbar."),
    )

    ergebnis = pruefen(URL)

    assert ergebnis.status == "geloescht"
    assert ergebnis.rueckgabecode == 0


def test_erreichbare_detailseite_ist_keine_aussage(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Der Kern des Befunds vom 2026-09-04.

    kleinanzeigen.de liefert die Detailseite einer geloeschten Anzeige weiter
    mit HTTP 200 und vollem Inhalt aus. Frueher stand hier "online" - und damit
    ein falscher Alarm nach jedem erfolgreichen Loeschlauf.
    """
    monkeypatch.setattr(
        "urllib.request.urlopen",
        lambda *args, **kwargs: Antwort(200, '<main class="aditem">Preis 10 €</main>'),
    )

    ergebnis = pruefen(URL)

    assert ergebnis.status == "unbekannt"
    assert ergebnis.rueckgabecode == 2
    assert "Anbieterliste" in ergebnis.meldung


def test_captcha_bleibt_unbekannt(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "urllib.request.urlopen",
        lambda *args, **kwargs: Antwort(200, "Bitte bestätige, dass du kein Roboter bist – CAPTCHA"),
    )

    ergebnis = pruefen(URL)

    assert ergebnis.status == "unbekannt"
    assert ergebnis.rueckgabecode == 2


def test_fremde_url_wird_vor_dem_netzwerk_abgewiesen(monkeypatch: pytest.MonkeyPatch) -> None:
    aufruf = False

    def _urlopen(*args: object, **kwargs: object) -> None:
        nonlocal aufruf
        aufruf = True

    monkeypatch.setattr("urllib.request.urlopen", _urlopen)

    ergebnis = pruefen("https://example.org/s-anzeige/test/3310837392")

    assert ergebnis.status == "unbekannt"
    assert ergebnis.rueckgabecode == 2
    assert aufruf is False


def test_cli_gibt_den_pruefstatus_zurueck(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    monkeypatch.setattr(
        "scripts.pruefe_kleinanzeigen_loeschung.pruefen",
        lambda url, *, timeout: type("Ergebnis", (), {
            "status": "geloescht", "meldung": "Test", "rueckgabecode": 0,
        })(),
    )

    assert main(["--url", URL]) == 0
    assert "Ergebnis: gelöscht" in capsys.readouterr().out


# -- Anbieterliste: der belastbare Weg ---------------------------------------

LISTE = (
    '<li data-adid="111"><a href="/s-anzeige/tisch/111">Tisch</a></li>'
    '<li data-adid="222"><a href="/s-anzeige/stuhl/222">Stuhl</a></li>'
)


def _liste(monkeypatch: pytest.MonkeyPatch, inhalt: str) -> None:
    monkeypatch.setattr(
        "urllib.request.urlopen",
        lambda *args, **kwargs: Antwort(200, inhalt, url = "https://www.kleinanzeigen.de/s-bestandsliste.html"),
    )


def test_nummer_fehlt_in_der_liste_heisst_geloescht(monkeypatch: pytest.MonkeyPatch) -> None:
    _liste(monkeypatch, LISTE)

    ergebnis = anbieterliste_pruefen("55557058", "333")

    assert ergebnis.status == "geloescht"
    assert ergebnis.rueckgabecode == 0


def test_nummer_in_der_liste_heisst_online(monkeypatch: pytest.MonkeyPatch) -> None:
    _liste(monkeypatch, LISTE)

    ergebnis = anbieterliste_pruefen("55557058", "222")

    assert ergebnis.status == "online"
    assert ergebnis.rueckgabecode == 1


def test_zweite_seite_verbietet_das_urteil(monkeypatch: pytest.MonkeyPatch) -> None:
    # Die Anzeige koennte auf Seite zwei stehen - "geloescht" waere geraten.
    _liste(monkeypatch, LISTE + '<a rel="next" href="?page=2">Weiter</a>')

    ergebnis = anbieterliste_pruefen("55557058", "333")

    assert ergebnis.status == "unbekannt"
    assert ergebnis.rueckgabecode == 2


def test_liste_ohne_jede_nummer_ist_kein_beleg(monkeypatch: pytest.MonkeyPatch) -> None:
    # Eher ein geaendertes Markup als ein leeres Konto - im Zweifel nachfragen.
    _liste(monkeypatch, "<main>Nichts gefunden</main>")

    ergebnis = anbieterliste_pruefen("55557058", "333")

    assert ergebnis.status == "unbekannt"
    assert ergebnis.rueckgabecode == 2


def test_captcha_in_der_liste_bleibt_unbekannt(monkeypatch: pytest.MonkeyPatch) -> None:
    _liste(monkeypatch, "Bitte bestätige, dass du kein Roboter bist – CAPTCHA")

    ergebnis = anbieterliste_pruefen("55557058", "333")

    assert ergebnis.status == "unbekannt"
    assert ergebnis.rueckgabecode == 2


def test_nichtziffern_kommen_nicht_ins_netz(monkeypatch: pytest.MonkeyPatch) -> None:
    aufruf = False

    def _urlopen(*args: object, **kwargs: object) -> None:
        nonlocal aufruf
        aufruf = True

    monkeypatch.setattr("urllib.request.urlopen", _urlopen)

    ergebnis = anbieterliste_pruefen("55557058; rm -rf /", "333")

    assert ergebnis.status == "unbekannt"
    assert aufruf is False
