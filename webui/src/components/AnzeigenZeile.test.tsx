// SPDX-FileCopyrightText: © Anzeigen-Studio contributors
// SPDX-License-Identifier: AGPL-3.0-or-later
//
// Test des „Gelöscht"-Badges an der Anzeigenzeile (AP-3.10).
//
// Klassifiziert wird im Backend über das YAML-Feld `active` (BestandsAnzeige.
// geloescht). Die Zeile muss den Unterschied sichtbar machen: eine eigene,
// einst online gestellte Anzeige, die nicht mehr aktiv ist, trägt ein rotes
// „Gelöscht" - eine bloß inaktive fremde Anzeige das neutrale „Inaktiv".

import { describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { AnzeigenZeile } from './AnzeigenZeile';
import type { BestandsAnzeige } from '../types';

vi.mock('../services/api', () => ({
  api: { bestand: { bildUrl: () => '' } },
}));

function anzeige(t: Partial<BestandsAnzeige>): BestandsAnzeige {
  return {
    datei: 'downloaded-ads/ad_fire/ad_fire.yaml',
    ordner: 'ad_fire',
    titel: 'Amazon Fire TV Stick',
    id: 3461223245,
    art: 'OFFER',
    aktiv: true,
    kategorie: null,
    preis: 15,
    preistyp: 'FIXED',
    versandart: null,
    versandkosten: null,
    versandpakete: [],
    direkt_kaufen: false,
    bilder: 0,
    vorschaubild: null,
    erstellt_am: null,
    aktualisiert_am: null,
    neueinstellung_am: null,
    faellig: false,
    lokal_geaendert: false,
    hinweise: [],
    unlesbar: null,
    herkunft: 'eigene',
    geloescht: false,
    ...t,
  };
}

describe('AnzeigenZeile: „Gelöscht"-Badge (AP-3.10)', () => {
  it('zeigt „Gelöscht" für eine eigene, nicht mehr aktive Anzeige', () => {
    render(<AnzeigenZeile anzeige={anzeige({ aktiv: false, geloescht: true })} profil="test" />);

    expect(screen.getByText('Gelöscht')).toBeDefined();
    expect(screen.queryByText('Inaktiv')).toBeNull();
  });

  it('zeigt für eine inaktive fremde Anzeige das neutrale „Inaktiv"', () => {
    render(
      <AnzeigenZeile
        anzeige={anzeige({ herkunft: 'fremde', aktiv: false, geloescht: false })}
        profil="test"
      />,
    );

    expect(screen.getByText('Inaktiv')).toBeDefined();
    expect(screen.queryByText('Gelöscht')).toBeNull();
  });

  it('zeigt kein Statusmerkmal für eine aktive Anzeige', () => {
    render(<AnzeigenZeile anzeige={anzeige({})} profil="test" />);

    expect(screen.queryByText('Gelöscht')).toBeNull();
    expect(screen.queryByText('Inaktiv')).toBeNull();
  });

  it('zeigt den Gelöscht-Präfix nicht als Teil des Titels', () => {
    render(
      <AnzeigenZeile
        anzeige={anzeige({ titel: 'Gelöscht • Amazon Fire TV Stick', aktiv: false, geloescht: true })}
        profil="test"
      />,
    );

    expect(screen.getByText('Amazon Fire TV Stick')).toBeDefined();
    expect(screen.queryByText('Gelöscht • Amazon Fire TV Stick')).toBeNull();
  });
});
