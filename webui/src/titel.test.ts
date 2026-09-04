// SPDX-FileCopyrightText: © Anzeigen-Studio contributors
// SPDX-License-Identifier: AGPL-3.0-or-later
//
// Display-only cleanup of the deleted-listing title decoration.

import { describe, expect, it } from 'vitest';
import { titelFuerAnzeige } from './titel';

describe('titelFuerAnzeige', () => {
  it.each(['Gelöscht • Fahrrad', 'Gelöscht · Fahrrad'])('strips %s', titel => {
    expect(titelFuerAnzeige(titel)).toBe('Fahrrad');
  });

  it('leaves the title unchanged when the deleted badge is absent', () => {
    // Seit AP-2.35 unabhängig von `geloescht`: Das Präfix ist eine Dekoration
    // der Plattform und nie Teil des Titels. Bei fremden Anzeigen ist
    // `geloescht` immer false (AP-3.10) - dort stand es vorher im Titelfeld.
    expect(titelFuerAnzeige('Gelöscht • Fahrrad')).toBe('Fahrrad');
  });
});
