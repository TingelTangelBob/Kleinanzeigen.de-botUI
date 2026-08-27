# SPDX-FileCopyrightText: © Anzeigen-Studio contributors
# SPDX-ArtifactOfProjectHomePage: https://github.com/TingelTangelBob/Kleinanzeigen.de-botUI/
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# Laufzeitkonfiguration des Backends. Ausschliesslich aus Umgebungsvariablen -
# die Anwendung soll in einem Container ohne eigene Konfigurationsdatei starten.

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

#: Vorgabe des Datenverzeichnisses. Im Container das Volume, lokal ein Unterordner.
_DEFAULT_DATA_DIR = "/data"

#: Vorgaben des KI-Moduls. Stehen hier und nicht nur in `from_env`, damit
#: Dataclass-Vorgabe und Umgebungslesung nicht auseinanderlaufen koennen.
_DEFAULT_KI_MODELL = "gpt-5.6-luna"
_DEFAULT_KI_BILDKANTE = 768

#: Monatsgrenze fuer KI-Aufrufe in US-Dollar (AP-4.7). Bei rund 0,13 Cent je
#: Entwurf sind 5 Dollar ueber 3800 Entwuerfe - grosszuegig fuer den
#: gedachten Gebrauch und trotzdem eine Grenze, die eine Schleife stoppt,
#: bevor sie in der Abrechnung auffaellt.
_DEFAULT_KI_BUDGET_USD = 5.0


def _env_flag(name: str, *, default: bool = False) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _env_zahl(name: str, vorgabe: int, *, mindestens: int, hoechstens: int) -> int:
    """Ganze Zahl aus der Umgebung, auf einen sinnvollen Bereich begrenzt.

    Ein Tippfehler in einer Umgebungsvariable darf den Start nicht verhindern -
    aber auch keinen unsinnigen Wert durchreichen. Beides waere schlechter als
    die Vorgabe zu nehmen.
    """
    roh = os.environ.get(name)
    if roh is None:
        return vorgabe
    try:
        wert = int(roh.strip())
    except ValueError:
        return vorgabe
    return max(mindestens, min(hoechstens, wert))


def _env_kommazahl(name: str, vorgabe: float) -> float:
    """Kommazahl aus der Umgebung, niemals negativ.

    Eine negative Grenze waere keine Grenze, sondern eine Sperre - und wer
    das will, entfernt den Schluessel.
    """
    roh = os.environ.get(name)
    if roh is None:
        return vorgabe
    try:
        wert = float(roh.strip().replace(",", "."))
    except ValueError:
        return vorgabe
    return max(0.0, wert)


@dataclass(frozen = True, slots = True)
class Settings:
    """Alles, was das Backend zum Starten braucht.

    Bewusst eingefroren: Konfiguration wird beim Start einmal gelesen und danach
    nicht mehr veraendert. Was sich zur Laufzeit aendern koennen soll, gehoert in
    die Datenbank, nicht hierher.
    """

    #: Wurzel aller persistenten Daten. Enthaelt app.db und profiles/.
    data_dir: Path

    #: Schluessel fuer die Verschluesselung der Zugangsdaten (AP-1.4).
    #: Bewusst ohne Vorgabewert - ein fest eingebauter Standardschluessel waere
    #: schlimmer als gar keine Verschluesselung, weil er Sicherheit vortaeuscht.
    secret_key: str | None

    #: Entwicklungsmodus: ausfuehrlichere Fehler, CORS fuer den Vite-Server.
    dev_mode: bool

    #: Pfad zum Chromium im Abbild. Serverseitig gesetzt, nie aus der
    #: Oberflaeche - binary_location startet ein beliebiges Programm (AP-1.11).
    chromium: str

    #: Welches Modell das KI-Entwurfsmodul benutzt (AP-4.1).
    #:
    #: Serverseitig gesetzt, nicht aus der Oberflaeche: Ein Modellname geht in
    #: eine Adresse beim Anbieter ein, und was dort landet, soll nicht aus einem
    #: Formularfeld stammen. Entschieden am 2026-08-27 auf `gpt-5.6-luna` -
    #: bildfaehig, ~0,13 Cent je Anzeige. Begruendung und Preisvergleich in
    #: 00_Agentenordner/04_Serververwaltung/KI-API-Zugaenge.md.
    ki_modell: str = _DEFAULT_KI_MODELL

    #: Obergrenze fuer die Bildkante vor dem Versand an den Anbieter (AP-4.7).
    #: 768 px ergibt vier Kacheln à 140 Token plus 70 Grundtoken = 630 Token je
    #: Bild. Groesser kostet mehr, ohne fuer die Erkennung eines
    #: Verkaufsgegenstands erkennbar mehr zu liefern.
    ki_bildkante: int = _DEFAULT_KI_BILDKANTE

    #: Wie viel je Kalendermonat hoechstens fuer KI-Entwuerfe ausgegeben
    #: werden darf (AP-4.7). Geprueft wird vor dem Aufruf; ueberschritten
    #: werden kann die Grenze nur um den Betrag eines einzelnen Aufrufs,
    #: weil vorher niemand weiss, wie viele Token eine Antwort braucht.
    ki_budget_usd: float = _DEFAULT_KI_BUDGET_USD

    @property
    def database_path(self) -> Path:
        return self.data_dir / "app.db"

    @property
    def profiles_dir(self) -> Path:
        return self.data_dir / "profiles"

    @classmethod
    def from_env(cls) -> Settings:
        return cls(
            data_dir = Path(os.environ.get("ANZEIGEN_STUDIO_DATA_DIR", _DEFAULT_DATA_DIR)),
            secret_key = os.environ.get("ANZEIGEN_STUDIO_SECRET_KEY") or None,
            dev_mode = _env_flag("ANZEIGEN_STUDIO_DEV"),
            chromium = os.environ.get("ANZEIGEN_STUDIO_CHROMIUM", "/usr/bin/chromium"),
            ki_modell = os.environ.get("ANZEIGEN_STUDIO_KI_MODELL", _DEFAULT_KI_MODELL),
            ki_bildkante = _env_zahl(
                "ANZEIGEN_STUDIO_KI_BILDKANTE", _DEFAULT_KI_BILDKANTE,
                mindestens = 256, hoechstens = 2048,
            ),
            ki_budget_usd = _env_kommazahl(
                "ANZEIGEN_STUDIO_KI_BUDGET_USD", _DEFAULT_KI_BUDGET_USD,
            ),
        )

    def missing_for_production(self) -> list[str]:
        """Was fehlt, um die Anwendung produktiv betreiben zu duerfen.

        Wird beim Start gemeldet, statt spaeter beim ersten Speichern von
        Zugangsdaten zu scheitern.
        """
        missing: list[str] = []
        if not self.secret_key:
            missing.append("ANZEIGEN_STUDIO_SECRET_KEY")
        return missing
