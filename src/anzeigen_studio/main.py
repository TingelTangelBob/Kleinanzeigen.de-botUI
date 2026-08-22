# SPDX-License-Identifier: AGPL-3.0-or-later
#
# ASGI-Einstiegspunkt des Backends.
#
# Stand: Geruest aus AP-0.6. Es gibt bewusst nur den Gesundheitsendpunkt - alles
# Weitere kommt mit den Paketen der Phase 1, damit hier keine leeren Attrappen
# stehen, die Funktion vortaeuschen.

from __future__ import annotations

import logging
from typing import Any

from fastapi import FastAPI
from fastapi.responses import JSONResponse

from anzeigen_studio import __version__
from anzeigen_studio.core.settings import Settings

LOG = logging.getLogger(__name__)


def create_app(settings: Settings | None = None) -> FastAPI:
    """Baut die Anwendung.

    Als Fabrik statt als Modulvariable, damit Tests eine eigene Konfiguration
    einsetzen koennen, ohne Umgebungsvariablen zu veraendern.
    """
    cfg = settings or Settings.from_env()

    app = FastAPI(
        title = "Anzeigen-Studio",
        version = __version__,
        # Die Oberflaeche ist deutsch; die API-Dokumentation bleibt technisch.
        description = "Backend der Weboberflaeche fuer kleinanzeigen-bot.",
    )
    app.state.settings = cfg

    missing = cfg.missing_for_production()
    if missing:
        # Kein harter Abbruch: das Geruest soll sich starten lassen, um die
        # Werkzeugkette zu pruefen. Sobald Zugangsdaten gespeichert werden
        # koennen (AP-1.4), wird daraus ein Startfehler.
        LOG.warning(
            "Nicht gesetzte Umgebungsvariablen: %s. "
            "Fuer den produktiven Betrieb erforderlich.",
            ", ".join(missing),
        )

    @app.get("/api/health")
    def health() -> JSONResponse:
        payload: dict[str, Any] = {
            "status": "ok",
            "version": __version__,
            "dev_mode": cfg.dev_mode,
            # Ehrlich melden, was noch fehlt - nicht stillschweigend "ok" sagen.
            "missing_config": cfg.missing_for_production(),
        }
        return JSONResponse(payload)

    return app


app = create_app()
