// SPDX-FileCopyrightText: © Anzeigen-Studio contributors
// SPDX-License-Identifier: AGPL-3.0-or-later
//
// Tests des Profilkontexts.
//
// Anlass ist ein Fehler, der am 2026-08-30 im Betrieb auffiel: Nach dem
// Anmelden meldete die Übersicht „Noch kein Profil angelegt", obwohl das
// Profil existierte. Der Provider umschließt die Anmeldeseite und lud die
// Liste EINMAL beim Einhängen - also vor der Anmeldung. `/api/profile`
// antwortete mit 401, die Liste blieb leer, und danach fragte niemand mehr
// nach. Erst ein vollständiges Neuladen der Seite half.
//
// Der zweite Test ist der wichtigere: Der 401 erschien als gültiger
// Leerzustand. Ein Fehler, der aussieht wie ein normaler Zustand, wird nicht
// gemeldet - deshalb blieb das tagelang unbemerkt.

import { describe, expect, it, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { ProfilProvider } from './ProfilContext';
import { useProfil } from './useProfil';

const liste = vi.fn();
let angemeldet = false;

vi.mock('../services/api', () => ({
  api: { profile: { liste: () => liste() } },
  ApiFehler: class ApiFehler extends Error {
    constructor(meldung: string, readonly status: number) { super(meldung); }
  },
}));

vi.mock('./useAuth', () => ({
  useAuth: () => ({ status: { eingerichtet: true, angemeldet, name: 'Steffen' } }),
}));

function Anzeige() {
  const { profile, aktiv, laedt, fehler } = useProfil();
  if (laedt) return <p>laedt</p>;
  if (fehler) return <p>Störung: {fehler}</p>;
  if (profile.length === 0) return <p>kein Profil</p>;
  return <p>aktiv: {aktiv?.slug}</p>;
}

const PROFIL = {
  slug: 'steffen', anzeigename: 'Steffen',
  angelegt_am: '2026-08-23T12:46:53+00:00', geaendert_am: '2026-08-23T12:46:53+00:00',
};

beforeEach(() => {
  liste.mockReset();
  angemeldet = false;
  window.localStorage.clear();
});

describe('Profilkontext', () => {
  it('holt die Profile nicht, solange niemand angemeldet ist', async () => {
    render(<ProfilProvider><Anzeige /></ProfilProvider>);

    await waitFor(() => { expect(screen.getByText('kein Profil')).toBeDefined(); });
    // Der Abruf hätte nur einen 401 geliefert - und genau der wurde vorher
    // als Leerzustand eingefroren.
    expect(liste).not.toHaveBeenCalled();
  });

  it('holt sie, sobald jemand angemeldet ist', async () => {
    angemeldet = true;
    liste.mockResolvedValue([PROFIL]);

    render(<ProfilProvider><Anzeige /></ProfilProvider>);

    expect(await screen.findByText('aktiv: steffen')).toBeDefined();
  });

  it('meldet eine Störung als Störung, nicht als leeren Bestand', async () => {
    angemeldet = true;
    liste.mockRejectedValue(new Error('Das Backend ist nicht erreichbar.'));

    render(<ProfilProvider><Anzeige /></ProfilProvider>);

    // Der Kern des Fehlers: Vorher stand hier „kein Profil".
    expect(await screen.findByText(/Störung:/)).toBeDefined();
    expect(screen.queryByText('kein Profil')).toBeNull();
  });

  it('leert die Liste beim Abmelden', async () => {
    angemeldet = true;
    liste.mockResolvedValue([PROFIL]);
    const { rerender } = render(<ProfilProvider><Anzeige /></ProfilProvider>);
    expect(await screen.findByText('aktiv: steffen')).toBeDefined();

    // Sonst stünden nach dem Abmelden die Profile des vorigen Benutzers noch da.
    angemeldet = false;
    rerender(<ProfilProvider><Anzeige /></ProfilProvider>);

    await waitFor(() => { expect(screen.getByText('kein Profil')).toBeDefined(); });
  });
});
