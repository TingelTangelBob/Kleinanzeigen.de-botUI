// SPDX-FileCopyrightText: © Anzeigen-Studio contributors
// SPDX-License-Identifier: AGPL-3.0-or-later
//
// Kurze Rückfrage vor einem Bot-Lauf. Lese-Läufe dürfen dauerhaft übersprungen
// werden; Vorgänge, die etwas auf kleinanzeigen.de verändern, müssen weiterhin
// jedes Mal ausdrücklich bestätigt werden.

import { useCallback, useState } from 'react';
import { AlertTriangle, Play } from 'lucide-react';

const HINWEIS_AUSBLENDEN_KEY = 'anzeigen-studio:lauf-start-hinweis-aus';

export interface LaufStartDetails {
  titel: string;
  text: string;
  startText?: string;
  /** Plattformänderungen brauchen trotz gespeicherter Präferenz eine Rückfrage. */
  ueberspringenErlaubt?: boolean;
}

type LaufStartAktion = () => void | Promise<void>;

function hinweisAusgeblendet(): boolean {
  try {
    return window.localStorage.getItem(HINWEIS_AUSBLENDEN_KEY) === '1';
  } catch {
    // Eingeschränkte Browser (z. B. privates Fenster mit gesperrtem Speicher)
    // sollen den Lauf nicht verhindern.
    return false;
  }
}

function hinweisAusblenden(): void {
  try {
    window.localStorage.setItem(HINWEIS_AUSBLENDEN_KEY, '1');
  } catch {
    // Nur eine Komforteinstellung. Bei gesperrtem Speicher bleibt der Dialog
    // beim nächsten Lauf sichtbar.
  }
}

export function useLaufStartHinweis() {
  const [anfrage, setAnfrage] = useState<{
    details: LaufStartDetails;
    starten: LaufStartAktion;
  } | null>(null);

  const anfragen = useCallback((details: LaufStartDetails, starten: LaufStartAktion) => {
    if (details.ueberspringenErlaubt !== false && hinweisAusgeblendet()) {
      void starten();
      return;
    }
    setAnfrage({ details, starten });
  }, []);

  const dialog = anfrage ? (
    <LaufStartDialog
      details={anfrage.details}
      aufAbbrechen={() => setAnfrage(null)}
      aufBestaetigen={nichtMehrZeigen => {
        if (nichtMehrZeigen) hinweisAusblenden();
        const starten = anfrage.starten;
        setAnfrage(null);
        void starten();
      }}
    />
  ) : null;

  return { anfragen, dialog };
}

function LaufStartDialog({
  details, aufAbbrechen, aufBestaetigen,
}: {
  details: LaufStartDetails;
  aufAbbrechen: () => void;
  aufBestaetigen: (nichtMehrZeigen: boolean) => void;
}) {
  const [nichtMehrZeigen, setNichtMehrZeigen] = useState(false);
  const ueberspringenErlaubt = details.ueberspringenErlaubt !== false;

  return (
    <div className="fixed inset-0 z-50 flex items-end justify-center bg-black/40 p-4 sm:items-center">
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="lauf-start-titel"
        className="dialog"
      >
        <div className="mb-3 flex items-start gap-3">
          <AlertTriangle
            className="mt-0.5 h-5 w-5 flex-shrink-0"
            style={{ color: 'var(--hinweis-warn-text)' }}
            aria-hidden
          />
          <div className="min-w-0">
            <h2 id="lauf-start-titel" className="font-semibold text-stark">
              {details.titel}
            </h2>
            <p className="mt-1 text-sm text-normal">{details.text}</p>
          </div>
        </div>

        {ueberspringenErlaubt && (
          <label className="mb-4 flex items-start gap-2 text-sm text-normal">
            <input
              type="checkbox"
              checked={nichtMehrZeigen}
              onChange={e => setNichtMehrZeigen(e.target.checked)}
              className="mt-0.5"
            />
            <span>Diesen Hinweis nicht mehr zeigen</span>
          </label>
        )}

        <div className="flex flex-col-reverse gap-2 sm:flex-row sm:justify-end">
          <button type="button" onClick={aufAbbrechen} className="btn-ghost">
            Abbrechen
          </button>
          <button
            type="button"
            onClick={() => aufBestaetigen(nichtMehrZeigen)}
            className="btn-primaer"
          >
            <Play className="h-4 w-4" aria-hidden />
            {details.startText ?? 'Lauf starten'}
          </button>
        </div>
      </div>
    </div>
  );
}
