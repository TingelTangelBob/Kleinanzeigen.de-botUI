// SPDX-FileCopyrightText: © Anzeigen-Studio contributors
// SPDX-License-Identifier: AGPL-3.0-or-later
//
// Die zwei Zweige des Hochladen-Dialogs (AP-3.8).
//
// Der Dialog ist die letzte Stelle vor einem Vorgang, der etwas auf
// kleinanzeigen.de verändert. Er muss deshalb sagen, WELCHER Vorgang das ist -
// bearbeiten oder neu einstellen. Beides klingt im Alltag wie „hochladen", ist
// aber nicht dasselbe: Neu einstellen kostet Nummer, Aufrufe und Alter.

import { describe, expect, it, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { HochladenDialog } from './HochladenDialog';
import type { BestandsAnzeige } from '../types';

const vergleich = vi.fn();

vi.mock('../services/api', () => ({
  api: { bestand: { vergleich: (...a: unknown[]) => vergleich(...a) } },
}));

function anzeige(id: number | null): BestandsAnzeige {
  return {
    datei: 'ads/ad_9/ad_9.yaml', ordner: 'ad_9',
    titel: 'Samsung SSD 980 1TB NVMe',
    id, art: 'OFFER', aktiv: true, kategorie: null, preis: 45, preistyp: 'FIXED',
    versandart: 'PICKUP', versandkosten: null, versandpakete: [], direkt_kaufen: false,
    bilder: 2, vorschaubild: null, erstellt_am: null, aktualisiert_am: null,
    neueinstellung_am: null, faellig: false, lokal_geaendert: false,
    hinweise: [], unlesbar: null, herkunft: 'eigene', geloescht: false,
  };
}

function zeigen(id: number | null) {
  render(
    <HochladenDialog
      anzeige={anzeige(id)}
      profil="test"
      laeuft={false}
      aufAbbrechen={vi.fn()}
      aufBestaetigen={vi.fn()}
    />,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  vergleich.mockResolvedValue({ stand_von: null, quelle: null, unterschiede: [] });
});

describe('Ohne Anzeigennummer: veröffentlichen', () => {

  it('heißt Einstellen, nicht Aktualisieren', () => {
    zeigen(null);
    expect(screen.getByRole('heading', { name: /Neu auf kleinanzeigen\.de einstellen/ })).toBeTruthy();
    expect(screen.queryByRole('heading', { name: /aktualisieren/i })).toBeNull();
  });

  it('bietet „Jetzt veröffentlichen" an', () => {
    zeigen(null);
    expect(screen.getByRole('button', { name: /Jetzt veröffentlichen/ })).toBeTruthy();
    expect(screen.queryByRole('button', { name: /Jetzt aktualisieren/ })).toBeNull();
  });

  it('sagt, dass eine Nummer erst vergeben wird', () => {
    zeigen(null);
    expect(screen.getByText(/noch keine – wird beim Einstellen vergeben/)).toBeTruthy();
  });

  it('verspricht, dass bestehende Anzeigen unberührt bleiben', () => {
    zeigen(null);
    const dialog = screen.getByRole('dialog');
    expect(dialog.textContent).toContain('neu eingestellt');
    expect(dialog.textContent).toContain('auch eine gleichnamige wird nicht ersetzt');
  });

  it('fragt keinen Vergleich ab – es gibt keinen Plattformstand', () => {
    zeigen(null);
    expect(vergleich).not.toHaveBeenCalled();
  });
});

describe('Mit Anzeigennummer: aktualisieren', () => {

  it('heißt Aktualisieren und nennt die Nummer', () => {
    zeigen(3310837392);
    expect(screen.getByRole('heading', { name: /Auf kleinanzeigen\.de aktualisieren/ })).toBeTruthy();
    expect(screen.getByText('3310837392')).toBeTruthy();
  });

  it('bietet „Jetzt aktualisieren" an', () => {
    zeigen(3310837392);
    expect(screen.getByRole('button', { name: /Jetzt aktualisieren/ })).toBeTruthy();
    expect(screen.queryByRole('button', { name: /Jetzt veröffentlichen/ })).toBeNull();
  });

  it('sagt weiter zu, dass bearbeitet und nicht ersetzt wird', () => {
    zeigen(3310837392);
    const dialog = screen.getByRole('dialog');
    expect(dialog.textContent).toContain('bearbeitet, nicht neu eingestellt');
    expect(dialog.textContent).toContain('Anzeigennummer, Aufrufe, Merker und das Alter bleiben');
  });

  it('holt den Vergleich mit dem letzten Stand', async () => {
    zeigen(3310837392);
    await waitFor(() => expect(vergleich).toHaveBeenCalledWith('test', 'ads/ad_9/ad_9.yaml'));
  });
});
