// SPDX-FileCopyrightText: © Anzeigen-Studio contributors
// SPDX-License-Identifier: AGPL-3.0-or-later
//
// Kleines Info-Zeichen mit Kurzhilfe bei Zeigen oder Tastatur-Fokus (AP-2.25).
//
// Für unkritische Erklärungen, die vorher als Dauerbanner über der ganzen
// Seite standen. Der Text hängt per `aria-describedby` am Knopf, damit ein
// Screenreader ihn vorliest; sichtbar wird er über Hover und Fokus. Die Blase
// hängt seit AP-2.49 per Portal an `document.body` mit `position: fixed` -
// vorher lag sie im Fluss (`position: absolute`, z-index 30) und verschwand
// unter der Sidebar (`z-40`) neben „Steht an", und `.liste` schnitt sie an
// den runden Ecken ab (`overflow: hidden`). Seit AP-2.53 wird die Lage so
// geklemmt bzw. nach rechts geklappt, dass die Blase im Hauptbereich bleibt
// und die dunkelgrüne Sidebar weder unterlegt noch überdeckt. AP-2.56 engt
// auf schmalen Viewports maxWidth/maxHeight ein und klappt bei wenig Platz
// nach oben, damit Listenzeilen und Formularfelder weniger verdeckt werden.

import { useCallback, useId, useLayoutEffect, useRef, useState, type CSSProperties } from 'react';
import { createPortal } from 'react-dom';
import { Info } from 'lucide-react';
import { blasenLage, sidebarRechtsPx, type BlasenPos } from './infoTipLage';

interface InfoTipProps {
  text: string;
  /** Beschriftung des Knopfes für Screenreader. */
  label?: string;
  className?: string;
}

export function InfoTip({ text, label = 'Erklärung anzeigen', className = '' }: InfoTipProps) {
  const id = useId();
  const ankerRef = useRef<HTMLSpanElement>(null);
  const blaseRef = useRef<HTMLSpanElement>(null);
  const [offen, setOffen] = useState(false);
  const [pos, setPos] = useState<BlasenPos | null>(null);

  const messen = useCallback(() => {
    const el = ankerRef.current;
    if (!el) return;
    const r = el.getBoundingClientRect();
    const breite = blaseRef.current?.offsetWidth ?? 0;
    const hoehe = blaseRef.current?.offsetHeight ?? 0;
    setPos(
      blasenLage({
        anker: r,
        blasenBreite: breite,
        blasenHoehe: hoehe,
        sidebarRechts: sidebarRechtsPx(),
        viewportBreite: window.innerWidth,
        viewportHoehe: window.innerHeight,
      }),
    );
  }, []);

  useLayoutEffect(() => {
    if (!offen) {
      setPos(null);
      return;
    }
    messen();
    // Zweiter Pass: nach dem ersten setPos hat die Blase oft erst ihre
    // max-content-Breite/Höhe; ohne Nachmessen bliebe ein Überhang über der
    // Sidebar bzw. eine zu tiefe Blase unter dem Anker (AP-2.53 / AP-2.56).
    const idRahmen = window.requestAnimationFrame(() => messen());
    const on = () => messen();
    window.addEventListener('scroll', on, true);
    window.addEventListener('resize', on);
    return () => {
      window.cancelAnimationFrame(idRahmen);
      window.removeEventListener('scroll', on, true);
      window.removeEventListener('resize', on);
    };
  }, [offen, messen]);

  const stil: CSSProperties = pos
    ? {
        top: pos.top,
        ...(pos.left != null ? { left: pos.left, right: 'auto' } : { right: pos.right ?? 0 }),
        ...(pos.maxWidth != null ? { maxWidth: pos.maxWidth } : {}),
        ...(pos.maxHeight != null ? { maxHeight: pos.maxHeight } : {}),
      }
    : { top: 0, right: 0 };

  const blase = createPortal(
    <span
      ref={blaseRef}
      role="tooltip"
      id={id}
      className={`info-tip-blase${offen && pos ? ' info-tip-blase-sichtbar' : ''}`}
      style={stil}
    >
      {text}
    </span>,
    document.body,
  );

  return (
    <span
      ref={ankerRef}
      className={`info-tip ${className}`.trim()}
      onMouseEnter={() => setOffen(true)}
      onMouseLeave={() => setOffen(false)}
    >
      <button
        type="button"
        className="info-tip-knopf"
        aria-label={label}
        aria-describedby={id}
        onFocus={() => setOffen(true)}
        onBlur={() => setOffen(false)}
      >
        <Info className="h-4 w-4" aria-hidden />
      </button>
      {blase}
    </span>
  );
}
