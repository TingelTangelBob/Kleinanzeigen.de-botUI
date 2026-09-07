# SPDX-FileCopyrightText: © Anzeigen-Studio contributors
# SPDX-ArtifactOfProjectHomePage: https://github.com/TingelTangelBob/Kleinanzeigen.de-botUI/
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# Verschluesselter eBay-Credential-Store (AP-E-02).
#
# Muster wie core/zugang.py: Geheimnisse nur verschluesselt in die Datenbank,
# Klartext ausschliesslich fuer spaetere OAuth-/API-Aufrufe (AP-E-03/04).
# Statusantworten enthalten niemals Tokens oder Secrets.
#
# Sandbox und Produktion sind getrennte Zeilen (UNIQUE profil_id + umgebung).
# Fehlender oder falscher ANZEIGEN_STUDIO_SECRET_KEY blockiert Speichern/Lesen;
# Klartext ist keine Rueckfalloption.

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING, Final, Sequence

from anzeigen_studio.core.crypto import tresor_oder_fehler
from anzeigen_studio.core.db import transaction
from anzeigen_studio.core.errors import FachlicherFehler
from anzeigen_studio.marketplaces.ebay.models import (
    SCHEMA_VERSION,
    EbayGeheimnisse,
    EbayUmgebung,
    EbayVerbindung,
    EbayZugangStatus,
)

if TYPE_CHECKING:
    import sqlite3

#: Platzhalter: ``None`` als Argument bedeutet „bestehenden Wert behalten“.
_BEHALTEN: Final[object] = object()


def _jetzt() -> str:
    return datetime.now(UTC).isoformat(timespec = "seconds")


def _umgebung(wert: EbayUmgebung | str) -> EbayUmgebung:
    try:
        return wert if isinstance(wert, EbayUmgebung) else EbayUmgebung(wert)
    except ValueError as fehler:
        raise FachlicherFehler(
            "Unbekannte eBay-Umgebung. Erlaubt sind „sandbox“ und „production“.",
            feld = "umgebung",
        ) from fehler


def _scopes_als_tuple(roh: str | None) -> tuple[str, ...]:
    if not roh:
        return ()
    return tuple(teil for teil in roh.split(" ") if teil)


def _scopes_als_text(scopes: Sequence[str] | None) -> str:
    if not scopes:
        return ""
    bereinigt = [teil.strip() for teil in scopes if teil and teil.strip()]
    # Reihenfolge erhalten, Duplikate streichen.
    gesehen: set[str] = set()
    einzig: list[str] = []
    for teil in bereinigt:
        if teil not in gesehen:
            gesehen.add(teil)
            einzig.append(teil)
    return " ".join(einzig)


def _zeile_zu_status(row: sqlite3.Row) -> EbayZugangStatus:
    return EbayZugangStatus(
        profil_id = int(row["profil_id"]),
        umgebung = EbayUmgebung(row["umgebung"]),
        verbindung = EbayVerbindung(row["verbindung"]),
        konto_id = row["konto_id"],
        app_id = row["app_id"],
        scopes = _scopes_als_tuple(row["scopes"]),
        schema_version = int(row["schema_version"]),
        access_token_hinterlegt = row["access_token_chiffre"] is not None,
        refresh_token_hinterlegt = row["refresh_token_chiffre"] is not None,
        app_secret_hinterlegt = row["app_secret_chiffre"] is not None,
        access_token_laeuft_ab = row["access_token_laeuft_ab"],
        refresh_token_laeuft_ab = row["refresh_token_laeuft_ab"],
        verbunden_am = row["verbunden_am"],
        geaendert_am = row["geaendert_am"],
    )


def _laden(conn: sqlite3.Connection, profil_id: int, umgebung: EbayUmgebung) -> sqlite3.Row | None:
    return conn.execute(
        "SELECT * FROM ebay_zugang WHERE profil_id = ? AND umgebung = ?",
        (profil_id, umgebung.value),
    ).fetchone()


