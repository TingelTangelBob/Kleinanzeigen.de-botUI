// SPDX-FileCopyrightText: © Anzeigen-Studio contributors
// SPDX-License-Identifier: AGPL-3.0-or-later
//
// Der lokale Anzeigenbestand: Liste, Suche, Filter (AP-2.4, AP-3.2).
//
// Gefiltert und gesucht wird in der Oberfläche, nicht im Backend. Bei einem
// privaten Bestand - Dutzende Anzeigen, nicht Zehntausende - ist das die
// einfachere Lösung und fühlt sich besser an, weil jeder Tastendruck sofort
// wirkt. Sobald ein Bestand das nicht mehr hergibt, wandert es serverseitig.

import { useCallback, useEffect, useMemo, useState } from 'react';
import { Download, RefreshCw, Search } from 'lucide-react';
import { api, ApiFehler } from '../services/api';
import { useProfil } from '../context/useProfil';
import type { BestandsAnzeige } from '../types';
import { AnzeigenEditor } from './AnzeigenEditor';
import { AnzeigenZeile } from './AnzeigenZeile';
import { NachladenDialog } from './NachladenDialog';
import { VorlagenListe } from './VorlagenListe';

type Filter = 'alle' | 'faellig' | 'geaendert' | 'auffaellig' | 'inaktiv';

const FILTER: { id: Filter; label: string }[] = [
  { id: 'alle', label: 'Alle' },
  { id: 'faellig', label: 'Fällig' },
  { id: 'geaendert', label: 'Lokal geändert' },
  { id: 'auffaellig', label: 'Mit Hinweis' },
  { id: 'inaktiv', label: 'Inaktiv' },
];

function passtZumFilter(anzeige: BestandsAnzeige, filter: Filter): boolean {
  switch (filter) {
    case 'faellig': return anzeige.faellig;
    case 'geaendert': return anzeige.lokal_geaendert;
    case 'auffaellig': return anzeige.hinweise.length > 0 || anzeige.unlesbar !== null;
    case 'inaktiv': return !anzeige.aktiv;
    default: return true;
  }
}

function passtZurSuche(anzeige: BestandsAnzeige, suche: string): boolean {
  if (!suche) return true;
  const begriff = suche.trim().toLowerCase();
  if (!begriff) return true;
  return [anzeige.titel, anzeige.kategorie ?? '', String(anzeige.id ?? '')]
    .some(feld => feld.toLowerCase().includes(begriff));
}

