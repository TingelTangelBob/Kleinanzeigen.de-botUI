// SPDX-FileCopyrightText: © Anzeigen-Studio contributors
// SPDX-License-Identifier: AGPL-3.0-or-later
//
// Befunde des täglichen Abgleichs in der Glocke (AP-3.12).
//
// Geprüft wird über die Glocke statt über die Komponente allein: Sie rendert
// selbst nichts, ihr einziger Zweck ist, dass die Meldung dort ankommt.

import { beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { AbgleichMeldungen } from './AbgleichMeldungen';
import { Glocke } from './Glocke';
import { MeldungenProvider } from '../context/MeldungenContext';
import type { AbgleichMeldung } from '../types';

const abgleichMeldungen = vi.fn();

vi.mock('../services/api', () => ({
  api: {
    jobs: { liste: () => Promise.resolve([]) },
    bestand: { liste: () => Promise.resolve([]) },
    abgleich: { meldungen: () => abgleichMeldungen() },
  },
}));

function befund(teil: Partial<AbgleichMeldung> = {}): AbgleichMeldung {
  return {
    id: 7,
    profil: 'haushalt',
    profil_name: 'Haushalt',
    zeitpunkt: '2026-09-04T06:00:00Z',
    art: 'aenderung',
    titel: 'Täglicher Abgleich: 1 Änderung',
    text: 'Nicht mehr online: „Esstisch“.',
    ...teil,
  };
}

function aufbauen() {
  return render(
    <MeldungenProvider>
      <AbgleichMeldungen />
      <Glocke aufZiel={() => {}} />
    </MeldungenProvider>,
  );
}

describe('AbgleichMeldungen', () => {
  beforeEach(() => {
    localStorage.clear();
    abgleichMeldungen.mockReset();
  });

  it('bringt einen Befund in die Glocke', async () => {
    abgleichMeldungen.mockResolvedValue([befund()]);
    aufbauen();

    const knopf = await screen.findByRole('button', { name: /Benachrichtigungen – 1/ });
    fireEvent.click(knopf);

    expect(await screen.findByText('Täglicher Abgleich: 1 Änderung')).toBeTruthy();
    expect(screen.getByText(/Nicht mehr online/)).toBeTruthy();
  });

  it('meldet nichts, wenn es nichts gefunden hat', async () => {
    abgleichMeldungen.mockResolvedValue([]);
    aufbauen();

    await waitFor(() => expect(abgleichMeldungen).toHaveBeenCalled());
    expect(
      screen.getByRole('button', { name: 'Benachrichtigungen' }),
    ).toBeTruthy();
  });

  it('bleibt still, wenn das Backend nicht antwortet', async () => {
    // Ein nicht erreichbares Backend meldet sich an anderer Stelle laut genug;
    // hier wäre eine zweite Fehlerzeile nur Lärm.
    abgleichMeldungen.mockRejectedValue(new Error('weg'));
    aufbauen();

    await waitFor(() => expect(abgleichMeldungen).toHaveBeenCalled());
    expect(
      screen.getByRole('button', { name: 'Benachrichtigungen' }),
    ).toBeTruthy();
  });

  it('nennt bei mehreren Konten das Profil', async () => {
    abgleichMeldungen.mockResolvedValue([
      befund({ id: 1, profil: 'haushalt', profil_name: 'Haushalt' }),
      befund({ id: 2, profil: 'werkstatt', profil_name: 'Werkstatt' }),
    ]);
    aufbauen();

    fireEvent.click(await screen.findByRole('button', { name: /Benachrichtigungen – 2/ }));
    expect(await screen.findByText(/Werkstatt ·/)).toBeTruthy();
  });
});
