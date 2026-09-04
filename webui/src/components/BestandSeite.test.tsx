// SPDX-FileCopyrightText: © Anzeigen-Studio contributors
// SPDX-License-Identifier: AGPL-3.0-or-later
//
// Test der Navigation im Bestand (AP-2.13).
//
// Der Fall stammt aus dem Betrieb: Wer eine Anzeige bearbeitet und links auf
// „Von anderen“ klickt, blieb in der Bearbeiten-Maske hängen. App.tsx rendert
// für beide Herkünfte dieselbe Komponente; React unmountet nicht, also überlebt
// der Zustand `bearbeitet` den Wechsel. Der Test bildet genau das nach: nicht
// neu rendern lassen, sondern dieselbe Instanz mit anderer `herkunft`.

import { describe, expect, it, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { fireEvent } from '@testing-library/dom';
import type { ReactNode } from 'react';
import { BestandSeite } from './BestandSeite';
import { MeldungenProvider } from '../context/MeldungenContext';
import type { BestandsAnzeige } from '../types';

// Der Editor meldet seine Tipps an die Glocke (AP-2.30) und braucht dafür den
// Provider.
function huelle({ children }: { children: ReactNode }) {
  return <MeldungenProvider>{children}</MeldungenProvider>;
}

const liste = vi.fn();
const anzeige = vi.fn();
const vorlagen = vi.fn();

vi.mock('../services/api', () => ({
  api: {
    bestand: {
      liste: (...a: unknown[]) => liste(...a),
      anzeige: (...a: unknown[]) => anzeige(...a),
      vorlagen: (...a: unknown[]) => vorlagen(...a),
      bildUrl: () => '',
      herkunftSetzen: vi.fn(),
      lokaleAenderungen: vi.fn(),
    },
    jobs: { starten: vi.fn() },
  },
  ApiFehler: class extends Error {},
}));

vi.mock('../context/useProfil', () => ({
  useProfil: () => ({ aktiv: { slug: 'test' }, profile: [], laedt: false }),
}));

function bestandsAnzeige(
  titel: string,
  herkunft: 'eigene' | 'fremde',
): BestandsAnzeige {
  return {
    datei: `${herkunft}/${titel}.yaml`,
    ordner: titel,
    titel,
    id: 1,
    art: 'OFFER',
    aktiv: true,
    kategorie: null,
    preis: 10,
    preistyp: 'FIXED',
    versandart: 'PICKUP',
    versandkosten: null,
    versandpakete: [],
    direkt_kaufen: false,
    bilder: 0,
    vorschaubild: null,
    erstellt_am: null,
    aktualisiert_am: null,
    neueinstellung_am: null,
    faellig: false,
    lokal_geaendert: false,
    hinweise: [],
    unlesbar: null,
    herkunft,
    geloescht: false,
  };
}

const EIGENE = bestandsAnzeige('Kinderwagen', 'eigene');
const FREMDE = bestandsAnzeige('Bohrmaschine', 'fremde');

beforeEach(() => {
  liste.mockReset();
  anzeige.mockReset();
  vorlagen.mockReset();
  liste.mockResolvedValue([EIGENE, FREMDE]);
  vorlagen.mockResolvedValue([]);
  anzeige.mockResolvedValue({
    kopf: EIGENE,
    felder: { title: 'Kinderwagen', description: 'Text', price: 10 },
    aenderbar: ['title', 'description', 'price'],
  });
});

/**
 * Merkmal der offenen Maske. Nicht die Überschrift: die trägt seit AP-2.15 den
 * Anzeigentitel, und den zeigt die Liste auch. Seit AP-2.30 hat der Editor
 * keinen „Zurück"-Link mehr - der „Speichern"-Knopf in der Fußleiste gibt es
 * dagegen nur dort.
 */
const maske = () => screen.queryByRole('button', { name: 'Speichern' });

/** Öffnet die Bearbeiten-Maske über die Anzeigenzeile, wie ein Klick es tut. */
async function maskeOeffnen(titel: string) {
  fireEvent.click(await screen.findByText(titel));
  await waitFor(() => { expect(maske()).not.toBeNull(); });
}

describe('Bestand: Maske folgt der Navigation (AP-2.13)', () => {
  it('schließt die Bearbeiten-Maske beim Wechsel zu „Von anderen“', async () => {
    const { rerender } = render(
      <BestandSeite herkunft="eigene" aufZiel={vi.fn()} />, { wrapper: huelle },
    );
    await maskeOeffnen('Kinderwagen');

    // Kein Remount: genau das macht die Seitenleiste auch.
    rerender(<BestandSeite herkunft="fremde" aufZiel={vi.fn()} />);

    expect(maske()).toBeNull();
    expect(await screen.findByText('Von anderen')).toBeDefined();
    expect(await screen.findByText('Bohrmaschine')).toBeDefined();
  });

  it('schließt die Maske auch auf dem Rückweg zu „Meine Anzeigen“', async () => {
    const { rerender } = render(
      <BestandSeite herkunft="fremde" aufZiel={vi.fn()} />, { wrapper: huelle },
    );
    await maskeOeffnen('Bohrmaschine');

    rerender(<BestandSeite herkunft="eigene" aufZiel={vi.fn()} />);

    expect(maske()).toBeNull();
    expect(await screen.findByText('Meine Anzeigen')).toBeDefined();
  });

  it('setzt Suche und Filter beim Wechsel zurück', async () => {
    const { rerender } = render(
      <BestandSeite herkunft="eigene" aufZiel={vi.fn()} />, { wrapper: huelle },
    );

    const suchfeld = await screen.findByPlaceholderText('Titel, Kategorie oder Anzeigennummer');
    fireEvent.change(suchfeld, { target: { value: 'Kinderwagen' } });
    // Seit AP-2.36 heißt der Filter „Gelöscht" und die Reiter tragen ihre
    // Zahl - deshalb per Regex statt über den blanken Namen.
    fireEvent.click(screen.getByRole('button', { name: /^Gelöscht/ }));

    rerender(<BestandSeite herkunft="fremde" aufZiel={vi.fn()} />);

    await waitFor(() => {
      expect(
        (screen.getByPlaceholderText('Titel, Kategorie oder Anzeigennummer') as HTMLInputElement)
          .value,
      ).toBe('');
    });
    // Ein mitgeschleppter Filter versteckt sonst genau die Liste, die man
    // sehen wollte.
    // Vorgabe ist seit AP-2.36 „Aktiv", nicht mehr „Alle".
    expect(screen.getByRole('button', { name: /^Aktiv/ }).getAttribute('aria-pressed')).toBe('true');
    expect(await screen.findByText('Bohrmaschine')).toBeDefined();
  });

  it('öffnet den Editor ohne „Zurück"-Link (AP-2.30)', async () => {
    render(<BestandSeite herkunft="eigene" aufZiel={vi.fn()} />, { wrapper: huelle });
    await maskeOeffnen('Kinderwagen');

    // Mockup v4: die Kopfzeile trägt nur noch Titel und Badge. Zurück führt
    // die Seitenleiste.
    expect(screen.queryByRole('button', { name: /Zurück/ })).toBeNull();
    expect(screen.getByRole('heading', { name: 'Kinderwagen' })).toBeDefined();
  });
});