export function BestandSeite() {
  const { aktiv, laedt: profileLaden } = useProfil();
  const [anzeigen, setAnzeigen] = useState<BestandsAnzeige[]>([]);
  const [laedt, setLaedt] = useState(false);
  const [fehler, setFehler] = useState<string | null>(null);
  const [suche, setSuche] = useState('');
  const [filter, setFilter] = useState<Filter>('alle');
  const [bearbeitet, setBearbeitet] = useState<string | null>(null);
  const [holtNach, setHoltNach] = useState(false);

  const laden = useCallback(async () => {
    if (!aktiv) {
      setAnzeigen([]);
      return;
    }
    setLaedt(true);
    setFehler(null);
    try {
      setAnzeigen(await api.bestand.liste(aktiv.slug));
    } catch (ursache) {
      setFehler(ursache instanceof ApiFehler ? ursache.message : 'Unbekannter Fehler.');
    } finally {
      setLaedt(false);
    }
  }, [aktiv]);

  useEffect(() => {
    void laden();
  }, [laden]);

  const gefiltert = useMemo(
    () => anzeigen.filter(a => passtZumFilter(a, filter) && passtZurSuche(a, suche)),
    [anzeigen, filter, suche],
  );

  const zaehler = useMemo(() => ({
    faellig: anzeigen.filter(a => a.faellig).length,
    geaendert: anzeigen.filter(a => a.lokal_geaendert).length,
    auffaellig: anzeigen.filter(a => a.hinweise.length > 0 || a.unlesbar).length,
  }), [anzeigen]);

  if (bearbeitet && aktiv) {
    return (
      <AnzeigenEditor
        profil={aktiv.slug}
        datei={bearbeitet}
        aufZurueck={geaendert => {
          setBearbeitet(null);
          // Nach einer Änderung neu einlesen: Titel, Preis und die Merkmale in
          // der Liste stammen aus derselben Datei.
          if (geaendert) void laden();
        }}
        aufKopie={kopie => {
          // Ohne Umweg über die Liste direkt in die Kopie: Wer dupliziert,
          // will Titel und Preis ändern, und zwar sofort.
          void laden();
          setBearbeitet(kopie);
        }}
      />
    );
  }

  if (profileLaden) return <p className="text-sm text-gray-500">Wird geladen …</p>;

  if (!aktiv) {
    return (
      <p className="rounded border border-amber-200 bg-amber-50 p-4 text-sm text-amber-900">
        Zuerst ein Profil anlegen.
      </p>
    );
  }

  return (
    <div className="mx-auto max-w-4xl">
      {/* Auf schmalen Schirmen untereinander. Vorher stand hier nur
          `items-center justify-between`: Die beiden Knöpfe brachen bei 375 px
          in zwei Zeilen um, und die Überschrift wurde gegen diesen zweizeiligen
          Stapel mittig gesetzt - Titel und Knöpfe liefen sichtbar ineinander.
          Ein `flex-wrap` am äußeren Element allein hätte das nicht behoben. */}
      <div className="mb-6 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <h1 className="text-2xl font-bold text-gray-900">Anzeigen</h1>
        <div className="flex flex-wrap gap-2">
          <button
            type="button"
            onClick={() => setHoltNach(true)}
            className="flex items-center gap-2 rounded border border-gray-300 px-3 py-2 text-sm
                       text-gray-700 hover:bg-gray-50"
          >
            <Download className="h-4 w-4" aria-hidden />
            Ältere holen
          </button>
          <button
            type="button"
            onClick={() => void laden()}
            className="flex items-center gap-2 rounded border border-gray-300 px-3 py-2 text-sm
                       text-gray-700 hover:bg-gray-50"
          >
            <RefreshCw className={`h-4 w-4 ${laedt ? 'animate-spin' : ''}`} aria-hidden />
            Neu einlesen
          </button>
        </div>
      </div>

      {holtNach && (
        <NachladenDialog profil={aktiv.slug} aufSchliessen={() => { setHoltNach(false); void laden(); }} />
      )}

      {fehler && (
        <p className="mb-4 rounded border border-red-200 bg-red-50 p-3 text-sm text-red-800">{fehler}</p>
      )}

      {/* Über den Anzeigen, weil eine Vorlage der Anfang einer Anzeige ist -
          und weil der Abschnitt verschwindet, sobald es keine gibt. */}
      <VorlagenListe
        profil={aktiv.slug}
        aufAngewendet={datei => {
          // Direkt in die neue Anzeige: Titel und Preis stimmen noch nicht,
          // genau wie beim Duplizieren.
          void laden();
          setBearbeitet(datei);
        }}
      />

      <div className="mb-4 space-y-3">
        <label className="relative block">
          <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-gray-400" aria-hidden />
          <span className="sr-only">Anzeigen durchsuchen</span>
          <input
            type="search"
            value={suche}
            onChange={e => setSuche(e.target.value)}
            placeholder="Titel, Kategorie oder Anzeigennummer"
            className="w-full rounded border border-gray-300 py-2 pl-9 pr-3 text-sm
                       focus:border-primary-custom focus:outline-none focus:ring-1 focus:ring-primary-custom"
          />
        </label>

        <div className="flex flex-wrap gap-2">
          {FILTER.map(f => {
            const anzahl = f.id === 'faellig' ? zaehler.faellig
              : f.id === 'geaendert' ? zaehler.geaendert
              : f.id === 'auffaellig' ? zaehler.auffaellig
              : null;
            return (
              <button
                key={f.id}
                type="button"
                onClick={() => setFilter(f.id)}
                aria-pressed={filter === f.id}
                className={`rounded-full border px-3 py-1 text-sm
                            ${filter === f.id
                              ? 'border-primary-custom bg-primary-custom'
                              : 'border-gray-300 bg-white text-gray-700 hover:bg-gray-50'}`}
              >
                {f.label}{anzahl !== null && anzahl > 0 ? ` (${anzahl})` : ''}
              </button>
            );
          })}
        </div>
      </div>

      {anzeigen.length === 0 && !laedt ? (
        <div className="rounded border border-gray-200 bg-white p-6 text-center">
          <p className="text-sm text-gray-700">Noch keine Anzeigen auf der Platte.</p>
          <p className="mt-1 text-sm text-gray-500">
            Starte unter „Läufe" einen Download, um den Bestand zu holen.
          </p>
        </div>
      ) : (
        <>
          <p className="mb-2 text-xs text-gray-500">
            {gefiltert.length} von {anzeigen.length} Anzeigen
          </p>
          <ul className="divide-y divide-gray-200 overflow-hidden rounded border border-gray-200 bg-white">
            {gefiltert.map(a => (
              <li key={a.datei}>
                <AnzeigenZeile
                  anzeige={a}
                  profil={aktiv.slug}
                  aufKlick={a.unlesbar ? undefined : () => setBearbeitet(a.datei)}
                />
              </li>
            ))}
          </ul>
          {gefiltert.length === 0 && (
            <p className="mt-3 text-sm text-gray-600">Kein Treffer für diese Auswahl.</p>
          )}
        </>
      )}
    </div>
  );
}
