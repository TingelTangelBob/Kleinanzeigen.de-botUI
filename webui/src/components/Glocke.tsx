// SPDX-FileCopyrightText: © Anzeigen-Studio contributors
// SPDX-License-Identifier: AGPL-3.0-or-later
//
// Meldungen und Lauf-Zustand in der Kopfleiste (AP-2.25, erweitert AP-2.30).
//
// Zwei Dinge sammeln sich hier, damit sie nicht als vollbreite Banner Höhe im
// Seiteninhalt fressen:
//
//   * Tipps, Hinweise und Warnungen der aktuellen Seite (über `useMeldungen`).
//     Farbe und Symbol nach Schwere; Tipps und Hinweise lassen sich wegklicken
//     und bleiben weg, eine Warnung kommt wieder, sobald die Seite sie erneut
//     meldet.
//   * Läufe: „eingereiht", „läuft", „fertig" - mit Link auf die Warteschlange.
//
// Was hier NICHT passiert: Ein Lauf, der den Menschen braucht
// (`braucht_eingabe`), bleibt zusätzlich als sichtbare Pille daneben stehen -
// er darf nicht hinter einem Klick verschwinden. Das Protokoll und die
// Captcha-Übernahme liegen weiterhin nur auf der Warteschlangen-Seite.

import { useEffect, useRef, useState } from 'react';
import { AlertTriangle, Bell, Info, Lightbulb, X } from 'lucide-react';
import type { LucideIcon } from 'lucide-react';
import { api } from '../services/api';
import { befehlText } from '../jobText';
import { useMeldungen } from '../context/useMeldungen';
import type { MeldungTon } from '../context/meldungenKontext';
import type { Job, JobZustand } from '../types';

const AKTIV = new Set<JobZustand>(['wartet', 'laeuft', 'braucht_eingabe']);

const ZUSTAND_TEXT: Record<JobZustand, string> = {
  wartet: 'wartet',
  laeuft: 'läuft',
  braucht_eingabe: 'braucht dich',
  fertig: 'fertig',
  pruefen: 'zu prüfen',
  gescheitert: 'gescheitert',
  abgebrochen: 'abgebrochen',
};

const ZUSTAND_PUNKT: Record<JobZustand, string> = {
  wartet: 'status-punkt-grau',
  laeuft: 'status-punkt-gruen',
  braucht_eingabe: 'status-punkt-gelb',
  fertig: 'status-punkt-gruen',
  pruefen: 'status-punkt-gelb',
  gescheitert: 'status-punkt-rot',
  abgebrochen: 'status-punkt-grau',
};

const MELDUNG_ICON: Record<MeldungTon, LucideIcon> = {
  tipp: Lightbulb,
  hinweis: Info,
  warnung: AlertTriangle,
};

// Als volle Klassennamen, nicht zusammengesetzt: Tailwind entfernt sonst die
// `@layer components`-Regeln, deren Klasse im Quelltext nie wörtlich vorkommt.
const MELDUNG_KLASSE: Record<MeldungTon, string> = {
  tipp: 'glocke-meldung-tipp',
  hinweis: 'glocke-meldung-hinweis',
  warnung: 'glocke-meldung-warnung',
};


function zeitText(iso: string | null): string {
  if (!iso) return '';
  const zeitpunkt = new Date(iso);
  if (Number.isNaN(zeitpunkt.getTime())) return '';
  return zeitpunkt.toLocaleTimeString('de-DE', { hour: '2-digit', minute: '2-digit' });
}

