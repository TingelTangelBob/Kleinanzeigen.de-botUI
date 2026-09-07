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
import { fireEvent } from '@testing-library/dom';
import { render, screen } from '@testing-library/react';
import { VersandpaketWahl } from './VersandpaketWahl';

const versandpakete = vi.fn();

vi.mock('../services/api', () => ({
  api: { katalog: { versandpakete: () => versandpakete() } },
}));

beforeEach(() => {
  versandpakete.mockReset();
  window.localStorage.clear();
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
        gewaehlt={['Hermes_Päckchen']}
        versandkosten={null}
        direktKaufen={false}
        versandart="SHIPPING"
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
        gewaehlt={['Hermes_Päckchen']}
        versandkosten={null}
        direktKaufen={false}
        versandart="SHIPPING"
        aufAenderung={() => {}}
      />,
    );

    expect(await screen.findByText(/Preise gerade nicht abrufbar/)).toBeDefined();
    expect(screen.queryByText(/Preise live von Kleinanzeigen/)).toBeNull();
  });

  it('zeigt konkrete Optionen erst nach der Größenwahl', async () => {
    versandpakete.mockResolvedValue([
      paket('Hermes_Päckchen', 'Klein', 0.99),
      paket('DHL_2', 'Klein', 6.19),
    ]);
    const aufAenderung = vi.fn();
    const aufVersandart = vi.fn();

    render(
      <VersandpaketWahl
        gewaehlt={[]}
        versandkosten={null}
        direktKaufen={false}
        speicherSchluessel="profil:anzeige.yaml"
        aufAenderung={aufAenderung}
        aufVersandart={aufVersandart}
      />,
    );

    await screen.findByText(/Preise live von Kleinanzeigen/);
    // Angezeigt wird der Name ohne Unterstrich; der rohe Katalogwert bleibt.
    expect(screen.queryByText('Hermes Päckchen')).toBeNull();

    fireEvent.click(screen.getByRole('button', { name: 'Klein' }));
    expect(aufVersandart).toHaveBeenCalledWith('SHIPPING');
    expect(screen.getByText('Optionen für Klein')).toBeDefined();
    expect(screen.getByText('Hermes Päckchen')).toBeDefined();

    fireEvent.click(screen.getByRole('button', { name: /Hermes Päckchen/ }));
    expect(aufAenderung).toHaveBeenCalledWith(['Hermes_Päckchen']);
  });

  it('behält die reine Größenwahl beim erneuten Öffnen der Anzeige', async () => {
    versandpakete.mockResolvedValue([
      paket('Hermes_Päckchen', 'Klein', 0.99),
    ]);
    const eigenschaften = {
      gewaehlt: [] as string[],
      versandkosten: null,
      direktKaufen: false,
      versandart: 'NOT_APPLICABLE',
      speicherSchluessel: 'profil:anzeige.yaml',
      aufAenderung: () => {},
    } as const;

    const ersteAnsicht = render(<VersandpaketWahl {...eigenschaften} />);
    await screen.findByText(/Preise live von Kleinanzeigen/);
    fireEvent.click(screen.getByRole('button', { name: 'Klein' }));
    ersteAnsicht.unmount();

    render(<VersandpaketWahl {...eigenschaften} versandart="SHIPPING" />);
    expect(await screen.findByText('Optionen für Klein')).toBeDefined();
  });

  it('verändert die Chipbreite nicht durch ein Auswahlhäkchen', async () => {
    versandpakete.mockResolvedValue([paket('DHL_2', 'Klein', 6.19)]);
    render(
      <VersandpaketWahl
        gewaehlt={[]}
        versandkosten={null}
        direktKaufen={false}
        aufAenderung={() => {}}
      />,
    );

    await screen.findByText(/Preise live von Kleinanzeigen/);
    const klein = screen.getByRole('button', { name: 'Klein' });
    fireEvent.click(klein);
    expect(klein.querySelector('svg')).toBeNull();
    expect(screen.getByRole('button', { name: /DHL 2/ }).querySelector('svg')).toBeNull();
  });

  it('setzt Abholung und schaltet Direkt kaufen dabei aus', async () => {
    versandpakete.mockResolvedValue([paket('Hermes_Päckchen', 'Klein', 0.99)]);
    const aufAenderung = vi.fn();
    const aufVersandart = vi.fn();
    const aufDirektKaufen = vi.fn();

    render(
      <VersandpaketWahl
        gewaehlt={['Hermes_Päckchen']}
        versandkosten={null}
        direktKaufen
        versandart="SHIPPING"
        aufAenderung={aufAenderung}
        aufVersandart={aufVersandart}
        aufDirektKaufen={aufDirektKaufen}
      />,
    );

    await screen.findByText('Hermes Päckchen');
    fireEvent.click(screen.getByRole('button', { name: 'Abholung' }));
    expect(aufVersandart).toHaveBeenCalledWith('PICKUP');
    expect(aufDirektKaufen).toHaveBeenCalledWith(false);
    expect(aufAenderung).toHaveBeenCalledWith([]);
  });
});
