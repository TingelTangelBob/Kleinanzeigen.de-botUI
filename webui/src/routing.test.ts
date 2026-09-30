// SPDX-FileCopyrightText: © Anzeigen-Studio contributors
// SPDX-License-Identifier: AGPL-3.0-or-later
//
// Test des Hash-Routings, Schwerpunkt Warteschlange (AP-2.31): der neue
// Menüpunkt und die Umlenkung der alten Läufe-Hashes.

import { describe, expect, it } from 'vitest';
import { hashFuer, hashFuerAnzeige, routeAusHash } from './routing';

describe('routeAusHash', () => {
  it('erkennt #warteschlange', () => {
    expect(routeAusHash('#warteschlange').seite).toBe('warteschlange');
  });

  it('lenkt den alten Unterpunkt #einstellungen/laeufe auf die Warteschlange', () => {
    expect(routeAusHash('#einstellungen/laeufe').seite).toBe('warteschlange');
  });

  it('lenkt den alten Top-Level-Hash #jobs auf die Warteschlange', () => {
    expect(routeAusHash('#jobs').seite).toBe('warteschlange');
  });

  it('hält alte Läufe-Hashes durch die Warteschlange kompatibel', () => {
    const route = routeAusHash('#einstellungen/laeufe');
    // Die Umlenkung greift, bevor der Abschnitt geraten wird.
    expect(route.seite).toBe('warteschlange');
    expect(routeAusHash('#einstellungen/profile')).toMatchObject({
      seite: 'einstellungen',
      einstellung: 'profile',
    });
  });

  it('öffnet die Ersteinrichtung über den nackten Einstellungen-Hash', () => {
    expect(routeAusHash('#einstellungen')).toMatchObject({
      seite: 'einstellungen',
      einstellung: 'uebersicht',
    });
  });

  it('öffnet einen fertigen KI-Entwurf direkt zur Prüfung', () => {
    expect(routeAusHash('#neu?erkennung=42')).toMatchObject({
      seite: 'neu',
      erkennungId: 42,
    });
    expect(routeAusHash('#neu?erkennung=0').erkennungId).toBeNull();
  });

  it('fällt für Unbekanntes auf die Übersicht zurück', () => {
    expect(routeAusHash('#quatsch').seite).toBe('uebersicht');
  });

  it('merkt sich die offene Anzeige und den Bearbeitungsmodus im Hash', () => {
    expect(routeAusHash('#anzeigen/eigene?datei=ads%2Fmein-entwurf.yaml&bearbeiten=1')).toMatchObject({
      seite: 'anzeigen',
      anzeigen: 'eigene',
      anzeigeDatei: 'ads/mein-entwurf.yaml',
      anzeigeBearbeiten: true,
    });
    expect(routeAusHash('#anzeigen/fremde?datei=fremde%2Flink.yaml')).toMatchObject({
      anzeigen: 'fremde',
      anzeigeDatei: 'fremde/link.yaml',
      anzeigeBearbeiten: false,
    });
  });
  it('erkennt #anzeigen/archiv (AP-2.58)', () => {
    expect(routeAusHash('#anzeigen/archiv')).toMatchObject({
      seite: 'anzeigen',
      anzeigen: 'archiv',
      anzeigeDatei: null,
    });
  });

  it('lenkt den Top-Level-Hash #archiv auf die Archiv-Liste', () => {
    expect(routeAusHash('#archiv').anzeigen).toBe('archiv');
  });

  it('öffnet eine Anzeige im Archiv-Hash', () => {
    expect(routeAusHash('#anzeigen/archiv?datei=ads%2Falt.yaml')).toMatchObject({
      anzeigen: 'archiv',
      anzeigeDatei: 'ads/alt.yaml',
      anzeigeBearbeiten: false,
    });
  });
});

describe('hashFuer', () => {
  it('gibt den nackten Seitennamen für die Warteschlange zurück', () => {
    expect(hashFuer('warteschlange')).toBe('warteschlange');
  });

  it('trennt die Ersteinrichtung vom Bot-Abschnitt', () => {
    expect(hashFuer('einstellungen')).toBe('einstellungen');
    expect(hashFuer('einstellungen', 'bot')).toBe('einstellungen/bot');
  });

  it('kodiert den Archiv-Listenpfad (AP-2.58)', () => {
    expect(hashFuer('anzeigen', 'archiv')).toBe('anzeigen/archiv');
  });

  it('kodiert den Dateipfad einer offenen Anzeige', () => {
    expect(hashFuerAnzeige('eigene', 'ads/Mein Entwurf.yaml', true))
      .toBe('anzeigen/eigene?datei=ads%2FMein+Entwurf.yaml&bearbeiten=1');
  });

  it('kodiert eine offene Anzeige im Archiv', () => {
    expect(hashFuerAnzeige('archiv', 'ads/alt.yaml'))
      .toBe('anzeigen/archiv?datei=ads%2Falt.yaml');
  });
});
