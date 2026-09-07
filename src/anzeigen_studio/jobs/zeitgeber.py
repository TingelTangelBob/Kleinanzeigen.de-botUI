# SPDX-FileCopyrightText: © Anzeigen-Studio contributors
# SPDX-ArtifactOfProjectHomePage: https://github.com/TingelTangelBob/Kleinanzeigen.de-botUI/
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# Zeitgeber fuer taeglichen Abgleich (AP-3.12) und Auto-Verlaengern (AP-3.15).
#
# Das hier ist der einzige Ort im Studio, an dem ein Lauf gegen das echte Konto
# OHNE einen Knopfdruck entsteht. Deshalb gelten fuer ihn engere Regeln als fuer
# alles andere - `EXPECTATIONS.md` Paragraph 7 verlangt fuer Konto-Laeufe eine
# ausdrueckliche Freigabe, und ein Automatismus laeuft gerade dann, wenn
# niemand hinsieht:
#
#   * VORGABE AUS. Ohne den Schalter unter Einstellungen passiert nichts. Die
#     Datenbank legt `eingeschaltet` mit 0 an, nicht mit 1.
#   * EIN LAUF JE PROFIL UND TAG. Der Tag steht in der Datenbank, nicht im
#     Speicher - ein Neustart um 23:59 loest keinen zweiten Lauf aus.
#   * DIESELBE WARTESCHLANGE wie alles andere. Kein eigener Browser, keine
#     Umgehung von Taktung, Profilsperre und Abbruch (AP-1.6/AP-1.12). Der
#     Abgleich draengelt sich nicht vor; er wartet wie jeder andere Lauf.
#   * OHNE ZUGANGSDATEN GAR NICHT ERST STARTEN. Ein Lauf, der sich nicht
#     anmelden kann, erzeugt nur eine rote Zeile und einen Browserstart.
#   * SICHTBAR. Zeitpunkt und Ergebnis des letzten Laufs stehen unter
#     Einstellungen; Befunde landen in der Glocke. Ein stiller
#     Hintergrunddienst waere genau das, was hier nicht entstehen soll.
#
# Der Takt ist bewusst kurz (eine Minute) und die Faelligkeitspruefung teuer-frei:
# Sie liest eine Zeile je Profil und vergleicht ein Datum. Ein stuendlicher Takt
# wuerde dasselbe leisten, aber das Ergebnis eines Laufs bis zu einer Stunde
# spaeter in die Glocke bringen - der Lauf selbst dauert nur Minuten.

from __future__ import annotations

import asyncio
import contextlib
import logging
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Final

from anzeigen_studio.bestand import plattform_reihenfolge, tagesabgleich, verlaengern
from anzeigen_studio.jobs.warteschlange import GLOB_HERUNTERGELADEN
from anzeigen_studio.core import db, zugang
from anzeigen_studio.core import profile as profile_dienst
from anzeigen_studio.jobs import speicher
from anzeigen_studio.jobs.modelle import JobZustand

if TYPE_CHECKING:
    import sqlite3
    from pathlib import Path

    from anzeigen_studio.core.settings import Settings
    from anzeigen_studio.jobs.warteschlange import Warteschlange

LOG = logging.getLogger(__name__)

#: Abstand zwischen zwei Pruefungen in Sekunden.
STANDARD_TAKT_S: Final[float] = 60.0
REIHENFOLGE_INTERVAL_S: Final[int] = 60 * 60


def _mindestens_so_neu(geprueft_am: str, lauf_start: str) -> bool:
    """Ist die Kontoliste mindestens so neu wie der Start des Laufs?

    Bewusst geparst und nicht als Zeichenketten verglichen: Beide Stempel
    entstehen heute im selben Format, aber das ist ein Zufall zweier Stellen im
    Code. Aendert eine davon `timespec` oder die Zeitzone, waere ein
    Zeichenkettenvergleich still falsch - und die Folge waere eine Glocke, die
    lebende Anzeigen als verschwunden meldet.
    """
    try:
        liste = datetime.fromisoformat(geprueft_am)
        start = datetime.fromisoformat(lauf_start)
    except ValueError:
        return False
    if liste.tzinfo is None:
        liste = liste.replace(tzinfo = UTC)
    if start.tzinfo is None:
        start = start.replace(tzinfo = UTC)
    return liste >= start


