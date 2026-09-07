// SPDX-FileCopyrightText: © Anzeigen-Studio contributors
// SPDX-License-Identifier: AGPL-3.0-or-later
//
// InfoTip: Portal-Blase über der Sidebar (AP-2.49) und Clamp rechts davon (AP-2.53).

import { afterEach, describe, expect, it, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { InfoTip } from './InfoTip';
import {
  INFOTIP_RAND_PX,
  SIDEBAR_BREITE_FALLBACK_PX,
  blasenLage,
} from './infoTipLage';

describe('blasenLage (AP-2.53)', () => {
  it('richtet rechts am Anker aus, wenn genug Platz neben der Sidebar ist', () => {
    const pos = blasenLage({
      anker: { bottom: 100, right: 800 },
      blasenBreite: 200,
      sidebarRechts: SIDEBAR_BREITE_FALLBACK_PX,
      viewportBreite: 1440,
    });
    expect(pos.top).toBe(106);
    expect(pos.right).toBe(1440 - 800);
    expect(pos.left).toBeUndefined();
    expect(pos.maxWidth).toBeUndefined();
  });

  it('klappt auf left rechts der Sidebar, wenn Rechtsausrichtung überlappt', () => {
    // Anker dicht hinter der Sidebar; 280px-Blase würde ~168px ins Grün ragen.
    const pos = blasenLage({
      anker: { bottom: 200, right: 280 },
      blasenBreite: 280,
      sidebarRechts: SIDEBAR_BREITE_FALLBACK_PX,
      viewportBreite: 1440,
    });
    expect(pos.top).toBe(206);
    expect(pos.right).toBeUndefined();
    expect(pos.left).toBe(SIDEBAR_BREITE_FALLBACK_PX + INFOTIP_RAND_PX);
    expect(pos.maxWidth).toBeGreaterThan(0);
    // Überhang gegen Sidebar: left - sidebarRechts == Rand (8px), Ziel <= 8px.
    expect((pos.left ?? 0) - SIDEBAR_BREITE_FALLBACK_PX).toBeLessThanOrEqual(INFOTIP_RAND_PX);
  });

  it('ohne gemessene Breite erst rechts ausrichten (Nachmessen folgt)', () => {
    const pos = blasenLage({
      anker: { bottom: 200, right: 280 },
      blasenBreite: 0,
      sidebarRechts: SIDEBAR_BREITE_FALLBACK_PX,
      viewportBreite: 1440,
    });
    expect(pos.right).toBe(1440 - 280);
    expect(pos.left).toBeUndefined();
  });
});

describe('InfoTip (AP-2.49 / AP-2.53)', () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('hängt die Blase per Portal an document.body, nicht unter dem Anker', async () => {
    const user = userEvent.setup();
    const { container } = render(
      <div className="sidebar-schale" style={{ position: 'relative', zIndex: 40 }}>
        <InfoTip text="Fällig heißt Abstand erreicht." label="Was fällig bedeutet" />
      </div>,
    );

    const tipGeschlossen = document.getElementById(
      screen.getByRole('button', { name: 'Was fällig bedeutet' }).getAttribute('aria-describedby')!,
    );
    expect(tipGeschlossen).toBeTruthy();
    expect(tipGeschlossen!.parentElement).toBe(document.body);
    expect(tipGeschlossen!.className).toContain('info-tip-blase');
    expect(tipGeschlossen!.className).not.toContain('info-tip-blase-sichtbar');

    await user.hover(screen.getByRole('button', { name: 'Was fällig bedeutet' }));

    const tip = await screen.findByRole('tooltip');
    expect(tip.textContent).toContain('Fällig heißt Abstand erreicht.');
    expect(tip.parentElement).toBe(document.body);
    expect(tip.className).toContain('info-tip-blase-sichtbar');
    // Nicht Nachfahre der Sidebar-Schale / des Ankers — sonst deckt z-40 die Blase zu.
    expect(container.querySelector('.sidebar-schale')!.contains(tip)).toBe(false);
    expect(container.querySelector('.info-tip')!.contains(tip)).toBe(false);
  });

  it('zeigt die Blase auch bei Tastatur-Fokus', async () => {
    const user = userEvent.setup();
    render(<InfoTip text="Kurzhilfe per Fokus." />);

    await user.tab();
    expect(document.activeElement).toBe(screen.getByRole('button', { name: 'Erklärung anzeigen' }));

    const tip = await screen.findByRole('tooltip');
    expect(tip.className).toContain('info-tip-blase-sichtbar');
    expect(tip.textContent).toContain('Kurzhilfe per Fokus.');
  });

  it('klemmt die sichtbare Blase rechts der Sidebar (AP-2.53)', async () => {
    const user = userEvent.setup();

    const aside = document.createElement('aside');
    aside.className = 'sidebar-schale';
    aside.dataset.infotipTest = '1';
    document.body.appendChild(aside);
    vi.spyOn(aside, 'getBoundingClientRect').mockReturnValue({
      x: 0,
      y: 0,
      top: 0,
      left: 0,
      bottom: 900,
      right: SIDEBAR_BREITE_FALLBACK_PX,
      width: SIDEBAR_BREITE_FALLBACK_PX,
      height: 900,
      toJSON() {
        return {};
      },
    });

    Object.defineProperty(window, 'innerWidth', { configurable: true, value: 1440 });

    const { unmount } = render(
      <InfoTip
        text="Steht an sammelt fällige und lokal geänderte Anzeigen ohne gelöschte."
        label="Was Steht an bedeutet"
      />,
    );

    try {
      const knopf = screen.getByRole('button', { name: 'Was Steht an bedeutet' });
      const anker = knopf.parentElement as HTMLSpanElement;
      vi.spyOn(anker, 'getBoundingClientRect').mockReturnValue({
        x: 256,
        y: 200,
        top: 200,
        left: 256,
        bottom: 224,
        right: 280,
        width: 24,
        height: 24,
        toJSON() {
          return {};
        },
      });

      const tipId = knopf.getAttribute('aria-describedby')!;
      const tipEl = document.getElementById(tipId) as HTMLSpanElement;
      Object.defineProperty(tipEl, 'offsetWidth', { configurable: true, get: () => 280 });

      await user.hover(knopf);
      const tip = await screen.findByRole('tooltip');

      await waitFor(() => {
        expect(tip.style.left).toBe('248px');
      });

      const left = Number.parseFloat(tip.style.left);
      expect(left).toBe(SIDEBAR_BREITE_FALLBACK_PX + INFOTIP_RAND_PX);
      expect(left - SIDEBAR_BREITE_FALLBACK_PX).toBeLessThanOrEqual(INFOTIP_RAND_PX);
      expect(tip.style.right).toBe('auto');
      expect(Number.parseFloat(tip.style.maxWidth)).toBeGreaterThan(0);
    } finally {
      unmount();
      aside.remove();
    }
  });
});
