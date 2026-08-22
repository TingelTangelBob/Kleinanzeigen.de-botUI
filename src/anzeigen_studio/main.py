# SPDX-FileCopyrightText: © Anzeigen-Studio contributors
# SPDX-ArtifactOfProjectHomePage: https://github.com/TingelTangelBob/Kleinanzeigen.de-botUI/
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# ASGI-Einstiegspunkt des Backends.

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

from fastapi import FastAPI
from fastapi.responses import JSONResponse

from anzeigen_studio import __version__
from anzeigen_studio.api import jobs as jobs_api
from anzeigen_studio.api import profile as profile_api
from anzeigen_studio.core import db, errors
from anzeigen_studio.core.settings import Settings
from anzeigen_studio.jobs import speicher as job_speicher
from anzeigen_studio.jobs.warteschlange import Warteschlange

LOG = logging.getLogger(__name__)


def create_app(settings: Settings | None = None) -> FastAPI:
    """Baut die Anwendung.

    Als Fabrik statt als Modulvariable, damit Tests eine eigene Konfiguration
    einsetzen koennen, ohne Umgebungsvariablen zu veraendern.
    """
    cfg = settings or Settings.from_env()

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        # Migrationen einmal beim Start, mit einer eigenen, sofort wieder
        # geschlossenen Verbindung.
        #
        # Bewusst KEINE dauerhafte Verbindung im App-Zustand: FastAPI fuehrt
        # synchrone Endpunkte in einem Threadpool aus, und SQLite-Verbindungen
        # sind threadgebunden ("SQLite objects created in a thread can only be
        # used in that same thread"). Stattdessen oeffnet jede Anfrage ihre
        # eigene Verbindung - bei einer lokalen Datei kostet das kaum etwas und
        # umgeht das Problem grundsaetzlich, statt es mit check_same_thread und
        # Sperren abzudichten.
        conn = db.connect(cfg.database_path)
        try:
            angewandt = db.migrate(conn)
            if angewandt:
                LOG.info("%d Migration(en) ausgefuehrt", angewandt)
            # Jobs, die beim letzten Beenden noch liefen, koennen es nicht mehr
            # sein - ihr Prozess ist mit dem Backend gestorben. Ehrlich als
            # abgebrochen melden statt einen Zustand anzuzeigen, den es nicht
            # mehr gibt.
            with db.transaction(conn):
                verwaist = job_speicher.verwaiste_aufraeumen(conn)
            if verwaist:
                LOG.warning("%d Lauf/Laeufe als abgebrochen markiert (Neustart)", verwaist)
        finally:
            conn.close()

        _app.state.warteschlange = Warteschlange(cfg)
        try:
            yield
        finally:
            await _app.state.warteschlange.stillegen()

    app = FastAPI(
        title = "Anzeigen-Studio",
        version = __version__,
        description = "Backend der Weboberflaeche fuer kleinanzeigen-bot.",
        lifespan = lifespan,
    )
    app.state.settings = cfg

    errors.register(app)
    app.include_router(profile_api.router)
    app.include_router(jobs_api.router)

    missing = cfg.missing_for_production()
    if missing:
        # Kein harter Abbruch: das Geruest soll sich starten lassen. Sobald
        # Zugangsdaten gespeichert werden koennen (AP-1.4), wird daraus ein
        # Startfehler - eine Anwendung, die Geheimnisse unverschluesselt
        # ablegen wuerde, darf nicht anlaufen.
        LOG.warning(
            "Nicht gesetzte Umgebungsvariablen: %s. Fuer den produktiven Betrieb erforderlich.",
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

    _ = health
    return app


app = create_app()
