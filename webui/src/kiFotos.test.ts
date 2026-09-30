// SPDX-FileCopyrightText: © Anzeigen-Studio contributors
// SPDX-License-Identifier: AGPL-3.0-or-later
//
// Gruppenbildung der Stapel-Erkennung (2026-09-30).

import { describe, expect, it } from 'vitest';
import { anfaengeJe, fotosPruefen, gruppenAus } from './kiFotos';

describe('Gruppen', () => {
  it('teilt in Reihenfolge je N Fotos', () => {
    expect(gruppenAus(5, anfaengeJe(5, 2))).toEqual([[0, 1], [2, 3], [4]]);
  });

  it('ein Foto je Anzeige', () => {
    expect(gruppenAus(3, anfaengeJe(3, 1))).toEqual([[0], [1], [2]]);
  });

  it('von Hand gesetzte Trennungen gelten', () => {
    expect(gruppenAus(4, new Set([0, 3]))).toEqual([[0, 1, 2], [3]]);
  });

  it('ohne Fotos keine Gruppe', () => {
    expect(gruppenAus(0, new Set([0]))).toEqual([]);
  });
});

describe('Fotoprüfung', () => {
  it('weist HEIC mit Hinweis ab und behält JPEG', () => {
    const jpeg = new File(['x'], 'a.jpg', { type: 'image/jpeg' });
    const heic = new File(['x'], 'b.heic', { type: 'image/heic' });
    const { brauchbar, fehler } = fotosPruefen([jpeg, heic]);
    expect(brauchbar).toEqual([jpeg]);
    expect(fehler).toContain('HEIC');
  });
});
