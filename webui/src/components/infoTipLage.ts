// SPDX-FileCopyrightText: © Anzeigen-Studio contributors
// SPDX-License-Identifier: AGPL-3.0-or-later
//
// Lage-Rechnung für die InfoTip-Portal-Blase (AP-2.53).

export interface BlasenPos {
  top: number;
  /** Abstand vom rechten Viewport-Rand (bevorzugte Rechtsausrichtung am Anker). */
  right?: number;
  /** Nach Clamp: linker Viewport-Abstand, rechts der Sidebar. */
  left?: number;
  /** Nach Clamp: Breite begrenzen, damit die Blase im Hauptbereich bleibt. */
  maxWidth?: number;
}

/** Außenabstand zu Viewport- und Sidebar-Kante (AP-2.34 / AP-2.53). */
export const INFOTIP_RAND_PX = 8;

/** CSS `w-60` der Sidebar, Fallback-Hinweis für Tests. */
export const SIDEBAR_BREITE_FALLBACK_PX = 240;

/** CSS `max-width: min(18rem, …)` der Blase. */
const BLASEN_MAX_REM_PX = 18 * 16;

export function sidebarRechtsPx(): number {
  const el = document.querySelector('.sidebar-schale');
  if (!el) return 0;
  return el.getBoundingClientRect().right;
}

/**
 * Rechnet die feste Blasenlage. Bevorzugt Rechtsausrichtung am Anker
 * (AP-2.34); wenn die Blase sonst in die Sidebar ragen würde, klappt sie auf
 * `left = sidebarRechts + Rand` und begrenzt `maxWidth` (AP-2.53).
 */
export function blasenLage(args: {
  anker: Pick<DOMRect, 'bottom' | 'right'>;
  blasenBreite: number;
  sidebarRechts: number;
  viewportBreite: number;
  rand?: number;
}): BlasenPos {
  const rand = args.rand ?? INFOTIP_RAND_PX;
  const top = args.anker.bottom + 6;
  const minLeft = args.sidebarRechts + rand;
  const maxRight = args.viewportBreite - rand;
  const right = Math.max(rand, args.viewportBreite - args.anker.right);
  const breite = Math.max(0, args.blasenBreite);
  const leftBeiRechts = args.viewportBreite - right - breite;

  // Noch keine gemessene Breite: erst rechts am Anker ausrichten; der
  // nächste Layout-Pass klemmt nach, sobald offsetWidth steht.
  if (breite <= 0 || leftBeiRechts >= minLeft) {
    return { top, right };
  }

  const maxWidth = Math.max(rand, Math.min(BLASEN_MAX_REM_PX, maxRight - minLeft));
  return { top, left: minLeft, maxWidth };
}
