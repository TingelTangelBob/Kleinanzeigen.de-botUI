// SPDX-FileCopyrightText: © Anzeigen-Studio contributors
// SPDX-License-Identifier: AGPL-3.0-or-later
//
// Test des Kategorie-Rückfalls (AP-2.7, K-2.7-002).
//
// Der Fall, um den es geht: Die Kategorieliste ist nicht abrufbar. Vorher war
// das einzige Eingabefeld dann deaktiviert - eine Anzeige ohne Kategorie ließ
// sich nicht mehr versorgen. Geprüft wird deshalb beides: dass ein Textfeld
// erscheint und dass der vorhandene Wert dabei erhalten bleibt.

import { describe, expect, it, vi, beforeEach } from 'vitest';
import { useState } from 'react';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { KategorieWahl } from './KategorieWahl';

const kategorien = vi.fn();

vi.mock('../services/api', () => ({
  api: { katalog: { kategorien: () => kategorien() } },
}));

beforeEach(() => {
  kategorien.mockReset();
});

describe('KategorieWahl ohne Liste', () => {
  it('zeigt ein bearbeitbares Textfeld, wenn der Abruf scheitert', async () => {
    kategorien.mockRejectedValue(new Error('Netz weg'));
    render(<KategorieWahl wert="161/278" aufAenderung={() => {}} />);

    const feld = await screen.findByDisplayValue('161/278');
    expect(feld).toBeDefined();
    expect((feld as HTMLInputElement).disabled).toBe(false);
  });

  it('zeigt ein Textfeld, wenn die Liste leer zurückkommt', async () => {
    // `kategorien()` gibt auch dann [] zurück, wenn categories.yaml
    // unlesbar war - für die Bedienung derselbe Fall.
    kategorien.mockResolvedValue([]);
    render(<KategorieWahl wert="161/278" aufAenderung={() => {}} />);

    const feld = await screen.findByDisplayValue('161/278');
    expect((feld as HTMLInputElement).disabled).toBe(false);
  });

  it('verliert den vorhandenen Wert nicht', async () => {
    kategorien.mockRejectedValue(new Error('Netz weg'));
    render(<KategorieWahl wert="161/278/laptop" aufAenderung={() => {}} />);

    // Gerade ein Wert, den die Liste nicht kennt, darf nicht stillschweigend
    // verschwinden - beobachtet an heruntergeladenen Anzeigen.
    expect(await screen.findByDisplayValue('161/278/laptop')).toBeDefined();
  });

  it('nimmt eine Eingabe an und gibt sie nach oben weiter', async () => {
    kategorien.mockRejectedValue(new Error('Netz weg'));

    // Mit eigenem Zustand, sonst setzt das kontrollierte Feld nach jedem
    // Tastendruck wieder auf den unveränderten Wert von außen zurück.
    function Huelle() {
      const [wert, setWert] = useState('');
      return <KategorieWahl wert={wert} aufAenderung={setWert} />;
    }
    render(<Huelle />);

    const feld = await screen.findByRole('textbox');
    await userEvent.type(feld, '161/278');

    expect((feld as HTMLInputElement).value).toBe('161/278');
  });
});

describe('KategorieWahl mit Liste', () => {
  it('zeigt den lesbaren Pfad statt des Nummernpfads', async () => {
    kategorien.mockResolvedValue([
      { name: 'Elektronik > Notebooks', wert: '161/278' },
    ]);
    render(<KategorieWahl wert="161/278" aufAenderung={() => {}} />);

    expect(await screen.findByText('Elektronik > Notebooks')).toBeDefined();
    // Kein Textfeld: Mit Liste wird ausgewählt, nicht getippt.
    expect(screen.queryByDisplayValue('161/278')).toBeNull();
  });
});
