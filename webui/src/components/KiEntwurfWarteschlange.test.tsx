// SPDX-FileCopyrightText: © Anzeigen-Studio contributors
// SPDX-License-Identifier: AGPL-3.0-or-later
//
// KI-Entwürfe erscheinen unabhängig vom geöffneten Formular in Dashboard und
// Warteschlange (AP-4.8).

import { beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { KiEntwurfWarteschlange } from './KiEntwurfWarteschlange';
import type { KiErkennung } from '../types';

const erkennungen = vi.fn();

vi.mock('../services/api', () => ({
  ApiFehler: class extends Error {},
  api: { ki: { erkennungen: (...args: unknown[]) => erkennungen(...args) } },
}));

function lauf(partial: Partial<KiErkennung>): KiErkennung {
  return {
    id: 1,
    profil_slug: 'test',
    zustand: 'wartet',
    eingereicht_am: '2026-09-13T12:00:00+00:00',
    gestartet_am: null,
    beendet_am: null,
    bilder: 2,
    entwurf: null,
    kosten: null,
    meldung: null,
    ...partial,
  };
}

beforeEach(() => {
  erkennungen.mockReset();
  erkennungen.mockResolvedValue([]);
});

describe('KiEntwurfWarteschlange', () => {
  it('zeigt fertige Entwürfe und führt direkt in den Prüf-Schritt', async () => {
    erkennungen.mockResolvedValue([
      lauf({
        id: 42,
        zustand: 'pruefen',
        bilder: 3,
        entwurf: {
          titel: 'Kinderfahrrad',
        } as KiErkennung['entwurf'],
      }),
    ]);
    const aufZiel = vi.fn();

    render(<KiEntwurfWarteschlange profil="test" aufZiel={aufZiel} />);

    expect(await screen.findByText('Kinderfahrrad')).toBeTruthy();
    expect(screen.getByText(/Entwurf ist bereit/)).toBeTruthy();
    fireEvent.click(screen.getByRole('button', { name: 'Prüfen' }));
    expect(aufZiel).toHaveBeenCalledWith('neu?erkennung=42');
  });

  it('blendet eine leere KI-Liste aus', async () => {
    render(<KiEntwurfWarteschlange profil="test" aufZiel={vi.fn()} />);

    await waitFor(() => expect(screen.queryByRole('heading', { name: /KI-Entwürfe prüfen/ })).toBeNull());
  });
});
