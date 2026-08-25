// SPDX-FileCopyrightText: © Anzeigen-Studio contributors
// SPDX-License-Identifier: AGPL-3.0-or-later
//
// Läufe starten und live mitlesen (AP-2.8, AP-1.7).

import { useCallback, useEffect, useRef, useState } from 'react';
import { AlertTriangle, Ban, Hand, Hourglass, Play } from 'lucide-react';
import { api, ApiFehler } from '../services/api';
import { useProfil } from '../context/useProfil';
import type { BestandsAnzeige, Job, JobZustand, LogZeile } from '../types';

/** Nur Befehle, die ohne weitere Eingaben sinnvoll sind. */
const BEFEHLE: { id: string; label: string; hinweis: string; schreibend: boolean }[] = [
  { id: 'verify', label: 'Prüfen', hinweis: 'Prüft nur die Konfiguration. Kein Zugriff aufs Konto.', schreibend: false },
  { id: 'diagnose', label: 'Diagnose', hinweis: 'Prüft die Browserverbindung.', schreibend: false },
  { id: 'download', label: 'Herunterladen', hinweis: 'Lädt die eigenen Anzeigen. Meldet sich an.', schreibend: false },
  { id: 'publish', label: 'Veröffentlichen', hinweis: 'Stellt Anzeigen auf kleinanzeigen.de ein.', schreibend: true },
  { id: 'extend', label: 'Verlängern', hinweis: 'Verlängert Anzeigen im Acht-Tage-Fenster.', schreibend: true },
];

const ZUSTAND_TEXT: Record<JobZustand, { text: string; klasse: string }> = {
  wartet: { text: 'wartet', klasse: 'bg-gray-100 text-gray-700' },
  laeuft: { text: 'läuft', klasse: 'bg-blue-100 text-blue-800' },
  braucht_eingabe: { text: 'braucht dich', klasse: 'bg-amber-100 text-amber-900' },
  fertig: { text: 'fertig', klasse: 'bg-green-100 text-green-800' },
  pruefen: { text: 'prüfen', klasse: 'bg-orange-100 text-orange-900' },
  gescheitert: { text: 'gescheitert', klasse: 'bg-red-100 text-red-800' },
  abgebrochen: { text: 'abgebrochen', klasse: 'bg-gray-200 text-gray-700' },
};

