// SPDX-FileCopyrightText: © Anzeigen-Studio contributors
// SPDX-License-Identifier: AGPL-3.0-or-later
//
// Einstellungen: Abgleich/Feldtexte (AP-2.46) sowie Reiterzeile und Suche
// (AP-2.47).
//
// Die Seitenintros über den Reitern sind weg; die Suche sitzt rechts neben
// der Reiterleiste wie in Meine Anzeigen und filtert Gruppen/Felder.

import { beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { EinstellungenSeite } from './EinstellungenSeite';
import type { EinstellungsGruppe } from '../types';

const lesen = vi.fn();
const zugang = vi.fn();
const abgleichStand = vi.fn();
const abgleichSchalten = vi.fn();
const einstellungenSpeichern = vi.fn();

vi.mock('../services/api', () => ({
  ApiFehler: class extends Error {},
  api: {
    einstellungen: {
      lesen: (...a: unknown[]) => lesen(...a),
      speichern: (...a: unknown[]) => einstellungenSpeichern(...a),
      browserprofilZuruecksetzen: vi.fn(),
    },
    profile: {
      zugang: (...a: unknown[]) => zugang(...a),
      liste: vi.fn().mockResolvedValue([]),
      anlegen: vi.fn(),
      loeschen: vi.fn(),
      zugangSetzen: vi.fn(),
    },
    abgleich: {
      stand: (...a: unknown[]) => abgleichStand(...a),
      schalten: (...a: unknown[]) => abgleichSchalten(...a),
    },
    archiv: {
      exportUrl: () => '/api/archiv/export',
      vorschau: vi.fn(),
      einspielen: vi.fn(),
    },
    auth: {
      passwortAendern: vi.fn(),
    },
    ki: {
      status: vi.fn().mockResolvedValue({ hinterlegt: false, bildkante: 768 }),
      schluesselSetzen: vi.fn(),
      schluesselEntfernen: vi.fn(),
    },
  },
}));

// Stabil halten: EinstellungenSeite hängt `laden` an `aktiv`. Ein frisches
// Objekt je Render würde die Lade-Schleife nie verlassen.
const profilKontext = {
  aktiv: { slug: 'test', anzeigename: 'Privatkonto' },
  profile: [{ slug: 'test', anzeigename: 'Privatkonto' }],
  laedt: false,
  fehler: null as string | null,
  neuLaden: vi.fn(),
};

vi.mock('../context/useProfil', () => ({
  useProfil: () => profilKontext,
}));

vi.mock('../hooks/useThema', () => ({
  useThema: () => ({ wahl: 'system' as const, setzen: vi.fn() }),
}));

function gruppe(
  id: string,
  titel: string,
  felder: { pfad: string; titel: string; beschreibung?: string }[],
): EinstellungsGruppe {
  return {
    id,
    wurzel: id,
    titel,
    beschreibung: `${titel}-Beschreibung`,
    eingeklappt: false,
    felder: felder.map(f => ({
      pfad: f.pfad,
      titel: f.titel,
      beschreibung: f.beschreibung ?? '',
      typ: 'boolean' as const,
      vorgabe: false,
      null_erlaubt: false,
    })),
  };
}

async function warteAufBot() {
  await waitFor(() => {
    expect(screen.queryByText('Wird geladen …')).toBeNull();
    expect(screen.getByLabelText('Einstellungsbereiche')).toBeTruthy();
  });
}

beforeEach(() => {
  lesen.mockReset();
  zugang.mockReset();
  abgleichStand.mockReset();
  abgleichSchalten.mockReset();
  einstellungenSpeichern.mockReset();
  zugang.mockResolvedValue({
    benutzername: 'a@b.c',
    passwort_hinterlegt: true,
    geaendert_am: '',
  });
  abgleichStand.mockResolvedValue({
    profil: 'test',
    eingeschaltet: false,
    letzter_lauf_am: null,
    letztes_ergebnis: null,
    laeuft: false,
    heute_gelaufen: false,
    zugang_vorhanden: true,
  });
  abgleichSchalten.mockResolvedValue({
    profil: 'test',
    eingeschaltet: true,
    letzter_lauf_am: null,
    letztes_ergebnis: null,
    laeuft: false,
    heute_gelaufen: false,
    zugang_vorhanden: true,
  });
  einstellungenSpeichern.mockResolvedValue({ profil: 'test', werte: {} });
  lesen.mockResolvedValue({
    profil: 'test',
    werte: {},
    gruppen: [
      gruppe('publishing', 'Veröffentlichung', [
        { pfad: 'publishing.foo', titel: 'Zeitgrenze', beschreibung: 'Maximale Wartezeit' },
      ]),
      gruppe('diagnostics', 'Diagnose', [
        { pfad: 'diagnostics.enabled', titel: 'Diagnose an', beschreibung: 'Artefakte speichern' },
      ]),
      gruppe('ad_defaults', 'Standardwerte für Anzeigen', [
        { pfad: 'ad_defaults.active', titel: 'Aktiv', beschreibung: 'Neue Anzeigen veröffentlichen' },
        { pfad: 'ad_defaults.repost_wait', titel: 'Standard-Abstand', beschreibung: 'Tage bis Neueinstellung' },
      ]),
    ],
  });
});

describe('EinstellungenSeite AP-2.47', () => {
  it('zeigt keine Seitenbeschreibung über den Reitern', async () => {
    render(<EinstellungenSeite abschnitt="bot" aufZiel={vi.fn()} />);
    await warteAufBot();
    expect(document.querySelector('.seite-beschrieb')).toBeNull();
    expect(screen.queryByText(/Gilt für/)).toBeNull();
    expect(screen.queryByText(/Kleinanzeigen-Konten und KI-Zugang/)).toBeNull();
  });

  it('legt die Suche rechts neben die nicht gestreckte Reiterleiste', async () => {
    render(<EinstellungenSeite abschnitt="bot" aufZiel={vi.fn()} />);
    await warteAufBot();
    const nav = screen.getByLabelText('Einstellungsbereiche');
    expect(nav.className).toContain('sm:flex-none');
    expect(nav.className).not.toContain('mb-8');
    // Unter sm ist das Feld per Tailwind `hidden`; jsdom kennt kein sm-Breakpoint.
    const suche = document.querySelector('input[placeholder="Einstellung oder Beschreibung suchen"]') as HTMLInputElement | null;
    expect(suche).toBeTruthy();
    expect(suche?.closest('label')?.className).toContain('sm:ml-auto');
    expect(screen.getByLabelText('Suche ein- oder ausblenden')).toBeTruthy();
  });

  it('filtert Gruppen und Felder über die Reiter-Suche', async () => {
    render(<EinstellungenSeite abschnitt="bot" aufZiel={vi.fn()} />);
    await warteAufBot();
    expect(screen.getByText('Zeitgrenze')).toBeTruthy();
    expect(screen.getByText('Diagnose an')).toBeTruthy();

    fireEvent.change(
      document.querySelector('input[placeholder="Einstellung oder Beschreibung suchen"]')!,
      { target: { value: 'Zeitgrenze' } },
    );

    await waitFor(() => {
      expect(screen.getByText('Zeitgrenze')).toBeTruthy();
      expect(screen.queryByText('Diagnose an')).toBeNull();
    });
  });

  it('zeigt Feldbeschreibungen als InfoTip statt als Untertitel', async () => {
    render(<EinstellungenSeite abschnitt="anzeigen" aufZiel={vi.fn()} />);
    await waitFor(() => expect(screen.getByText('Aktiv')).toBeTruthy());

    const feld = screen.getByText('Aktiv').closest('label');
    expect(feld?.querySelector('.text-xs.text-leise')).toBeNull();
    expect(screen.getByRole('button', { name: 'Erklärung zu Aktiv' })).toBeTruthy();
  });

  it('merkt den Abgleich vor und speichert ihn erst über die Speichern-Leiste', async () => {
    render(<EinstellungenSeite abschnitt="bot" aufZiel={vi.fn()} />);
    await waitFor(() => expect(screen.getByLabelText('Täglich abgleichen')).toBeTruthy());

    const speichern = screen.getByRole('button', { name: 'Speichern' });
    expect((speichern as HTMLButtonElement).disabled).toBe(true);

    fireEvent.click(screen.getByLabelText('Täglich abgleichen'));
    expect(abgleichSchalten).not.toHaveBeenCalled();
    expect((speichern as HTMLButtonElement).disabled).toBe(false);
    expect(screen.getByText('1 Änderung ungespeichert')).toBeTruthy();

    fireEvent.click(speichern);
    await waitFor(() => expect(abgleichSchalten).toHaveBeenCalledWith('test', true));
    expect(einstellungenSpeichern).not.toHaveBeenCalled();
  });

  it('setzt den Abgleich zusammen mit den übrigen Änderungen zurück', async () => {
    render(<EinstellungenSeite abschnitt="bot" aufZiel={vi.fn()} />);
    await waitFor(() => expect(screen.getByLabelText('Täglich abgleichen')).toBeTruthy());

    fireEvent.click(screen.getByLabelText('Täglich abgleichen'));
    fireEvent.click(screen.getByRole('button', { name: 'Zurücksetzen' }));

    expect((screen.getByLabelText('Täglich abgleichen') as HTMLInputElement).checked).toBe(false);
    expect((screen.getByRole('button', { name: 'Speichern' }) as HTMLButtonElement).disabled).toBe(true);
    expect(abgleichSchalten).not.toHaveBeenCalled();
  });

  it('blendet die Suche auf dem Profil-Reiter aus', async () => {
    render(<EinstellungenSeite abschnitt="profile" aufZiel={vi.fn()} />);
    await waitFor(() => expect(screen.getByLabelText('Einstellungsbereiche')).toBeTruthy());
    expect(document.querySelector('input[placeholder="Einstellung oder Beschreibung suchen"]')).toBeNull();
    expect(document.querySelector('.seite-beschrieb')).toBeNull();
  });
});
