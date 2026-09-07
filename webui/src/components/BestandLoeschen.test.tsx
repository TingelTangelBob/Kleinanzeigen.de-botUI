// SPDX-FileCopyrightText: © Anzeigen-Studio contributors
// SPDX-License-Identifier: AGPL-3.0-or-later
//
// Mehrfachauswahl und lokales Löschen (AP-2.20).
//
// Zwei Zusagen werden hier geprüft, und die zweite ist die, bei der ein Fehler
// teuer wäre: dass genau die ausgewählten Dateien gehen, und dass der Dialog
// sagt, dass auf kleinanzeigen.de nichts passiert. Dazu die Gegenprobe, dass
// kein Bot-Lauf eingereiht wird.

import { describe, expect, it, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, within } from '@testing-library/react';
import { fireEvent } from '@testing-library/dom';
import type { ReactNode } from 'react';
import { BestandSeite } from './BestandSeite';
import { MeldungenProvider } from '../context/MeldungenContext';
import type { BestandsAnzeige } from '../types';

// BestandSeite meldet eingereihte Läufe an die Glocke (AP-2.30) und braucht
// dafür den Provider.
function huelle({ children }: { children: ReactNode }) {
  return <MeldungenProvider>{children}</MeldungenProvider>;
}

const liste = vi.fn();
const loeschen = vi.fn();
const hochladen = vi.fn();
const herkunftSetzen = vi.fn();
const jobsStarten = vi.fn();

vi.mock('../services/api', () => ({
  api: {
    bestand: {
      liste: (...a: unknown[]) => liste(...a),
      loeschen: (...a: unknown[]) => loeschen(...a),
      hochladen: (...a: unknown[]) => hochladen(...a),
      herkunftSetzen: (...a: unknown[]) => herkunftSetzen(...a),
      anzeige: vi.fn(),
      vorlagen: vi.fn().mockResolvedValue([]),
      bildUrl: () => '',
      lokaleAenderungen: vi.fn().mockResolvedValue([]),
    },
    jobs: { starten: (...a: unknown[]) => jobsStarten(...a) },
  },
  ApiFehler: class extends Error {},
}));

vi.mock('../context/useProfil', () => ({
  useProfil: () => ({ aktiv: { slug: 'test' }, profile: [], laedt: false }),
}));

function anzeige(titel: string, datei: string): BestandsAnzeige {
  return {
    datei, ordner: titel, titel, id: 1, art: 'OFFER', aktiv: true,
    kategorie: null, preis: 10, preistyp: 'FIXED', versandart: 'PICKUP',
    versandkosten: null, versandpakete: [], direkt_kaufen: false,
    bilder: 2, vorschaubild: null, erstellt_am: null, aktualisiert_am: null,
    neueinstellung_am: null, faellig: false, lokal_geaendert: false,
    hinweise: [], unlesbar: null, herkunft: 'eigene', geloescht: false,
  };
}

const A = anzeige('Kinderwagen', 'downloaded-ads/a/ad_1.yaml');
const B = anzeige('Bohrmaschine', 'downloaded-ads/b/ad_2.yaml');
const C = anzeige('Teakregal', 'downloaded-ads/c/ad_3.yaml');

beforeEach(() => {
  vi.clearAllMocks();
  liste.mockResolvedValue([A, B, C]);
  loeschen.mockResolvedValue({
    geloescht: [
      { datei: A.datei, titel: A.titel, bilder: 2, ordner_entfernt: true },
      { datei: B.datei, titel: B.titel, bilder: 2, ordner_entfernt: true },
    ],
  });
});

/** Das Kästchen einer Zeile über sein aria-label. */
function kaestchen(titel: string): HTMLElement {
  return screen.getByLabelText(`„${titel}" auswählen`);
}

/**
 * Der Knopf im Dialog, nicht der in der Sammelleiste: Bei einer einzelnen
 * Anzeige heißt er „Löschen", bei mehreren „Lokal löschen".
 */
