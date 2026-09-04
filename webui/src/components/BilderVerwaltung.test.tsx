// SPDX-FileCopyrightText: © Anzeigen-Studio contributors
// SPDX-License-Identifier: AGPL-3.0-or-later
//
// Automatische Zweispaltenansicht und Bildvorschau der Bilderverwaltung.

import { fireEvent } from '@testing-library/dom';
import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { BilderVerwaltung } from './BilderVerwaltung';

vi.mock('../services/api', () => ({
  ApiFehler: class ApiFehler extends Error {},
  api: {
    bestand: {
      bildUrl: (profil: string, datei: string, name: string) =>
        `/api/bestand/bild?profil=${profil}&datei=${datei}&name=${name}`,
    },
  },
}));

function renderBilder(bilder = ['eins.jpg', 'zwei.jpg']) {
  return render(
    <BilderVerwaltung
      profil="test"
      datei="ads/test.yaml"
      bilder={bilder}
      aufAenderung={vi.fn()}
    />,
  );
}

describe('BilderVerwaltung', () => {
  it('zeigt zwei Bilder untereinander und ab drei Bildern zweispaltig', () => {
    const view = renderBilder();
    const { container } = view;
    const liste = () => container.querySelector('.bild-spalte');

    expect(liste()?.className).not.toContain('bild-spalte-zweispaltig');
    expect(container.querySelectorAll('.bild-kachel-knopf')).toHaveLength(2);
    expect(screen.getByRole('button', { name: 'eins.jpg verschieben' })).toBeDefined();

    view.rerender(
      <BilderVerwaltung
        profil="test"
        datei="ads/test.yaml"
        bilder={['eins.jpg', 'zwei.jpg', 'drei.jpg']}
        aufAenderung={vi.fn()}
      />,
    );
    const dreierListe = container.querySelector('.bild-spalte');
    expect(dreierListe?.className).toContain('bild-spalte-zweispaltig');
    expect(screen.queryByRole('button', { name: 'Zweispaltige Bildansicht wählen' })).toBeNull();
    expect(screen.getByRole('button', { name: 'eins.jpg verschieben' })).toBeDefined();
    expect(container.querySelectorAll('.bild-kachel-knopf')).toHaveLength(3);
  });

  it('öffnet die Vorschau mit beschreibendem Dialog und schließt sie per Escape', () => {
    renderBilder(['eins.jpg']);
    const bildKnopf = screen.getByRole('button', { name: 'eins.jpg in Vorschau öffnen' });
    bildKnopf.focus();

    fireEvent.click(bildKnopf);

    const dialog = screen.getByRole('dialog', { name: 'Vorschau von eins.jpg' });
    expect(dialog.querySelector('img')?.getAttribute('src')).toContain('eins.jpg');
    expect(screen.getByRole('button', { name: 'Vorschau schließen' })).toBeDefined();
    expect(document.activeElement).toBe(screen.getByRole('button', { name: 'Vorschau schließen' }));

    fireEvent.keyDown(window, { key: 'Escape' });

    expect(screen.queryByRole('dialog', { name: 'Vorschau von eins.jpg' })).toBeNull();
    expect(document.activeElement).toBe(bildKnopf);
  });

  it('schließt die Vorschau durch Klick auf Overlay oder Schließen', () => {
    const { container } = renderBilder(['eins.jpg']);
    const bildKnopf = screen.getByRole('button', { name: 'eins.jpg in Vorschau öffnen' });

    fireEvent.click(bildKnopf);
    fireEvent.click(container.querySelector('.bild-vorschau-overlay')!);
    expect(screen.queryByRole('dialog')).toBeNull();

    fireEvent.click(bildKnopf);
    fireEvent.click(screen.getByRole('button', { name: 'Vorschau schließen' }));
    expect(screen.queryByRole('dialog')).toBeNull();
  });
});
