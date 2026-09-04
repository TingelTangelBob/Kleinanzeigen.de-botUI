// SPDX-FileCopyrightText: © Anzeigen-Studio contributors
// SPDX-License-Identifier: AGPL-3.0-or-later
//
// Wächter für die Befunde der UI-Sichtprüfung (AP-2.34).
//
// Alle vier Fälle hier sind am laufenden Browser gefunden worden, nicht
// ausgedacht. Sie stehen als Test, weil sie sonst beim nächsten Umbau
// zurückkommen: Es sind lauter Kleinigkeiten, die einzeln niemand vermisst.

import { describe, expect, it, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { UebersichtSeite } from './UebersichtSeite';
import { AnzeigenEditor } from './AnzeigenEditor';
import { MeldungenProvider } from '../context/MeldungenContext';
import type { BestandsAnzeige, Job } from '../types';

const bestandListe = vi.fn();
const jobsListe = vi.fn();
const zugang = vi.fn();
const anzeigeLesen = vi.fn();

vi.mock('../services/api', () => ({
  api: {
    bestand: {
      liste: (...a: unknown[]) => bestandListe(...a),
      anzeige: (...a: unknown[]) => anzeigeLesen(...a),
      bildUrl: () => '',
      vergleich: vi.fn().mockResolvedValue({ stand_von: null, quelle: null, unterschiede: [] }),
    },
    jobs: { liste: (...a: unknown[]) => jobsListe(...a) },
    profile: { zugang: (...a: unknown[]) => zugang(...a) },
  },
  ApiFehler: class extends Error {},
}));

vi.mock('../context/useProfil', () => ({
  useProfil: () => ({
    aktiv: { slug: 'test', anzeigename: 'Privatkonto' },
    profile: [], laedt: false, fehler: null, neuLaden: vi.fn(),
  }),
}));

function anzeige(titel: string, herkunft: 'eigene' | 'fremde'): BestandsAnzeige {
  return {
    datei: `${herkunft}/${titel}.yaml`, ordner: titel, titel, id: 1, art: 'OFFER',
    aktiv: true, kategorie: null, preis: 10, preistyp: 'FIXED', versandart: 'PICKUP',
    versandkosten: null, versandpakete: [], direkt_kaufen: false, bilder: 1,
    vorschaubild: null, erstellt_am: null, aktualisiert_am: null,
    neueinstellung_am: null, faellig: false, lokal_geaendert: true,
    hinweise: ['x'], unlesbar: null, herkunft, geloescht: false,
  };
}

function job(id: number, zustand: string): Job {
  return {
    id, profil_slug: 'test', befehl: 'publish', argumente: [],
    zustand: zustand as Job['zustand'], eingereicht_am: '2026-09-04T09:00:00Z',
    gestartet_am: null, beendet_am: null, rueckgabecode: null, aufmerksamkeit: [],
    eingriff: null, meldung: null, wartet_bis: null, wartegrund: null,
    anzeigen_glob: null, phase: null, phase_text: null, phase_seit: null,
  };
}

beforeEach(() => {
  vi.clearAllMocks();
  zugang.mockResolvedValue({ benutzername: 'a@b.c', passwort_hinterlegt: true, geaendert_am: '' });
  jobsListe.mockResolvedValue([]);
  bestandListe.mockResolvedValue([]);
});

describe('Kachelzahlen zählen nur eigene Anzeigen', () => {

  it('lässt fremde Anzeigen aus allen vier Zahlen heraus', async () => {
    // Zwei eigene, eine fremde. Alle drei sind „lokal geändert" und tragen
    // einen Hinweis - die fremde darf trotzdem nirgends mitzählen.
    bestandListe.mockResolvedValue([
      anzeige('Eigen1', 'eigene'), anzeige('Eigen2', 'eigene'), anzeige('Fremd', 'fremde'),
    ]);
    render(<UebersichtSeite aufZiel={vi.fn()} />);

    await waitFor(() => expect(screen.getByText('Anzeigen')).toBeTruthy());
    const kacheln = document.querySelectorAll('.kachel');
    const zahlen = [...kacheln].map(k => k.querySelector('.kachel-zahl')?.textContent);
    // Anzeigen, Fällig, Lokal geändert, Mit Hinweis
    expect(zahlen).toEqual(['2', '0', '2', '2']);
  });

  it('die Kachel führt auf dieselbe Liste, die sie zählt', async () => {
    bestandListe.mockResolvedValue([anzeige('Eigen1', 'eigene'), anzeige('Fremd', 'fremde')]);
    const aufZiel = vi.fn();
    render(<UebersichtSeite aufZiel={aufZiel} />);

    await waitFor(() => expect(screen.getByText('Anzeigen')).toBeTruthy());
    const zahl = document.querySelector('.kachel .kachel-zahl')?.textContent;
    expect(zahl).toBe('1');
  });
});

describe('Lauf-Status hängt nicht allein an der Farbe', () => {

  it('beschriftet gescheiterte Läufe zusätzlich mit Text', async () => {
    jobsListe.mockResolvedValue([job(1, 'gescheitert')]);
    render(<UebersichtSeite aufZiel={vi.fn()} />);
    await waitFor(() => expect(screen.getByText('gescheitert')).toBeTruthy());
  });

  it('beschriftet Läufe, die den Menschen brauchen', async () => {
    jobsListe.mockResolvedValue([job(2, 'braucht_eingabe')]);
    render(<UebersichtSeite aufZiel={vi.fn()} />);
    await waitFor(() => expect(screen.getByText('braucht dich')).toBeTruthy());
  });

  it('lässt harmlose Zustände ruhig – sonst ist es wieder eine Wand', async () => {
    jobsListe.mockResolvedValue([job(3, 'fertig'), job(4, 'laeuft')]);
    render(<UebersichtSeite aufZiel={vi.fn()} />);
    await waitFor(() => expect(screen.getAllByText('Veröffentlichen').length).toBe(2));
    // Der Zustand steht am Punkt für Screenreader, aber nicht als sichtbares
    // Etikett neben dem Titel.
    expect(screen.queryByText('fertig')).toBeNull();
    expect(screen.queryByText('läuft')).toBeNull();
  });

  it('hält den Zustand für Screenreader am Punkt fest', async () => {
    jobsListe.mockResolvedValue([job(5, 'fertig')]);
    render(<UebersichtSeite aufZiel={vi.fn()} />);
    await waitFor(() => expect(screen.getByRole('img', { name: 'fertig' })).toBeTruthy());
  });
});

describe('Zu langer Titel führt nicht mehr in den 422', () => {

  it('sperrt Hochladen und färbt den Zähler, wenn der Titel zu lang ist', async () => {
    // Der Fall kommt von der Plattform, nicht aus der Tastatur: `maxLength`
    // bremst das Tippen, nicht einen Wert, der schon in der Datei stand.
    const lang = 'x'.repeat(77);
    anzeigeLesen.mockResolvedValue({
      kopf: { ...anzeige('Lang', 'eigene'), titel: lang, id: 4711 },
      felder: { title: lang, description: 'Text', images: [] },
      aenderbar: ['title', 'description'],
    });
    render(
      <MeldungenProvider>
        <AnzeigenEditor profil="test" datei="a.yaml" aufZurueck={vi.fn()} />
      </MeldungenProvider>,
    );

    await waitFor(() => expect(screen.getByText(/77 von 65 Zeichen/)).toBeTruthy());
    expect(screen.getByText(/12 zu viel/)).toBeTruthy();

    const knopf = screen.getByRole('button', { name: /Aktualisieren/ });
    expect((knopf as HTMLButtonElement).disabled).toBe(true);

    const feld = document.querySelector('input[type=text]');
    expect(feld?.getAttribute('aria-invalid')).toBe('true');
  });

  it('lässt einen gültigen Titel durch', async () => {
    anzeigeLesen.mockResolvedValue({
      kopf: { ...anzeige('Gut', 'eigene'), titel: 'Ein guter Anzeigentitel', id: 4711 },
      felder: { title: 'Ein guter Anzeigentitel', description: 'Text', images: [] },
      aenderbar: ['title', 'description'],
    });
    render(
      <MeldungenProvider>
        <AnzeigenEditor profil="test" datei="a.yaml" aufZurueck={vi.fn()} />
      </MeldungenProvider>,
    );

    await waitFor(() => expect(screen.getByText(/23 von 65 Zeichen/)).toBeTruthy());
    const knopf = screen.getByRole('button', { name: /Aktualisieren/ });
    expect((knopf as HTMLButtonElement).disabled).toBe(false);
  });
});
