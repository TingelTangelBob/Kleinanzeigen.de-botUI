# SPDX-FileCopyrightText: © Anzeigen-Studio contributors
# SPDX-ArtifactOfProjectHomePage: https://github.com/TingelTangelBob/Kleinanzeigen.de-botUI/
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# Erzeugt die config.yaml eines Profils (AP-1.5, zusammen mit AP-1.11).
#
# Zwei Regeln bestimmen diese Datei:
#
# 1. Zugangsdaten stehen NIE im Klartext darin - nur die Platzhalter, die der
#    Bot aus der Umgebung ersetzt.
# 2. Die vier Felder browser.binary_location, browser.extensions,
#    browser.arguments und ad_files sind serverseitig festgelegt und werden aus
#    nutzergelieferten Daten VERWORFEN. Zusammengenommen sind sie ein
#    vollwertiger Codeausfuehrungspfad: die ersten drei starten beliebige
#    Programme, Erweiterungen und Chromium-Schalter, das vierte hat im Upstream
#    keinen Traversal-Schutz.
#
# Die Reihenfolge ist der ganze Punkt: die feste Basis wird UEBER die
# nutzereditierbare Konfiguration gelegt, nicht umgekehrt.

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Final

from ruamel.yaml import YAML

from anzeigen_studio.core.zugang import PLATZHALTER_BENUTZER, PLATZHALTER_PASSWORT

if TYPE_CHECKING:
    from pathlib import Path

#: Felder, die der Nutzer niemals setzen darf. Siehe Kopfkommentar.
GESPERRTE_FELDER: Final[frozenset[str]] = frozenset({
    "browser.binary_location",
    "browser.extensions",
    "browser.arguments",
    "ad_files",
})


def _basis(anzeigen_glob: str, chromium: str) -> dict[str, Any]:
    """Serverseitig festgelegter Teil. Nicht ueberschreibbar."""
    return {
        # Fest auf das Anzeigenverzeichnis des Profils begrenzt. Kein
        # nutzergeliefertes Glob-Muster, damit kein `..` den Profilordner
        # verlassen kann.
        "ad_files": [anzeigen_glob],
        "login": {
            "username": PLATZHALTER_BENUTZER,
            "password": PLATZHALTER_PASSWORT,
        },
        "browser": {
            # Chromium kommt aus dem Container-Abbild, nicht aus der
            # Konfiguration. Erweiterungen und freie Schalter sind ausgeschlossen.
            "binary_location": chromium,
            "arguments": [
                # Im Container ohne eigenen Kernel-Namensraum unvermeidbar.
                "--no-sandbox",
                # Ohne dies stuerzt Chromium bei knappem /dev/shm reproduzierbar
                # ab - der haeufigste Containerfehler ueberhaupt.
                "--disable-dev-shm-usage",
                "--disable-gpu",
            ],
            "extensions": [],
            "use_private_window": False,
        },
        # Bot-eigene Aktualisierungspruefung aus: Aktualisierungen laufen ueber
        # das Container-Abbild, nicht zur Laufzeit.
        "update_check": {"enabled": False},
    }


def zusammenfuehren(nutzer: dict[str, Any], basis: dict[str, Any]) -> dict[str, Any]:
    """Legt die Basis ueber die Nutzerkonfiguration.

    Rekursiv, damit z. B. `browser.use_private_window` gesetzt werden kann,
    ohne dass der Nutzer die gesperrten Geschwisterfelder mitliefert.
    """
    ergebnis = dict(nutzer)
    for schluessel, wert in basis.items():
        if isinstance(wert, dict) and isinstance(ergebnis.get(schluessel), dict):
            ergebnis[schluessel] = zusammenfuehren(ergebnis[schluessel], wert)
        else:
            ergebnis[schluessel] = wert
    return ergebnis


def gesperrte_entfernen(nutzer: dict[str, Any]) -> list[str]:
    """Entfernt gesperrte Felder aus einer Nutzerkonfiguration.

    Gibt zurueck, was entfernt wurde - der Aufrufer soll das protokollieren
    koennen. Verworfen wird, nicht nur ignoriert: was nicht in der Datei
    landet, kann auch nicht durch einen spaeteren Fehler wirksam werden.
    """
    entfernt: list[str] = []
    for pfad in sorted(GESPERRTE_FELDER):
        teile = pfad.split(".")
        knoten: Any = nutzer
        for teil in teile[:-1]:
            if not isinstance(knoten, dict) or teil not in knoten:
                knoten = None
                break
            knoten = knoten[teil]
        if isinstance(knoten, dict) and teile[-1] in knoten:
            del knoten[teile[-1]]
            entfernt.append(pfad)
    return entfernt


def schreiben(ziel: Path, nutzer: dict[str, Any], *, anzeigen_glob: str,
              chromium: str = "/usr/bin/chromium") -> list[str]:
    """Schreibt die config.yaml. Gibt die verworfenen Felder zurueck."""
    entwurf = dict(nutzer)
    entfernt = gesperrte_entfernen(entwurf)
    vollstaendig = zusammenfuehren(entwurf, _basis(anzeigen_glob, chromium))

    ziel.parent.mkdir(parents = True, exist_ok = True)
    yaml = YAML()
    yaml.default_flow_style = False
    with ziel.open("w", encoding = "utf-8") as datei:
        datei.write(
            "# Von Anzeigen-Studio erzeugt. Aenderungen von Hand werden beim\n"
            "# naechsten Lauf ueberschrieben.\n"
            "#\n"
            "# Zugangsdaten stehen hier bewusst nur als Platzhalter - der Bot\n"
            "# ersetzt sie zur Laufzeit aus der Umgebung.\n",
        )
        yaml.dump(vollstaendig, datei)
    return entfernt
