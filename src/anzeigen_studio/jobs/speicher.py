# SPDX-FileCopyrightText: © Anzeigen-Studio contributors
# SPDX-ArtifactOfProjectHomePage: https://github.com/TingelTangelBob/Kleinanzeigen.de-botUI/
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# Persistenz der Jobs und ihrer Protokollzeilen (AP-1.6, AP-1.7).

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from anzeigen_studio.jobs.modelle import Job, JobZustand

if TYPE_CHECKING:
    import sqlite3

    from anzeigen_studio.botbridge.events import Ereignis

#: Wie viele Protokollzeilen je Job aufbewahrt werden. Ohne Grenze waechst die
#: Datenbank unbegrenzt - ein Download-Lauf ueber hunderte Anzeigen erzeugt
#: schnell fuenfstellige Zeilenzahlen.
LOG_GRENZE_JE_JOB = 5000


def _jetzt() -> str:
    return datetime.now(UTC).isoformat(timespec = "milliseconds")


def _zu_job(row: sqlite3.Row) -> Job:
    return Job(
        id = row["id"],
        profil_id = row["profil_id"],
        profil_slug = row["profil_slug"],
        befehl = row["befehl"],
        argumente = json.loads(row["argumente"]) if row["argumente"] else [],
        zustand = JobZustand(row["zustand"]),
        eingereicht_am = row["eingereicht_am"],
        gestartet_am = row["gestartet_am"],
        beendet_am = row["beendet_am"],
        rueckgabecode = row["rueckgabecode"],
        aufmerksamkeit = row["aufmerksamkeit"].split(",") if row["aufmerksamkeit"] else [],
        eingriff = row["eingriff"],
        meldung = row["meldung"],
        wartet_bis = row["wartet_bis"],
        wartegrund = row["wartegrund"],
        anzeigen_glob = row["anzeigen_glob"],
    )


#: Die beiden Zustaende, in denen ein Job das Profil belegt. Bewusst hier als
#: feste Zweiergruppe ausgeschrieben statt dynamisch aus einem Set erzeugt:
#: So bleiben alle Abfragen unten vollstaendige Zeichenketten-Literale, und es
#: gibt keine zusammengesetzte SQL, die man auf Injektion pruefen muesste.
_AKTIV_A = JobZustand.LAEUFT
_AKTIV_B = JobZustand.BRAUCHT_EINGABE

#: Zustaende, die einen Neustart des Dienstes nicht ueberdauern koennen.
#:
#: WARTET gehoert dazu, auch wenn kein Prozess dranhaengt: Ein eingereihter Job
#: wird von `asyncio.create_task` getragen und lebt nur im Speicher des
#: Backends. Nach einem Neustart nimmt ihn niemand wieder auf - er stuende
#: sonst fuer immer auf "wartet". Beobachtet am 2026-08-23 an einem `verify`,
#: das einen Neubau des Containers scheinbar unbeschadet ueberstand.
#:
#: Bewusst getrennt von _AKTIV_A/_AKTIV_B: Fuer die Frage, ob fuer ein Profil
#: gerade ein Lauf laeuft, zaehlt ein wartender Job nicht mit.
_VERWAIST_BEIM_START = (JobZustand.WARTET, JobZustand.LAEUFT, JobZustand.BRAUCHT_EINGABE)


def einreihen(
    conn: sqlite3.Connection,
    profil_id: int,
    befehl: str,
    argumente: list[str],
    *,
    anzeigen_glob: str | None = None,
) -> int:
    cursor = conn.execute(
        "INSERT INTO job (profil_id, befehl, argumente, zustand, eingereicht_am, anzeigen_glob) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (profil_id, befehl, json.dumps(argumente), JobZustand.WARTET, _jetzt(), anzeigen_glob),
    )
    return int(cursor.lastrowid or 0)


def holen(conn: sqlite3.Connection, job_id: int) -> Job | None:
    row = conn.execute(
        "SELECT j.*, p.slug AS profil_slug FROM job j JOIN profil p ON p.id = j.profil_id "
        "WHERE j.id = ?",
        (job_id,),
    ).fetchone()
    return _zu_job(row) if row else None


def liste(conn: sqlite3.Connection, *, profil_id: int | None = None, grenze: int = 50) -> list[Job]:
    if profil_id is None:
        rows = conn.execute(
            "SELECT j.*, p.slug AS profil_slug FROM job j JOIN profil p ON p.id = j.profil_id "
            "ORDER BY j.id DESC LIMIT ?",
            (grenze,),
        )
    else:
        rows = conn.execute(
            "SELECT j.*, p.slug AS profil_slug FROM job j JOIN profil p ON p.id = j.profil_id "
            "WHERE j.profil_id = ? ORDER BY j.id DESC LIMIT ?",
            (profil_id, grenze),
        )
    return [_zu_job(row) for row in rows]


