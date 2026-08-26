// SPDX-FileCopyrightText: © Anzeigen-Studio contributors
// SPDX-License-Identifier: AGPL-3.0-or-later
//
// Tests der Verkleinerungsrechnung (AP-2.6, K-2.6-004).
//
// Geprüft wird die Rechnung, nicht der Canvas-Durchlauf: Die Fehler sitzen
// beim Runden, beim Hochkantbild und beim Bild, das schon klein genug ist.

import { describe, expect, it } from 'vitest';
import { MAX_KANTE, sollVerkleinern, zielgroesse } from './bilder';

/** Eine Datei mit gesetzter Größe - `File` rechnet sie sonst aus dem Inhalt. */
function mitGroesse(groesse: number, typ = 'image/jpeg'): File {
  const f = new File([new Uint8Array(1)], 'foto.jpg', { type: typ, lastModified: 0 });
  Object.defineProperty(f, 'size', { value: groesse });
  return f;
}

describe('zielgroesse', () => {
  it('lässt ein kleines Bild unangetastet', () => {
    expect(zielgroesse(800, 600)).toEqual({ breite: 800, hoehe: 600 });
  });

  it('lässt ein Bild genau auf der Grenze unangetastet', () => {
    expect(zielgroesse(MAX_KANTE, 1000)).toEqual({ breite: MAX_KANTE, hoehe: 1000 });
  });

  it('verkleinert ein Querformat auf die lange Kante', () => {
    expect(zielgroesse(4000, 3000)).toEqual({ breite: 1920, hoehe: 1440 });
  });

  it('verkleinert ein Hochformat auf die lange Kante', () => {
    // Die lange Kante ist hier die Höhe - sie muss die Grenze treffen.
    expect(zielgroesse(3000, 4000)).toEqual({ breite: 1440, hoehe: 1920 });
  });

  it('behält das Seitenverhältnis auch bei krummen Werten', () => {
    const { breite, hoehe } = zielgroesse(4032, 3024);
    expect(breite).toBe(1920);
    expect(Math.abs(breite / hoehe - 4032 / 3024)).toBeLessThan(0.01);
  });

  it('erzeugt nie eine Kante der Länge null', () => {
    const { breite, hoehe } = zielgroesse(10000, 3);
    expect(breite).toBe(MAX_KANTE);
    expect(hoehe).toBeGreaterThanOrEqual(1);
  });

  it('verträgt unsinnige Eingaben', () => {
    expect(zielgroesse(0, 0)).toEqual({ breite: 0, hoehe: 0 });
    expect(zielgroesse(-5, 100)).toEqual({ breite: 0, hoehe: 0 });
  });
});

describe('sollVerkleinern', () => {
  it('greift bei einem großen Foto', () => {
    // Rund 20 MB - die Größenordnung aus dem Auftrag.
    expect(sollVerkleinern(mitGroesse(20 * 1024 * 1024))).toBe(true);
  });

  it('lässt kleine Dateien in Ruhe', () => {
    expect(sollVerkleinern(mitGroesse(500 * 1024))).toBe(false);
  });

  it('rührt GIF nicht an', () => {
    // Ein Canvas-Durchlauf würde eine Animation auf ihr erstes Bild reduzieren.
    expect(sollVerkleinern(mitGroesse(20 * 1024 * 1024, 'image/gif'))).toBe(false);
  });
});
