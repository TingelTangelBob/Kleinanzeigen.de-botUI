// SPDX-FileCopyrightText: © Anzeigen-Studio contributors
// SPDX-License-Identifier: AGPL-3.0-or-later
//
// Test der Übersicht: „Letzte Läufe" detaillierter (AP-2.29).
//
// Geprüft: je Eintrag steht der lesbare Lauf-Typ, und wo die Job-Metadaten eine
// Anzeige benennen (Glob beim Hochladen, `--ads=` sonst), steht deren Titel;
// ein Klick führt auf die Warteschlange (AP-2.31).

import { describe, expect, it, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { UebersichtSeite } from './UebersichtSeite';
import type { BestandsAnzeige, Job } from '../types';

const bestandListe = vi.fn();
const jobsListe = vi.fn();
const zugang = vi.fn();

vi.mock('../services/api', () => ({
  api: {
    bestand: { liste: (...a: unknown[]) => bestandListe(...a) },
    jobs: { liste: (...a: unknown[]) => jobsListe(...a) },
    profile: { zugang: (...a: unknown[]) => zugang(...a) },
  },
  ApiFehler: class extends Error {},
}));

// Stabile Referenz: UebersichtSeite hängt `laden` an `aktiv`. Ein bei jedem
// Render neu gebautes Objekt triebe die Ladeschleife endlos.
const mockProfilWert = {
  aktiv: { slug: 'test', anzeigename: 'Testkonto' },
  laedt: false,
  fehler: null,
  neuLaden: vi.fn(),
};

vi.mock('../context/useProfil', () => ({
  useProfil: () => mockProfilWert,
}));

function anzeige(t: Partial<BestandsAnzeige>): BestandsAnzeige {
  return {
    datei: 'downloaded-ads/ad_4711/ad_4711.yaml',
    ordner: 'ad_4711',
    titel: 'Roter Sessel',
    id: 4711,
    art: 'OFFER',
    aktiv: true,
    kategorie: null,
    preis: null,
    preistyp: null,
    versandart: null,
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
    herkunft: 'eigene',
    geloescht: false,
    ...t,
  };
}

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
  bestandListe.mockReset().mockResolvedValue([anzeige({})]);
  zugang.mockReset().mockResolvedValue({ passwort_hinterlegt: true });
  jobsListe.mockReset();
});

describe('UebersichtSeite – Letzte Läufe (AP-2.29)', () => {
  it('zeigt lesbaren Lauf-Typ statt des rohen Befehls', async () => {
    jobsListe.mockResolvedValue([job({ id: 1, befehl: 'update', anzeigen_glob: null })]);

    render(<UebersichtSeite aufZiel={vi.fn()} />);

    expect(await screen.findByText('Aktualisieren')).toBeDefined();
  });

  it('nennt die Anzeige über den Glob beim Hochladen einer einzelnen Anzeige', async () => {
    jobsListe.mockResolvedValue([
      job({ id: 1, befehl: 'update', anzeigen_glob: './downloaded-ads/ad_4711/ad_4711.yaml' }),
    ]);

    render(<UebersichtSeite aufZiel={vi.fn()} />);

    expect(await screen.findByText(/Roter Sessel · #4711/)).toBeDefined();
  });

  it('nennt die Anzeige über --ads= wenn kein Glob gesetzt ist', async () => {
    jobsListe.mockResolvedValue([job({ id: 1, befehl: 'update', argumente: ['--ads=4711'] })]);

    render(<UebersichtSeite aufZiel={vi.fn()} />);

    expect(await screen.findByText(/Roter Sessel · #4711/)).toBeDefined();
  });

  it('führt per Klick auf die Warteschlange', async () => {
    const aufZiel = vi.fn();
    jobsListe.mockResolvedValue([job({ id: 1, befehl: 'download' })]);

    render(<UebersichtSeite aufZiel={aufZiel} />);

    await userEvent.click(await screen.findByRole('button', { name: /Herunterladen/ }));
    expect(aufZiel).toHaveBeenCalledWith('warteschlange');
  });
});
