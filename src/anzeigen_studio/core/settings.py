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


def _env_flag(name: str, *, default: bool = False) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


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
