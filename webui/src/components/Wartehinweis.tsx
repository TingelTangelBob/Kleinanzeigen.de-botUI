// SPDX-FileCopyrightText: © Anzeigen-Studio contributors
// SPDX-License-Identifier: AGPL-3.0-or-later
//
// Gemeinsame Warteanzeige für JobKarte, Glocke und Übersicht (AP-2.45).

import { Hourglass } from 'lucide-react';
import { warteHinweisText } from './Wartezeit';

export function Wartehinweis({
  restzeit,
  grund,
  kompakt = false,
}: {
  restzeit: string;
  grund: string | null;
  kompakt?: boolean;
}) {
  const label = warteHinweisText(restzeit, grund);

  if (kompakt) {
    return (
      <span className="wartehinweis-kompakt" title={label} aria-label={label}>
        <Hourglass className="h-3.5 w-3.5 flex-shrink-0" aria-hidden />
        <span className="font-medium">wartet absichtlich</span>
        <span>{restzeit}</span>
        {grund && <span className="min-w-0 truncate">· {grund}</span>}
      </span>
    );
  }

  return (
    <div
      className="hinweis"
      style={{ borderRadius: 0, border: 0, borderTop: '1px solid var(--hinweis-ok-rand)' }}
    >
      <p className="flex items-start gap-2 text-sm text-blue-900" title={label} aria-label={label}>
        <Hourglass className="mt-0.5 h-4 w-4 flex-shrink-0" aria-hidden />
        <span>
          <strong>Wartet absichtlich – {restzeit}.</strong>
          {grund && <span className="mt-1 block">{grund}</span>}
          <span className="mt-1 block text-blue-800">
            Kein Fehler. Der Abstand lässt sich in den Einstellungen ändern.
          </span>
        </span>
      </p>
    </div>
  );
}
