// SPDX-FileCopyrightText: © Anzeigen-Studio contributors
// SPDX-License-Identifier: AGPL-3.0-or-later
//
// Test des Lauf-Popups in der Glocke (AP-2.39): Vorgangs-Icon, kurzer
// Anzeigenbezug, kein sichtbarer Zustands-Text und ein atmender Punkt für
// aktive Läufe.

import { beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { Glocke } from './Glocke';
import { MeldungenProvider } from '../context/MeldungenContext';
import type { BestandsAnzeige, Job } from '../types';

const jobsListe = vi.fn();
const bestandListe = vi.fn();

vi.mock('../services/api', () => ({
  api: {
    jobs: { liste: (...a: unknown[]) => jobsListe(...a) },
    bestand: { liste: (...a: unknown[]) => bestandListe(...a) },
  },
}));

function job(teil: Partial<Job>): Job {
  return {
    id: 1,
    profil_slug: 'test',
    befehl: 'publish',
    argumente: [],
    zustand: 'fertig',
    eingereicht_am: '2026-09-04T09:00:00Z',
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
    ...teil,
  };
}

function anzeige(teil: Partial<BestandsAnzeige>): BestandsAnzeige {
  return {
    datei: 'ads/adapter/adapter.yaml',
    ordner: 'adapter',
    titel: 'Adapter mit einer sehr langen Überschrift für die Zeile',
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
    ...teil,
  };
}

beforeEach(() => {
  vi.clearAllMocks();
  jobsListe.mockResolvedValue([]);
  bestandListe.mockResolvedValue([]);
});

describe('Glocke – Laufzeilen (AP-2.39)', () => {
  it('zeigt Icon und einzeiligen Anzeigenbezug ohne sichtbare Fertig-Spalte', async () => {
    jobsListe.mockResolvedValue([
      job({
        id: 1,
        befehl: 'publish',
        zustand: 'fertig',
        anzeigen_glob: './ads/adapter/adapter.yaml',
      }),
      job({
        id: 2,
        befehl: 'update',
        zustand: 'laeuft',
        anzeigen_glob: './ads/adapter/adapter.yaml',
      }),
    ]);
    bestandListe.mockResolvedValue([anzeige({})]);

    render(
      <MeldungenProvider>
        <Glocke aufZiel={vi.fn()} />
      </MeldungenProvider>,
    );

    fireEvent.click(await screen.findByRole('button', { name: /^Benachrichtigungen/ }));
    const menue = await screen.findByRole('menu', { name: 'Benachrichtigungen' });
    const eintraege = within(menue).getAllByRole('menuitem', { name: /Adapter mit einer sehr langen/ });
    const erledigt = eintraege[0];
    const aktiv = eintraege[1];

    expect(within(menue).queryByText('Läufe')).toBeNull();
    expect(within(menue).queryByText('fertig')).toBeNull();
    expect(erledigt.className).toContain('glocke-zeile-fertig');
    expect(erledigt.querySelector('svg.lucide-upload')).toBeTruthy();
    expect(erledigt.querySelector('.glocke-zeile-titel')?.className).toContain('truncate');
    expect(aktiv.querySelector('svg.lucide-refresh-cw')).toBeTruthy();
    expect(aktiv.querySelector('.status-punkt-aktiv')).toBeTruthy();
  });

  it('lädt den Anzeigenbezug für jedes Profil der Läufe', async () => {
    jobsListe.mockResolvedValue([
      job({ id: 1, profil_slug: 'eins' }),
      job({ id: 2, profil_slug: 'zwei' }),
    ]);

    render(
      <MeldungenProvider>
        <Glocke aufZiel={vi.fn()} />
      </MeldungenProvider>,
    );

    await waitFor(() => expect(bestandListe).toHaveBeenCalledTimes(2));
    expect(bestandListe).toHaveBeenCalledWith('eins');
    expect(bestandListe).toHaveBeenCalledWith('zwei');
  });
});