export function JobSeite() {
  // Das Profil kommt jetzt aus der Schale (AP-2.10) - eine Auswahl je Seite
  // hätte spätestens mit Übersicht und Bestand auseinanderlaufen können.
  const { profile, aktiv } = useProfil();
  const gewaehlt = aktiv?.slug ?? '';
  const [jobs, setJobs] = useState<Job[]>([]);
  const [offenerJob, setOffenerJob] = useState<number | null>(null);
  const [fehler, setFehler] = useState<string | null>(null);
  const [warnung, setWarnung] = useState<BestandsAnzeige[] | null>(null);

  const jobsLaden = useCallback(async () => {
    try {
      setJobs(await api.jobs.liste());
    } catch (ursache) {
      setFehler(ursache instanceof ApiFehler ? ursache.message : 'Unbekannter Fehler.');
    }
  }, []);

  useEffect(() => {
    void jobsLaden();
  }, [jobsLaden]);

  // Solange etwas läuft, regelmäßig nachsehen. Der Log-Strom hängt am
  // einzelnen Job; die Liste braucht ihren eigenen Takt.
  useEffect(() => {
    const aktiv = jobs.some(j => ['wartet', 'laeuft', 'braucht_eingabe'].includes(j.zustand));
    if (!aktiv) return undefined;
    const timer = window.setInterval(() => void jobsLaden(), 2000);
    return () => window.clearInterval(timer);
  }, [jobs, jobsLaden]);

  const [startet, setStartet] = useState<string | null>(null);

  const einreihen = async (befehl: string) => {
    setFehler(null);
    // Sofortige Rückmeldung: Ohne sie wirkt der Klick folgenlos, bis die Liste
    // das nächste Mal geladen wird.
    setStartet(befehl);
    try {
      const job = await api.jobs.starten(gewaehlt, befehl);
      setOffenerJob(job.id);
      await jobsLaden();
    } catch (ursache) {
      setFehler(ursache instanceof ApiFehler ? ursache.message : 'Unbekannter Fehler.');
    } finally {
      setStartet(null);
    }
  };

  // Vor dem Herunterladen nachsehen, ob lokale Änderungen überschrieben würden
  // (AP-3.1). Der Bot übernimmt beim Download den Stand der Plattform und
  // erhält nur vier Automatikfelder - siehe docs/RUNDLAUF.md. Wer etwas
  // geändert hat, soll das vorher erfahren, nicht hinterher.
  const starten = async (befehl: string) => {
    if (befehl !== 'download' || !gewaehlt) {
      await einreihen(befehl);
      return;
    }
    setFehler(null);
    setStartet(befehl);
    try {
      const betroffen = await api.bestand.lokaleAenderungen(gewaehlt);
      if (betroffen.length > 0) {
        setWarnung(betroffen);
        return;
      }
    } catch {
      // Die Prüfung ist eine Vorsichtsmaßnahme, keine Voraussetzung. Wenn sie
      // scheitert, darf sie den Download nicht verhindern.
    } finally {
      setStartet(null);
    }
    await einreihen(befehl);
  };

  return (
    <div className="mx-auto max-w-4xl">
      <h1 className="mb-6 text-2xl font-bold text-gray-900">Läufe</h1>

      {profile.length === 0 ? (
        <p className="rounded border border-amber-200 bg-amber-50 p-4 text-sm text-amber-900">
          Zuerst ein Profil anlegen und Zugangsdaten hinterlegen.
        </p>
      ) : (
        <div className="mb-6 rounded border border-gray-200 bg-white p-4">
          <p className="mb-3 text-sm text-gray-700">
            Läuft für <span className="font-medium text-gray-900">{aktiv?.anzeigename}</span>.
            Umschalten geht links in der Seitenleiste.
          </p>

          <p className="mb-3 text-xs text-gray-600">
            Läufe desselben Profils werden nacheinander abgearbeitet, mit einem
            Mindestabstand dazwischen. Ein Lauf kann deshalb ein bis zwei Minuten
            warten, bevor er startet – das ist Absicht und wird unten angezeigt.
          </p>

          <div className="grid gap-2 sm:grid-cols-2">
            {BEFEHLE.map(b => (
              <button
                key={b.id}
                type="button"
                disabled={startet !== null}
                onClick={() => void starten(b.id)}
                className={`flex items-start gap-3 rounded border p-3 text-left transition-colors
                            disabled:cursor-not-allowed disabled:opacity-60
                            ${b.schreibend
                              ? 'border-amber-300 bg-amber-50 hover:bg-amber-100'
                              : 'border-gray-300 bg-white hover:bg-gray-50'}`}
              >
                <Play className="mt-0.5 h-4 w-4 flex-shrink-0 text-primary-custom" />
                <span className="min-w-0">
                  <span className="block text-sm font-medium text-gray-900">
                    {startet === b.id ? 'Wird eingereiht …' : b.label}
                    {b.schreibend && (
                      <span className="ml-2 text-xs font-normal text-amber-800">
                        verändert etwas auf der Plattform
                      </span>
                    )}
                  </span>
                  <span className="block text-xs text-gray-600">{b.hinweis}</span>
                </span>
              </button>
            ))}
          </div>
        </div>
      )}

      {warnung && (
        <UeberschreibWarnung
          anzeigen={warnung}
          aufAbbrechen={() => setWarnung(null)}
          aufWeiter={() => {
            setWarnung(null);
            void einreihen('download');
          }}
        />
      )}

      {fehler && (
        <p role="alert" className="mb-4 rounded border border-red-200 bg-red-50 p-3 text-sm text-red-800">
          {fehler}
        </p>
      )}

      <div className="space-y-3">
        {jobs.map(job => (
          <JobKarte
            key={job.id}
            job={job}
            offen={offenerJob === job.id}
            aufUmschalten={() => setOffenerJob(offenerJob === job.id ? null : job.id)}
            aufAenderung={jobsLaden}
          />
        ))}
        {jobs.length === 0 && (
          <p className="rounded border border-gray-200 bg-white p-6 text-center text-sm text-gray-600">
            Noch keine Läufe.
          </p>
        )}
      </div>
    </div>
  );
}

