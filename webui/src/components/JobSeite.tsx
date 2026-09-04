// SPDX-FileCopyrightText: © Anzeigen-Studio contributors
// SPDX-License-Identifier: AGPL-3.0-or-later
//
// Bausteine für Läufe (AP-2.8, AP-1.7, umgebaut AP-2.31).
//
// Hier liegen die wiederverwendbaren Teile: die Lauf-Karte (`JobKarte`) mit
// Protokoll, Captcha-Übernahme und Abbruch, und der Start-Block (`LaufStarten`)
// mit den Befehlskacheln. Die Seite selbst ist `WarteschlangeSeite` - sie setzt
// diese Teile queue-first zusammen. „Neue Anzeige" nutzt `JobKarte` kompakt.

import { useEffect, useRef, useState } from 'react';
import { AlertTriangle, Ban, Hand, Hourglass, Loader2, Play } from 'lucide-react';
import { api, ApiFehler } from '../services/api';
import { useProfil } from '../context/useProfil';
import { befehlIcon, befehlText } from '../jobText';
import type { BestandsAnzeige, Job, JobZustand, LogZeile } from '../types';
import { Hinweis } from './Hinweis';

/** Nur Befehle, die ohne weitere Eingaben sinnvoll sind. */
const BEFEHLE: { id: string; label: string; hinweis: string; schreibend: boolean }[] = [
  { id: 'verify', label: 'Prüfen', hinweis: 'Prüft nur die Konfiguration. Kein Zugriff aufs Konto.', schreibend: false },
  { id: 'diagnose', label: 'Diagnose', hinweis: 'Prüft die Browserverbindung.', schreibend: false },
  { id: 'download', label: 'Herunterladen', hinweis: 'Lädt die eigenen Anzeigen. Meldet sich an.', schreibend: false },
  { id: 'publish', label: 'Veröffentlichen', hinweis: 'Stellt Anzeigen auf kleinanzeigen.de ein.', schreibend: true },
  { id: 'extend', label: 'Verlängern', hinweis: 'Verlängert Anzeigen im Acht-Tage-Fenster.', schreibend: true },
];

const ZUSTAND_TEXT: Record<JobZustand, { text: string; klasse: string }> = {
  wartet: { text: 'wartet', klasse: 'merkmal merkmal-grau' },
  laeuft: { text: 'läuft', klasse: 'merkmal merkmal-blau' },
  braucht_eingabe: { text: 'braucht dich', klasse: 'merkmal merkmal-gelb' },
  fertig: { text: 'fertig', klasse: 'merkmal merkmal-gruen' },
  pruefen: { text: 'prüfen', klasse: 'merkmal merkmal-gelb' },
  gescheitert: { text: 'gescheitert', klasse: 'merkmal merkmal-rot' },
  abgebrochen: { text: 'abgebrochen', klasse: 'merkmal merkmal-grau' },
};

/** Farbpunkt statt Badge, wenn die Karte schmal wird (AP-2.32). Gleiche
 *  Farben wie `status-punkt-*` in Glocke und Dashboard. */
const ZUSTAND_PUNKT: Record<JobZustand, string> = {
  wartet: 'status-punkt-grau',
  laeuft: 'status-punkt-gruen',
  braucht_eingabe: 'status-punkt-gelb',
  fertig: 'status-punkt-gruen',
  pruefen: 'status-punkt-gelb',
  gescheitert: 'status-punkt-rot',
  abgebrochen: 'status-punkt-grau',
};

function kurzZeit(iso: string | null): string {
  if (!iso) return '';
  const zeitpunkt = new Date(iso);
  if (Number.isNaN(zeitpunkt.getTime())) return '';
  return zeitpunkt.toLocaleString('de-DE', {
    day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit',
  });
}

/**
 * Der Start-Block: Befehlskacheln, die einen Lauf einreihen (AP-2.31).
 *
 * Auf der Warteschlangen-Seite steht er sekundär und eingeklappt - primär ist
 * die Queue selbst. `aufEingereiht` bekommt die Id des frisch eingereihten
 * Laufs, damit die Seite ihn gleich aufklappen kann.
 */
