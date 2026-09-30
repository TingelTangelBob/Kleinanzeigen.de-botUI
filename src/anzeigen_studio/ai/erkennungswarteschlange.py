# SPDX-FileCopyrightText: © Anzeigen-Studio contributors
# SPDX-ArtifactOfProjectHomePage: https://github.com/TingelTangelBob/Kleinanzeigen.de-botUI/
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# Persistente Warteschlange fuer KI-Erkennungen.
# Neue Datei, Anzeigen-Studio, 2026-09-13.
#
# Eine Analyse ist kein Browser-Lauf: Sie braucht weder das Kleinanzeigen-Konto
# noch den Profil-Browser. Deshalb hat sie eine eigene kleine Warteschlange und
# darf parallel zu einer weiteren Bildanalyse laufen. In der Datenbank bleibt
# nur der Entwurf und der Verbrauch; die Originalbilder liegen bis zum lokalen
# Speichern unter dem temporaeren Profilpfad.

from __future__ import annotations

import asyncio
import json
import logging
import shutil
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

from anzeigen_studio.ai import entwurf_lauf
from anzeigen_studio.core import db
from anzeigen_studio.core.errors import FachlicherFehler

if TYPE_CHECKING:
    import sqlite3

    from anzeigen_studio.core.settings import Settings

LOG = logging.getLogger(__name__)

OFFENE_ZUSTAENDE = frozenset({"wartet", "laeuft", "speichert"})
LISTEN_ZUSTAENDE = frozenset({"wartet", "laeuft", "pruefen", "gescheitert", "abgebrochen"})


@dataclass(frozen = True, slots = True)
class Erkennung:
    """Ein KI-Lauf ohne Zugangsdaten oder Bildinhalt in der Antwort."""

    id: int
    profil_slug: str
    zustand: str
    eingereicht_am: str
    gestartet_am: str | None
    beendet_am: str | None
    bilder: int
    entwurf: dict[str, Any] | None
    kosten: dict[str, Any] | None
    meldung: str | None


def _jetzt() -> str:
    return datetime.now(UTC).isoformat(timespec = "seconds")


def _json_objekt(roh: str | None) -> dict[str, Any] | None:
    if not roh:
        return None
    try:
        wert = json.loads(roh)
    except (TypeError, ValueError):
        return None
    return wert if isinstance(wert, dict) else None


def _aus_zeile(zeile: sqlite3.Row) -> Erkennung:
    return Erkennung(
        id = int(zeile["id"]),
        profil_slug = str(zeile["profil_slug"]),
        zustand = str(zeile["zustand"]),
        eingereicht_am = str(zeile["eingereicht_am"]),
        gestartet_am = zeile["gestartet_am"],
        beendet_am = zeile["beendet_am"],
        bilder = int(zeile["bilder_anzahl"]),
        entwurf = _json_objekt(zeile["entwurf"]),
        kosten = _json_objekt(zeile["kosten"]),
        meldung = zeile["meldung"],
    )


def _bilderpfad(profil_wurzel: Path, relativ: str) -> Path:
    """Loest den internen Bildpfad auf und verhindert einen Pfadausbruch."""
    wurzel = profil_wurzel.resolve()
    pfad = (profil_wurzel / relativ).resolve()
    if not pfad.is_relative_to(wurzel):
        raise FachlicherFehler("Ungültiger Speicherort der Erkennung.", status = 500)
    return pfad


def _zeile(conn: sqlite3.Connection, erkennung_id: int, profil_slug: str | None = None) -> sqlite3.Row:
    sql = (
        "SELECT e.*, p.slug AS profil_slug "
        "FROM ki_entwurf_lauf e JOIN profil p ON p.id = e.profil_id "
        "WHERE e.id = ?"
    )
    parameter: list[Any] = [erkennung_id]
    if profil_slug is not None:
        sql += " AND p.slug = ?"
        parameter.append(profil_slug)
    gefunden = conn.execute(sql, parameter).fetchone()
    if gefunden is None:
        raise FachlicherFehler("KI-Entwurf nicht gefunden.", status = 404)
    return cast("sqlite3.Row", gefunden)


def liste(conn: sqlite3.Connection, profil_slug: str, *, limit: int = 30) -> list[Erkennung]:
    """Offene, pruefbare und fehlgeschlagene Entwuerfe eines Profils."""
    zeilen = conn.execute(
        "SELECT e.*, p.slug AS profil_slug "
        "FROM ki_entwurf_lauf e JOIN profil p ON p.id = e.profil_id "
        "WHERE p.slug = ? AND e.zustand IN ('wartet', 'laeuft', 'pruefen', 'gescheitert', 'abgebrochen') "
        "ORDER BY e.id DESC LIMIT ?",
        (profil_slug, limit),
    )
    return [_aus_zeile(zeile) for zeile in zeilen]


