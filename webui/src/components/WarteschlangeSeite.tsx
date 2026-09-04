// SPDX-FileCopyrightText: © Anzeigen-Studio contributors
// SPDX-License-Identifier: AGPL-3.0-or-later
//
// Die Warteschlange als eigene Seite (AP-2.31).
//
// Wozu: Die Läufe lagen bis hier als Mini-Liste unter der Seitenleisten-Nav und
// als Unterpunkt „Läufe" der Einstellungen - zwei halbe Einstiege. Jetzt ist es
// ein Menüpunkt „Warteschlange" und diese Seite. Sie ist queue-first: oben die
// aktiven und wartenden Läufe, detailliert und mit Aktionen (Protokoll,
// Abbruch, Captcha-Übernahme über `JobKarte`), darunter die zuletzt beendeten,
// und erst ganz unten - eingeklappt - der Block zum Starten neuer Läufe.
//
// Verhältnis zur Glocke (AP-2.25/2.30): Die Glocke meldet Ereignisse und pulst
// bei Neuem. Diese Seite ist der ruhige, vollständige Blick auf die Queue.
// Beide lesen dieselbe `api.jobs.liste()`.

import { useCallback, useEffect, useMemo, useState } from 'react';
import { AlertTriangle, ChevronDown, Plus, Trash2 } from 'lucide-react';
import { api, ApiFehler } from '../services/api';
import { useProfil } from '../context/useProfil';
import { anzeigeBezug } from '../jobText';
import type { BestandsAnzeige, Job, JobZustand } from '../types';
import { JobKarte, LaufStarten } from './JobSeite';

const AKTIV = new Set<JobZustand>(['wartet', 'laeuft', 'braucht_eingabe']);

/** Wie viele beendete Läufe die Seite zeigt - der Rest wäre eine Wand. */
const BEENDET_MAX = 8;