export function LaufStarten({ aufEingereiht }: { aufEingereiht?: (jobId: number) => void }) {
  const { profile, aktiv } = useProfil();
  const gewaehlt = aktiv?.slug ?? '';
  const [startet, setStartet] = useState<string | null>(null);
  const [fehler, setFehler] = useState<string | null>(null);
  const [warnung, setWarnung] = useState<BestandsAnzeige[] | null>(null);

  const einreihen = async (befehl: string) => {
    setFehler(null);
    setStartet(befehl);
    try {
      const job = await api.jobs.starten(gewaehlt, befehl);
      aufEingereiht?.(job.id);
    } catch (ursache) {
      setFehler(ursache instanceof ApiFehler ? ursache.message : 'Unbekannter Fehler.');
    } finally {
      setStartet(null);
    }
  };

  // Vor dem Herunterladen nachsehen, ob lokale Änderungen überschrieben würden
  // (AP-3.1). Wer etwas geändert hat, soll das vorher erfahren, nicht hinterher.
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
      // Die Prüfung ist eine Vorsichtsmaßnahme, keine Voraussetzung.
    } finally {
      setStartet(null);
    }
    await einreihen(befehl);
  };

  if (profile.length === 0) {
    return (
      <p className="hinweis hinweis-warn">
        Zuerst ein Profil anlegen und Zugangsdaten hinterlegen.
      </p>
    );
  }

  return (
    <div>
      <p className="mb-3 text-sm text-normal">
        Läuft für <span className="font-medium text-stark">{aktiv?.anzeigename}</span>.
        Umschalten geht links in der Seitenleiste.
      </p>

      <p className="mb-3 text-xs text-leise">
        Läufe desselben Profils werden nacheinander abgearbeitet, mit einem
        Mindestabstand dazwischen. Ein Lauf kann deshalb ein bis zwei Minuten
        warten, bevor er startet – das ist Absicht und wird oben angezeigt.
      </p>

      <Hinweis id="jobseite-alle-oder-keine" ton="warn" className="mb-3 text-xs">
        <span className="font-medium">Von hier aus gilt: alle oder keine.</span>{' '}
        „Veröffentlichen" stellt <span className="font-medium">alle</span> lokal
        angelegten Anzeigen ein, die noch nicht online sind – einzeln geht das im
        Editor über „Veröffentlichen", und nur dort siehst du vorher, welche es trifft.
        „Verlängern" findet derzeit gar keine Anzeigen: Heruntergeladene liegen in
        einem Ordner, den der Lauf nicht durchsucht.
      </Hinweis>

      {fehler && (
        <p role="alert" className="mb-3 hinweis hinweis-fehler">
          {fehler}
        </p>
      )}

      <div className="grid gap-2 sm:grid-cols-2">
        {BEFEHLE.map(b => (
          <button
            key={b.id}
            type="button"
            disabled={startet !== null}
            onClick={() => void starten(b.id)}
            className={`kachel flex items-start gap-3 text-left disabled:cursor-not-allowed disabled:opacity-60
                        ${b.schreibend ? 'kachel-betont' : ''}`}
          >
            <Play className="mt-0.5 h-4 w-4 flex-shrink-0 text-primary-custom" />
            <span className="min-w-0">
              <span className="block text-sm font-medium text-stark">
                {startet === b.id ? 'Wird eingereiht …' : b.label}
                {b.schreibend && (
                  <span className="ml-2 text-xs font-normal text-amber-800">
                    verändert etwas auf der Plattform
                  </span>
                )}
              </span>
              <span className="block text-xs text-leise">{b.hinweis}</span>
            </span>
          </button>
        ))}
      </div>

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
        className="dialog"
      >
        <div className="mb-3 flex items-start gap-3">
          <AlertTriangle className="mt-0.5 h-5 w-5 flex-shrink-0 text-amber-600" aria-hidden />
          <div className="min-w-0">
            <h2 id="warnung-titel" className="font-semibold text-stark">
              Lokale Änderungen gehen verloren
            </h2>
            <p className="mt-1 text-sm text-normal">
              Beim Herunterladen wird der Stand der Plattform übernommen.
              {' '}
              {anzeigen.length === 1
                ? 'Eine Anzeige wurde hier geändert und wird überschrieben:'
                : `${anzeigen.length} Anzeigen wurden hier geändert und werden überschrieben:`}
            </p>
          </div>
        </div>

        <ul className="mb-4 max-h-48 overflow-y-auto rounded-xl p-2 text-sm" style={{ background: 'var(--canvas)', border: '1px solid var(--karte-rand)' }}>
          {anzeigen.map(a => (
            <li key={a.datei} className="truncate py-0.5 text-normal">{a.titel}</li>
          ))}
        </ul>

        <p className="mb-4 text-xs text-leise">
          Erhalten bleiben nur die Automatikfelder: Preisautomatik, Abstand zur
          Neueinstellung und die beiden Zähler.
        </p>

        <div className="flex flex-col-reverse gap-2 sm:flex-row sm:justify-end">
          <button
            type="button"
            onClick={aufAbbrechen}
            className="btn-ghost"
          >
            Abbrechen
          </button>
          <button
            type="button"
            onClick={aufWeiter}
            className="btn-primaer"
          >
            Trotzdem herunterladen
          </button>
        </div>
      </div>
    </div>
  );
}

