// SPDX-FileCopyrightText: © Anzeigen-Studio contributors
// SPDX-License-Identifier: AGPL-3.0-or-later
//
// Gemeinsame Countdown- und Beschriftungslogik für Wartehinweise (AP-2.45).

import { useEffect, useState } from 'react';

/** Formats the remaining deliberate queue delay for the user. */
export function wartezeitText(bis: string, jetzt = Date.now()): string {
  const zeitpunkt = Date.parse(bis);
  const rest = Number.isNaN(zeitpunkt) ? 0 : Math.max(0, (zeitpunkt - jetzt) / 1000);
  const sekunden = Math.ceil(rest);
  const minuten = Math.ceil(rest / 60);
  return rest >= 90
    ? `noch ${minuten} Minuten`
    : `noch ${sekunden} ${sekunden === 1 ? 'Sekunde' : 'Sekunden'}`;
}

/** Full accessible description shared by the visible compact and full forms. */
export function warteHinweisText(restzeit: string, grund: string | null): string {
  return `Wartet absichtlich – ${restzeit}.${grund ? ` Grund: ${grund}.` : ''} Kein Fehler.`;
}

/** Keeps a countdown current without duplicating timer logic in each view. */
export function useWartezeit(bis: string | null): string | null {
  const [jetzt, setJetzt] = useState(() => Date.now());

  useEffect(() => {
    if (!bis) return undefined;
    const timer = window.setInterval(() => setJetzt(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, [bis]);

  return bis ? wartezeitText(bis, jetzt) : null;
}
