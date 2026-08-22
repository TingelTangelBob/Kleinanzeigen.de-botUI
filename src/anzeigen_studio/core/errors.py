# SPDX-FileCopyrightText: © Anzeigen-Studio contributors
# SPDX-ArtifactOfProjectHomePage: https://github.com/TingelTangelBob/Kleinanzeigen.de-botUI/
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# Einheitliches Fehlerformat.
#
# Jeder Fehler kommt in derselben Struktur zurueck, damit die Oberflaeche ihn
# ohne Sonderfaelle anzeigen kann. Die Meldung ist DEUTSCH und fuer Menschen
# gedacht - technische Einzelheiten gehoeren ins Log, nicht in die Antwort an
# den Browser.

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

if TYPE_CHECKING:
    from fastapi import FastAPI, Request

LOG = logging.getLogger(__name__)


class FachlicherFehler(Exception):
    """Ein Fehler, dessen Meldung dem Nutzer gezeigt werden darf.

    Alles andere wird bewusst zu einer allgemeinen Meldung verallgemeinert -
    interne Ausnahmetexte koennen Pfade, Zugangsdaten oder Implementierungs-
    details enthalten und gehoeren nicht in den Browser.
    """

    def __init__(self, meldung: str, *, status: int = 400, feld: str | None = None) -> None:
        super().__init__(meldung)
        self.meldung = meldung
        self.status = status
        self.feld = feld


def _antwort(status: int, meldung: str, feld: str | None = None) -> JSONResponse:
    inhalt: dict[str, Any] = {"fehler": {"meldung": meldung}}
    if feld:
        inhalt["fehler"]["feld"] = feld
    return JSONResponse(inhalt, status_code = status)


def register(app: FastAPI) -> None:
    """Haengt die Fehlerbehandlung in die Anwendung ein."""

    @app.exception_handler(FachlicherFehler)
    async def _fachlich(_request: Request, exc: FachlicherFehler) -> JSONResponse:
        return _antwort(exc.status, exc.meldung, exc.feld)

    @app.exception_handler(RequestValidationError)
    async def _validierung(_request: Request, exc: RequestValidationError) -> JSONResponse:
        # Den ersten Fehler herausgreifen: eine verstaendliche Meldung ist
        # nuetzlicher als eine vollstaendige, unlesbare Liste.
        fehler = exc.errors()
        feld = None
        if fehler:
            pfad = [str(teil) for teil in fehler[0].get("loc", ()) if teil not in ("body", "query")]
            feld = ".".join(pfad) or None
        return _antwort(422, "Die Eingabe ist nicht gültig.", feld)

    @app.exception_handler(Exception)
    async def _unerwartet(request: Request, exc: Exception) -> JSONResponse:
        # Vollstaendig ins Log - mit Stapelspur, aber ueber exc_info statt
        # .exception(), weil wir hier nicht in einem except-Block stehen.
        # Nach aussen bewusst verallgemeinert: interne Ausnahmetexte koennen
        # Pfade oder Zugangsdaten enthalten.
        LOG.error("Unbehandelter Fehler bei %s %s", request.method, request.url.path, exc_info = exc)
        return _antwort(500, "Es ist ein unerwarteter Fehler aufgetreten.")

    # Die Namen werden nicht weiterverwendet; das Registrieren ist der Zweck.
    _ = (_fachlich, _validierung, _unerwartet)