export function WarteschlangeSeite() {
  const { aktiv } = useProfil();
  const [jobs, setJobs] = useState<Job[]>([]);
  const [bestand, setBestand] = useState<BestandsAnzeige[]>([]);
  const [offenerJob, setOffenerJob] = useState<number | null>(null);
  const [starterOffen, setStarterOffen] = useState(false);
  const [fehler, setFehler] = useState<string | null>(null);
  const [leerenOffen, setLeerenOffen] = useState(false);
  const [leert, setLeert] = useState(false);

  const jobsLaden = useCallback(async () => {
    try {
      setJobs(await api.jobs.liste());
      setFehler(null);
    } catch (ursache) {
      setFehler(ursache instanceof ApiFehler ? ursache.message : 'Unbekannter Fehler.');
    }
  }, []);

  useEffect(() => {
    void jobsLaden();
  }, [jobsLaden]);

  // Für den Anzeige-Bezug (AP-2.29): den Bestand des aktiven Profils laden.
  // Läufe fremder Profile bleiben bei der nackten Kennung - das ist der
  // seltene Fall und keinen zweiten Abruf je Profil wert.
  useEffect(() => {
    if (!aktiv) {
      setBestand([]);
      return;
    }
    let tot = false;
    void api.bestand.liste(aktiv.slug)
      .then(liste => { if (!tot) setBestand(liste); })
      .catch(() => { if (!tot) setBestand([]); });
    return () => { tot = true; };
  }, [aktiv]);

  // Solange etwas offen ist, im Zwei-Sekunden-Takt nachsehen - derselbe Takt
  // wie bisher auf der Läufe-Seite. Eine ruhende Queue muss das nicht.
  const offeneDa = jobs.some(j => AKTIV.has(j.zustand));
  useEffect(() => {
    if (!offeneDa) return undefined;
    const timer = window.setInterval(() => void jobsLaden(), 2000);
    return () => window.clearInterval(timer);
  }, [offeneDa, jobsLaden]);

  const { aktive, beendete } = useMemo(() => {
    const a = jobs
      .filter(j => AKTIV.has(j.zustand))
      .sort((x, y) => (x.eingereicht_am ?? '').localeCompare(y.eingereicht_am ?? ''));
    const b = jobs
      .filter(j => !AKTIV.has(j.zustand))
      .sort((x, y) =>
        (y.beendet_am ?? y.eingereicht_am ?? '').localeCompare(x.beendet_am ?? x.eingereicht_am ?? ''))
      .slice(0, BEENDET_MAX);
    return { aktive: a, beendete: b };
  }, [jobs]);

  const umschalten = (id: number) => setOffenerJob(alt => (alt === id ? null : id));

  // „Beendete leeren" (AP-2.32): entfernt die abgeschlossenen Läufe des aktiven
  // Profils samt Protokoll. Aktive und wartende Läufe rührt der Endpunkt nie an.
  const beendeteLeeren = async () => {
    if (!aktiv) return;
    setLeert(true);
    try {
      await api.jobs.beendeteLeeren(aktiv.slug);
      setLeerenOffen(false);
      setOffenerJob(null);
      await jobsLaden();
    } catch (ursache) {
      setFehler(ursache instanceof ApiFehler ? ursache.message : 'Unbekannter Fehler.');
    } finally {
      setLeert(false);
    }
  };

  const karte = (job: Job) => (
    <JobKarte
      key={job.id}
      job={job}
      bezug={anzeigeBezug(job, bestand)}
      offen={offenerJob === job.id}
      aufUmschalten={() => umschalten(job.id)}
      aufAenderung={jobsLaden}
    />
  );

  return (
    <div className="seite">
      <h1 className="sr-only">
        Warteschlange
      </h1>
      <p className="seite-beschrieb mb-6">
        Was läuft, was wartet, was zuletzt fertig wurde. Ein Lauf nach dem anderen je Profil –
        Protokoll, Captcha und Abbruch je Lauf.
      </p>

      {fehler && (
        <p role="alert" className="hinweis hinweis-fehler mb-4">{fehler}</p>
      )}

      <section className="mb-8">
        <h2 className="mb-3 flex items-center gap-2 text-base font-semibold tracking-tight text-stark">
          Aktiv
          {aktive.length > 0 && (
            <span className="merkmal merkmal-blau">{aktive.length}</span>
          )}
        </h2>
        {aktive.length === 0 ? (
          <p className="leer">Gerade läuft und wartet nichts.</p>
        ) : (
          <div className="space-y-3">{aktive.map(karte)}</div>
        )}
      </section>

      <section className="mb-8">
        <div className="mb-3 flex items-center justify-between gap-2">
          <h2 className="text-base font-semibold tracking-tight text-stark">
            Zuletzt beendet
          </h2>
          {beendete.length > 0 && aktiv && (
            <button
              type="button"
              onClick={() => setLeerenOffen(true)}
              className="btn-leise flex-shrink-0"
            >
              <Trash2 className="h-4 w-4" aria-hidden />
              Beendete leeren
            </button>
          )}
        </div>
        {beendete.length === 0 ? (
          <p className="leer">Noch kein Lauf abgeschlossen.</p>
        ) : (
          <div className="space-y-3">{beendete.map(karte)}</div>
        )}
      </section>

      {/* Sekundär und eingeklappt (AP-2.31): Der Einstieg dieser Seite ist die
          Queue, nicht das Starten. Wer einen Lauf braucht, klappt hier auf. */}
      <section>
        <button
          type="button"
          onClick={() => setStarterOffen(o => !o)}
          aria-expanded={starterOffen}
          className="flex w-full items-center gap-2 rounded-xl px-1 py-2 text-left text-base font-semibold tracking-tight text-stark"
        >
          <Plus className="h-4 w-4 text-primary-custom" aria-hidden />
          Neuen Lauf starten
          <ChevronDown
            className={`ml-auto h-4 w-4 text-leise transition-transform ${starterOffen ? 'rotate-180' : ''}`}
            aria-hidden
          />
        </button>
        {starterOffen && (
          <div className="karte mt-2 p-4">
            <LaufStarten
              aufEingereiht={id => {
                setOffenerJob(id);
                void jobsLaden();
              }}
            />
          </div>
        )}
      </section>

      {leerenOffen && (
        <div className="fixed inset-0 z-50 flex items-end justify-center bg-black/40 p-4 sm:items-center">
          <div role="dialog" aria-modal="true" aria-labelledby="leeren-titel" className="dialog">
            <div className="mb-3 flex items-start gap-3">
              <Trash2 className="mt-0.5 h-5 w-5 flex-shrink-0" style={{ color: 'var(--hinweis-fehler-text)' }} aria-hidden />
              <div className="min-w-0">
                <h2 id="leeren-titel" className="font-semibold text-stark">
                  Beendete Läufe leeren?
                </h2>
                <p className="mt-1 text-sm text-normal">
                  Entfernt alle abgeschlossenen Läufe von {aktiv?.anzeigename} samt ihren
                  Protokollen. Was gerade läuft oder wartet, bleibt stehen.
                </p>
              </div>
            </div>
            <p className="hinweis hinweis-warn mb-4 flex items-start gap-2">
              <AlertTriangle className="mt-0.5 h-4 w-4 flex-shrink-0" aria-hidden />
              <span>Nur diese Liste hier – auf kleinanzeigen.de ändert sich nichts. Rückgängig geht es nicht.</span>
            </p>
            <div className="flex flex-col-reverse gap-2 sm:flex-row sm:justify-end">
              <button type="button" onClick={() => setLeerenOffen(false)} disabled={leert} className="btn-ghost">
                Abbrechen
              </button>
              <button
                type="button"
                onClick={() => void beendeteLeeren()}
                disabled={leert}
                className="btn-primaer disabled:opacity-60"
                style={{ background: 'var(--status-fehler)', color: '#fff' }}
              >
                <Trash2 className="h-4 w-4" aria-hidden />
                {leert ? 'Leert …' : 'Beendete leeren'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