def einzeln(conn: sqlite3.Connection, erkennung_id: int, profil_slug: str) -> Erkennung:
    """Liest einen Entwurf nur innerhalb des aktiven Profils."""
    return _aus_zeile(_zeile(conn, erkennung_id, profil_slug))


def _status_setzen(
    conn: sqlite3.Connection,
    erkennung_id: int,
    zustand: str,
    *,
    gestartet_am: str | None = None,
    beendet_am: str | None = None,
    entwurf: dict[str, Any] | None = None,
    kosten: dict[str, Any] | None = None,
    meldung: str | None = None,
) -> None:
    """Schreibt einen Zustandswechsel in einem kurzen SQLite-Abschnitt."""
    with db.transaction(conn):
        conn.execute(
            "UPDATE ki_entwurf_lauf SET zustand = ?, gestartet_am = COALESCE(?, gestartet_am), "
            "beendet_am = ?, entwurf = ?, kosten = ?, meldung = ? WHERE id = ?",
            (
                zustand,
                gestartet_am,
                beendet_am,
                None if entwurf is None else json.dumps(entwurf, ensure_ascii = False),
                None if kosten is None else json.dumps(kosten, ensure_ascii = False),
                meldung,
                erkennung_id,
            ),
        )


def verwaiste_aufraeumen(conn: sqlite3.Connection) -> int:
    """Markiert beim Backend-Neustart nicht weiterlaufende Erkennungen."""
    jetzt = _jetzt()
    with db.transaction(conn):
        cursor = conn.execute(
            "UPDATE ki_entwurf_lauf SET zustand = 'abgebrochen', beendet_am = ?, "
            "meldung = 'Das Backend wurde neu gestartet. Bitte erneut erkennen lassen.' "
            "WHERE zustand IN ('wartet', 'laeuft', 'speichert')",
            (jetzt,),
        )
    return cursor.rowcount


