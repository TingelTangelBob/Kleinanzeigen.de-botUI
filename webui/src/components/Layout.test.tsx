// SPDX-FileCopyrightText: © Anzeigen-Studio contributors
// SPDX-License-Identifier: AGPL-3.0-or-later
//
// Test of the responsive page title in the application topbar (AP-2.33).

import { describe, expect, it, vi } from 'vitest';
import { render } from '@testing-library/react';
import type { Route } from '../routing';
import { Layout } from './Layout';

vi.mock('../context/useAuth', () => ({
  useAuth: () => ({ status: { name: 'Test' }, abmelden: vi.fn() }),
}));

vi.mock('../context/useProfil', () => ({
  useProfil: () => ({ profile: [], aktiv: null, waehlen: vi.fn() }),
}));

vi.mock('../hooks/useThema', () => ({
  useThema: () => ({ effektiv: 'hell' }),
}));

vi.mock('../services/api', () => ({
  api: { jobs: { liste: vi.fn().mockResolvedValue([]) } },
}));

vi.mock('./Glocke', () => ({ Glocke: () => null }));

const route = (seite: Route['seite'], anzeigen: Route['anzeigen'] = 'eigene'): Route => ({
  seite,
  anzeigen,
  einstellung: 'bot',
  anzeigeDatei: null,
  anzeigeBearbeiten: false,
});

describe('Layout: Seitentitel in der Topbar (AP-2.33)', () => {
  it.each([
    [route('uebersicht'), 'Übersicht'],
    [route('anzeigen'), 'Meine Anzeigen'],
    [route('anzeigen', 'fremde'), 'Von anderen'],
    [route('neu'), 'Neue Anzeige'],
    [route('warteschlange'), 'Warteschlange'],
    [route('einstellungen'), 'Einstellungen'],
  ] as const)('zeigt %s nach dem Menü-Button', (aktuelleRoute, titel) => {
    const { container } = render(
      <Layout route={aktuelleRoute} aufZiel={vi.fn()}>
        <p>Inhalt</p>
      </Layout>,
    );
    const topbar = container.querySelector('header.topbar');

    expect(topbar?.textContent).toContain(titel);
    expect(topbar?.textContent).not.toContain('Anzeigen-Studio');
  });
});

describe('Layout: Nav-Fuß (AP-2.49)', () => {
  it('stellt Warteschlange und Einstellungen unter die Hauptnav, über Abmelden', () => {
    const { container } = render(
      <Layout route={route('uebersicht')} aufZiel={vi.fn()}>
        <p>Inhalt</p>
      </Layout>,
    );
    const aside = container.querySelector('aside.sidebar-schale');
    expect(aside).toBeTruthy();

    const nav = aside!.querySelector('nav');
    expect(nav?.textContent).toContain('Neue Anzeige');
    expect(nav?.textContent).not.toContain('Warteschlange');
    expect(nav?.textContent).not.toContain('Einstellungen');

    const labels = [...aside!.querySelectorAll('button')].map(b => b.textContent ?? '');
    const iNeu = labels.findIndex(t => t.includes('Neue Anzeige'));
    const iWart = labels.findIndex(t => t.includes('Warteschlange'));
    const iEinst = labels.findIndex(t => t.includes('Einstellungen'));
    const iAb = labels.findIndex(t => t.includes('Abmelden'));

    expect(iNeu).toBeGreaterThanOrEqual(0);
    expect(iWart).toBeGreaterThan(iNeu);
    expect(iEinst).toBeGreaterThan(iWart);
    expect(iAb).toBeGreaterThan(iEinst);
  });
});
