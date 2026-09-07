// SPDX-FileCopyrightText: © Anzeigen-Studio contributors
// SPDX-License-Identifier: AGPL-3.0-or-later
//
// Test of the responsive page title in the application topbar (AP-2.33 / AP-2.55).

import { describe, expect, it, vi } from 'vitest';
import { render, waitFor } from '@testing-library/react';
import type { Route } from '../routing';
import { useKopfAktionen } from '../context/kopfAktionenKontext';
import { Layout } from './Layout';

const profilMock = vi.hoisted(() => ({
  profile: [] as { slug: string; anzeigename: string; angelegt_am: string; geaendert_am: string }[],
  aktiv: null as null | { slug: string; anzeigename: string; angelegt_am: string; geaendert_am: string },
  waehlen: vi.fn(),
}));

vi.mock('../context/useAuth', () => ({
  useAuth: () => ({ status: { name: 'Test' }, abmelden: vi.fn() }),
}));

vi.mock('../context/useProfil', () => ({
  useProfil: () => profilMock,
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

const aktivProfil = {
  slug: 'privat',
  anzeigename: 'Privatkonto',
  angelegt_am: '2026-01-01',
  geaendert_am: '2026-01-01',
};

function KopfAktionKnopf() {
  return useKopfAktionen(
    <button type="button" className="btn-primaer">Holen</button>,
  );
}

describe('Layout: Seitentitel in der Topbar (AP-2.33)', () => {
  it.each([
    [route('uebersicht'), 'Übersicht'],
    [route('anzeigen'), 'Meine Anzeigen'],
    [route('anzeigen', 'fremde'), 'Von anderen'],
    [route('anzeigen', 'archiv'), 'Archiv'],
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

describe('Layout: Nav-Ordnung (AP-2.49 / AP-2.58)', () => {
  it('ordnet Übersicht → Warteschlange → Anzeigen-Gruppe; Einstellungen/Abmelden unten', () => {
    const { container } = render(
      <Layout route={route('uebersicht')} aufZiel={vi.fn()}>
        <p>Inhalt</p>
      </Layout>,
    );
    const aside = container.querySelector('aside.sidebar-schale');
    expect(aside).toBeTruthy();

    const nav = aside!.querySelector('nav');
    expect(nav?.textContent).toContain('Übersicht');
    expect(nav?.textContent).toContain('Warteschlange');
    expect(nav?.textContent).toContain('Meine Anzeigen');
    expect(nav?.textContent).toContain('Von anderen');
    expect(nav?.textContent).toContain('Neue Anzeige');
    expect(nav?.textContent).toContain('Archiv');
    expect(nav?.textContent).toContain('Anzeigen');
    expect(nav?.textContent).not.toContain('Einstellungen');

    const labels = [...aside!.querySelectorAll('button')].map(b => b.textContent ?? '');
    const iUeb = labels.findIndex(t => t.includes('Übersicht'));
    const iWart = labels.findIndex(t => t.includes('Warteschlange'));
    const iMeine = labels.findIndex(t => t.includes('Meine Anzeigen'));
    const iFremde = labels.findIndex(t => t.includes('Von anderen'));
    const iNeu = labels.findIndex(t => t.includes('Neue Anzeige'));
    const iArchiv = labels.findIndex(t => t.includes('Archiv'));
    const iEinst = labels.findIndex(t => t.includes('Einstellungen'));
    const iAb = labels.findIndex(t => t.includes('Abmelden'));

    expect(iUeb).toBeGreaterThanOrEqual(0);
    expect(iWart).toBeGreaterThan(iUeb);
    expect(iMeine).toBeGreaterThan(iWart);
    expect(iFremde).toBeGreaterThan(iMeine);
    expect(iNeu).toBeGreaterThan(iFremde);
    expect(iArchiv).toBeGreaterThan(iNeu);
    expect(iEinst).toBeGreaterThan(iArchiv);
    expect(iAb).toBeGreaterThan(iEinst);

    // Einstellungen vs. Abmelden: Trennlinie wie bisher (AP-2.49).
    const fuss = aside!.querySelector('.safe-unten');
    expect(fuss?.querySelector('[style*="sidebar-rand"]') || fuss?.innerHTML.includes('sidebar-rand')).toBeTruthy();
  });
});

describe('Layout: Topbar-Dichte mobil (AP-2.55)', () => {
  it('zeigt den Profilnamen, wenn der Aktions-Slot leer ist', () => {
    profilMock.aktiv = aktivProfil;
    profilMock.profile = [aktivProfil];
    const { container } = render(
      <Layout route={route('uebersicht')} aufZiel={vi.fn()}>
        <p>Inhalt</p>
      </Layout>,
    );
    const topbar = container.querySelector('header.topbar');
    expect(topbar?.textContent).toContain('Privatkonto');
    expect(topbar?.querySelector('.topbar-profilname')?.textContent).toBe('Privatkonto');
  });

  it('blendet den Profilnamen aus, sobald kopf-aktionen Kinder hat', async () => {
    profilMock.aktiv = aktivProfil;
    profilMock.profile = [aktivProfil];
    const { container } = render(
      <Layout route={route('anzeigen')} aufZiel={vi.fn()}>
        <KopfAktionKnopf />
      </Layout>,
    );
    const topbar = container.querySelector('header.topbar');
    expect(topbar?.textContent).toContain('Meine Anzeigen');

    await waitFor(() => {
      expect(container.querySelector('.kopf-aktionen')?.childElementCount).toBeGreaterThan(0);
      expect(topbar?.querySelector('.topbar-profilname')).toBeNull();
      expect(topbar?.textContent).not.toContain('Privatkonto');
      expect(topbar?.textContent).toContain('Holen');
    });
  });

  it('gibt dem Seitentitel unter sm Vorrang-Klassen', () => {
    profilMock.aktiv = null;
    profilMock.profile = [];
    const { container } = render(
      <Layout route={route('anzeigen')} aufZiel={vi.fn()}>
        <p>Inhalt</p>
      </Layout>,
    );
    const titel = container.querySelector('header.topbar span.font-semibold');
    expect(titel?.className).toContain('min-w-[7.5rem]');
    expect(titel?.className).toContain('flex-1');
    expect(titel?.className).toContain('sm:flex-initial');
    expect(titel?.getAttribute('title')).toBe('Meine Anzeigen');
  });

  it('hält einen eigenen Aktions-Slot unter der Topleiste bereit (mobil)', () => {
    profilMock.aktiv = null;
    profilMock.profile = [];
    const { container } = render(
      <Layout route={route('anzeigen')} aufZiel={vi.fn()}>
        <p>Inhalt</p>
      </Layout>,
    );
    // Der Mobil-Slot steht außerhalb der Topleiste, direkt davor das <header>.
    const mobil = container.querySelector('.kopf-aktionen-mobil');
    expect(mobil).not.toBeNull();
    expect(mobil?.closest('header.topbar')).toBeNull();
    expect(mobil?.className).toContain('md:hidden');
  });
});
