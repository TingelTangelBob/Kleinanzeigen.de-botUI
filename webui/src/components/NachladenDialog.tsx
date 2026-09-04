// SPDX-FileCopyrightText: © Anzeigen-Studio contributors
// SPDX-License-Identifier: AGPL-3.0-or-later
//
// Ältere Anzeigen über eingefügte Links holen (AP-3.7).
//
// Gedacht für den Weg, den der Projektinhaber beschrieben hat: alte
// Nachrichtenverläufe durchgehen, die Links der verkauften Anzeigen kopieren,
// hier einfügen. Was dabei mitkommt, ist selten sauber - deshalb frisst das
// Feld ganze Absätze und sucht sich die Nummern heraus.
//
// Eine Grenze gehört hierher und nicht in eine Fußnote: Was Kleinanzeigen
// gelöscht hat, ist weg. Steht das nicht vorher da, liest sich ein leeres
// Ergebnis wie ein Fehler des Programms.

import { useState } from 'react';
import { AlertTriangle, Download, Info } from 'lucide-react';
import { api, ApiFehler } from '../services/api';

interface Props {
  profil: string;
  aufSchliessen: () => void;
}

interface Fund {
  neu: number[];
  schon_vorhanden: number[];
  unlesbare_zeilen: string[];
}

export function NachladenDialog({ profil, aufSchliessen }: Props) {
  const [text, setText] = useState('');
  const [fund, setFund] = useState<Fund | null>(null);
  const [fehler, setFehler] = useState<string | null>(null);
  const [laeuft, setLaeuft] = useState(false);
  const [eingereiht, setEingereiht] = useState<{ job_id: number; nummern: number[] } | null>(null);

  const pruefen = async (roh: string) => {
    setText(roh);
    setFehler(null);
    if (roh.trim() === '') {
      setFund(null);
      return;
    }
    try {
      setFund(await api.bestand.linksLesen(profil, roh));
    } catch {
      // Das Erkennen ist eine Hilfe, kein Muss - ein Fehler hier darf das
      // Einfügen nicht blockieren.
      setFund(null);
    }
  };

  const holen = async () => {
    setLaeuft(true);
    setFehler(null);
    try {
      setEingereiht(await api.bestand.nachladen(profil, text));
    } catch (ursache) {
      setFehler(ursache instanceof ApiFehler ? ursache.message : 'Unbekannter Fehler.');
    } finally {
      setLaeuft(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-end justify-center bg-black/40 p-4 sm:items-center">
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="nachladen-titel"
        className="dialog"
      >
        <h2 id="nachladen-titel" className="mb-1 font-semibold text-stark">
          Anzeigen per Link holen
        </h2>
        <p className="mb-3 text-sm text-normal">
          Beliebige Kleinanzeigen-Adressen oder Anzeigennummern einfügen – auch von anderen.
          Eine pro Zeile, Text drumherum stört nicht. Die Anzeigen landen unter „Von anderen“.
        </p>

        {eingereiht ? (
          <>
            <p className="mb-4 hinweis">
              Lauf {eingereiht.job_id} ist eingereiht und holt {eingereiht.nummern.length}{' '}
              {eingereiht.nummern.length === 1 ? 'Anzeige' : 'Anzeigen'}. Unter Einstellungen →
              Läufe lässt er sich mitlesen.
            </p>
            <div className="flex justify-end">
              <button
                type="button"
                onClick={aufSchliessen}
                className="btn-primaer"
              >
                Schließen
              </button>
            </div>
          </>
        ) : (
          <>
            <label className="block">
              <span className="sr-only">Links oder Nummern</span>
              <textarea
                rows={6}
                value={text}
                onChange={e => void pruefen(e.target.value)}
                placeholder={'https://www.kleinanzeigen.de/s-anzeige/…/3310837392-161-168\n3275022547'}
className="feld"
              />
            </label>

            {fund && (
              <div className="mt-3 space-y-2 text-sm">
                <p className="text-stark">
                  <span className="font-medium">{fund.neu.length}</span>{' '}
                  {fund.neu.length === 1 ? 'Anzeige wird geholt' : 'Anzeigen werden geholt'}
                  {fund.neu.length > 0 && (
                    <span className="block text-xs text-leise">{fund.neu.join(', ')}</span>
                  )}
                </p>
                {fund.schon_vorhanden.length > 0 && (
                  <p className="text-leise">
                    {fund.schon_vorhanden.length} schon im Bestand, wird übersprungen.
                  </p>
                )}
                {fund.unlesbare_zeilen.length > 0 && (
                  <p className="flex items-start gap-1.5 text-xs text-leise">
                    <Info className="mt-0.5 h-3.5 w-3.5 flex-shrink-0" aria-hidden />
                    <span>
                      {fund.unlesbare_zeilen.length}{' '}
                      {fund.unlesbare_zeilen.length === 1 ? 'Zeile enthält' : 'Zeilen enthalten'}{' '}
                      keine Nummer und bleibt außen vor.
                    </span>
                  </p>
                )}
              </div>
            )}

            <p className="hinweis hinweis-warn mt-3 flex items-start gap-2 text-xs">
              <AlertTriangle className="mt-0.5 h-3.5 w-3.5 flex-shrink-0" aria-hidden />
              <span>
                Nur was auf kleinanzeigen.de noch als Seite erreichbar ist, lässt sich holen.
                Endgültig gelöschte Anzeigen kann kein Werkzeug zurückholen – der Lauf meldet
                sie dann einzeln als nicht erreichbar.
              </span>
            </p>

            {fehler && (
              <p role="alert" className="mt-3 hinweis hinweis-fehler">
                {fehler}
              </p>
            )}

            <div className="mt-4 flex flex-col-reverse gap-2 sm:flex-row sm:justify-end">
              <button
                type="button"
                onClick={aufSchliessen}
                className="btn-ghost"
              >
                Abbrechen
              </button>
              <button
                type="button"
                onClick={() => void holen()}
                disabled={laeuft || !fund || fund.neu.length === 0}
                className="flex items-center justify-center gap-2 rounded bg-primary-custom px-4 py-2
                           text-sm font-medium disabled:cursor-not-allowed disabled:opacity-60"
              >
                <Download className="h-4 w-4" aria-hidden />
                {laeuft ? 'Wird eingereiht …' : 'Holen'}
              </button>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
