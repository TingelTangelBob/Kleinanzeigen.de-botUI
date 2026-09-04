// SPDX-FileCopyrightText: © Anzeigen-Studio contributors
// SPDX-License-Identifier: AGPL-3.0-or-later
//
// Theme-Wahl mit drei Modi (AP-2.27): hell | dunkel | system, Vorgabe system.
//
// Bis AP-2.26 kannte die Oberfläche nur hell und dunkel: Der Sidebar-Schalter
// schrieb den einen oder den anderen Wert nach `localStorage` und blieb dort
// stehen. „Folge dem Betriebssystem" ging nur, solange man den Schalter nie
// angefasst hatte, und ein späterer OS-Wechsel wirkte erst nach Neuladen.
//
// Jetzt ist `system` ein eigener, wählbarer und gespeicherter Modus. Bei
// `system` wertet der Hook `prefers-color-scheme` aus und hört auf dessen
// `change`-Ereignis, damit ein OS-Wechsel ohne Neuladen greift. Das effektive
// Erscheinungsbild (`hell`|`dunkel`) landet weiterhin als `data-theme` am
// `#app-shell` - die Tokens in index.css bleiben unberührt.

import { useCallback, useEffect, useState } from 'react';

export type ThemaWahl = 'hell' | 'dunkel' | 'system';
export type ThemaEffektiv = 'hell' | 'dunkel';

/** Derselbe Schlüssel wie vor AP-2.27 - alte Werte `hell`/`dunkel` bleiben gültig. */
export const THEMA_SCHLUESSEL = 'anzeigen-studio-theme';

/** Feuert im selben Tab, wenn die Wahl wechselt - `storage` feuert nur in anderen. */
const EREIGNIS = 'anzeigen-studio:thema';

const ABFRAGE = '(prefers-color-scheme: dark)';

/**
 * Der gespeicherte Modus. `hell` und `dunkel` bleiben aus alten Versionen
 * gültig; alles andere - fehlender Eintrag, ausdrückliches `system`, Müll -
 * heißt `system`.
 */
export function themaLesen(): ThemaWahl {
  if (typeof window === 'undefined') return 'system';
  const roh = window.localStorage.getItem(THEMA_SCHLUESSEL);
  return roh === 'hell' || roh === 'dunkel' ? roh : 'system';
}

/** Ob das Betriebssystem gerade dunkel bevorzugt. Ohne `matchMedia`: nein. */
export function systemIstDunkel(): boolean {
  if (typeof window === 'undefined') return false;
  return window.matchMedia?.(ABFRAGE).matches ?? false;
}

/** Aus Wahl und OS-Zustand das tatsächliche Erscheinungsbild. */
export function themaAufloesen(wahl: ThemaWahl, osDunkel: boolean): ThemaEffektiv {
  if (wahl === 'system') return osDunkel ? 'dunkel' : 'hell';
  return wahl;
}

/** Die Wahl schreiben und die anderen Hörer im selben Tab wecken. */
export function themaSchreiben(wahl: ThemaWahl): void {
  if (typeof window === 'undefined') return;
  window.localStorage.setItem(THEMA_SCHLUESSEL, wahl);
  window.dispatchEvent(new Event(EREIGNIS));
}

/**
 * `wahl` ist der gespeicherte Modus, `effektiv` das daraus (plus OS-Zustand)
 * abgeleitete Erscheinungsbild. `setWahl` schreibt sofort nach `localStorage`
 * und hält weitere Instanzen des Hooks - Sidebar und Einstellungen - im
 * Gleichschritt.
 */
export function useThema(): {
  wahl: ThemaWahl;
  setWahl: (wahl: ThemaWahl) => void;
  effektiv: ThemaEffektiv;
} {
  const [wahl, setWahlLokal] = useState<ThemaWahl>(themaLesen);
  const [osDunkel, setOsDunkel] = useState<boolean>(systemIstDunkel);

  // OS-Wechsel live übernehmen - ohne das greift „System" erst nach Neuladen.
  useEffect(() => {
    const mq = window.matchMedia?.(ABFRAGE);
    if (!mq) return;
    const auf = () => setOsDunkel(mq.matches);
    mq.addEventListener('change', auf);
    return () => mq.removeEventListener('change', auf);
  }, []);

  // Wahl aus einem anderen Tab (`storage`) oder einer anderen Instanz im
  // selben Tab (`EREIGNIS`) nachziehen.
  useEffect(() => {
    const auf = () => setWahlLokal(themaLesen());
    window.addEventListener('storage', auf);
    window.addEventListener(EREIGNIS, auf);
    return () => {
      window.removeEventListener('storage', auf);
      window.removeEventListener(EREIGNIS, auf);
    };
  }, []);

  const setWahl = useCallback((neu: ThemaWahl) => {
    themaSchreiben(neu);
    setWahlLokal(neu);
  }, []);

  return { wahl, setWahl, effektiv: themaAufloesen(wahl, osDunkel) };
}
