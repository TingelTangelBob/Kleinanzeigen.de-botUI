// SPDX-FileCopyrightText: © Anzeigen-Studio contributors
// SPDX-License-Identifier: AGPL-3.0-or-later
//
// Stapel-Erkennung (2026-09-30): jede Gruppe wird einzeln eingereiht, eine
// abgelehnte Gruppe bleibt mit ihren Fotos stehen.

import { describe, expect, it, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import { StapelErkennung } from './StapelErkennung';
import type { KiStatus } from '../types';

const erkennungStarten = vi.fn();

vi.mock('../services/api', () => {
  class ApiFehler extends Error {
    status: number;
    constructor(meldung: string, status: number) { super(meldung); this.status = status; }
  }
  return { api: { ki: { erkennungStarten: (...args: unknown[]) => erkennungStarten(...args) } }, ApiFehler };
});

const STATUS: KiStatus = {
  hinterlegt: true, endet_auf: null, geaendert_am: null, modell: 'gpt-6-luna',
  modelle: [{ kennung: 'gpt-6-luna', name: 'GPT-6 Luna', beschreibung: '', preis_eingabe_usd: 0.1, preis_ausgabe_usd: 0.5 }],
  modell_waehlbar: true, bildkante: 512, verbrauch_usd: 0, budget_usd: 5, verbrauch_aufrufe: 0,
  modus: 'open_source', schluessel_selbst_setzbar: true, max_bilder: 4, parallel: 4, max_offen: 50,
};

function foto(name: string): File {
  return new File([new Uint8Array([0xff, 0xd8, 0xff])], name, { type: 'image/jpeg' });
}

function waehlen(dateien: File[]) {
  const feld = screen.getByLabelText('Fotos für den Stapel wählen') as HTMLInputElement;
  const liste = Object.assign([...dateien], { item: (i: number) => dateien[i] ?? null });
  Object.defineProperty(feld, 'files', { get: () => liste, configurable: true });
  fireEvent.change(feld);
}

beforeEach(() => {
  erkennungStarten.mockReset();
  let n = 0;
  globalThis.URL.createObjectURL = vi.fn(() => `blob:${n++}`);
  globalThis.URL.revokeObjectURL = vi.fn();
});

describe('StapelErkennung', () => {
  it('reiht je Anzeige eine Erkennung ein', async () => {
    erkennungStarten.mockResolvedValue({ id: 1 });
    const eingereiht = vi.fn();
    render(<StapelErkennung profil="test" kiStatus={STATUS} aufEingereiht={eingereiht} />);

    waehlen([foto('a.jpg'), foto('b.jpg'), foto('c.jpg')]);
    fireEvent.change(screen.getByLabelText('Fotos je Anzeige'), { target: { value: '2' } });
    fireEvent.click(screen.getByRole('button', { name: /2 Entwürfe erkennen lassen/ }));

    await waitFor(() => expect(erkennungStarten).toHaveBeenCalledTimes(2));
    expect(erkennungStarten.mock.calls[0][1].map((d: File) => d.name)).toEqual(['a.jpg', 'b.jpg']);
    expect(erkennungStarten.mock.calls[1][1].map((d: File) => d.name)).toEqual(['c.jpg']);
    expect(eingereiht).toHaveBeenCalledTimes(2);
    expect(await screen.findByText(/2 Anzeigen werden jetzt analysiert/)).toBeTruthy();
  });

  it('von Hand trennen ergibt eine weitere Anzeige', async () => {
    erkennungStarten.mockResolvedValue({ id: 1 });
    render(<StapelErkennung profil="test" kiStatus={STATUS} aufEingereiht={() => {}} />);
    waehlen([foto('a.jpg'), foto('b.jpg')]);
    fireEvent.change(screen.getByLabelText('Fotos je Anzeige'), { target: { value: '2' } });
    expect(screen.getByRole('button', { name: 'Erkennen lassen' })).toBeTruthy();

    fireEvent.click(screen.getByRole('button', { name: 'Vor Foto 2 eine neue Anzeige beginnen' }));
    expect(screen.getByRole('button', { name: /2 Entwürfe erkennen lassen/ })).toBeTruthy();
  });

  it('bricht bei der Obergrenze ab und behält die restlichen Fotos', async () => {
    const { ApiFehler } = await import('../services/api');
    erkennungStarten
      .mockResolvedValueOnce({ id: 1 })
      .mockRejectedValueOnce(new (ApiFehler as unknown as new (m: string, s: number) => Error)('Es warten bereits 50 Fotoanalysen.', 429));
    render(<StapelErkennung profil="test" kiStatus={STATUS} aufEingereiht={() => {}} />);
    waehlen([foto('a.jpg'), foto('b.jpg'), foto('c.jpg')]);
    fireEvent.click(screen.getByRole('button', { name: /3 Entwürfe erkennen lassen/ }));

    expect(await screen.findByText(/Es warten bereits 50 Fotoanalysen/)).toBeTruthy();
    expect(erkennungStarten).toHaveBeenCalledTimes(2);
    // a.jpg wurde angenommen; b und c bleiben stehen.
    expect(screen.getByRole('button', { name: /2 Entwürfe erkennen lassen/ })).toBeTruthy();
  });

  it('sperrt eine Anzeige mit zu vielen Fotos', () => {
    render(<StapelErkennung profil="test" kiStatus={{ ...STATUS, max_bilder: 2 }} aufEingereiht={() => {}} />);
    waehlen([foto('a.jpg'), foto('b.jpg'), foto('c.jpg')]);
    fireEvent.change(screen.getByLabelText('Fotos je Anzeige'), { target: { value: '2' } });
    // Fotos 2 und 3 zusammenfügen -> [a] [b, c] ist ok; [a,b] [c] auch. Alles zusammen: zu viel.
    fireEvent.click(screen.getByRole('button', { name: 'Foto 3 mit der vorigen Anzeige zusammenfügen' }));
    expect(screen.getByText(/mehr als 2 Fotos/)).toBeTruthy();
    expect((screen.getByRole('button', { name: /Erkennen lassen/ }) as HTMLButtonElement).disabled).toBe(true);
  });
});
