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
//   * Läufe: Vorgangs-Icon, kurzer Anzeigenbezug und Zeit - mit Link auf die
//     Warteschlange. Der Zustand bleibt am Punkt für Screenreader, aber nicht
//     als zusätzliche Textspalte.
//
// Was hier NICHT passiert: Ein Lauf, der den Menschen braucht
// (`braucht_eingabe`), bleibt zusätzlich als sichtbare Pille daneben stehen -
// er darf nicht hinter einem Klick verschwinden. Das Protokoll und die
// Captcha-Übernahme liegen weiterhin nur auf der Warteschlangen-Seite.

import { useEffect, useRef, useState } from 'react';
import { AlertTriangle, Bell, Info, Lightbulb, X } from 'lucide-react';
import type { LucideIcon } from 'lucide-react';
import { api } from '../services/api';
import { anzeigeBezug, befehlIcon, befehlText } from '../jobText';
import { useMeldungen } from '../context/useMeldungen';
import type { MeldungTon } from '../context/meldungenKontext';
import type { BestandsAnzeige, Job, JobZustand } from '../types';
import { useWartezeit, warteHinweisText } from './Wartezeit';
import { Wartehinweis } from './Wartehinweis';

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

function GlockeLaufzeile({
  job,
  titel,
  bezug,
  aufOeffnen,
}: {
  job: Job;
  titel: string;
  bezug: string | null;
  aufOeffnen: () => void;
}) {
  const wartezeit = useWartezeit(job.wartet_bis);
  const warteText = wartezeit ? `, ${warteHinweisText(wartezeit, job.wartegrund)}` : '';
  const Icon = befehlIcon(job.befehl);
  const istAktiv = AKTIV.has(job.zustand);

  return (
    <button
      type="button"
      onClick={aufOeffnen}
      className={`glocke-zeile ${job.zustand === 'fertig' ? 'glocke-zeile-fertig' : ''}`}
      role="menuitem"
      aria-label={`${titel}, ${befehlText(job.befehl)}, ${ZUSTAND_TEXT[job.zustand]}${warteText}`}
      title={`${befehlText(job.befehl)}${bezug ? ` · ${bezug}` : ''} · ${ZUSTAND_TEXT[job.zustand]}${warteText}`}
    >
      <span
        className={`status-punkt ${ZUSTAND_PUNKT[job.zustand]} ${istAktiv ? 'status-punkt-aktiv' : ''}`}
        role="img"
        aria-label={ZUSTAND_TEXT[job.zustand]}
      />
      <Icon className="h-4 w-4 flex-shrink-0 text-leise" aria-hidden />
      <span className="glocke-zeile-inhalt min-w-0 flex-1">
        <span className="glocke-zeile-titel block truncate text-stark">{titel}</span>
        {wartezeit && <Wartehinweis restzeit={wartezeit} grund={job.wartegrund} kompakt />}
      </span>
      <span className="flex-shrink-0 self-start text-xs text-leise">{zeitText(job.eingereicht_am)}</span>
    </button>
  );
}

export function Glocke({ aufZiel }: { aufZiel: (ziel: string) => void }) {
  const [jobs, setJobs] = useState<Job[]>([]);
  const [anzeigen, setAnzeigen] = useState<BestandsAnzeige[]>([]);
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

        // Der Job trägt nur Profil und Dateigrenze/ID. Die Titel kommen aus
        // dem Bestand. Pro Profil getrennt laden, damit die Glocke auch bei
        // mehreren Konten denselben Bezug wie die Warteschlange zeigt.
        const profile = [...new Set(liste.map(job => job.profil_slug))];
        const bestaende = (await Promise.all(profile.map(async profil => {
          try {
            return await api.bestand.liste(profil);
          } catch {
            return [];
          }
        }))).flat();
        if (!tot) setAnzeigen(bestaende);
      } catch {
        if (!tot) {
          setJobs([]);
          setAnzeigen([]);
        }
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

          {juengste.length === 0 ? (
            <p className="glocke-leer">Noch kein Lauf.</p>
          ) : (
            juengste.map(job => {
              const bezug = anzeigeBezug(job, anzeigen);
              const titel = (bezug ?? befehlText(job.befehl)).replace(/ · #\d+$/, '');
              return (
                <GlockeLaufzeile
                  key={job.id}
                  job={job}
                  titel={titel}
                  bezug={bezug}
                  aufOeffnen={zumProtokoll}
                />
              );
            })
          )}
          <button type="button" onClick={zumProtokoll} className="glocke-fuss" role="menuitem">
            Zur Warteschlange
          </button>
        </div>
      )}
    </div>
  );
}
