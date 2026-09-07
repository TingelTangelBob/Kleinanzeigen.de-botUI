// SPDX-FileCopyrightText: © Anzeigen-Studio contributors
// SPDX-License-Identifier: AGPL-3.0-or-later
//
// Lage-Rechnung für die InfoTip-Portal-Blase (AP-2.53 / AP-2.56).

export interface BlasenPos {
  top: number;
  /** Abstand vom rechten Viewport-Rand (bevorzugte Rechtsausrichtung am Anker). */
  right?: number;
  /** Nach Clamp: linker Viewport-Abstand, rechts der Sidebar. */
  left?: number;
  /** Nach Clamp: Breite begrenzen, damit die Blase im Hauptbereich bleibt. */
  maxWidth?: number;
  /** Nach Clamp: Höhe begrenzen (schmale Viewports / wenig Platz unter dem Anker). */
  maxHeight?: number;
}

/** Außenabstand zu Viewport- und Sidebar-Kante (AP-2.34 / AP-2.53). */
export const INFOTIP_RAND_PX = 8;

/** CSS `w-60` der Sidebar, Fallback-Hinweis für Tests. */
export const SIDEBAR_BREITE_FALLBACK_PX = 240;

/** CSS `max-width: min(18rem, …)` der Blase (Desktop / ab sm). */
export const BLASEN_MAX_REM_PX = 18 * 16;

/**
 * Engerer Inhalts-Deckel auf schmalen Viewports (AP-2.56).
 * Unter Tailwind `sm` (640) wirkt 18rem (~288px) auf 375 optisch zu groß.
 */
export const BLASEN_MAX_MOBIL_REM_PX = 14 * 16;

/** Viewport-Schwelle für den mobilen Deckel (Tailwind `sm`). */
export const INFOTIP_MOBIL_MAX_VW = 640;

/** Senkrechter Abstand Anker ↔ Blase. */
export const INFOTIP_VERT_ABSTAND_PX = 6;

/** Soft-Cap für Blasenhöhe (AP-2.56); CSS spiegelt ~40vh / 12rem. */
export const BLASEN_MAX_HEIGHT_PX = 12 * 16;

export function sidebarRechtsPx(): number {
  const el = document.querySelector('.sidebar-schale');
  if (!el) return 0;
  return el.getBoundingClientRect().right;
}

function inhaltsMaxBreite(viewportBreite: number): number {
  return viewportBreite < INFOTIP_MOBIL_MAX_VW ? BLASEN_MAX_MOBIL_REM_PX : BLASEN_MAX_REM_PX;
}

/**
 * Senkrechte Lage: bevorzugt unter dem Anker (AP-2.34); klappt nach oben,
 * wenn unten zu wenig Platz ist und oben mehr bleibt (AP-2.56). Klemmt top
 * und setzt maxHeight, damit die Blase im Viewport bleibt.
 */
export function blasenVertikal(args: {
  anker: Pick<DOMRect, 'bottom'> & Partial<Pick<DOMRect, 'top'>>;
  blasenHoehe: number;
  viewportHoehe: number;
  rand?: number;
}): Pick<BlasenPos, 'top' | 'maxHeight'> {
  const rand = args.rand ?? INFOTIP_RAND_PX;
  const abstand = INFOTIP_VERT_ABSTAND_PX;
  const topUnten = args.anker.bottom + abstand;

  // Ohne Viewport-Höhe: bisheriges Verhalten (nur unter dem Anker).
  if (args.viewportHoehe <= 0) {
    return { top: topUnten };
  }

  const vh = args.viewportHoehe;
  const hoeheMess = Math.max(0, args.blasenHoehe);
  const ankerTop = args.anker.top ?? Math.max(0, args.anker.bottom - 24);
  const platzUnten = Math.max(0, vh - args.anker.bottom - abstand - rand);
  const platzOben = Math.max(0, ankerTop - abstand - rand);
  const softCap = Math.min(BLASEN_MAX_HEIGHT_PX, Math.max(rand, Math.floor(vh * 0.4)));

  // Noch keine gemessene Höhe: unter dem Anker starten; Nachmessen folgt.
  if (hoeheMess <= 0) {
    return { top: topUnten, maxHeight: Math.max(rand, Math.min(softCap, Math.max(platzUnten, softCap))) };
  }

  const untenPasst = hoeheMess <= platzUnten;
  const obenBesser = !untenPasst && platzOben > platzUnten;

  if (obenBesser) {
    const maxHeight = Math.max(rand, Math.min(softCap, platzOben));
    const sichtbar = Math.min(hoeheMess, maxHeight);
    return { top: Math.max(rand, ankerTop - abstand - sichtbar), maxHeight };
  }

  const maxHeight = Math.max(rand, Math.min(softCap, platzUnten > 0 ? platzUnten : softCap));
  const top = Math.min(topUnten, Math.max(rand, vh - rand - Math.min(hoeheMess, maxHeight)));
  return { top, maxHeight };
}

/**
 * Rechnet die feste Blasenlage. Bevorzugt Rechtsausrichtung am Anker
 * (AP-2.34); wenn die Blase sonst in die Sidebar ragen würde, klappt sie auf
 * `left = sidebarRechts + Rand` und begrenzt `maxWidth` (AP-2.53).
 * AP-2.56: engere maxWidth mobil; maxHeight + optional Flip nach oben.
 */
export function blasenLage(args: {
  anker: Pick<DOMRect, 'bottom' | 'right'> & Partial<Pick<DOMRect, 'top'>>;
  blasenBreite: number;
  blasenHoehe?: number;
  sidebarRechts: number;
  viewportBreite: number;
  viewportHoehe?: number;
  rand?: number;
}): BlasenPos {
  const rand = args.rand ?? INFOTIP_RAND_PX;
  const vert = blasenVertikal({
    anker: args.anker,
    blasenHoehe: args.blasenHoehe ?? 0,
    viewportHoehe: args.viewportHoehe ?? 0,
    rand,
  });
  const minLeft = args.sidebarRechts + rand;
  const maxRight = args.viewportBreite - rand;
  const right = Math.max(rand, args.viewportBreite - args.anker.right);
  const breite = Math.max(0, args.blasenBreite);
  const leftBeiRechts = args.viewportBreite - right - breite;
  const deckel = inhaltsMaxBreite(args.viewportBreite);

  // Noch keine gemessene Breite: erst rechts am Anker ausrichten; der
  // nächste Layout-Pass klemmt nach, sobald offsetWidth steht.
  if (breite <= 0 || leftBeiRechts >= minLeft) {
    const frei = Math.max(rand, maxRight - minLeft);
    // Mobil/ohne Sidebar: maxWidth mitgeben, damit CSS-18rem nicht „zu groß“ wirkt,
    // auch wenn rechts am Anker genug Platz wäre (AP-2.56).
    if (args.viewportBreite < INFOTIP_MOBIL_MAX_VW) {
      return {
        top: vert.top,
        right,
        maxWidth: Math.min(deckel, frei),
        ...(vert.maxHeight != null ? { maxHeight: vert.maxHeight } : {}),
      };
    }
    return {
      top: vert.top,
      right,
      ...(vert.maxHeight != null ? { maxHeight: vert.maxHeight } : {}),
    };
  }

  const maxWidth = Math.max(rand, Math.min(deckel, maxRight - minLeft));
  return {
    top: vert.top,
    left: minLeft,
    maxWidth,
    ...(vert.maxHeight != null ? { maxHeight: vert.maxHeight } : {}),
  };
}
