// SPDX-FileCopyrightText: © Anzeigen-Studio contributors
// SPDX-License-Identifier: AGPL-3.0-or-later
//
// Sicherung, Export und Import (AP-3.6), kurze Kartentexte (AP-2.52).
//
// Der wichtigste Test hier ist `bietet Einspielen erst nach der Vorschau an`:
// Ein Import ohne vorherige Vorschau wäre ein Knopf, hinter dem sich der
// Bestand verändert, ohne dass vorher jemand sagen konnte, was passiert.

import { beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { SicherungAbschnitt } from './SicherungAbschnitt';

const vorschau = vi.fn();
const einspielen = vi.fn();

vi.mock('../services/api', () => ({
  ApiFehler: class extends Error {},
  api: {
    archiv: {
      exportUrl: (profil: string) => `/api/archiv/export?profil=${profil}`,
      vorschau: (...a: unknown[]) => vorschau(...a),
      einspielen: (...a: unknown[]) => einspielen(...a),
    },
  },
}));

function datei(name = 'sicherung.zip'): File {
  return new File([new Uint8Array([0x50, 0x4b])], name, { type: 'application/zip' });
}

function waehlen() {
  const eingabe = screen.getByLabelText('Archivdatei wählen') as HTMLInputElement;
  fireEvent.change(eingabe, { target: { files: [datei()] } });
}

describe('SicherungAbschnitt', () => {
  beforeEach(() => {
    vorschau.mockReset();
    einspielen.mockReset();
  });

  it('hält die Karte kurz und legt die Sicherheitsdetails in den InfoTip', () => {
    render(<SicherungAbschnitt profil="haushalt" />);
    expect(screen.getByText('Anzeigen, Bilder, Vorlagen und Bot-Einstellungen als ZIP.')).toBeTruthy();
    expect(screen.getByRole('button', { name: 'Erklärung zur Sicherung' })).toBeTruthy();
    expect(screen.queryByText(/Sichert Anzeigen mit Bildern/)).toBeNull();
  });

  it('verlinkt den Export auf das aktive Profil', () => {
    render(<SicherungAbschnitt profil="haushalt" />);
    const link = screen.getByText('Archiv herunterladen').closest('a');
    expect(link?.getAttribute('href')).toBe('/api/archiv/export?profil=haushalt');
  });

  it('bietet Einspielen erst nach der Vorschau an', async () => {
    vorschau.mockResolvedValue({
      dateien: 2, anzeigen: 1, bilder: 1,
      neu: ['downloaded-ads/a/ad_1.yaml', 'downloaded-ads/a/bild.jpg'],
      doppelt: [], abgewiesen: [],
    });
    render(<SicherungAbschnitt profil="haushalt" />);
    waehlen();

    expect(screen.queryByText('Einspielen')).toBeNull();

    fireEvent.click(screen.getByText('Ansehen'));

    expect(await screen.findByText(/2 Datei\(en\)/)).toBeTruthy();
    expect(screen.getByText('Einspielen')).toBeTruthy();
    expect(einspielen).not.toHaveBeenCalled();
  });

  it('fragt beim Überschreiben nach und gibt die Wahl weiter', async () => {
    vorschau.mockResolvedValue({
      dateien: 1, anzeigen: 1, bilder: 0,
      neu: [], doppelt: ['downloaded-ads/a/ad_1.yaml'], abgewiesen: [],
    });
    einspielen.mockResolvedValue({
      geschrieben: [], ersetzt: ['downloaded-ads/a/ad_1.yaml'],
      uebersprungen: [], abgewiesen: [], zusammenfassung: '0 übernommen, 1 ersetzt.',
    });
    render(<SicherungAbschnitt profil="haushalt" />);
    waehlen();
    fireEvent.click(screen.getByText('Ansehen'));

    const haken = await screen.findByLabelText(/bereits vorhandenen Dateien überschreiben/);
    fireEvent.click(haken);
    fireEvent.click(screen.getByText('Einspielen'));

    await waitFor(() => expect(einspielen).toHaveBeenCalled());
    expect(einspielen.mock.calls[0][2]).toBe(true);
    expect(await screen.findByText('0 übernommen, 1 ersetzt.')).toBeTruthy();
  });

  it('zeigt, was das Archiv nicht mitbringen durfte', async () => {
    vorschau.mockResolvedValue({
      dateien: 0, anzeigen: 0, bilder: 0, neu: [], doppelt: [],
      abgewiesen: ['.temp/browser-profile/Cookies: Ordner „.temp“ gehört nicht ins Archiv.'],
    });
    render(<SicherungAbschnitt profil="haushalt" />);
    waehlen();
    fireEvent.click(screen.getByText('Ansehen'));

    expect(await screen.findByText(/Keine übernehmbare Datei/)).toBeTruthy();
    expect(screen.getByText(/gehört nicht ins Archiv/)).toBeTruthy();
    // Ohne übernehmbare Datei gibt es auch nichts einzuspielen.
    expect(screen.queryByText('Einspielen')).toBeNull();
  });
});
