// SPDX-FileCopyrightText: © Anzeigen-Studio contributors
// SPDX-License-Identifier: AGPL-3.0-or-later
//
// Merkt sich je Kennung, ob der Nutzer einen Hinweis weggeklickt hat
// (AP-2.25). Seit AP-2.30 teilt sich die Glocke dieselbe Ablage: Ein Tipp, den
// man dort wegklickt, bleibt weg - egal ob er als Banner oder in der Glocke
// steckt.
//
// Nur für unkritische Instruktionsbanner und Tipps gedacht. Kritische Fehler
// bekommen keine Kennung und lassen sich damit gar nicht dauerhaft ausblenden.

import { useCallback, useEffect, useState } from 'react';

const SCHLUESSEL = 'anzeigen-studio:hinweise-weg';

/** Die gemerkten Kennungen aus localStorage - defensiv gelesen. */
export function weggeklickteKennungen(): Set<string> {
  if (typeof window === 'undefined') return new Set();
  try {
    const roh = window.localStorage.getItem(SCHLUESSEL);
    const liste = roh ? (JSON.parse(roh) as unknown) : [];
    return new Set(
      Array.isArray(liste) ? liste.filter((x): x is string => typeof x === 'string') : [],
    );
  } catch {
    return new Set();
  }
}

/** Schreibt eine Kennung in die gemerkte Liste. Fehlschlag ist kein Grund zu scheitern. */
export function merkeWeggeklickt(id: string): void {
  if (typeof window === 'undefined' || id === '') return;
  try {
    const neu = weggeklickteKennungen();
    neu.add(id);
    window.localStorage.setItem(SCHLUESSEL, JSON.stringify([...neu]));
  } catch {
    // localStorage kann voll oder gesperrt sein. Dann bleibt der Hinweis bis
    // zum Neuladen weg und kommt danach wieder.
  }
}

/**
 * `sichtbar` ist `false`, sobald der Hinweis mit dieser `id` schon einmal
 * weggeklickt wurde. `ausblenden` schreibt das in `localStorage` und wirkt
 * über Neuladen und weitere Tabs hinweg.
 */
export function useHinweisSichtbar(id: string): { sichtbar: boolean; ausblenden: () => void } {
  const [weg, setWeg] = useState<Set<string>>(weggeklickteKennungen);

  // Ein zweiter Tab soll denselben Stand sehen, ohne dass man neu lädt.
  useEffect(() => {
    const aufSpeicher = (e: StorageEvent) => {
      if (e.key === SCHLUESSEL) setWeg(weggeklickteKennungen());
    };
    window.addEventListener('storage', aufSpeicher);
    return () => window.removeEventListener('storage', aufSpeicher);
  }, []);

  const ausblenden = useCallback(() => {
    merkeWeggeklickt(id);
    setWeg(vorher => {
      const neu = new Set(vorher);
      neu.add(id);
      return neu;
    });
  }, [id]);

  return { sichtbar: id === '' || !weg.has(id), ausblenden };
}
