// SPDX-FileCopyrightText: © Anzeigen-Studio contributors
// SPDX-License-Identifier: AGPL-3.0-or-later
//
// Test der Warteschlangen-Seite (AP-2.31).
//
// Geprüft: aktive Läufe stehen oben mit lesbarem Befehl und Zustand, beendete
// darunter, der Start-Block ist sekundär (eingeklappt) und reiht beim Klick
// einen Lauf ein.

import { describe, expect, it, vi, beforeEach } from 'vitest';
import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { WarteschlangeSeite } from './WarteschlangeSeite';
import type { Job } from '../types';

const jobsListe = vi.fn();
const jobsStarten = vi.fn();
const jobsBeendeteLeeren = vi.fn();
const bestandListe = vi.fn();
const lokaleAenderungen = vi.fn();

vi.mock('../services/api', () => ({
  api: {
    jobs: {
      liste: (...a: unknown[]) => jobsListe(...a),
      starten: (...a: unknown[]) => jobsStarten(...a),
      beendeteLeeren: (...a: unknown[]) => jobsBeendeteLeeren(...a),
      log: () => Promise.resolve([]),
      stromUrl: () => '/api/jobs/1/strom',
      abbrechen: vi.fn(),
      eingabe: vi.fn(),
    },
    bestand: {
      liste: (...a: unknown[]) => bestandListe(...a),
      lokaleAenderungen: (...a: unknown[]) => lokaleAenderungen(...a),
    },
  },
  ApiFehler: class extends Error {},
}));

const mockProfilWert = {
  profile: [{ slug: 'test', anzeigename: 'Testkonto' }],
  aktiv: { slug: 'test', anzeigename: 'Testkonto' },
};

vi.mock('../context/useProfil', () => ({
  useProfil: () => mockProfilWert,
}));

function job(t: Partial<Job>): Job {
  return {
    id: 1,
    profil_slug: 'test',
    befehl: 'publish',
    argumente: [],
    zustand: 'fertig',
    eingereicht_am: '2026-09-02T10:00:00Z',
    gestartet_am: null,
    beendet_am: null,
    rueckgabecode: null,
    aufmerksamkeit: [],
    eingriff: null,
    meldung: null,
    wartet_bis: null,
    wartegrund: null,
    anzeigen_glob: null,
    phase: null,
    phase_text: null,
    phase_seit: null,
    ...t,
  };
}

beforeEach(() => {
  jobsListe.mockReset().mockResolvedValue([]);
  jobsStarten.mockReset().mockResolvedValue({ id: 99 });
  jobsBeendeteLeeren.mockReset().mockResolvedValue({ geloescht: 1 });
  bestandListe.mockReset().mockResolvedValue([]);
  lokaleAenderungen.mockReset().mockResolvedValue([]);
});

describe('WarteschlangeSeite', () => {
  it('zeigt aktive Läufe oben mit lesbarem Befehl und Zustand', async () => {
    jobsListe.mockResolvedValue([
      job({ id: 1, befehl: 'download', zustand: 'laeuft' }),
      job({ id: 2, befehl: 'publish', zustand: 'wartet' }),
    ]);

    render(<WarteschlangeSeite />);

    expect(await screen.findByText('Herunterladen')).toBeDefined();
    expect(screen.getByText('läuft')).toBeDefined();
    expect(screen.getByText('Veröffentlichen')).toBeDefined();
    expect(screen.getByText('wartet')).toBeDefined();
  });

  it('führt beendete Läufe unter „Zuletzt beendet"', async () => {
    jobsListe.mockResolvedValue([
      job({ id: 3, befehl: 'verify', zustand: 'gescheitert', beendet_am: '2026-09-02T09:00:00Z' }),
    ]);

    render(<WarteschlangeSeite />);

    expect(await screen.findByText('Zuletzt beendet')).toBeDefined();
    expect(screen.getByText('Prüfen')).toBeDefined();
    expect(screen.getByText('gescheitert')).toBeDefined();
  });

  it('meldet leere Abschnitte, statt sie zu verstecken', async () => {
    render(<WarteschlangeSeite />);

    expect(await screen.findByText(/Gerade läuft und wartet nichts/)).toBeDefined();
    expect(screen.getByText(/Noch kein Lauf abgeschlossen/)).toBeDefined();
  });

  it('leert beendete Läufe erst nach Rückfrage', async () => {
    jobsListe.mockResolvedValue([
      job({ id: 3, befehl: 'verify', zustand: 'fertig', beendet_am: '2026-09-02T09:00:00Z' }),
    ]);

    render(<WarteschlangeSeite />);

    await userEvent.click(await screen.findByRole('button', { name: /Beendete leeren/ }));
    // Erst die Rückfrage, kein sofortiger Aufruf.
    expect(jobsBeendeteLeeren).not.toHaveBeenCalled();

    const dialog = screen.getByRole('dialog');
    await userEvent.click(within(dialog).getByRole('button', { name: /Beendete leeren/ }));

    expect(jobsBeendeteLeeren).toHaveBeenCalledWith('test');
  });

  it('hält den Start-Block eingeklappt und reiht beim Klick einen Lauf ein', async () => {
    render(<WarteschlangeSeite />);

    // Eingeklappt: die Befehlskacheln sind nicht im Baum.
    await screen.findByText(/Gerade läuft und wartet nichts/);
    expect(screen.queryByText('Diagnose')).toBeNull();

    await userEvent.click(screen.getByRole('button', { name: /Neuen Lauf starten/ }));

    const diagnose = await screen.findByText('Diagnose');
    await userEvent.click(diagnose);

    expect(jobsStarten).toHaveBeenCalledWith('test', 'diagnose');
  });
});
