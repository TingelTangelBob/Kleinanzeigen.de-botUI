// SPDX-FileCopyrightText: © Anzeigen-Studio contributors
// SPDX-License-Identifier: AGPL-3.0-or-later
//
// Test der Preisherkunft (AP-2.22).
//
// Worum es geht: Die Preise dürfen nicht in der Komponente stehen, sondern
// kommen live aus `api.katalog.versandpakete()`. Geprüft wird deshalb beides -
// dass ein gelieferter Preis unverändert erscheint und dass die Oberfläche
// diese Herkunft benennt, statt die Beträge als feste Wahrheit auszugeben.

import { describe, expect, it, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import { VersandpaketWahl } from './VersandpaketWahl';

const versandpakete = vi.fn();

vi.mock('../services/api', () => ({
  api: { katalog: { versandpakete: () => versandpakete() } },
}));

beforeEach(() => {
  versandpakete.mockReset();
});

const paket = (wert: string, groesse: string, preis: number | null) => ({
  wert, groesse, anbieter: wert.split('_')[0], preis,
});

describe('VersandpaketWahl', () => {
  it('zeigt den gelieferten Preis und benennt die Live-Herkunft', async () => {
    versandpakete.mockResolvedValue([
      paket('Hermes_Päckchen', 'Klein', 0.99),
      paket('DHL_2', 'Klein', 6.19),
    ]);

    render(
      <VersandpaketWahl
        gewaehlt={[]}
        versandkosten={null}
        direktKaufen={false}
        aufAenderung={() => {}}
      />,
    );

    // Der Betrag stammt 1:1 aus der Antwort, nicht aus einer Tabelle hier.
    expect(await screen.findByText(/0,99\s*€/)).toBeDefined();
    expect(screen.getByText(/6,19\s*€/)).toBeDefined();
    expect(screen.getByText(/Preise live von Kleinanzeigen/)).toBeDefined();
  });

  it('nennt die Live-Herkunft nicht, wenn keine Preise ankommen', async () => {
    versandpakete.mockResolvedValue([
      paket('Hermes_Päckchen', 'Klein', null),
      paket('DHL_2', 'Klein', null),
    ]);

    render(
      <VersandpaketWahl
        gewaehlt={[]}
        versandkosten={null}
        direktKaufen={false}
        aufAenderung={() => {}}
      />,
    );

    expect(await screen.findByText(/Preise gerade nicht abrufbar/)).toBeDefined();
    expect(screen.queryByText(/Preise live von Kleinanzeigen/)).toBeNull();
  });
});
