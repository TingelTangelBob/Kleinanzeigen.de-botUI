// SPDX-FileCopyrightText: © Anzeigen-Studio contributors
// SPDX-License-Identifier: AGPL-3.0-or-later
//
// Kategorie suchen statt Nummernpfad tippen (AP-2.7).
//
// Die Liste kommt vollständig aus `categories.yaml` des Bots und wird hier
// gefiltert. Rund 520 Einträge sind für den Browser nichts, und jeder
// Tastendruck wirkt sofort - eine Suche über das Netz fühlte sich träge an,
// ohne etwas zu gewinnen.
//
// Ein Fall gehört ausdrücklich behandelt: Heruntergeladene Anzeigen tragen
// mitunter Werte, die die Liste nicht kennt (beobachtet an `161/278/laptop`,
// während die Liste nur `161/278` führt). So einer wird angezeigt und
// stehengelassen - ersetzt wird er nur, wenn jemand etwas auswählt.

import { useEffect, useMemo, useRef, useState } from 'react';
import { AlertTriangle, Check, Search } from 'lucide-react';
import { api } from '../services/api';
import type { Kategorie } from '../types';

const MAX_TREFFER = 40;

interface Props {
  wert: string;
  aufAenderung: (wert: string) => void;
}

export function KategorieWahl({ wert, aufAenderung }: Props) {
  const [alle, setAlle] = useState<Kategorie[]>([]);
  const [suche, setSuche] = useState('');
  const [offen, setOffen] = useState(false);
  const huelle = useRef<HTMLDivElement>(null);

  useEffect(() => {
    void (async () => {
      try {
        setAlle(await api.katalog.kategorien());
      } catch {
        // Ohne Liste bleibt das Feld ein Textfeld - unschön, aber bedienbar.
        setAlle([]);
      }
    })();
  }, []);

  // Klick daneben schließt die Liste.
  useEffect(() => {
    if (!offen) return undefined;
    const aufKlick = (e: MouseEvent) => {
      if (huelle.current && !huelle.current.contains(e.target as Node)) setOffen(false);
    };
    document.addEventListener('mousedown', aufKlick);
    return () => document.removeEventListener('mousedown', aufKlick);
  }, [offen]);

  const bekannt = useMemo(() => alle.find(k => k.wert === wert) ?? null, [alle, wert]);

  const treffer = useMemo(() => {
    const begriff = suche.trim().toLowerCase();
    if (!begriff) return alle.slice(0, MAX_TREFFER);
    return alle
      .filter(k => k.name.toLowerCase().includes(begriff) || k.wert.includes(begriff))
      .slice(0, MAX_TREFFER);
  }, [alle, suche]);

  return (
    <div ref={huelle} className="relative">
      <span className="text-sm font-medium text-gray-700">Kategorie</span>

      <div className="mt-1 rounded border border-gray-300 px-3 py-2">
        {bekannt ? (
          <span className="block truncate text-sm text-gray-900">{bekannt.name}</span>
        ) : wert ? (
          <span className="flex items-start gap-1.5 text-sm text-amber-900">
            <AlertTriangle className="mt-0.5 h-3.5 w-3.5 flex-shrink-0" aria-hidden />
            <span className="min-w-0">
              <span className="block truncate">{wert}</span>
              <span className="block text-xs">
                Nicht in der Liste. Bleibt so, bis du etwas anderes wählst.
              </span>
            </span>
          </span>
        ) : (
          <span className="block text-sm text-gray-500">Keine Kategorie gesetzt</span>
        )}
        <span className="mt-0.5 block text-xs text-gray-500">{wert || '—'}</span>
      </div>

      <label className="relative mt-2 block">
        <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-gray-400" aria-hidden />
        <span className="sr-only">Kategorie suchen</span>
        <input
          type="search"
          value={suche}
          onFocus={() => setOffen(true)}
          onChange={e => { setSuche(e.target.value); setOffen(true); }}
          onKeyDown={e => { if (e.key === 'Escape') setOffen(false); }}
          placeholder={alle.length > 0 ? 'Kategorie suchen …' : 'Liste nicht verfügbar'}
          disabled={alle.length === 0}
          className="w-full rounded border border-gray-300 py-2 pl-9 pr-3 text-sm
                     focus:border-primary-custom focus:outline-none focus:ring-1 focus:ring-primary-custom"
        />
      </label>

      {offen && treffer.length > 0 && (
        <ul className="absolute z-20 mt-1 max-h-64 w-full overflow-y-auto rounded border border-gray-300 bg-white shadow-lg">
          {treffer.map(k => (
            <li key={k.wert}>
              <button
                type="button"
                onClick={() => { aufAenderung(k.wert); setSuche(''); setOffen(false); }}
                className="flex w-full items-center justify-between gap-2 px-3 py-2 text-left text-sm
                           hover:bg-gray-50"
              >
                <span className="min-w-0">
                  <span className="block truncate text-gray-900">{k.name}</span>
                  <span className="block text-xs text-gray-500">{k.wert}</span>
                </span>
                {k.wert === wert && <Check className="h-4 w-4 flex-shrink-0 text-primary-custom" aria-hidden />}
              </button>
            </li>
          ))}
        </ul>
      )}
      {offen && suche.trim() !== '' && treffer.length === 0 && (
        <p className="absolute z-20 mt-1 w-full rounded border border-gray-300 bg-white px-3 py-2 text-sm text-gray-600">
          Kein Treffer.
        </p>
      )}
    </div>
  );
}