function bestaetigen() {
  const dialog = screen.getByRole('dialog');
  fireEvent.click(within(dialog).getByRole('button', { name: /löschen/i }));
}

async function geladen() {
  await waitFor(() => expect(screen.getByText('Kinderwagen')).toBeTruthy());
}

describe('Mehrfachauswahl', () => {

  it('zeigt die Sammelleiste erst mit einer Auswahl', async () => {
    render(<BestandSeite herkunft="eigene" aufZiel={vi.fn()} />, { wrapper: huelle });
    await geladen();

    expect(screen.queryByRole('group', { name: 'Sammelaktionen' })).toBeNull();

    fireEvent.click(kaestchen('Kinderwagen'));

    expect(screen.getByRole('group', { name: 'Sammelaktionen' })).toBeTruthy();
    expect(screen.getByText('1 ausgewählt')).toBeTruthy();
  });

  it('wählt mit dem Kopfkästchen alle sichtbaren und hebt wieder auf', async () => {
    render(<BestandSeite herkunft="eigene" aufZiel={vi.fn()} />, { wrapper: huelle });
    await geladen();

    fireEvent.click(screen.getByLabelText('Alle sichtbaren auswählen'));
    expect(screen.getByText('3 ausgewählt')).toBeTruthy();

    fireEvent.click(screen.getByLabelText('Auswahl aufheben'));
    expect(screen.queryByRole('group', { name: 'Sammelaktionen' })).toBeNull();
  });

  it('wählt nur, was der Filter übrig lässt', async () => {
    render(<BestandSeite herkunft="eigene" aufZiel={vi.fn()} />, { wrapper: huelle });
    await geladen();

    fireEvent.change(screen.getByPlaceholderText(/Titel, Kategorie/), {
      target: { value: 'Bohr' },
    });
    fireEvent.click(screen.getByLabelText('Alle sichtbaren auswählen'));

    expect(screen.getByText('1 ausgewählt')).toBeTruthy();
  });
});

describe('Löschen', () => {

  it('sagt im Dialog, dass die Plattform unberührt bleibt', async () => {
    render(<BestandSeite herkunft="eigene" aufZiel={vi.fn()} />, { wrapper: huelle });
    await geladen();

    fireEvent.click(kaestchen('Kinderwagen'));
    fireEvent.click(screen.getByRole('button', { name: /Lokal löschen/ }));

    const dialog = screen.getByRole('dialog');
    expect(dialog.textContent).toContain('Nur auf diesem Rechner, nicht auf kleinanzeigen.de');
    // Der Name muss dastehen, sonst weiß niemand, was gleich weg ist.
    expect(dialog.textContent).toContain('Kinderwagen');
  });

  it('schickt genau die ausgewählten Dateien', async () => {
    render(<BestandSeite herkunft="eigene" aufZiel={vi.fn()} />, { wrapper: huelle });
    await geladen();

    fireEvent.click(kaestchen('Kinderwagen'));
    fireEvent.click(kaestchen('Bohrmaschine'));
    fireEvent.click(screen.getByRole('button', { name: /Lokal löschen/ }));
    bestaetigen();

    await waitFor(() => expect(loeschen).toHaveBeenCalledTimes(1));
    expect(loeschen).toHaveBeenCalledWith('test', [A.datei, B.datei]);
    // Teakregal war nicht gewählt und darf nicht mitgehen.
    expect(loeschen.mock.calls[0][1]).not.toContain(C.datei);
  });

  it('reiht keinen Bot-Lauf ein', async () => {
    render(<BestandSeite herkunft="eigene" aufZiel={vi.fn()} />, { wrapper: huelle });
    await geladen();

    fireEvent.click(kaestchen('Kinderwagen'));
    fireEvent.click(screen.getByRole('button', { name: /Lokal löschen/ }));
    bestaetigen();

    await waitFor(() => expect(loeschen).toHaveBeenCalled());
    expect(jobsStarten).not.toHaveBeenCalled();
    expect(hochladen).not.toHaveBeenCalled();
  });

  it('liest die Liste neu und meldet das Ergebnis', async () => {
    render(<BestandSeite herkunft="eigene" aufZiel={vi.fn()} />, { wrapper: huelle });
    await geladen();
    const vorher = liste.mock.calls.length;

    fireEvent.click(kaestchen('Kinderwagen'));
    fireEvent.click(kaestchen('Bohrmaschine'));
    fireEvent.click(screen.getByRole('button', { name: /Lokal löschen/ }));
    bestaetigen();

    await waitFor(() => expect(liste.mock.calls.length).toBeGreaterThan(vorher));
    await waitFor(() =>
      expect(screen.getByText(/2 Anzeigen und 4 Bilder von diesem Rechner gelöscht/)).toBeTruthy());
  });

  it('lässt die Auswahl stehen, wenn das Löschen scheitert', async () => {
    loeschen.mockRejectedValueOnce(new Error('kaputt'));
    render(<BestandSeite herkunft="eigene" aufZiel={vi.fn()} />, { wrapper: huelle });
    await geladen();

    fireEvent.click(kaestchen('Kinderwagen'));
    fireEvent.click(screen.getByRole('button', { name: /Lokal löschen/ }));
    bestaetigen();

    await waitFor(() => expect(loeschen).toHaveBeenCalled());
    await waitFor(() => expect(screen.getByText('1 ausgewählt')).toBeTruthy());
  });
});

