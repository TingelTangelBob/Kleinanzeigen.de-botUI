// SPDX-FileCopyrightText: © Anzeigen-Studio contributors
// SPDX-License-Identifier: AGPL-3.0-or-later
//
// Kategorie suchen statt Nummernpfad tippen (AP-2.7).
// UI-Anpassung 2026-09-04: Suchfeld für die kompakte Editorzeile verdichtet.
// UI-Anpassung 2026-09-05: Suche als Symbol im Kategoriefeld.
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
//
// Und ein zweiter: Ist die Liste gar nicht abrufbar, wird das Feld zum
// Textfeld. Das ist der einzige Weg, der dann noch bleibt - ein Suchfeld ohne
// Liste zu deaktivieren hieße, die Kategorie überhaupt nicht mehr setzen zu
// können, auch bei einer Anzeige, die noch keine hat.

import { useEffect, useMemo, useRef, useState } from 'react';
import { AlertTriangle, Check, Search } from 'lucide-react';
import { api } from '../services/api';
import type { Kategorie } from '../types';

const MAX_TREFFER = 40;

interface Props {
  wert: string;
  aufAenderung: (wert: string) => void;
  bearbeitbar?: boolean;
  kompakt?: boolean;
}

export function KategorieWahl({ wert, aufAenderung, bearbeitbar = true, kompakt = false }: Props) {
  const [alle, setAlle] = useState<Kategorie[]>([]);
  const [suche, setSuche] = useState('');
  const [offen, setOffen] = useState(false);
  const [geladen, setGeladen] = useState(false);
  const huelle = useRef<HTMLDivElement>(null);

  useEffect(() => {
    void (async () => {
      try {
        setAlle(await api.katalog.kategorien());
      } catch {
        // Ohne Liste bleibt das Feld ein Textfeld - unschön, aber bedienbar.
        setAlle([]);
      } finally {
        setGeladen(true);
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

  // Leer heißt hier auch "nicht abrufbar": `kategorien()` gibt eine leere Liste
  // zurück, wenn `categories.yaml` nicht lesbar war. Für die Bedienung ist das
  // derselbe Fall wie ein gescheiterter Aufruf.
  const ohneListe = geladen && alle.length === 0;

  if (!bearbeitbar) {
    return (
      <div>
        <span className="beschriftung">Kategorie</span>
        <div className="feld feld-lesbar mt-1">
          {bekannt ? (
            <span className="block break-words text-sm text-stark">{bekannt.name}</span>
          ) : wert ? (
            <span className="flex items-start gap-1.5 text-sm text-normal">
              <AlertTriangle className="mt-0.5 h-3.5 w-3.5 flex-shrink-0" aria-hidden />
              <span className="min-w-0 break-words">{wert}</span>
            </span>
          ) : (
            <span className="block text-sm text-leise">Keine Kategorie gesetzt</span>
          )}
          <span className="mt-0.5 block break-words text-xs text-leise">{wert || '—'}</span>
        </div>
      </div>
    );
  }

  if (ohneListe) {
    return (
      <div>
        <label className="block">
          <span className="text-sm font-medium text-normal">Kategorie</span>
          <input
            type="text"
            value={wert}
            onChange={e => aufAenderung(e.target.value)}
            placeholder="Nummernpfad, z. B. 161/278"
            className="feld mt-1"
          />
        </label>
        <p className="mt-1 flex items-start gap-1.5 text-xs text-amber-900">
          <AlertTriangle className="mt-0.5 h-3.5 w-3.5 flex-shrink-0" aria-hidden />
          <span>
            Die Kategorieliste ist gerade nicht verfügbar. Der Wert geht so in die Anzeige,
            wie er hier steht – der Bot erwartet den Nummernpfad.
          </span>
        </p>
      </div>
    );
  }

  return (
    <div ref={huelle} className={`relative ${kompakt ? 'kategorie-wahl-kompakt' : ''}`}>
      <span className="text-sm font-medium text-normal">Kategorie</span>

      <div className="feld kategorie-wert-feld mt-1">
        {/* Die Kopfzeile bleibt einzeilig (AP-2.35/AP-2.42). Lange Kategorien
            werden im Feld gekürzt, der vollständige Name bleibt im title
            sichtbar; der Nummernpfad bleibt daneben als kurze Kennung stehen. */}
        <span className="kategorie-wert-inhalt">
        {bekannt ? (
          <span className="block truncate text-sm text-stark" title={bekannt.name}>{bekannt.name}</span>
        ) : wert ? (
          <span className="flex min-w-0 items-center gap-1.5 text-sm text-amber-900">
            <AlertTriangle className="h-3.5 w-3.5 flex-shrink-0" aria-hidden />
            <span className="truncate" title={wert}>{wert}</span>
          </span>
        ) : (
          <span className="block text-sm text-leise">Keine Kategorie gesetzt</span>
        )}
        </span>
        {wert && <span className="kategorie-wert-pfad">{wert}</span>}
        <button
          type="button"
          className="kategorie-suche-knopf"
          aria-label="Kategorie suchen"
          title="Kategorie suchen"
          aria-expanded={offen}
          onClick={() => setOffen(vorher => !vorher)}
        >
          <Search className="h-4 w-4" aria-hidden />
        </button>
      </div>

      {offen && (
        <div className="karte absolute z-20 mt-1 w-full p-2">
          <label className="relative block">
            <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-leise" aria-hidden />
            <span className="sr-only">Kategorie suchen</span>
            <input
              type="search"
              autoFocus
              value={suche}
              onChange={e => setSuche(e.target.value)}
              onKeyDown={e => { if (e.key === 'Escape') setOffen(false); }}
              placeholder="Kategorie suchen …"
              className={`feld w-full py-2 pl-9 pr-3 ${kompakt ? 'kategorie-suche-kompakt' : ''}`}
            />
          </label>

          {treffer.length > 0 && (
            <ul className="mt-2 max-h-64 overflow-y-auto">
              {treffer.map(k => (
                <li key={k.wert}>
                  <button
                    type="button"
                    onClick={() => { aufAenderung(k.wert); setSuche(''); setOffen(false); }}
                    className="flex w-full items-center justify-between gap-2 rounded-lg px-3 py-2 text-left text-sm
                               hover:bg-[var(--primary-light)]"
                  >
                    <span className="min-w-0">
                      <span className="block truncate text-stark">{k.name}</span>
                      <span className="block text-xs text-leise">{k.wert}</span>
                    </span>
                    {k.wert === wert && <Check className="h-4 w-4 flex-shrink-0 text-primary-custom" aria-hidden />}
                  </button>
                </li>
              ))}
            </ul>
          )}
          {suche.trim() !== '' && treffer.length === 0 && (
            <p className="px-3 py-2 text-sm text-leise">Kein Treffer.</p>
          )}
        </div>
      )}
    </div>
  );
}
