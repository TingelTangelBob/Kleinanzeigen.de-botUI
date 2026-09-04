// SPDX-FileCopyrightText: © Anzeigen-Studio contributors
// SPDX-License-Identifier: AGPL-3.0-or-later
//
// Tests der Theme-Wahl (AP-2.27): Migration alter Werte, der Resolver aus
// Wahl + OS-Zustand und das Live-Nachziehen bei OS-Wechsel.

import { afterEach, describe, expect, it, vi } from 'vitest';
import { act, renderHook } from '@testing-library/react';
import {
  THEMA_SCHLUESSEL, themaAufloesen, themaLesen, themaSchreiben, useThema,
} from './useThema';

/** Eine steuerbare `matchMedia`-Attrappe - jsdom bringt keine mit. */
function attrappe(startDunkel: boolean) {
  let matches = startDunkel;
  const hoerer = new Set<() => void>();
  const mql = {
    get matches() { return matches; },
    media: '(prefers-color-scheme: dark)',
    addEventListener: (_: string, cb: () => void) => { hoerer.add(cb); },
    removeEventListener: (_: string, cb: () => void) => { hoerer.delete(cb); },
    addListener: () => {},
    removeListener: () => {},
    onchange: null,
    dispatchEvent: () => false,
  } as unknown as MediaQueryList;
  return {
    einsetzen() { window.matchMedia = () => mql; },
    umschalten(dunkel: boolean) { matches = dunkel; act(() => hoerer.forEach(cb => cb())); },
  };
}

afterEach(() => {
  window.localStorage.clear();
  // @ts-expect-error – Aufräumen der Attrappe zwischen den Tests.
  delete window.matchMedia;
});

describe('themaLesen', () => {
  it('ohne gespeicherten Wert ist system die Vorgabe', () => {
    expect(themaLesen()).toBe('system');
  });

  it('alte Werte hell und dunkel bleiben gültig', () => {
    window.localStorage.setItem(THEMA_SCHLUESSEL, 'hell');
    expect(themaLesen()).toBe('hell');
    window.localStorage.setItem(THEMA_SCHLUESSEL, 'dunkel');
    expect(themaLesen()).toBe('dunkel');
  });

  it('ausdrückliches system und Müll ergeben beide system', () => {
    window.localStorage.setItem(THEMA_SCHLUESSEL, 'system');
    expect(themaLesen()).toBe('system');
    window.localStorage.setItem(THEMA_SCHLUESSEL, 'dark');
    expect(themaLesen()).toBe('system');
  });
});

describe('themaAufloesen', () => {
  it('system folgt dem OS-Zustand', () => {
    expect(themaAufloesen('system', true)).toBe('dunkel');
    expect(themaAufloesen('system', false)).toBe('hell');
  });

  it('hell und dunkel ignorieren den OS-Zustand', () => {
    expect(themaAufloesen('hell', true)).toBe('hell');
    expect(themaAufloesen('dunkel', false)).toBe('dunkel');
  });
});

describe('themaSchreiben', () => {
  it('legt den gewählten Modus wörtlich ab', () => {
    themaSchreiben('dunkel');
    expect(window.localStorage.getItem(THEMA_SCHLUESSEL)).toBe('dunkel');
    themaSchreiben('system');
    expect(window.localStorage.getItem(THEMA_SCHLUESSEL)).toBe('system');
  });

  it('weckt Hörer im selben Tab', () => {
    const auf = vi.fn();
    window.addEventListener('anzeigen-studio:thema', auf);
    themaSchreiben('hell');
    window.removeEventListener('anzeigen-studio:thema', auf);
    expect(auf).toHaveBeenCalledOnce();
  });
});

describe('useThema', () => {
  it('startet aus dem gespeicherten Wert', () => {
    window.localStorage.setItem(THEMA_SCHLUESSEL, 'dunkel');
    const { result } = renderHook(() => useThema());
    expect(result.current.wahl).toBe('dunkel');
    expect(result.current.effektiv).toBe('dunkel');
  });

  it('setWahl schreibt und aktualisiert das effektive Thema', () => {
    const { result } = renderHook(() => useThema());
    act(() => result.current.setWahl('dunkel'));
    expect(result.current.wahl).toBe('dunkel');
    expect(result.current.effektiv).toBe('dunkel');
    expect(window.localStorage.getItem(THEMA_SCHLUESSEL)).toBe('dunkel');
  });

  it('bei system wechselt effektiv live mit dem OS', () => {
    const mm = attrappe(false);
    mm.einsetzen();
    const { result } = renderHook(() => useThema());
    act(() => result.current.setWahl('system'));
    expect(result.current.effektiv).toBe('hell');
    mm.umschalten(true);
    expect(result.current.effektiv).toBe('dunkel');
    mm.umschalten(false);
    expect(result.current.effektiv).toBe('hell');
  });

  it('zieht eine Wahl aus einer anderen Instanz nach', () => {
    const { result } = renderHook(() => useThema());
    act(() => {
      window.localStorage.setItem(THEMA_SCHLUESSEL, 'dunkel');
      window.dispatchEvent(new Event('anzeigen-studio:thema'));
    });
    expect(result.current.wahl).toBe('dunkel');
  });
});