/** Warnt vor einem Download, der lokale Änderungen überschreiben würde (AP-3.1). */
function UeberschreibWarnung({
  anzeigen, aufAbbrechen, aufWeiter,
}: { anzeigen: BestandsAnzeige[]; aufAbbrechen: () => void; aufWeiter: () => void }) {
  return (
    <div className="fixed inset-0 z-50 flex items-end justify-center bg-black/40 p-4 sm:items-center">
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="warnung-titel"
        className="max-h-[80vh] w-full max-w-lg overflow-y-auto rounded-lg bg-white p-5 shadow-xl"
      >
        <div className="mb-3 flex items-start gap-3">
          <AlertTriangle className="mt-0.5 h-5 w-5 flex-shrink-0 text-amber-600" aria-hidden />
          <div className="min-w-0">
            <h2 id="warnung-titel" className="font-semibold text-gray-900">
              Lokale Änderungen gehen verloren
            </h2>
            <p className="mt-1 text-sm text-gray-700">
              Beim Herunterladen wird der Stand der Plattform übernommen.
              {' '}
              {anzeigen.length === 1
                ? 'Eine Anzeige wurde hier geändert und wird überschrieben:'
                : `${anzeigen.length} Anzeigen wurden hier geändert und werden überschrieben:`}
            </p>
          </div>
        </div>

        <ul className="mb-4 max-h-48 overflow-y-auto rounded border border-gray-200 bg-gray-50 p-2 text-sm">
          {anzeigen.map(a => (
            <li key={a.datei} className="truncate py-0.5 text-gray-800">{a.titel}</li>
          ))}
        </ul>

        <p className="mb-4 text-xs text-gray-600">
          Erhalten bleiben nur die Automatikfelder: Preisautomatik, Abstand zur
          Neueinstellung und die beiden Zähler.
        </p>

        <div className="flex flex-col-reverse gap-2 sm:flex-row sm:justify-end">
          <button
            type="button"
            onClick={aufAbbrechen}
            className="rounded border border-gray-300 px-4 py-2 text-sm text-gray-700 hover:bg-gray-50"
          >
            Abbrechen
          </button>
          <button
            type="button"
            onClick={aufWeiter}
            className="rounded bg-amber-600 px-4 py-2 text-sm font-medium text-white hover:bg-amber-700"
          >
            Trotzdem herunterladen
          </button>
        </div>
      </div>
    </div>
  );
}

function JobKarte({
  job, offen, aufUmschalten, aufAenderung,
}: { job: Job; offen: boolean; aufUmschalten: () => void; aufAenderung: () => void }) {
  const zustand = ZUSTAND_TEXT[job.zustand];
  const laeuftNoch = ['wartet', 'laeuft', 'braucht_eingabe'].includes(job.zustand);

  return (
    <div className="rounded border border-gray-200 bg-white">
      <div className="flex flex-wrap items-center justify-between gap-3 p-4">
        <button type="button" onClick={aufUmschalten} className="min-w-0 flex-1 text-left">
          <span className="flex flex-wrap items-center gap-2">
            <span className={`rounded px-2 py-0.5 text-xs font-medium ${zustand.klasse}`}>
              {zustand.text}
            </span>
            <span className="font-medium text-gray-900">{job.befehl}</span>
            <span className="text-sm text-gray-500">{job.profil_slug}</span>
          </span>
          {job.meldung && (
            <span className="mt-1 block text-sm text-gray-700">{job.meldung}</span>
          )}
        </button>

        <div className="flex flex-wrap gap-2">
          {job.zustand === 'braucht_eingabe' && (
            <button
              type="button"
              onClick={() => void api.jobs.eingabe(job.id).then(aufAenderung)}
              className="flex items-center gap-2 rounded bg-amber-600 px-3 py-2 text-sm font-medium text-white"
            >
              <Hand className="h-4 w-4" />
              Erledigt, weiter
            </button>
          )}
          {laeuftNoch && (
            <button
              type="button"
              onClick={() => void api.jobs.abbrechen(job.id).then(aufAenderung)}
              className="flex items-center gap-2 rounded border border-gray-300 px-3 py-2 text-sm text-red-700 hover:bg-red-50"
            >
              <Ban className="h-4 w-4" />
              Abbrechen
            </button>
          )}
        </div>
      </div>

      {job.wartet_bis && <Wartehinweis bis={job.wartet_bis} grund={job.wartegrund} />}

      {job.zustand === 'braucht_eingabe' && (
        <div className="border-t border-amber-200 bg-amber-50 p-4">
          <p className="mb-3 flex items-start gap-2 text-sm text-amber-900">
            <AlertTriangle className="mt-0.5 h-4 w-4 flex-shrink-0" />
            <span>
              Der Lauf wartet auf dich – vermutlich ein Captcha oder eine Bestätigung.
              Löse es in der Browsersicht und klicke dann „Erledigt, weiter".
            </span>
          </p>
          <a
            href="/browsersicht/vnc.html?autoconnect=1&resize=scale"
            target="_blank"
            rel="noreferrer"
            className="inline-block rounded bg-primary-custom px-4 py-2 text-sm font-medium"
          >
            Browsersicht öffnen
          </a>
        </div>
      )}

      {job.zustand === 'pruefen' && (
        <div className="border-t border-orange-200 bg-orange-50 p-4 text-sm text-orange-900">
          <strong>Dieser Lauf braucht eine Prüfung von Hand.</strong> Bitte auf
          kleinanzeigen.de nachsehen, was tatsächlich passiert ist – lokaler und
          entfernter Zustand können auseinanderlaufen.
        </div>
      )}

      {offen && <JobLog jobId={job.id} laeuftNoch={laeuftNoch} />}
    </div>
  );
}

