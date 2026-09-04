// SPDX-FileCopyrightText: © Anzeigen-Studio contributors
// SPDX-License-Identifier: AGPL-3.0-or-later

import { useContext, useEffect } from 'react';
import { MeldungenKontext, type Meldung, type MeldungenWert } from './meldungenKontext';

export function useMeldungen(): MeldungenWert {
  const wert = useContext(MeldungenKontext);
  if (!wert) throw new Error('useMeldungen muss innerhalb von MeldungenProvider stehen');
  return wert;
}

/**
 * Meldet die Meldungen einer Seite an die Glocke und räumt sie beim Verlassen
 * wieder ab. `liste` darf bei jedem Render neu entstehen - verglichen wird der
 * Inhalt, nicht die Referenz.
 */
export function useMeldungenQuelle(quelle: string, liste: Meldung[]): void {
  const { melden } = useMeldungen();
  const abbild = JSON.stringify(liste);
  useEffect(() => {
    melden(quelle, JSON.parse(abbild) as Meldung[]);
    return () => melden(quelle, []);
  }, [quelle, abbild, melden]);
}
