// SPDX-FileCopyrightText: © Anzeigen-Studio contributors
// SPDX-License-Identifier: AGPL-3.0-or-later
//
// InfoTip: Portal-Blase über der Sidebar (AP-2.49), Clamp rechts davon (AP-2.53),
// mobil engere maxWidth/maxHeight + Flip nach oben (AP-2.56).

import { afterEach, describe, expect, it, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { InfoTip } from './InfoTip';
import {
  BLASEN_MAX_HEIGHT_PX,
  BLASEN_MAX_MOBIL_REM_PX,
  BLASEN_MAX_REM_PX,
  INFOTIP_RAND_PX,
  SIDEBAR_BREITE_FALLBACK_PX,
  blasenLage,
  blasenVertikal,
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
    expect(pos.maxWidth).toBeLessThanOrEqual(BLASEN_MAX_REM_PX);
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

describe('blasenLage / blasenVertikal (AP-2.56)', () => {
  it('engt maxWidth auf ~375 px ohne Sidebar (Drawer) ein', () => {
    const pos = blasenLage({
      anker: { top: 200, bottom: 224, right: 120 },
      blasenBreite: 288,
      sidebarRechts: 0,
      viewportBreite: 375,
      viewportHoehe: 812,
    });
    expect(pos.maxWidth).toBeLessThanOrEqual(BLASEN_MAX_MOBIL_REM_PX);
    expect(pos.maxWidth).toBeLessThanOrEqual(375 - 2 * INFOTIP_RAND_PX);
    // Links geklemmt bzw. rechts am Anker — jedenfalls im Viewport.
    if (pos.left != null) {
      expect(pos.left).toBeGreaterThanOrEqual(INFOTIP_RAND_PX);
    } else {
      expect(pos.right).toBeGreaterThanOrEqual(INFOTIP_RAND_PX);
    }
  });

  it('setzt maxHeight und klappt nach oben, wenn unten zu wenig Platz ist', () => {
    const vert = blasenVertikal({
      anker: { top: 700, bottom: 724 },
      blasenHoehe: 160,
      viewportHoehe: 812,
    });
    expect(vert.maxHeight).toBeDefined();
    expect(vert.maxHeight!).toBeLessThanOrEqual(BLASEN_MAX_HEIGHT_PX);
    // Oben mehr Platz → Blase über dem Anker.
    expect(vert.top).toBeLessThan(700);

    const pos = blasenLage({
      anker: { top: 700, bottom: 724, right: 200 },
      blasenBreite: 200,
      blasenHoehe: 160,
      sidebarRechts: 0,
      viewportBreite: 375,
      viewportHoehe: 812,
    });
    expect(pos.top).toBeLessThan(700);
    expect(pos.maxHeight).toBeDefined();
    expect(pos.maxHeight!).toBeLessThanOrEqual(BLASEN_MAX_HEIGHT_PX);
  });

  it('bleibt unter dem Anker, wenn unten genug Platz ist', () => {
    const vert = blasenVertikal({
      anker: { top: 200, bottom: 224 },
      blasenHoehe: 80,
      viewportHoehe: 812,
    });
    expect(vert.top).toBe(230);
    expect(vert.maxHeight).toBeDefined();
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
    Object.defineProperty(window, 'innerHeight', { configurable: true, value: 900 });

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
      Object.defineProperty(tipEl, 'offsetHeight', { configurable: true, get: () => 72 });

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

  it('setzt mobil maxWidth/maxHeight an der sichtbaren Blase (AP-2.56)', async () => {
    const user = userEvent.setup();
    Object.defineProperty(window, 'innerWidth', { configurable: true, value: 375 });
    Object.defineProperty(window, 'innerHeight', { configurable: true, value: 812 });

    const { unmount } = render(
      <InfoTip
        text="Fällig heißt: Der eingestellte Abstand zur letzten Veröffentlichung ist erreicht."
        label="Was fällig bedeutet"
      />,
    );

    try {
      const knopf = screen.getByRole('button', { name: 'Was fällig bedeutet' });
      const anker = knopf.parentElement as HTMLSpanElement;
      vi.spyOn(anker, 'getBoundingClientRect').mockReturnValue({
        x: 96,
        y: 200,
        top: 200,
        left: 96,
        bottom: 224,
        right: 120,
        width: 24,
        height: 24,
        toJSON() {
          return {};
        },
      });

      const tipId = knopf.getAttribute('aria-describedby')!;
      const tipEl = document.getElementById(tipId) as HTMLSpanElement;
      Object.defineProperty(tipEl, 'offsetWidth', { configurable: true, get: () => 288 });
      Object.defineProperty(tipEl, 'offsetHeight', { configurable: true, get: () => 120 });

      await user.hover(knopf);
      const tip = await screen.findByRole('tooltip');

      await waitFor(() => {
        expect(Number.parseFloat(tip.style.maxWidth)).toBeGreaterThan(0);
      });

      expect(Number.parseFloat(tip.style.maxWidth)).toBeLessThanOrEqual(BLASEN_MAX_MOBIL_REM_PX);
      expect(Number.parseFloat(tip.style.maxHeight)).toBeGreaterThan(0);
      expect(Number.parseFloat(tip.style.maxHeight)).toBeLessThanOrEqual(BLASEN_MAX_HEIGHT_PX);
    } finally {
      unmount();
    }
  });
});