class ErkennungsWarteschlange:
    """Fuehrt KI-Erkennungen unabhaengig vom Bot-Lauf aus."""

    def __init__(self, cfg: Settings, *, parallel: int = 2) -> None:
        self._cfg = cfg
        self._semaphore = asyncio.Semaphore(max(1, parallel))
        self._aufgaben: dict[int, asyncio.Task[None]] = {}

    async def einreihen(
        self,
        conn: sqlite3.Connection,
        *,
        profil_id: int,
        profil_slug: str,
        profil_wurzel: Path,
        inhalte: list[bytes],
    ) -> Erkennung:
        """Legt Bilder ab, schreibt den Lauf und startet ihn im Hintergrund."""
        eingereicht = _jetzt()
        with db.transaction(conn):
            cursor = conn.execute(
                "INSERT INTO ki_entwurf_lauf "
                "(profil_id, bilder_pfad, bilder_anzahl, zustand, eingereicht_am) "
                "VALUES (?, '', ?, 'wartet', ?)",
                (profil_id, len(inhalte), eingereicht),
            )
            erkennung_id = int(cursor.lastrowid or 0)

        relativ = Path(".temp") / "ki-erkennungen" / str(erkennung_id)
        ziel = _bilderpfad(profil_wurzel, relativ.as_posix())
        try:
            ziel.mkdir(parents = True, exist_ok = False)
            for nummer, inhalt in enumerate(inhalte, start = 1):
                (ziel / f"bild-{nummer}.bin").write_bytes(inhalt)
            with db.transaction(conn):
                conn.execute(
                    "UPDATE ki_entwurf_lauf SET bilder_pfad = ? WHERE id = ?",
                    (relativ.as_posix(), erkennung_id),
                )
        except BaseException:
            if ziel.exists():
                shutil.rmtree(ziel)
            with db.transaction(conn):
                conn.execute("DELETE FROM ki_entwurf_lauf WHERE id = ?", (erkennung_id,))
            raise

        aufgabe = asyncio.create_task(
            self._arbeiten(erkennung_id, profil_slug, profil_wurzel, relativ.as_posix()),
        )
        self._aufgaben[erkennung_id] = aufgabe
        aufgabe.add_done_callback(lambda _aufgabe: self._aufgaben.pop(erkennung_id, None))
        return einzeln(conn, erkennung_id, profil_slug)

    async def _arbeiten(
        self, erkennung_id: int, profil_slug: str, profil_wurzel: Path, bild_relativ: str,
    ) -> None:
        async with self._semaphore:
            conn = db.connect(self._cfg.database_path)
            try:
                zeile = _zeile(conn, erkennung_id, profil_slug)
                if zeile["zustand"] != "wartet":
                    return
                _status_setzen(conn, erkennung_id, "laeuft", gestartet_am = _jetzt())
                inhalte = [
                    pfad.read_bytes()
                    for pfad in sorted(_bilderpfad(profil_wurzel, bild_relativ).glob("bild-*.bin"))
                ]
                ergebnis = await entwurf_lauf.erzeugen(
                    conn,
                    self._cfg,
                    profil_slug = profil_slug,
                    profil_wurzel = profil_wurzel,
                    inhalte = inhalte,
                )
                _status_setzen(
                    conn,
                    erkennung_id,
                    "pruefen",
                    beendet_am = _jetzt(),
                    entwurf = entwurf_lauf.entwurf_zu_dict(ergebnis.entwurf),
                    kosten = entwurf_lauf.kosten_zu_dict(ergebnis.kosten),
                )
                LOG.info("KI-Erkennung %d fuer Profil %s zur Prüfung bereit", erkennung_id, profil_slug)
            except asyncio.CancelledError:
                raise
            except FachlicherFehler as fehler:
                _status_setzen(
                    conn, erkennung_id, "gescheitert", beendet_am = _jetzt(), meldung = fehler.meldung,
                )
                LOG.warning("KI-Erkennung %d gescheitert: %s", erkennung_id, fehler.meldung)
            except Exception:  # noqa: BLE001 - Antwort fuer den Browser bleibt absichtlich allgemein
                _status_setzen(
                    conn,
                    erkennung_id,
                    "gescheitert",
                    beendet_am = _jetzt(),
                    meldung = "Die KI-Erkennung ist unerwartet gescheitert. Bitte erneut versuchen.",
                )
                LOG.exception("KI-Erkennung %d unerwartet gescheitert", erkennung_id)
            finally:
                conn.close()

    def fuer_anlegen(self, conn: sqlite3.Connection, erkennung_id: int, profil_slug: str) -> Erkennung:
        """Reserviert einen fertigen Entwurf gegen doppeltes lokales Anlegen."""
        with db.transaction(conn):
            zeile = _zeile(conn, erkennung_id, profil_slug)
            if zeile["zustand"] != "pruefen":
                raise FachlicherFehler(
                    "Dieser Entwurf ist noch nicht zur Prüfung bereit.", status = 409,
                )
            geaendert = conn.execute(
                "UPDATE ki_entwurf_lauf SET zustand = 'speichert' "
                "WHERE id = ? AND zustand = 'pruefen'",
                (erkennung_id,),
            ).rowcount
            if geaendert != 1:
                raise FachlicherFehler("Dieser Entwurf wird bereits gespeichert.", status = 409)
        return _aus_zeile(_zeile(conn, erkennung_id, profil_slug))

    def bilder_fuer_anlegen(
        self, conn: sqlite3.Connection, erkennung_id: int, profil_slug: str, profil_wurzel: Path,
    ) -> list[bytes]:
        """Liest die Originalbilder eines reservierten Entwurfs."""
        zeile = _zeile(conn, erkennung_id, profil_slug)
        if zeile["zustand"] != "speichert":
            raise FachlicherFehler("Dieser Entwurf ist nicht zum Speichern reserviert.", status = 409)
        relativ = str(zeile["bilder_pfad"])
        if not relativ:
            raise FachlicherFehler("Zu diesem Entwurf fehlen die Bilder.", status = 500)
        bilder = [
            pfad.read_bytes()
            for pfad in sorted(_bilderpfad(profil_wurzel, relativ).glob("bild-*.bin"))
        ]
        if not bilder:
            raise FachlicherFehler("Zu diesem Entwurf fehlen die Bilder.", status = 500)
        return bilder

    def speichern_abgeschlossen(
        self, conn: sqlite3.Connection, erkennung_id: int, profil_slug: str, profil_wurzel: Path,
    ) -> None:
        """Markiert den Entwurf als erledigt und entfernt die Originalbilder."""
        zeile = _zeile(conn, erkennung_id, profil_slug)
        with db.transaction(conn):
            conn.execute(
                "UPDATE ki_entwurf_lauf SET zustand = 'gespeichert', beendet_am = ? WHERE id = ?",
                (_jetzt(), erkennung_id),
            )
        relativ = str(zeile["bilder_pfad"])
        if relativ:
            ziel = _bilderpfad(profil_wurzel, relativ)
            if ziel.exists():
                shutil.rmtree(ziel)

    def speichern_zuruecksetzen(self, conn: sqlite3.Connection, erkennung_id: int) -> None:
        """Gibt einen fehlgeschlagenen lokalen Speicherversuch wieder frei."""
        with db.transaction(conn):
            conn.execute(
                "UPDATE ki_entwurf_lauf SET zustand = 'pruefen', meldung = NULL "
                "WHERE id = ? AND zustand = 'speichert'",
                (erkennung_id,),
            )

    async def stillegen(self) -> None:
        """Bricht nur noch laufende KI-Aufgaben beim Backend-Stopp ab."""
        aufgaben = list(self._aufgaben.values())
        for aufgabe in aufgaben:
            aufgabe.cancel()
        if aufgaben:
            await asyncio.gather(*aufgaben, return_exceptions = True)