export function Glocke({ aufZiel }: { aufZiel: (ziel: string) => void }) {
  const [jobs, setJobs] = useState<Job[]>([]);
  const [offen, setOffen] = useState(false);
  const [puls, setPuls] = useState(false);
  const huelle = useRef<HTMLDivElement>(null);
  const { meldungen, abweisen } = useMeldungen();

  useEffect(() => {
    let tot = false;
    const laden = async () => {
      try {
        const liste = await api.jobs.liste();
        if (!tot) setJobs(liste);
      } catch {
        if (!tot) setJobs([]);
      }
    };
    void laden();
    const timer = window.setInterval(() => void laden(), 3000);
    return () => { tot = true; window.clearInterval(timer); };
  }, []);

  // Zuklappen bei Klick daneben und mit Escape - sonst steht das Panel offen,
  // während man längst woanders arbeitet.
  useEffect(() => {
    if (!offen) return undefined;
    const aufKlick = (e: MouseEvent) => {
      if (huelle.current && !huelle.current.contains(e.target as Node)) setOffen(false);
    };
    const aufTaste = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setOffen(false);
    };
    document.addEventListener('mousedown', aufKlick);
    document.addEventListener('keydown', aufTaste);
    return () => {
      document.removeEventListener('mousedown', aufKlick);
      document.removeEventListener('keydown', aufTaste);
    };
  }, [offen]);

  const aktive = jobs.filter(j => AKTIV.has(j.zustand));
  const brauchtEingabe = aktive.find(j => j.zustand === 'braucht_eingabe') ?? null;
  const anzahl = aktive.length + meldungen.length;

  // Wird die Zahl größer, kurz pulsen lassen - der einzige Hinweis, wenn das
  // Panel zu ist und eine neue Meldung reinkommt (AP-2.30).
  const vorigeAnzahl = useRef(anzahl);
  useEffect(() => {
    if (anzahl > vorigeAnzahl.current) {
      setPuls(true);
      const t = window.setTimeout(() => setPuls(false), 700);
      vorigeAnzahl.current = anzahl;
      return () => window.clearTimeout(t);
    }
    vorigeAnzahl.current = anzahl;
    return undefined;
  }, [anzahl]);

  // Im Panel: die jüngsten Läufe, egal in welchem Zustand. `eingereicht_am`
  // absteigend - die Liste vom Backend ist schon so sortiert, aber verlassen
  // wollen wir uns hier nicht drauf.
  const juengste = [...jobs]
    .sort((a, b) => (b.eingereicht_am ?? '').localeCompare(a.eingereicht_am ?? ''))
    .slice(0, 6);

  const zumProtokoll = () => {
    setOffen(false);
    aufZiel('warteschlange');
  };

  return (
    <div className="relative flex items-center gap-2" ref={huelle}>
      {brauchtEingabe && (
        <button
          type="button"
          onClick={zumProtokoll}
          className="job-pille job-pille-eingabe"
          title="Zur Warteschlange"
        >
          <span className="status-punkt status-punkt-gelb" />
          Lauf braucht dich
        </button>
      )}

      <button
        type="button"
        onClick={() => setOffen(o => !o)}
        className={`glocke-knopf ${puls ? 'glocke-knopf-puls' : ''}`}
        aria-haspopup="menu"
        aria-expanded={offen}
        aria-label={anzahl > 0 ? `Benachrichtigungen – ${anzahl}` : 'Benachrichtigungen'}
      >
        <Bell className="h-5 w-5" aria-hidden />
        {anzahl > 0 && (
          <span className={`glocke-zahl ${brauchtEingabe ? 'glocke-zahl-eingabe' : ''}`}>
            {anzahl}
          </span>
        )}
      </button>

      {offen && (
        <div className="glocke-panel" role="menu" aria-label="Benachrichtigungen">
          <p className="glocke-kopf">Benachrichtigungen</p>

          {meldungen.length > 0 && (
            <div className="glocke-meldungen">
              {meldungen.map(m => {
                const Icon = MELDUNG_ICON[m.ton];
                return (
                  <div key={m.id} className={`glocke-meldung ${MELDUNG_KLASSE[m.ton]}`}>
                    <Icon className="mt-0.5 h-4 w-4 flex-shrink-0" aria-hidden />
                    <div className="min-w-0 flex-1">
                      <p className="glocke-meldung-titel">{m.titel}</p>
                      <p className="glocke-meldung-text">{m.text}</p>
                    </div>
                    <button
                      type="button"
                      onClick={() => abweisen(m.id)}
                      className="hinweis-schliessen"
                      aria-label={`${m.titel} ausblenden`}
                    >
                      <X className="h-4 w-4" aria-hidden />
                    </button>
                  </div>
                );
              })}
            </div>
          )}

          <p className="glocke-kopf glocke-kopf-zwischen">Läufe</p>
          {juengste.length === 0 ? (
            <p className="glocke-leer">Noch kein Lauf.</p>
          ) : (
            juengste.map(job => (
              <button
                key={job.id}
                type="button"
                onClick={zumProtokoll}
                className="glocke-zeile"
                role="menuitem"
              >
                <span className={`status-punkt ${ZUSTAND_PUNKT[job.zustand]}`} />
                <span className="min-w-0 flex-1 truncate text-stark">{befehlText(job.befehl)}</span>
                <span className="flex-shrink-0 text-xs text-leise">{zeitText(job.eingereicht_am)}</span>
                <span className="flex-shrink-0 text-xs text-normal">{ZUSTAND_TEXT[job.zustand]}</span>
              </button>
            ))
          )}
          <button type="button" onClick={zumProtokoll} className="glocke-fuss" role="menuitem">
            Zur Warteschlange
          </button>
        </div>
      )}
    </div>
  );
}
