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
import { fireEvent } from '@testing-library/dom';
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

  it('bietet für eigene Online-Anzeigen eine Aktualisieren-Iconaktion an', () => {
    const aufAktualisieren = vi.fn();
    const daten = anzeige({});
    render(
      <AnzeigenZeile
        anzeige={daten}
        profil="test"
        aufAktualisieren={aufAktualisieren}
      />,
    );

    fireEvent.click(screen.getByRole('button', { name: /Amazon Fire TV Stick.*aktualisieren/ }));
    expect(aufAktualisieren).toHaveBeenCalledWith(daten);
  });

  it('bietet eine eigenständige Iconaktion zum Öffnen an', () => {
    const aufOeffnen = vi.fn();
    const daten = anzeige({});
    render(
      <AnzeigenZeile
        anzeige={daten}
        profil="test"
        aufOeffnen={aufOeffnen}
      />,
    );

    const oeffnen = screen.getByRole('button', { name: /Amazon Fire TV Stick.*öffnen/ });
    fireEvent.click(oeffnen);

    expect(aufOeffnen).toHaveBeenCalledWith(daten);
    expect(oeffnen.querySelector('svg')).not.toBeNull();
  });
});

describe('AnzeigenZeile: Aktionsspalte (AP-2.50)', () => {
  it('legt Aktualisieren, Öffnen und Umsortieren in eine gemeinsame Icon-Reihe', () => {
    const { container } = render(
      <AnzeigenZeile
        anzeige={anzeige({})}
        profil="test"
        aufAktualisieren={vi.fn()}
        aufOeffnen={vi.fn()}
        aufUmsortieren={vi.fn()}
      />,
    );

    const aktionen = container.querySelector('.zeile-aktionen');
    expect(aktionen).not.toBeNull();
    const reihe = aktionen!.querySelector('.zeile-aktionen-reihe');
    expect(reihe).not.toBeNull();
    expect(reihe!.querySelectorAll('button')).toHaveLength(3);
    // Kein Text-Knopf „Zu Von anderen" mehr – nur Icon mit aria-label.
    expect(screen.queryByRole('button', { name: /^Zu / })).toBeNull();
  });

  it('ruft aufUmsortieren für eigene Anzeigen mit Verschieben-Label', () => {
    const aufUmsortieren = vi.fn();
    const daten = anzeige({ herkunft: 'eigene' });
    render(
      <AnzeigenZeile
        anzeige={daten}
        profil="test"
        aufUmsortieren={aufUmsortieren}
      />,
    );

    fireEvent.click(
      screen.getByRole('button', { name: /Amazon Fire TV Stick.*Von anderen.*verschieben/ }),
    );
    expect(aufUmsortieren).toHaveBeenCalledWith(daten);
  });

  it('beschriftet Umsortieren bei fremden Anzeigen als „zu meinen Anzeigen"', () => {
    const aufUmsortieren = vi.fn();
    const daten = anzeige({ herkunft: 'fremde' });
    render(
      <AnzeigenZeile
        anzeige={daten}
        profil="test"
        aufUmsortieren={aufUmsortieren}
      />,
    );

    fireEvent.click(
      screen.getByRole('button', { name: /Amazon Fire TV Stick.*zu meinen Anzeigen/ }),
    );
    expect(aufUmsortieren).toHaveBeenCalledWith(daten);
  });
});

describe('AnzeigenZeile: ⋯-Menü auf schmalen Viewports (AP-2.54)', () => {
  it('öffnet Aktualisieren, Öffnen und Umsortieren über das Kebab-Menü', () => {
    const aufAktualisieren = vi.fn();
    const aufOeffnen = vi.fn();
    const aufUmsortieren = vi.fn();
    const daten = anzeige({});
    render(
      <AnzeigenZeile
        anzeige={daten}
        profil="test"
        aufAktualisieren={aufAktualisieren}
        aufOeffnen={aufOeffnen}
        aufUmsortieren={aufUmsortieren}
      />,
    );

    const kebab = screen.getByRole('button', { name: /Aktionen für .*Amazon Fire TV Stick/ });
    expect(kebab.getAttribute('aria-haspopup')).toBe('menu');
    expect(kebab.getAttribute('aria-expanded')).toBe('false');

    fireEvent.click(kebab);
    expect(kebab.getAttribute('aria-expanded')).toBe('true');
    expect(screen.getByRole('menu', { name: /Aktionen für .*Amazon Fire TV Stick/ })).toBeDefined();

    fireEvent.click(screen.getByRole('menuitem', { name: 'Aktualisieren' }));
    expect(aufAktualisieren).toHaveBeenCalledWith(daten);
    expect(screen.queryByRole('menu')).toBeNull();

    fireEvent.click(kebab);
    fireEvent.click(screen.getByRole('menuitem', { name: 'Öffnen' }));
    expect(aufOeffnen).toHaveBeenCalledWith(daten);

    fireEvent.click(kebab);
    fireEvent.click(screen.getByRole('menuitem', { name: /Von anderen/ }));
    expect(aufUmsortieren).toHaveBeenCalledWith(daten);
  });

  it('schließt das Menü mit Escape', () => {
    render(
      <AnzeigenZeile
        anzeige={anzeige({})}
        profil="test"
        aufOeffnen={vi.fn()}
      />,
    );

    const kebab = screen.getByRole('button', { name: /Aktionen für / });
    fireEvent.click(kebab);
    expect(screen.getByRole('menu')).toBeDefined();
    fireEvent.keyDown(document, { key: 'Escape' });
    expect(screen.queryByRole('menu')).toBeNull();
  });
});

describe('AnzeigenZeile: Preis und Aktionen in einer Spalte (AP-2.59)', () => {
  it('legt Preis und Aktions-Icons in .zeile-rechts', () => {
    const { container } = render(
      <AnzeigenZeile
        anzeige={anzeige({})}
        profil="test"
        aufAktualisieren={vi.fn()}
        aufOeffnen={vi.fn()}
        aufUmsortieren={vi.fn()}
      />,
    );

    const rechts = container.querySelector('.zeile-rechts');
    expect(rechts).not.toBeNull();
    expect(rechts!.querySelector('.zeile-preis')?.textContent).toMatch(/15/);
    expect(rechts!.querySelector('.zeile-aktionen')).not.toBeNull();
    // Preis sitzt nicht mehr neben dem Titel in der Inhaltszeile.
    const inhalt = container.querySelector('.zeile-inhalt');
    expect(inhalt!.querySelector('.zeile-preis')).toBeNull();
  });

  it('zeigt den Preis rechts auch ohne Aktions-Callbacks', () => {
    const { container } = render(
      <AnzeigenZeile anzeige={anzeige({ preis: 42 })} profil="test" />,
    );
    const rechts = container.querySelector('.zeile-rechts');
    expect(rechts).not.toBeNull();
    expect(rechts!.querySelector('.zeile-preis')?.textContent).toMatch(/42/);
    expect(rechts!.querySelector('.zeile-aktionen')).toBeNull();
  });
});