class Zeitgeber:
    """Reiht faellige Abgleichlaeufe ein und wertet sie aus.

    Bewusst ohne Cron und ohne externen Scheduler: Ein Prozess, ein Takt, ein
    Zustand in derselben Datenbank. Alles andere waere fuer eine Anwendung mit
    einem Betreiber Betriebsaufwand ohne Gegenwert - dieselbe Begruendung wie
    bei der Warteschlange.
    """

    def __init__(
        self,
        settings: Settings,
        warteschlange: Warteschlange,
        *,
        takt_s: float = STANDARD_TAKT_S,
    ) -> None:
        self._settings = settings
        self._ws = warteschlange
        self._takt_s = takt_s
        self._aufgabe: asyncio.Task[None] | None = None

    # -- Lebenszyklus --------------------------------------------------------

    def starten(self) -> None:
        if self._aufgabe is not None:
            return
        self._aufgabe = asyncio.create_task(self._schleife())

    async def stillegen(self) -> None:
        if self._aufgabe is None:
            return
        self._aufgabe.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await self._aufgabe
        self._aufgabe = None

    async def _schleife(self) -> None:
        # Erst warten, dann pruefen. Ein Lauf gegen das echte Konto im selben
        # Moment, in dem der Container hochkommt, waere ueberraschend - und
        # gerade beim Neustart nach einem Absturz will man den Bot nicht
        # sofort wieder auf der Plattform haben.
        while True:
            await asyncio.sleep(self._takt_s)
            try:
                await self.tick()
            except asyncio.CancelledError:
                raise
            except Exception:  # noqa: BLE001 - der Zeitgeber darf nie sterben
                LOG.exception("Der Abgleich-Zeitgeber ist unerwartet gescheitert")

    # -- Ein Durchgang -------------------------------------------------------

    async def tick(self) -> None:
        """Ein Durchgang ueber alle Profile. Oeffentlich, damit Tests ihn rufen."""
        conn = db.connect(self._settings.database_path)
        try:
            for profil in profile_dienst.alle(conn):
                try:
                    await self._profil(conn, profil)
                except Exception:  # noqa: BLE001 - ein Profil darf die anderen nicht mitreissen
                    LOG.exception("Abgleich fuer Profil %s gescheitert", profil.slug)
        finally:
            conn.close()

    async def _profil(self, conn: sqlite3.Connection, profil: profile_dienst.Profil) -> None:
        wurzel = profile_dienst.pfade_fuer(self._settings.profiles_dir, profil.slug).wurzel
        zustand = tagesabgleich.lesen(conn, profil.id)
        zustand_v = verlaengern.lesen(conn, profil.id)

        # Ein offener Lauf hat Vorrang: Erst auswerten, dann darf ein neuer
        # entstehen. Sonst liefe der naechste Tag los, waehrend der Vergleich
        # des vorigen noch aussteht - und der Schnappschuss waere futsch.
        if zustand.job_id is not None:
            self._auswerten(conn, profil, zustand, wurzel)
            return

        if zustand.reihenfolge_job_id is not None:
            self._reihenfolge_auswerten(conn, profil, zustand)
            return

        if zustand_v.job_id is not None:
            self._verlaengern_auswerten(conn, profil, zustand_v)
            return

        # Taeglicher Abgleich (AP-3.12) - eigener Schalter, Vorgabe aus.
        if zustand.eingeschaltet:
            status = zugang.status(conn, profil.id)
            if status is None or not status.passwort_hinterlegt:
                # Kein Lauf, aber auch kein Schweigen: Wer den Schalter umgelegt
                # hat und nie eine Meldung sieht, soll unter Einstellungen den
                # Grund lesen koennen.
                with db.transaction(conn):
                    tagesabgleich.hinweis_vermerken(
                        conn, profil.id,
                        "Kein Abgleich: Für dieses Profil sind keine Zugangsdaten hinterlegt.",
                    )
            elif zustand.letzter_tag != tagesabgleich.heutiger_tag():
                # Der tägliche Abgleich hat Vorrang, wenn beides fällig ist. So
                # bleibt das bisherige Startverhalten erhalten und die tägliche
                # Bestandsprüfung wird nicht durch den kleinen Zwischenabgleich
                # verdrängt. Auto-Verlängern wartet auf den nächsten Tick.
                vorher = tagesabgleich.stand_aufnehmen(wurzel)

                job_id = await self._ws.einreihen(
                    conn, profil.id, "download", [], profil_verzeichnis = wurzel,
                )
                with db.transaction(conn):
                    tagesabgleich.lauf_vermerken(
                        conn, profil.id,
                        tag = tagesabgleich.heutiger_tag(), job_id = job_id, vorher = vorher,
                    )
                LOG.info("Täglicher Abgleich für %s eingereiht (Lauf %d)", profil.slug, job_id)
                return
            elif plattform_reihenfolge.faellig(
                zustand.reihenfolge_letzter_lauf_am,
                intervall_s = REIHENFOLGE_INTERVAL_S,
            ):
                # Die Reihenfolge ist eine kleine, schreibgeschützte JSON-Abfrage.
                # Sie läuft stündlich, aber nur nach derselben ausdrücklichen
                # Freigabe wie der tägliche Abgleich und immer durch die normale
                # Warteschlange.
                job_id = await self._ws.einreihen(
                    conn, profil.id, "sync-order", [], profil_verzeichnis = wurzel,
                )
                with db.transaction(conn):
                    tagesabgleich.reihenfolge_lauf_vermerken(conn, profil.id, job_id = job_id)
                LOG.info(
                    "Stündliche Plattform-Reihenfolge für %s eingereiht (Lauf %d)",
                    profil.slug, job_id,
                )
                return

        # Automatisches kostenloses Verlaengern (AP-3.15) - eigener Schalter,
        # Vorgabe aus. Unabhaengig vom Abgleich; Free-only via Upstream-extend.
        if not zustand_v.eingeschaltet:
            return
        status = zugang.status(conn, profil.id)
        if status is None or not status.passwort_hinterlegt:
            with db.transaction(conn):
                verlaengern.hinweis_vermerken(
                    conn, profil.id,
                    "Kein Verlängern: Für dieses Profil sind keine Zugangsdaten hinterlegt.",
                )
            return
        if zustand_v.letzter_tag == verlaengern.heutiger_tag():
            return

        job_id = await self._ws.einreihen(
            conn, profil.id, "extend", [],
            profil_verzeichnis = wurzel,
            anzeigen_glob = GLOB_HERUNTERGELADEN,
        )
        with db.transaction(conn):
            verlaengern.lauf_vermerken(
                conn, profil.id,
                tag = verlaengern.heutiger_tag(), job_id = job_id,
            )
        LOG.info("Automatisches Verlängern für %s eingereiht (Lauf %d)", profil.slug, job_id)

    def _verlaengern_auswerten(
        self, conn: sqlite3.Connection, profil: profile_dienst.Profil,
        zustand: verlaengern.Zustand,
    ) -> None:
        """Schliesst einen Auto-extend-Lauf ab und meldet Fehlschlaege."""
        job = speicher.holen(conn, zustand.job_id) if zustand.job_id is not None else None
        if job is None:
            with db.transaction(conn):
                verlaengern.ergebnis_vermerken(
                    conn, profil.id, "Der eingereihte Verlängern-Lauf ist nicht mehr auffindbar.",
                )
            return
        if job.laeuft_noch:
            return

        if job.zustand is not JobZustand.FERTIG:
            text = (
                f"Das automatische Verlängern für „{profil.anzeigename}“ endete als "
                f"{job.zustand.value}. Das Protokoll steht unter Warteschlange, Lauf {job.id}."
            )
            with db.transaction(conn):
                tagesabgleich.meldung_anlegen(
                    conn, profil.id, art = "fehlschlag",
                    titel = "Automatisches Verlängern nicht durchgelaufen", text = text,
                )
                verlaengern.ergebnis_vermerken(
                    conn, profil.id, f"Lauf {job.id} endete als {job.zustand.value}.",
                )
            return

        with db.transaction(conn):
            verlaengern.ergebnis_vermerken(
                conn, profil.id,
                "Kostenloses Verlängern durchgelaufen (+60 Tage, kein Hochschieben).",
            )
            tagesabgleich.aufraeumen(conn)

    def _reihenfolge_auswerten(
        self, conn: sqlite3.Connection, profil: profile_dienst.Profil,
        zustand: tagesabgleich.Zustand,
    ) -> None:
        """Close an order-only job after the worker imported its sidecar."""
        job = speicher.holen(conn, zustand.reihenfolge_job_id) if zustand.reihenfolge_job_id is not None else None
        if job is None:
            with db.transaction(conn):
                tagesabgleich.reihenfolge_ergebnis_vermerken(
                    conn, profil.id, "Die Plattform-Reihenfolge konnte nicht ausgewertet werden.",
                )
            return
        if job.laeuft_noch:
            return
        text = (
            "Plattform-Reihenfolge geprüft."
            if job.zustand is JobZustand.FERTIG
            else f"Plattform-Reihenfolge endete als {job.zustand.value}."
        )
        with db.transaction(conn):
            tagesabgleich.reihenfolge_ergebnis_vermerken(conn, profil.id, text)

    def _kontoliste(
        self, conn: sqlite3.Connection, profil: profile_dienst.Profil,
        zustand: tagesabgleich.Zustand,
    ) -> set[str] | None:
        """Die Anzeigennummern, die das Konto JETZT fuehrt - oder None.

        Ohne diese Liste findet der Abgleich eine Anzeige nicht, die ganz aus
        dem Konto verschwunden ist: Der Bot besucht beim Download nur, was auf
        der Uebersichtsseite steht, ruehrt die Datei einer verschwundenen
        Anzeige also nicht an, und der Dateivergleich sieht nichts (Befund
        2026-09-05). Die geordnete Kontoliste aus AP-3.14 wird vom selben
        `download`-Lauf geschrieben und von der Warteschlange uebernommen.

        `None` bei jedem Zweifel. Eine VERALTETE Liste waere schlimmer als
        keine - sie wuerde jede seit ihrer Aufnahme eingestellte Anzeige als
        verschwunden melden. Deshalb zaehlt sie nur, wenn sie nicht aelter ist
        als der Start dieses Laufs.
        """
        try:
            ids, geprueft_am, _ = plattform_reihenfolge.laden(conn, profil.id)
        except Exception:  # noqa: BLE001 - Zusatzauskunft darf den Abgleich nicht kippen
            LOG.warning("Kontoliste fuer %s nicht lesbar", profil.slug, exc_info = True)
            return None
        if not ids or geprueft_am is None or zustand.letzter_lauf_am is None:
            return None
        if not _mindestens_so_neu(geprueft_am, zustand.letzter_lauf_am):
            LOG.debug(
                "Kontoliste von %s ist aelter als der Lauf (%s < %s) - wird nicht verwendet",
                profil.slug, geprueft_am, zustand.letzter_lauf_am,
            )
            return None
        return {str(ad_id) for ad_id in ids}

    def _auswerten(
        self, conn: sqlite3.Connection, profil: profile_dienst.Profil,
        zustand: tagesabgleich.Zustand, wurzel: Path,
    ) -> None:
        """Vergleicht nach dem Lauf und schreibt Ergebnis und Meldung."""
        job = speicher.holen(conn, zustand.job_id) if zustand.job_id is not None else None
        if job is None:
            with db.transaction(conn):
                tagesabgleich.ergebnis_vermerken(
                    conn, profil.id, "Der eingereihte Lauf ist nicht mehr auffindbar.",
                )
            return
        if job.laeuft_noch:
            return

        if job.zustand is not JobZustand.FERTIG:
            # Ein Automatismus, der still scheitert, ist schlimmer als keiner:
            # Der Bestand sieht dann tagelang aktuell aus, ohne es zu sein.
            # Deshalb geht auch der Fehlschlag in die Glocke - einmal, nicht
            # jeden Tag aufs Neue, denn morgen laeuft ein neuer Lauf.
            text = (
                f"Der tägliche Abgleich für „{profil.anzeigename}“ endete als "
                f"{job.zustand.value}. Der Bestand kann veraltet sein. "
                f"Das Protokoll steht unter Warteschlange, Lauf {job.id}."
            )
            with db.transaction(conn):
                tagesabgleich.meldung_anlegen(
                    conn, profil.id, art = "fehlschlag",
                    titel = "Täglicher Abgleich nicht durchgelaufen", text = text,
                )
                tagesabgleich.ergebnis_vermerken(
                    conn, profil.id, f"Lauf {job.id} endete als {job.zustand.value}.",
                )
            return

        nachher = tagesabgleich.stand_aufnehmen(wurzel)
        aenderungen = tagesabgleich.vergleichen(
            zustand.vorher, nachher,
            plattform_ids = self._kontoliste(conn, profil, zustand),
        )
        gemeldet = tagesabgleich.meldungstext(aenderungen)

        with db.transaction(conn):
            # Der Lauf ist durch - eine stehengebliebene Fehlschlag-Warnung von
            # gestern waere ab jetzt falsch.
            tagesabgleich.fehlschlaege_loeschen(conn, profil.id)
            if gemeldet is None:
                tagesabgleich.ergebnis_vermerken(
                    conn, profil.id, "Ohne Änderung durchgelaufen.",
                )
            else:
                titel, text = gemeldet
                tagesabgleich.meldung_anlegen(
                    conn, profil.id, art = "aenderung", titel = titel, text = text,
                )
                tagesabgleich.ergebnis_vermerken(conn, profil.id, f"{titel}: {text}")
            tagesabgleich.aufraeumen(conn)
