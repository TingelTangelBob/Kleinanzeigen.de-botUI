// SPDX-FileCopyrightText: © Anzeigen-Studio contributors
// SPDX-License-Identifier: AGPL-3.0-or-later
//
// Test der kurzen Rückfrage vor einem Bot-Lauf.

import { beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/react';
import { useLaufStartHinweis, type LaufStartDetails } from './LaufStartDialog';

const DETAILS: LaufStartDetails = {
  titel: 'Anzeigen vom Konto holen?',
  text: 'Der Kontostand wird lokal eingelesen.',
};

function Testschale({ details = DETAILS }: { details?: LaufStartDetails }) {
  const laufHinweis = useLaufStartHinweis();
  const starten = vi.fn();
  return (
    <>
      <button type="button" onClick={() => laufHinweis.anfragen(details, starten)}>
        Auslösen
      </button>
      {laufHinweis.dialog}
    </>
  );
}

beforeEach(() => {
  window.localStorage.clear();
});

describe('LaufStartDialog', () => {
  it('fragt vor dem Lauf kurz nach und startet erst nach Bestätigung', () => {
    render(<Testschale />);

    fireEvent.click(screen.getByRole('button', { name: 'Auslösen' }));
    expect(screen.getByRole('dialog')).toBeDefined();
    expect(screen.getByText(DETAILS.text)).toBeDefined();

    fireEvent.click(screen.getByRole('button', { name: 'Lauf starten' }));
    expect(screen.queryByRole('dialog')).toBeNull();
  });

  it('überspringt den Hinweis nach bewusster Auswahl beim nächsten Lese-Lauf', () => {
    render(<Testschale />);

    fireEvent.click(screen.getByRole('button', { name: 'Auslösen' }));
    fireEvent.click(screen.getByLabelText('Diesen Hinweis nicht mehr zeigen'));
    fireEvent.click(screen.getByRole('button', { name: 'Lauf starten' }));

    fireEvent.click(screen.getByRole('button', { name: 'Auslösen' }));
    expect(screen.queryByRole('dialog')).toBeNull();
  });

  it('lässt Plattformänderungen trotz Präferenz nicht ohne Rückfrage starten', () => {
    const details: LaufStartDetails = { ...DETAILS, ueberspringenErlaubt: false };
    render(<Testschale details={details} />);

    fireEvent.click(screen.getByRole('button', { name: 'Auslösen' }));
    expect(screen.queryByLabelText('Diesen Hinweis nicht mehr zeigen')).toBeNull();
    fireEvent.click(screen.getByRole('button', { name: 'Lauf starten' }));

    fireEvent.click(screen.getByRole('button', { name: 'Auslösen' }));
    expect(screen.getByRole('dialog')).toBeDefined();
  });
});