/**
 * Woran der Lauf gerade ist, und seit wann (AP-2.8).
 *
 * Die Dauer ist der eigentliche Punkt. „Bild 2/3 hochladen" beruhigt;
 * dieselbe Zeile seit vier Minuten sagt, dass etwas klemmt.
 */
function Phasenzeile({ text, seit }: { text: string; seit: string | null }) {
  const [jetzt, setJetzt] = useState(() => Date.now());
  useEffect(() => {
    const timer = window.setInterval(() => setJetzt(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, []);

  const sekunden = seit ? Math.max(0, Math.round((jetzt - new Date(seit).getTime()) / 1000)) : null;
  const dauer = sekunden === null || Number.isNaN(sekunden)
    ? null
    : sekunden < 60
      ? `${sekunden} s`
      : `${Math.floor(sekunden / 60)} min ${sekunden % 60} s`;

  return (
    <span className="mt-1 flex flex-wrap items-center gap-x-2 text-sm text-blue-800">
      <Loader2 className="h-3.5 w-3.5 flex-shrink-0 animate-spin" aria-hidden />
      <span className="min-w-0 break-words">{text}</span>
      {dauer && <span className="flex-shrink-0 text-xs text-leise">seit {dauer}</span>}
    </span>
  );
}

/**
 * Ein Lauf als Karte.
 *
 * `kompakt` ist die Fassung für „Neue Anzeige" (AP-2.21): Zustand, Befehl,
 * Wartehinweis und Abbrechen - ohne Protokoll, ohne Captcha-Übernahme.
 * `bezug` benennt die betroffene Anzeige (AP-2.29/2.31), falls bekannt.
 */
export function JobKarte({
  job, offen, aufUmschalten, aufAenderung, kompakt = false, bezug = null,
}: {
  job: Job;
  offen: boolean;
  aufUmschalten: () => void;
  aufAenderung: () => void;
  kompakt?: boolean;
  bezug?: string | null;
}) {
  const zustand = ZUSTAND_TEXT[job.zustand];
  const punktKlasse = ZUSTAND_PUNKT[job.zustand] ?? 'status-punkt-grau';
  const laeuftNoch = ['wartet', 'laeuft', 'braucht_eingabe'].includes(job.zustand);
  const Icon = befehlIcon(job.befehl);
  // Primärzeile ist der Anzeigentitel (AP-2.32); fehlt der Bezug - ein Lauf
  // fürs ganze Profil wie „Herunterladen" -, tritt der Befehlsname an seine
  // Stelle. Der Befehl steht sonst nur noch leise in der Meta-Zeile.
  const titel = bezug ?? befehlText(job.befehl);
  const meta = [
    job.profil_slug,
    kurzZeit(job.beendet_am ?? job.eingereicht_am),
    bezug ? befehlText(job.befehl) : null,
  ].filter(Boolean).join(' · ');

  const kopf = (
    <span className="flex items-center gap-3">
      {/* AP-2.32 Follow-up: Symbol mittig zur zweizeiligen Karte, ~20% größer (16→19.2px ≈ h-5). */}
      <Icon className="h-5 w-5 flex-shrink-0 text-leise" aria-hidden />
      <span className="min-w-0 flex-1">
        <span className="flex flex-wrap items-center gap-x-2 gap-y-1">
          <span className="truncate font-semibold text-stark">{titel}</span>
          {/* Badge auf breiter Karte, farbiger Punkt sobald es eng wird. */}
          <span className={`${zustand.klasse} hidden flex-shrink-0 sm:inline-flex`}>
            {zustand.text}
          </span>
          <span
            className={`status-punkt ${punktKlasse} flex-shrink-0 sm:hidden`}
            role="img"
            aria-label={zustand.text}
          />
        </span>
        <span className="mt-0.5 block truncate text-xs text-leise">{meta}</span>
        {job.meldung && (
          <span className="mt-1 block text-sm text-normal">{job.meldung}</span>
        )}
        {laeuftNoch && job.phase_text && (
          <Phasenzeile text={job.phase_text} seit={job.phase_seit} />
        )}
      </span>
    </span>
  );

  return (
    <div className="karte">
      <div className="flex flex-wrap items-center justify-between gap-3 p-4">
        {kompakt ? (
          <div className="min-w-0 flex-1">{kopf}</div>
        ) : (
          <button type="button" onClick={aufUmschalten} className="min-w-0 flex-1 text-left">
            {kopf}
          </button>
        )}

        <div className="flex flex-wrap gap-2">
          {!kompakt && job.zustand === 'braucht_eingabe' && (
            <button
              type="button"
              onClick={() => void api.jobs.eingabe(job.id).then(aufAenderung)}
              className="btn-primaer"
            >
              <Hand className="h-4 w-4" />
              Erledigt, weiter
            </button>
          )}
          {laeuftNoch && (
            <button
              type="button"
              onClick={() => void api.jobs.abbrechen(job.id).then(aufAenderung)}
              className="btn-ghost"
            >
              <Ban className="h-4 w-4" />
              Abbrechen
            </button>
          )}
        </div>
      </div>

      {job.wartet_bis && <Wartehinweis bis={job.wartet_bis} grund={job.wartegrund} />}

      {!kompakt && job.zustand === 'braucht_eingabe' && (
        <div className="hinweis hinweis-warn" style={{ borderRadius: 0, border: 0, borderTop: '1px solid var(--hinweis-warn-rand)' }}>
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
            className="inline-block btn-primaer"
          >
            Browsersicht öffnen
          </a>
        </div>
      )}

      {!kompakt && job.zustand === 'pruefen' && (
        <div className="hinweis hinweis-warn text-sm" style={{ borderRadius: 0, border: 0, borderTop: '1px solid var(--hinweis-warn-rand)' }}>
          <strong>Dieser Lauf braucht eine Prüfung von Hand.</strong> Bitte auf
          kleinanzeigen.de nachsehen, was tatsächlich passiert ist – lokaler und
          entfernter Zustand können auseinanderlaufen.
        </div>
      )}

      {!kompakt && offen && <JobLog jobId={job.id} laeuftNoch={laeuftNoch} />}
    </div>
  );
}

/**
 * Zeigt an, dass ein Lauf ABSICHTLICH wartet, und wie lange noch.
 *
 * Ohne das steht ein Job minutenlang auf "wartet", ohne Grund. Eine Funktion,
 * die bremst, muss sagen dass und warum sie bremst.
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
    <div className="hinweis" style={{ borderRadius: 0, border: 0, borderTop: '1px solid var(--hinweis-ok-rand)' }}>
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
        : stufe === 'debug' ? 'text-leise' : 'text-white/80';

  return (
    <div style={{ borderTop: '1px solid var(--karte-rand)' }}>
      <div className="max-h-80 overflow-auto bg-gray-900 p-3 font-mono text-xs">
        {zeilen.length === 0 && <p className="text-leise">Noch keine Ausgabe.</p>}
        {zeilen.map(z => (
          <div key={z.id} className={`whitespace-pre ${farbe(z.stufe)}`}>{z.text}</div>
        ))}
        <div ref={ende} />
      </div>
    </div>
  );
}
