// SPDX-FileCopyrightText: © Anzeigen-Studio contributors
// SPDX-License-Identifier: AGPL-3.0-or-later
//
// Instruktionsbanner, das sich wegklicken lässt (AP-2.25).
//
// Mit `id` merkt sich der Browser das Wegklicken je Kennung (localStorage,
// über `useHinweisSichtbar`). Ohne `id` steht der Hinweis fest - so bleiben
// harte Validierung und gescheiterte Läufe sichtbar und wandern nicht in
// einen vergessenen Zustand.
//
// Aufbau (Symbol links, Schließen rechts, Rolle nach Schwere) nach dem Muster
// von SoloOffice `src/components/Notice.tsx` (AGPL-3.0-or-later); auf die
// hiesigen `.hinweis*`-Token gezogen.

import type { ReactNode } from 'react';
import { X } from 'lucide-react';
import type { LucideIcon } from 'lucide-react';
import { useHinweisSichtbar } from '../hooks/useHinweisSichtbar';

type Ton = 'ok' | 'warn' | 'fehler';

interface HinweisProps {
  /** Ohne Kennung ist der Hinweis nicht schließbar (kritische Meldungen). */
  id?: string;
  ton?: Ton;
  icon?: LucideIcon;
  role?: 'alert' | 'status';
  className?: string;
  children: ReactNode;
}

const TON_KLASSE: Record<Ton, string> = {
  ok: '',
  warn: 'hinweis-warn',
  fehler: 'hinweis-fehler',
};

export function Hinweis({ id, ton = 'ok', icon: Icon, role, className = '', children }: HinweisProps) {
  const { sichtbar, ausblenden } = useHinweisSichtbar(id ?? '');
  if (id && !sichtbar) return null;

  return (
    <div role={role} className={`hinweis ${TON_KLASSE[ton]} ${className}`.trim()}>
      <div className="flex items-start gap-2">
        {Icon && <Icon className="mt-0.5 h-4 w-4 flex-shrink-0" aria-hidden />}
        <div className="min-w-0 flex-1">{children}</div>
        {id && (
          <button
            type="button"
            onClick={ausblenden}
            aria-label="Hinweis ausblenden"
            className="hinweis-schliessen"
          >
            <X className="h-4 w-4" aria-hidden />
          </button>
        )}
      </div>
    </div>
  );
}