/**
 * Zeigt an, dass ein Lauf ABSICHTLICH wartet, und wie lange noch.
 *
 * Ohne das steht ein Job minutenlang auf "wartet", ohne Grund - im ersten Test
 * mit einem echten Konto wurde das für ein Hängen gehalten. Eine Funktion, die
 * bremst, muss sagen dass und warum sie bremst.
 */
function Wartehinweis({ bis, grund }: { bis: string; grund: string | null }) {
  const [rest, setRest] = useState(() => Math.max(0, (Date.parse(bis) - Date.now()) / 1000));

  useEffect(() => {
    const timer = window.setInterval(
      () => setRest(Math.max(0, (Date.parse(bis) - Date.now()) / 1000)),
      1000,
    );
    return () => window.clearInterval(timer);
  }, [bis]);

  const sekunden = Math.ceil(rest);
  const minuten = Math.ceil(rest / 60);
  const text = rest >= 90
    ? `noch ${minuten} Minuten`
    : `noch ${sekunden} ${sekunden === 1 ? 'Sekunde' : 'Sekunden'}`;

  return (
    <div className="border-t border-blue-200 bg-blue-50 p-4">
      <p className="flex items-start gap-2 text-sm text-blue-900">
        <Hourglass className="mt-0.5 h-4 w-4 flex-shrink-0" />
        <span>
          <strong>Wartet absichtlich – {text}.</strong>
          {grund && <span className="mt-1 block">{grund}</span>}
          <span className="mt-1 block text-blue-800">
            Kein Fehler. Der Abstand lässt sich in den Einstellungen ändern.
          </span>
        </span>
      </p>
    </div>
  );
}

function JobLog({ jobId, laeuftNoch }: { jobId: number; laeuftNoch: boolean }) {
  const [zeilen, setZeilen] = useState<LogZeile[]>([]);
  const ende = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    let abgebrochen = false;

    void api.jobs.log(jobId).then(anfang => {
      if (!abgebrochen) setZeilen(anfang);
    });

    if (!laeuftNoch) return () => { abgebrochen = true; };

    // Server-Sent-Events statt Abfragen im Takt: Die Ausgabe kommt so
    // unmittelbar an, und der Browser verbindet bei Abbruch selbst neu.
    const quelle = new EventSource(api.jobs.stromUrl(jobId));
    quelle.addEventListener('log', (e: MessageEvent<string>) => {
      const zeile = JSON.parse(e.data) as LogZeile;
      setZeilen(alt => (alt.some(z => z.id === zeile.id) ? alt : [...alt, zeile]));
    });
    quelle.addEventListener('ende', () => quelle.close());

    return () => { abgebrochen = true; quelle.close(); };
  }, [jobId, laeuftNoch]);

  useEffect(() => {
    ende.current?.scrollIntoView({ block: 'end' });
  }, [zeilen]);

  const farbe = (stufe: LogZeile['stufe']) =>
    stufe === 'fehler' ? 'text-red-400'
      : stufe === 'warnung' ? 'text-amber-300'
        : stufe === 'debug' ? 'text-gray-500' : 'text-gray-200';

  return (
    <div className="border-t border-gray-200">
      {/* Eigener Scrollbereich: Ein Lauf erzeugt hunderte Zeilen, die die
          Seite sonst endlos lang machen. overflow-x-auto statt Umbruch, damit
          die Ausrichtung der Bot-Ausgabe erhalten bleibt. */}
      <div className="max-h-80 overflow-auto bg-gray-900 p-3 font-mono text-xs">
        {zeilen.length === 0 && <p className="text-gray-500">Noch keine Ausgabe.</p>}
        {zeilen.map(z => (
          <div key={z.id} className={`whitespace-pre ${farbe(z.stufe)}`}>{z.text}</div>
        ))}
        <div ref={ende} />
      </div>
    </div>
  );
}
