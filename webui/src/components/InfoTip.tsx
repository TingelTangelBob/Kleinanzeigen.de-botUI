// SPDX-FileCopyrightText: © Anzeigen-Studio contributors
// SPDX-License-Identifier: AGPL-3.0-or-later
//
// Kleines Info-Zeichen mit Kurzhilfe bei Zeigen oder Tastatur-Fokus (AP-2.25).
//
// Für unkritische Erklärungen, die vorher als Dauerbanner über der ganzen
// Seite standen. Der Text hängt per `aria-describedby` am Knopf, damit ein
// Screenreader ihn vorliest; sichtbar wird er über `:hover` und
// `:focus-within` in index.css (`.info-tip`). Die Blase liegt bewusst im
// Fluss statt in einem Portal - die Seiten hier haben keinen Container mit
// `overflow: hidden` um solche Zeilen.

import { useId } from 'react';
import { Info } from 'lucide-react';

interface InfoTipProps {
  text: string;
  /** Beschriftung des Knopfes für Screenreader. */
  label?: string;
  className?: string;
}

export function InfoTip({ text, label = 'Erklärung anzeigen', className = '' }: InfoTipProps) {
  const id = useId();
  return (
    <span className={`info-tip ${className}`.trim()}>
      <button type="button" className="info-tip-knopf" aria-label={label} aria-describedby={id}>
        <Info className="h-4 w-4" aria-hidden />
      </button>
      <span role="tooltip" id={id} className="info-tip-blase">
        {text}
      </span>
    </span>
  );
}
