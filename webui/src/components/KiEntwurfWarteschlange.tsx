// SPDX-FileCopyrightText: © Anzeigen-Studio contributors
// SPDX-License-Identifier: AGPL-3.0-or-later
//
// Anzeige der serverseitigen KI-Erkennungen (AP-4.8).
// Neue Datei, Anzeigen-Studio, 2026-09-13.
// Geändert am 2026-09-30: Stapel - Nachladen von außen, Wiederholen, Verwerfen.

import { useCallback, useEffect, useMemo, useState } from 'react';
import { AlertTriangle, ArrowRight, Loader2, RotateCcw, Sparkles, X } from 'lucide-react';
import { api, ApiFehler } from '../services/api';
import type { KiErkennung, KiErkennungZustand } from '../types';

const LAUFEND = new Set<KiErkennungZustand>(['wartet', 'laeuft']);
const SICHTBAR = new Set<KiErkennungZustand>([
  'wartet', 'laeuft', 'pruefen', 'gescheitert', 'abgebrochen',
]);

function zustandText(zustand: KiErkennungZustand): string {
  if (zustand === 'wartet') return 'Wartet auf die Analyse';
  if (zustand === 'laeuft') return 'Fotos werden analysiert';
  if (zustand === 'pruefen') return 'Entwurf ist bereit';
  if (zustand === 'gescheitert') return 'Analyse fehlgeschlagen';
  if (zustand === 'abgebrochen') return 'Analyse abgebrochen';
  return 'Wird vorbereitet';
}

function zeitText(iso: string): string {
  const zeit = new Date(iso);
  if (Number.isNaN(zeit.getTime())) return '';
  return zeit.toLocaleString('de-DE', {
    day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit',
  });
}

