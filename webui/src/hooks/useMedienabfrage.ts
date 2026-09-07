// SPDX-FileCopyrightText: © Anzeigen-Studio contributors
// SPDX-License-Identifier: AGPL-3.0-or-later
//
// Ein `matchMedia`-Abo als Hook. Wie in `useThema` wird `matchMedia` mit `?.`
// abgesichert - jsdom bringt keins mit; dann gilt der `vorgabe`-Wert.

import { useEffect, useState } from 'react';

/**
 * `true`, solange die Medienabfrage passt. `vorgabe` greift, wenn `matchMedia`
 * fehlt (Tests, SSR) - Vorgabe ist `true`, damit die Oberfläche dort im
 * Desktop-Zweig bleibt.
 */
export function useMedienabfrage(abfrage: string, vorgabe = true): boolean {
  const [passt, setPasst] = useState(() => {
    if (typeof window === 'undefined') return vorgabe;
    return window.matchMedia?.(abfrage).matches ?? vorgabe;
  });

  useEffect(() => {
    if (typeof window === 'undefined') return undefined;
    const mq = window.matchMedia?.(abfrage);
    if (!mq) return undefined;
    const auf = () => setPasst(mq.matches);
    auf();
    mq.addEventListener('change', auf);
    return () => mq.removeEventListener('change', auf);
  }, [abfrage]);

  return passt;
}

/** Breakpoint `md` (768 px) von Tailwind - der Punkt, an dem das Mobil-Layout endet. */
export function useIstMobil(): boolean {
  return !useMedienabfrage('(min-width: 768px)', true);
}
