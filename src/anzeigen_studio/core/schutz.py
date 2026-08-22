# SPDX-FileCopyrightText: © Anzeigen-Studio contributors
# SPDX-ArtifactOfProjectHomePage: https://github.com/TingelTangelBob/Kleinanzeigen.de-botUI/
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# Zugriffsschutz fuer alle Pfade (AP-1.10).
#
# Bewusst als Middleware mit Positivliste statt als Abhaengigkeit je Endpunkt:
# Wer eine Abhaengigkeit an einem neuen Endpunkt vergisst, oeffnet ihn
# unbemerkt. Hier ist der Standard "geschuetzt", und jede Ausnahme muss
# ausdruecklich eingetragen werden.

from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi.responses import JSONResponse

from anzeigen_studio.api.auth import OEFFENTLICH
from anzeigen_studio.core import auth, db

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from fastapi import FastAPI, Request, Response

    from anzeigen_studio.core.settings import Settings


def register(app: FastAPI, settings: Settings) -> None:
    @app.middleware("http")
    async def schutz(request: Request, weiter: Callable[[Request], Awaitable[Response]]) -> Response:
        pfad = request.url.path

        # Nur /api ist geschuetzt. Die statischen Dateien der Oberflaeche
        # liefert nginx aus und enthalten keine Daten - die Anmeldemaske muss
        # ja erreichbar sein.
        if not pfad.startswith("/api"):
            return await weiter(request)

        if pfad in OEFFENTLICH:
            return await weiter(request)

        # Solange kein Konto eingerichtet ist, waere ein 401 irrefuehrend -
        # die Oberflaeche soll zur Einrichtung fuehren, nicht zur Anmeldung.
        conn = db.connect(settings.database_path)
        try:
            if not auth.gibt_es_benutzer(conn):
                return JSONResponse(
                    {"fehler": {"meldung": "Die Anwendung ist noch nicht eingerichtet."}},
                    status_code = 409,
                )
            benutzer = auth.sitzung_pruefen(conn, request.cookies.get(auth.COOKIE_NAME))
        finally:
            conn.close()

        if benutzer is None:
            return JSONResponse(
                {"fehler": {"meldung": "Nicht angemeldet."}}, status_code = 401,
            )

        request.state.benutzer = benutzer
        return await weiter(request)

    _ = schutz
