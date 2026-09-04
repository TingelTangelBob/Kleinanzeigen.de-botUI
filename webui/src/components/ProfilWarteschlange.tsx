// SPDX-FileCopyrightText: © Anzeigen-Studio contributors
// SPDX-License-Identifier: AGPL-3.0-or-later
//
// Die Warteschlange des aktuellen Profils, kompakt (AP-2.21).
//
// Wozu: „Neue Anzeige" reiht selbst keinen Lauf ein, aber die Queue ist je
// Profil einspurig. Wer hier gerade eine Anzeige anlegt, während ein
// Download läuft, wartet danach auf etwas, wovon er auf dieser Seite nichts
// sieht. Ein wartender Lauf, den man nicht kennt, sieht aus wie ein Hänger.
//
// Was hier NICHT steht: das Protokoll und die Captcha-Übernahme. Beides
// gehört auf die Warteschlangen-Seite, und zwar nur dorthin - zwei Konsolen
// für denselben Lauf wären zwei Wahrheiten. Diese Liste zeigt nur, was noch
// aussteht, und lässt Wartendes abbrechen.

import { useCallback, useEffect, useState } from 'react';
import { ArrowRight } from 'lucide-react';
import { api, ApiFehler } from '../services/api';
import type { Job } from '../types';
import { JobKarte } from './JobSeite';

/** Nur was noch aussteht. Fertige und gescheiterte Läufe wären eine Wand. */
const OFFEN = new Set(['wartet', 'laeuft', 'braucht_eingabe']);

export function ProfilWarteschlange({ profil }: { profil: string }) {
  const [jobs, setJobs] = useState<Job[]>([]);
  const [fehler, setFehler] = useState<string | null>(null);

  const laden = useCallback(async () => {
    try {
      const liste = await api.jobs.liste(profil);
      setJobs(liste.filter(j => OFFEN.has(j.zustand)));
      setFehler(null);
    } catch (ursache) {
      setFehler(ursache instanceof ApiFehler ? ursache.message : 'Unbekannter Fehler.');
    }
  }, [profil]);

  useEffect(() => {
    void laden();
  }, [laden]);

  // Derselbe Takt wie auf der Warteschlangen-Seite. Nur solange etwas offen ist -
  // eine leere Warteschlange muss nicht im Sekundentakt bestätigt werden.
  useEffect(() => {
    if (jobs.length === 0) return undefined;
    const timer = window.setInterval(() => void laden(), 2000);
    return () => window.clearInterval(timer);
  }, [jobs.length, laden]);

  // Ohne offene Läufe verschwindet der Abschnitt ganz. Eine Überschrift über
  // einer leeren Liste erklärt niemandem, wofür sie da wäre.
  if (jobs.length === 0 && !fehler) return null;

  // Lässt sich die Liste nicht lesen, bleibt es bei einer stillen Zeile:
  // ohne `role="alert"` und ohne Warnfarbe. Diese Seite legt Anzeigen an,
  // dafür braucht sie die Warteschlange nicht - und der laute Kanal gehört
  // den Fehlern des Formulars, sonst stehen zwei Meldungen um dieselbe
  // Aufmerksamkeit.
  if (jobs.length === 0) {
    return (
      <p className="lesebreite mb-6 text-xs text-leise">
        Die Warteschlange ließ sich nicht lesen: {fehler}
      </p>
    );
  }

  return (
    <section className="mb-6">
      <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
        <h2 className="text-sm font-medium text-normal">
          {jobs.length === 1 ? 'Ein Lauf steht aus' : `${jobs.length} Läufe stehen aus`}
        </h2>
        <a href="#warteschlange" className="btn-leise text-xs">
          Protokoll und Captcha <ArrowRight className="h-3.5 w-3.5" aria-hidden />
        </a>
      </div>

      <p className="lesebreite mb-2 text-xs text-leise">
        Je Profil läuft ein Lauf nach dem anderen. Ein neuer reiht sich dahinter ein.
      </p>

      {fehler && (
        <p className="lesebreite mb-2 text-xs text-leise">
          Zuletzt nicht erreichbar: {fehler}
        </p>
      )}

      <div className="space-y-2">
        {jobs.map(job => (
          <JobKarte
            key={job.id}
            job={job}
            kompakt
            offen={false}
            aufUmschalten={() => undefined}
            aufAenderung={() => void laden()}
          />
        ))}
      </div>
    </section>
  );
}