describe('Weitere Sammelaktionen', () => {

  it('verschiebt die Auswahl nacheinander', async () => {
    herkunftSetzen.mockResolvedValue(A);
    render(<BestandSeite herkunft="eigene" aufZiel={vi.fn()} />, { wrapper: huelle });
    await geladen();

    fireEvent.click(kaestchen('Kinderwagen'));
    fireEvent.click(kaestchen('Bohrmaschine'));
    fireEvent.click(screen.getByRole('button', { name: /Zu „Von anderen"/ }));

    await waitFor(() => expect(herkunftSetzen).toHaveBeenCalledTimes(2));
    expect(herkunftSetzen).toHaveBeenCalledWith('test', A.datei, 'fremde');
    expect(herkunftSetzen).toHaveBeenCalledWith('test', B.datei, 'fremde');
  });

  it('zeigt die Sammelaktionen unter md als eine fixe Leiste unten', async () => {
    // matchMedia auf „schmal" stellen -> useIstMobil == true.
    window.matchMedia = ((q: string) => ({
      matches: false, media: q,
      addEventListener: () => {}, removeEventListener: () => {},
      addListener: () => {}, removeListener: () => {}, onchange: null,
      dispatchEvent: () => false,
    })) as unknown as typeof window.matchMedia;
    try {
      render(<BestandSeite herkunft="eigene" aufZiel={vi.fn()} />, { wrapper: huelle });
      await geladen();
      fireEvent.click(kaestchen('Kinderwagen'));

      // Genau eine Sammelaktionsgruppe, und sie sitzt in der fixen Leiste.
      const gruppe = screen.getByRole('group', { name: 'Sammelaktionen' });
      expect(gruppe.closest('.leiste-fix.fixed')).not.toBeNull();
      expect(screen.getByRole('button', { name: /Lokal löschen/ })).toBeTruthy();
    } finally {
      // @ts-expect-error – Aufräumen der Attrappe.
      delete window.matchMedia;
    }
  });

  it('reiht je Anzeige einen Hochladen-Lauf ein', async () => {
    hochladen.mockResolvedValue({ job_id: 7, anzeige: A });
    render(<BestandSeite herkunft="eigene" aufZiel={vi.fn()} />, { wrapper: huelle });
    await geladen();

    fireEvent.click(kaestchen('Kinderwagen'));
    fireEvent.click(screen.getByRole('button', { name: /Hochladen/ }));

    await waitFor(() => expect(hochladen).toHaveBeenCalledWith('test', A.datei));
  });
});
