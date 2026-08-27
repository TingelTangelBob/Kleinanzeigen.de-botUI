// SPDX-FileCopyrightText: © Anzeigen-Studio contributors
// SPDX-License-Identifier: AGPL-3.0-or-later
//
// Test der Bildauswahl (AP-4.4).
//
// Der Fall, um den es geht, ist am 2026-08-27 im Betrieb aufgefallen: Ein Foto
// ließ sich wählen, danach passierte nichts. Grund war, dass `Array.from` auf
// der FileList erst im Aktualisierer von `setDateien` lief - also nachdem
// `input.value = ''` sie bereits geleert hatte. Der Test bildet genau diese
// Reihenfolge nach: auswählen, Eingabefeld leeren, und dann muss das Foto noch
// da sein.

import { describe, expect, it, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { fireEvent } from '@testing-library/dom';
import { NeueAnzeigeSeite } from './NeueAnzeigeSeite';

const status = vi.fn();
let objektUrlNummer = 0;

vi.mock('../services/api', () => ({
  api: { ki: { status: () => status() } },
  ApiFehler: class extends Error {},
}));

vi.mock('../context/useProfil', () => ({
  useProfil: () => ({ aktiv: { slug: 'test' }, profile: [] }),
}));

function foto(name: string, typ = 'image/jpeg'): File {
  return new File([new Uint8Array([0xff, 0xd8, 0xff])], name, { type: typ });
}

/** Eine FileList, wie der Browser sie liefert - jsdom kennt `DataTransfer` nicht. */
function alsFileList(dateien: File[]): FileList {
  const liste: Record<number | string, unknown> = {
    length: dateien.length,
    item: (i: number) => dateien[i] ?? null,
  };
  dateien.forEach((datei, index) => { liste[index] = datei; });
  return liste as unknown as FileList;
}

/**
 * Legt Dateien so in das versteckte Feld, wie der Browser es tut - einschließlich
 * des Verhaltens, an dem die erste Fassung gescheitert ist: `input.value = ''`
 * leert im Browser auch die FileList. Ohne diese Nachbildung würde der Test den
 * Fehler nicht auslösen und wäre wertlos.
 */
function auswaehlen(feld: HTMLInputElement, dateien: File[]) {
  const liste = alsFileList(dateien);
  Object.defineProperty(feld, 'files', { get: () => liste, configurable: true });
  Object.defineProperty(feld, 'value', {
    get: () => (liste.length > 0 ? 'C:\\fakepath\\datei' : ''),
    // Leert DASSELBE Objekt, statt die Variable neu zu binden. Der Unterschied
    // ist der ganze Test: Die Komponente hält eine Referenz auf diese FileList.
    // Wird nur die Variable hier umgehängt, merkt sie nichts davon - und der
    // Test bestünde auch mit dem Fehler. Genau das ist beim ersten Versuch
    // passiert und erst durch eine Gegenprobe aufgefallen.
    set: () => {
      const schreibbar = liste as unknown as Record<number | string, unknown>;
      for (let i = 0; i < dateien.length; i += 1) delete schreibbar[i];
      schreibbar.length = 0;
    },
    configurable: true,
  });
  fireEvent.change(feld);
}

beforeEach(() => {
  status.mockReset();
  objektUrlNummer = 0;
  status.mockResolvedValue({
    hinterlegt: true, endet_auf: 'TR0A', geaendert_am: null,
    modell: 'gpt-5.6-luna', bildkante: 768,
  });
  // jsdom kennt keine Objekt-URLs.
  URL.createObjectURL = vi.fn(() => `blob:test-${objektUrlNummer++}`);
  URL.revokeObjectURL = vi.fn();
});

describe('Bildauswahl', () => {
  it('behält das Foto, obwohl das Eingabefeld danach geleert wird', async () => {
    const { container } = render(<NeueAnzeigeSeite />);
    const feld = container.querySelector('input[type=file]') as HTMLInputElement;

    auswaehlen(feld, [foto('schrauber.jpg')]);

    // Genau hier lag der Fehler: Das Feld wird geleert, damit dieselbe Datei
    // erneut gewählt werden kann - und nahm das Foto mit.
    await waitFor(() => {
      expect(screen.getByText(/1 von 4 Fotos/)).toBeDefined();
    });
  });

  it('nimmt mehrere Fotos auf einmal an', async () => {
    const { container } = render(<NeueAnzeigeSeite />);
    const feld = container.querySelector('input[type=file]') as HTMLInputElement;

    auswaehlen(feld, [foto('a.jpg'), foto('b.jpg'), foto('c.jpg')]);

    await waitFor(() => {
      expect(screen.getByText(/3 von 4 Fotos/)).toBeDefined();
    });
  });

  it('nimmt ein Foto auch per Reinziehen an', async () => {
    const { container } = render(<NeueAnzeigeSeite />);
    const feld = container.querySelector('input[type=file]') as HTMLInputElement;

    fireEvent.drop(feld.parentElement!, {
      dataTransfer: { files: alsFileList([foto('gezogen.jpg')]) },
    });

    await waitFor(() => {
      expect(screen.getByText(/1 von 4 Fotos/)).toBeDefined();
    });
  });

  it('weist HEIC mit einem Hinweis ab, der weiterhilft', async () => {
    const { container } = render(<NeueAnzeigeSeite />);
    const feld = container.querySelector('input[type=file]') as HTMLInputElement;

    auswaehlen(feld, [foto('IMG_0042.HEIC', 'image/heic')]);

    await waitFor(() => {
      expect(screen.getByRole('alert').textContent).toMatch(/Maximale Kompatibilität/);
    });
    expect(screen.getByText(/0 von 4 Fotos/)).toBeDefined();
  });

  it('nimmt die brauchbaren Fotos an und meldet nur die unbrauchbaren', async () => {
    const { container } = render(<NeueAnzeigeSeite />);
    const feld = container.querySelector('input[type=file]') as HTMLInputElement;

    auswaehlen(feld, [foto('gut.jpg'), foto('text.txt', 'text/plain')]);

    await waitFor(() => {
      expect(screen.getByText(/1 von 4 Fotos/)).toBeDefined();
    });
    expect(screen.getByRole('alert').textContent).toMatch(/text\.txt/);
  });
});

describe('Erkennen-Knopf', () => {
  it('sagt, warum er nicht geht, wenn kein Schlüssel hinterlegt ist', async () => {
    status.mockResolvedValue({
      hinterlegt: false, endet_auf: null, geaendert_am: null,
      modell: 'gpt-5.6-luna', bildkante: 768,
    });
    render(<NeueAnzeigeSeite />);

    await waitFor(() => {
      expect(screen.getByText(/Es fehlt der OpenAI-Schlüssel/)).toBeDefined();
    });
  });

  it('sagt es auch, wenn sich der Zustand gar nicht laden ließ', async () => {
    // Vorher blieb der Knopf in diesem Fall stumm grau - der Nutzer musste raten.
    status.mockRejectedValue(new Error('Netz weg'));
    render(<NeueAnzeigeSeite />);

    await waitFor(() => {
      expect(screen.getByText(/ließ sich nicht laden/)).toBeDefined();
    });
  });
});
