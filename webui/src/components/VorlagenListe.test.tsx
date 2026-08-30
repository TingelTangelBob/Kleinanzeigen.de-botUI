// SPDX-FileCopyrightText: © Anzeigen-Studio contributors
// SPDX-License-Identifier: AGPL-3.0-or-later
//
// Tests der Vorlagenliste (AP-3.3).

import { describe, expect, it, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { fireEvent } from '@testing-library/dom';
import { VorlagenListe } from './VorlagenListe';

const vorlagen = vi.fn();
const anwenden = vi.fn();
const entfernen = vi.fn();

vi.mock('../services/api', () => ({
  api: {
    bestand: {
      vorlagen: (...a: unknown[]) => vorlagen(...a),
      vorlageAnwenden: (...a: unknown[]) => anwenden(...a),
      vorlageEntfernen: (...a: unknown[]) => entfernen(...a),
    },
  },
  ApiFehler: class extends Error {},
}));

const VORLAGE = {
  datei: 'vorlagen/kinderwagen/vorlage_kinderwagen.yaml',
  ordner: 'kinderwagen',
  titel: 'Kinderwagen',
  bilder: 2,
  vorschaubild: null,
  erstellt_am: null,
  unlesbar: null,
};

beforeEach(() => {
  vorlagen.mockReset();
  anwenden.mockReset();
  entfernen.mockReset();
});

describe('Vorlagenliste', () => {
  it('bleibt unsichtbar, solange es keine Vorlagen gibt', async () => {
    vorlagen.mockResolvedValue([]);
    const { container } = render(<VorlagenListe profil="test" aufAngewendet={vi.fn()} />);

    await waitFor(() => { expect(vorlagen).toHaveBeenCalled(); });
    // Eine leere Überschrift erklärt niemandem, wofür sie da wäre.
    expect(container.querySelector('section')).toBeNull();
  });

  it('zeigt die Vorlagen mit Bildzahl', async () => {
    vorlagen.mockResolvedValue([VORLAGE]);
    render(<VorlagenListe profil="test" aufAngewendet={vi.fn()} />);

    expect(await screen.findByText('Kinderwagen')).toBeDefined();
    expect(screen.getByText('2 Bilder')).toBeDefined();
  });

  it('sagt, dass eine Vorlage nie online geht', async () => {
    vorlagen.mockResolvedValue([VORLAGE]);
    render(<VorlagenListe profil="test" aufAngewendet={vi.fn()} />);

    expect(await screen.findByText(/geht nie online/)).toBeDefined();
  });

  it('meldet die neue Anzeige nach dem Anwenden', async () => {
    vorlagen.mockResolvedValue([VORLAGE]);
    anwenden.mockResolvedValue({ datei: 'ads/kinderwagen/ad_kinderwagen.yaml' });
    const angewendet = vi.fn();
    render(<VorlagenListe profil="test" aufAngewendet={angewendet} />);

    fireEvent.click(await screen.findByRole('button', { name: /Anwenden/ }));

    await waitFor(() => {
      expect(angewendet).toHaveBeenCalledWith('ads/kinderwagen/ad_kinderwagen.yaml');
    });
    expect(anwenden).toHaveBeenCalledWith('test', VORLAGE.datei);
  });

  it('löscht erst nach Rückfrage', async () => {
    vorlagen.mockResolvedValue([VORLAGE]);
    entfernen.mockResolvedValue(undefined);
    render(<VorlagenListe profil="test" aufAngewendet={vi.fn()} />);

    fireEvent.click(await screen.findByRole('button', { name: /löschen/ }));
    // Der erste Klick fragt nur - Löschen nimmt die Bilder mit.
    expect(entfernen).not.toHaveBeenCalled();

    fireEvent.click(screen.getByRole('button', { name: 'Löschen' }));
    await waitFor(() => { expect(entfernen).toHaveBeenCalledWith('test', VORLAGE.datei); });
  });

  it('bietet eine unlesbare Vorlage nicht zum Anwenden an', async () => {
    vorlagen.mockResolvedValue([{ ...VORLAGE, unlesbar: 'kaputtes YAML' }]);
    render(<VorlagenListe profil="test" aufAngewendet={vi.fn()} />);

    const knopf = await screen.findByRole('button', { name: /Anwenden/ });
    expect(knopf).toHaveProperty('disabled', true);
    expect(screen.getByText(/kaputtes YAML/)).toBeDefined();
  });
});