def status(
    conn: sqlite3.Connection,
    profil_id: int,
    umgebung: EbayUmgebung | str,
) -> EbayZugangStatus:
    """Bereinigter Status ohne Entschluesselung – sicher fuer API-Antworten."""
    umg = _umgebung(umgebung)
    row = _laden(conn, profil_id, umg)
    if row is None:
        return EbayZugangStatus(
            profil_id = profil_id,
            umgebung = umg,
            verbindung = EbayVerbindung.NICHT_VERBUNDEN,
            konto_id = None,
            app_id = None,
            scopes = (),
            schema_version = SCHEMA_VERSION,
            access_token_hinterlegt = False,
            refresh_token_hinterlegt = False,
            app_secret_hinterlegt = False,
            access_token_laeuft_ab = None,
            refresh_token_laeuft_ab = None,
            verbunden_am = None,
            geaendert_am = None,
        )
    return _zeile_zu_status(row)


def speichern(
    conn: sqlite3.Connection,
    profil_id: int,
    umgebung: EbayUmgebung | str,
    *,
    schluessel: str | None,
    access_token: str | None | object = _BEHALTEN,
    refresh_token: str | None | object = _BEHALTEN,
    app_secret: str | None | object = _BEHALTEN,
    app_id: str | None | object = _BEHALTEN,
    konto_id: str | None | object = _BEHALTEN,
    scopes: Sequence[str] | None | object = _BEHALTEN,
    access_token_laeuft_ab: str | None | object = _BEHALTEN,
    refresh_token_laeuft_ab: str | None | object = _BEHALTEN,
    verbindung: EbayVerbindung | str | None | object = _BEHALTEN,
    schema_version: int | object = _BEHALTEN,
) -> EbayZugangStatus:
    """Legt oder aktualisiert eBay-Zugangsdaten atomar.

    ``None`` als Wert loescht das betreffende Geheimnis bzw. Feld.
    Weglassen (Standard) belaesst den bisherigen Stand – noetig fuer
    Token-Refresh, der nur Access-Token und Ablaufzeit erneuert.
    """
    umg = _umgebung(umgebung)
    vorher = _laden(conn, profil_id, umg)

    braucht_tresor = any(
        wert is not _BEHALTEN and wert is not None
        for wert in (access_token, refresh_token, app_secret)
    )
    tresor = tresor_oder_fehler(schluessel) if braucht_tresor else None

    def _chiffre(neu: object, alt_blob: bytes | None) -> bytes | None:
        if neu is _BEHALTEN:
            return alt_blob
        if neu is None:
            return None
        assert isinstance(neu, str)
        if not neu:
            raise FachlicherFehler("Geheimnisse dürfen nicht leer sein.")
        assert tresor is not None
        return tresor.verschluesseln(neu)

    def _feld(neu: object, alt: object) -> object:
        return alt if neu is _BEHALTEN else neu

    alt_access = None if vorher is None else vorher["access_token_chiffre"]
    alt_refresh = None if vorher is None else vorher["refresh_token_chiffre"]
    alt_secret = None if vorher is None else vorher["app_secret_chiffre"]

    access_blob = _chiffre(access_token, bytes(alt_access) if alt_access is not None else None)
    refresh_blob = _chiffre(refresh_token, bytes(alt_refresh) if alt_refresh is not None else None)
    secret_blob = _chiffre(app_secret, bytes(alt_secret) if alt_secret is not None else None)

    neues_app_id = _feld(app_id, None if vorher is None else vorher["app_id"])
    if isinstance(neues_app_id, str):
        neues_app_id = neues_app_id.strip() or None

    neues_konto = _feld(konto_id, None if vorher is None else vorher["konto_id"])
    if isinstance(neues_konto, str):
        neues_konto = neues_konto.strip() or None

    if scopes is _BEHALTEN:
        scopes_text = "" if vorher is None else (vorher["scopes"] or "")
    else:
        assert scopes is None or isinstance(scopes, (list, tuple))
        scopes_text = _scopes_als_text(scopes)

    access_ablauf = _feld(
        access_token_laeuft_ab,
        None if vorher is None else vorher["access_token_laeuft_ab"],
    )
    refresh_ablauf = _feld(
        refresh_token_laeuft_ab,
        None if vorher is None else vorher["refresh_token_laeuft_ab"],
    )

    if verbindung is _BEHALTEN:
        if vorher is None:
            verb = EbayVerbindung.NICHT_VERBUNDEN
        else:
            verb = EbayVerbindung(vorher["verbindung"])
    elif verbindung is None:
        verb = EbayVerbindung.NICHT_VERBUNDEN
    else:
        try:
            verb = verbindung if isinstance(verbindung, EbayVerbindung) else EbayVerbindung(verbindung)
        except ValueError as fehler:
            raise FachlicherFehler(
                "Unbekannter Verbindungsstatus.",
                feld = "verbindung",
            ) from fehler

    if schema_version is _BEHALTEN:
        schema = SCHEMA_VERSION if vorher is None else int(vorher["schema_version"])
    else:
        assert isinstance(schema_version, int)
        if schema_version < 1:
            raise FachlicherFehler("schema_version muss ≥ 1 sein.", feld = "schema_version")
        schema = schema_version

    # Automatisch „verbunden“, wenn Tokens frisch gesetzt und Status nicht
    # ausdruecklich anders gewaehlt wurde.
    if (
        verbindung is _BEHALTEN
        and access_token is not _BEHALTEN
        and isinstance(access_token, str)
        and access_token
        and refresh_token is not _BEHALTEN
        and isinstance(refresh_token, str)
        and refresh_token
    ):
        verb = EbayVerbindung.VERBUNDEN

    jetzt = _jetzt()
    verbunden_am: str | None
    if verb == EbayVerbindung.VERBUNDEN:
        if vorher is not None and vorher["verbunden_am"] and EbayVerbindung(vorher["verbindung"]) == EbayVerbindung.VERBUNDEN:
            verbunden_am = vorher["verbunden_am"]
        else:
            verbunden_am = jetzt
    elif vorher is not None and verb == EbayVerbindung(vorher["verbindung"]):
        verbunden_am = vorher["verbunden_am"]
    else:
        verbunden_am = None if verb != EbayVerbindung.VERBUNDEN else jetzt

    with transaction(conn):
        if vorher is None:
            conn.execute(
                """
                INSERT INTO ebay_zugang (
                    profil_id, umgebung, konto_id, schema_version, scopes,
                    app_id, app_secret_chiffre,
                    access_token_chiffre, refresh_token_chiffre,
                    access_token_laeuft_ab, refresh_token_laeuft_ab,
                    verbindung, verbunden_am, geaendert_am
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    profil_id, umg.value, neues_konto, schema, scopes_text,
                    neues_app_id, secret_blob,
                    access_blob, refresh_blob,
                    access_ablauf, refresh_ablauf,
                    verb.value, verbunden_am, jetzt,
                ),
            )
        else:
            conn.execute(
                """
                UPDATE ebay_zugang SET
                    konto_id = ?, schema_version = ?, scopes = ?,
                    app_id = ?, app_secret_chiffre = ?,
                    access_token_chiffre = ?, refresh_token_chiffre = ?,
                    access_token_laeuft_ab = ?, refresh_token_laeuft_ab = ?,
                    verbindung = ?, verbunden_am = ?, geaendert_am = ?
                WHERE profil_id = ? AND umgebung = ?
                """,
                (
                    neues_konto, schema, scopes_text,
                    neues_app_id, secret_blob,
                    access_blob, refresh_blob,
                    access_ablauf, refresh_ablauf,
                    verb.value, verbunden_am, jetzt,
                    profil_id, umg.value,
                ),
            )

    return status(conn, profil_id, umg)


def tokens_erneuern(
    conn: sqlite3.Connection,
    profil_id: int,
    umgebung: EbayUmgebung | str,
    *,
    schluessel: str | None,
    access_token: str,
    access_token_laeuft_ab: str | None,
    refresh_token: str | None = None,
    refresh_token_laeuft_ab: str | None | object = _BEHALTEN,
) -> EbayZugangStatus:
    """Atomare Token-Erneuerung (Serialisierung ueber die DB-Transaktion).

    Refresh-Token bleibt unveraendert, sofern keines uebergeben wird – typisch
    fuer eBay Access-Token-Refresh. Fuer den echten HTTP-Refresh siehe AP-E-03.
    """
    if not access_token:
        raise FachlicherFehler("Access-Token darf nicht leer sein.", feld = "access_token")

    kwargs: dict[str, object] = {
        "schluessel": schluessel,
        "access_token": access_token,
        "access_token_laeuft_ab": access_token_laeuft_ab,
        "verbindung": EbayVerbindung.VERBUNDEN,
    }
    if refresh_token is not None:
        kwargs["refresh_token"] = refresh_token
    if refresh_token_laeuft_ab is not _BEHALTEN:
        kwargs["refresh_token_laeuft_ab"] = refresh_token_laeuft_ab

    vorher = status(conn, profil_id, umgebung)
    if not vorher.refresh_token_hinterlegt and refresh_token is None:
        raise FachlicherFehler(
            "Für dieses Profil/diese Umgebung ist kein Refresh-Token hinterlegt.",
            status = 409,
        )

    return speichern(conn, profil_id, umgebung, **kwargs)  # type: ignore[arg-type]


def als_erneut_verbinden(
    conn: sqlite3.Connection,
    profil_id: int,
    umgebung: EbayUmgebung | str,
) -> EbayZugangStatus:
    """Widerruf / ungueltige Tokens: Status setzen, Geheimnisse entfernen."""
    umg = _umgebung(umgebung)
    vorher = _laden(conn, profil_id, umg)
    if vorher is None:
        return status(conn, profil_id, umg)

    jetzt = _jetzt()
    with transaction(conn):
        conn.execute(
            """
            UPDATE ebay_zugang SET
                access_token_chiffre = NULL,
                refresh_token_chiffre = NULL,
                access_token_laeuft_ab = NULL,
                refresh_token_laeuft_ab = NULL,
                verbindung = ?,
                verbunden_am = NULL,
                geaendert_am = ?
            WHERE profil_id = ? AND umgebung = ?
            """,
            (EbayVerbindung.ERNEUT_VERBINDEN.value, jetzt, profil_id, umg.value),
        )
    return status(conn, profil_id, umg)


def entfernen(
    conn: sqlite3.Connection,
    profil_id: int,
    umgebung: EbayUmgebung | str,
) -> None:
    """Loescht die Zugangszeile fuer Profil und Umgebung."""
    umg = _umgebung(umgebung)
    with transaction(conn):
        conn.execute(
            "DELETE FROM ebay_zugang WHERE profil_id = ? AND umgebung = ?",
            (profil_id, umg.value),
        )


def lesen(
    conn: sqlite3.Connection,
    profil_id: int,
    umgebung: EbayUmgebung | str,
    *,
    schluessel: str | None,
) -> EbayGeheimnisse:
    """Holt Klartext-Geheimnisse fuer interne Aufrufe.

    Nur unmittelbar vor OAuth-/API-Nutzung rufen. Rueckgabe weder loggen noch
    in HTTP-Antworten oder Jobargumente schreiben.
    """
    umg = _umgebung(umgebung)
    row = _laden(conn, profil_id, umg)
    if row is None:
        raise FachlicherFehler(
            "Für dieses Profil sind in dieser eBay-Umgebung keine Zugangsdaten hinterlegt.",
            status = 409,
        )

    tresor = tresor_oder_fehler(schluessel)

    def _entsch(blob: object) -> str | None:
        if blob is None:
            return None
        return tresor.entschluesseln(bytes(blob))

    return EbayGeheimnisse(
        access_token = _entsch(row["access_token_chiffre"]),
        refresh_token = _entsch(row["refresh_token_chiffre"]),
        app_secret = _entsch(row["app_secret_chiffre"]),
        app_id = row["app_id"],
        konto_id = row["konto_id"],
        scopes = _scopes_als_tuple(row["scopes"]),
        schema_version = int(row["schema_version"]),
        access_token_laeuft_ab = row["access_token_laeuft_ab"],
        refresh_token_laeuft_ab = row["refresh_token_laeuft_ab"],
        umgebung = umg,
    )