def naechster_wartender(conn: sqlite3.Connection, profil_id: int) -> Job | None:
    """Der aelteste wartende Job eines Profils - aber nur, wenn keiner laeuft.

    Hier steckt die Serialisierung je Profil: Chromium sperrt sein
    Profilverzeichnis, und zwei Browsersitzungen auf einem Konto zerstoeren
    sich gegenseitig. Unterschiedliche Profile duerfen parallel.
    """
    aktiv = conn.execute(
        "SELECT COUNT(*) AS n FROM job WHERE profil_id = ? AND zustand IN (?, ?)",
        (profil_id, _AKTIV_A, _AKTIV_B),
    ).fetchone()
    if aktiv["n"] > 0:
        return None

    row = conn.execute(
        "SELECT j.*, p.slug AS profil_slug FROM job j JOIN profil p ON p.id = j.profil_id "
        "WHERE j.profil_id = ? AND j.zustand = ? ORDER BY j.id LIMIT 1",
        (profil_id, JobZustand.WARTET),
    ).fetchone()
    return _zu_job(row) if row else None


def warten_setzen(conn: sqlite3.Connection, job_id: int, *, bis: str | None, grund: str | None) -> None:
    """Haelt fest, dass und warum ein Job absichtlich wartet.

    `bis = None` loescht den Vermerk - der Job laeuft dann los.
    """
    conn.execute(
        "UPDATE job SET wartet_bis = ?, wartegrund = ? WHERE id = ?",
        (bis, grund, job_id),
    )


def zustand_setzen(
    conn: sqlite3.Connection,
    job_id: int,
    zustand: JobZustand,
    *,
    rueckgabecode: int | None = None,
    aufmerksamkeit: list[str] | None = None,
    eingriff: str | None = None,
    meldung: str | None = None,
) -> None:
    felder = ["zustand = ?"]
    werte: list[object] = [zustand]

    if zustand is JobZustand.LAEUFT:
        felder.append("gestartet_am = ?")
        werte.append(_jetzt())
        # Der Wartevermerk gilt nicht mehr, sobald der Lauf beginnt.
        felder.append("wartet_bis = NULL")
        felder.append("wartegrund = NULL")
    if zustand in {JobZustand.FERTIG, JobZustand.PRUEFEN, JobZustand.GESCHEITERT, JobZustand.ABGEBROCHEN}:
        felder.append("beendet_am = ?")
        werte.append(_jetzt())
    if rueckgabecode is not None:
        felder.append("rueckgabecode = ?")
        werte.append(rueckgabecode)
    if aufmerksamkeit is not None:
        felder.append("aufmerksamkeit = ?")
        werte.append(",".join(aufmerksamkeit))
    # eingriff wird auch auf NULL gesetzt, wenn der Wartepunkt vorbei ist -
    # deshalb kein "is not None"-Filter.
    felder.append("eingriff = ?")
    werte.append(eingriff)
    if meldung is not None:
        felder.append("meldung = ?")
        werte.append(meldung)

    werte.append(job_id)
    # Die Feldnamen stammen ausschliesslich aus den festen Zeichenketten oben,
    # nie aus Eingaben; die Werte gehen als Parameter.
    conn.execute(f"UPDATE job SET {', '.join(felder)} WHERE id = ?", werte)  # noqa: S608


def log_anhaengen(conn: sqlite3.Connection, job_id: int, ereignis: Ereignis) -> None:
    conn.execute(
        "INSERT INTO job_log (job_id, zeitpunkt, stufe, text) VALUES (?, ?, ?, ?)",
        (job_id, ereignis.zeitpunkt, str(ereignis.stufe), ereignis.text),
    )
    # Aelteste Zeilen abschneiden, sobald die Grenze ueberschritten ist.
    conn.execute(
        "DELETE FROM job_log WHERE job_id = ? AND id NOT IN "
        "(SELECT id FROM job_log WHERE job_id = ? ORDER BY id DESC LIMIT ?)",
        (job_id, job_id, LOG_GRENZE_JE_JOB),
    )


def log_lesen(conn: sqlite3.Connection, job_id: int, *, ab_id: int = 0) -> list[dict[str, Any]]:
    rows = conn.execute(
        "SELECT id, zeitpunkt, stufe, text FROM job_log WHERE job_id = ? AND id > ? ORDER BY id",
        (job_id, ab_id),
    )
    return [dict(row) for row in rows]


def verwaiste_aufraeumen(conn: sqlite3.Connection) -> int:
    """Markiert Jobs, die den Neustart nicht ueberdauern koennen, als abgebrochen.

    Betrifft laufende, auf Eingabe wartende und eingereihte Jobs (siehe
    `_VERWAIST_BEIM_START`). Keiner von ihnen laeuft nach einem Neustart weiter
    - ehrlich zu melden ist besser, als einen Zustand anzuzeigen, den es nicht
    mehr gibt. Ein Lauf, der Anzeigen veraendern kann, soll ausserdem nicht von
    selbst anspringen, nur weil der Dienst neu gestartet ist.
    """
    platzhalter = ", ".join("?" for _ in _VERWAIST_BEIM_START)
    cursor = conn.execute(
        "UPDATE job SET zustand = ?, beendet_am = ?, eingriff = NULL, "
        "wartet_bis = NULL, wartegrund = NULL, "
        "meldung = 'Beim Neustart des Dienstes abgebrochen.' "
        f"WHERE zustand IN ({platzhalter})",
        (JobZustand.ABGEBROCHEN, _jetzt(), *_VERWAIST_BEIM_START),
    )
    return cursor.rowcount or 0