export function KiEntwurfWarteschlange({
  profil,
  aufZiel,
  kompakt = false,
  neuLaden = 0,
}: {
  profil: string;
  aufZiel: (ziel: string) => void;
  kompakt?: boolean;
  /** Wechselt der Wert, lädt die Liste neu - etwa nach einer Stapelgruppe. */
  neuLaden?: number;
}) {
  const [laeufe, setLaeufe] = useState<KiErkennung[]>([]);
  const [fehler, setFehler] = useState<string | null>(null);
  const [aktion, setAktion] = useState<number | null>(null);

  const laden = useCallback(async () => {
    // Aeltere Test- oder Offline-Oberflaechen koennen das neue Ende noch nicht
    // anbieten. Dann bleibt dieser optionale Abschnitt einfach unsichtbar.
    const erkennungen = api.ki?.erkennungen;
    if (typeof erkennungen !== 'function') return;
    try {
      setLaeufe(await erkennungen(profil));
      setFehler(null);
    } catch (ursache) {
      setFehler(ursache instanceof ApiFehler ? ursache.message : 'KI-Entwürfe nicht abrufbar.');
    }
  }, [profil]);

  useEffect(() => {
    void laden();
  }, [laden, neuLaden]);

  const wiederholen = async (id: number) => {
    setAktion(id);
    try {
      await api.ki.erkennungWiederholen(profil, id);
      await laden();
    } catch (ursache) {
      setFehler(ursache instanceof ApiFehler ? ursache.message : 'Konnte nicht neu gestartet werden.');
    } finally {
      setAktion(null);
    }
  };

  const verwerfen = async (id: number) => {
    setAktion(id);
    try {
      await api.ki.erkennungVerwerfen(profil, id);
      await laden();
    } catch (ursache) {
      setFehler(ursache instanceof ApiFehler ? ursache.message : 'Konnte nicht verworfen werden.');
    } finally {
      setAktion(null);
    }
  };

  const laufend = useMemo(() => laeufe.some(lauf => LAUFEND.has(lauf.zustand)), [laeufe]);
  useEffect(() => {
    if (!laufend) return undefined;
    const timer = window.setInterval(() => void laden(), 1500);
    return () => window.clearInterval(timer);
  }, [laufend, laden]);

  const sichtbar = useMemo(
    () => laeufe.filter(lauf => SICHTBAR.has(lauf.zustand)).slice(0, kompakt ? 3 : 100),
    [kompakt, laeufe],
  );

  // Leere Listen haben auf dem Dashboard keinen eigenen Abschnitt. Auf der
  // Warteschlangen-Seite gilt dasselbe: Die Seite bleibt ruhig, wenn nichts
  // zur Analyse oder Prüfung ansteht.
  if (sichtbar.length === 0) {
    if (fehler && !kompakt) {
      return <p role="alert" className="hinweis hinweis-fehler mb-6">{fehler}</p>;
    }
    return null;
  }

  const pruefbar = sichtbar.filter(lauf => lauf.zustand === 'pruefen').length;
  const inArbeit = sichtbar.filter(lauf => LAUFEND.has(lauf.zustand)).length;
  return (
    <section className={kompakt ? 'mb-8' : 'mb-8'}>
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
        <h2 className="flex items-center gap-2 text-base font-semibold tracking-tight text-stark">
          <Sparkles className="h-4 w-4 text-primary-custom" aria-hidden />
          KI-Entwürfe prüfen
          {pruefbar > 0 && <span className="merkmal merkmal-gelb">{pruefbar}</span>}
          {inArbeit > 0 && !kompakt && (
            <span className="text-xs font-normal text-leise">{inArbeit} in Arbeit</span>
          )}
        </h2>
        <button type="button" onClick={() => aufZiel('warteschlange')} className="btn-leise">
          Warteschlange <ArrowRight className="h-4 w-4" aria-hidden />
        </button>
      </div>

      {fehler && (
        <p className="mb-2 text-xs text-leise">Zuletzt nicht erreichbar: {fehler}</p>
      )}
      <ul className="liste">
        {sichtbar.map(lauf => {
          const bereit = lauf.zustand === 'pruefen';
          const titel = lauf.entwurf?.titel ?? 'Neue Anzeige';
          return (
            <li key={lauf.id}>
              <div className="zeile items-center gap-3 !py-3">
                <span className="flex h-8 w-8 flex-shrink-0 items-center justify-center rounded-full" style={{ background: bereit ? 'var(--primary-light)' : 'var(--merkmal-grau-flaeche)' }}>
                  {LAUFEND.has(lauf.zustand)
                    ? <Loader2 className="h-4 w-4 animate-spin text-primary-custom" aria-hidden />
                    : bereit
                      ? <Sparkles className="h-4 w-4 text-primary-custom" aria-hidden />
                      : <AlertTriangle className="h-4 w-4 text-leise" aria-hidden />}
                </span>
                <span className="min-w-0 flex-1">
                  <span className="block truncate text-sm font-medium text-stark">{titel}</span>
                  <span className="mt-0.5 block text-xs text-leise">
                    {zustandText(lauf.zustand)} · {lauf.bilder} {lauf.bilder === 1 ? 'Foto' : 'Fotos'}
                    {zeitText(lauf.eingereicht_am) ? ` · ${zeitText(lauf.eingereicht_am)}` : ''}
                  </span>
                  {lauf.meldung && <span className="mt-1 block text-xs text-leise">{lauf.meldung}</span>}
                </span>
                {bereit && (
                  <button
                    type="button"
                    onClick={() => aufZiel(`neu?erkennung=${lauf.id}`)}
                    className="btn-primaer flex-shrink-0 text-xs"
                  >
                    Prüfen
                  </button>
                )}
                {!kompakt && (lauf.zustand === 'gescheitert' || lauf.zustand === 'abgebrochen') && (
                  <button
                    type="button"
                    onClick={() => void wiederholen(lauf.id)}
                    disabled={aktion !== null}
                    className="btn-ghost flex-shrink-0 text-xs"
                    title="Mit denselben Fotos erneut analysieren. Kostet wie eine neue Erkennung."
                  >
                    <RotateCcw className="h-3.5 w-3.5" aria-hidden />
                    Erneut
                  </button>
                )}
                {!kompakt && !LAUFEND.has(lauf.zustand) && (
                  <button
                    type="button"
                    onClick={() => void verwerfen(lauf.id)}
                    disabled={aktion !== null}
                    className="btn-leise flex-shrink-0 !px-2"
                    aria-label={`Entwurf „${titel}“ verwerfen`}
                    title="Entwurf verwerfen. Es wird keine Anzeige gelöscht."
                  >
                    <X className="h-4 w-4" aria-hidden />
                  </button>
                )}
              </div>
            </li>
          );
        })}
      </ul>
      {kompakt && laeufe.length > sichtbar.length && (
        <button type="button" onClick={() => aufZiel('warteschlange')} className="mt-2 text-sm text-primary-custom underline">
          Weitere Entwürfe in der Warteschlange
        </button>
      )}
    </section>
  );
}
