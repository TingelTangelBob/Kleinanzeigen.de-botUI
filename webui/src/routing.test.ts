// SPDX-FileCopyrightText: © Anzeigen-Studio contributors
// SPDX-License-Identifier: AGPL-3.0-or-later
//
// Test des Hash-Routings, Schwerpunkt Warteschlange (AP-2.31): der neue
// Menüpunkt und die Umlenkung der alten Läufe-Hashes.

import { describe, expect, it } from 'vitest';
import { hashFuer, routeAusHash } from './routing';

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

  it('führt unbekannte Einstellungs-Unterpunkte auf den Bot-Abschnitt', () => {
    const route = routeAusHash('#einstellungen/laeufe');
    // Die Umlenkung greift, bevor der Abschnitt geraten wird.
    expect(route.seite).toBe('warteschlange');
    expect(routeAusHash('#einstellungen/profile')).toMatchObject({
      seite: 'einstellungen',
      einstellung: 'profile',
    });
  });

  it('fällt für Unbekanntes auf die Übersicht zurück', () => {
    expect(routeAusHash('#quatsch').seite).toBe('uebersicht');
  });
});

describe('hashFuer', () => {
  it('gibt den nackten Seitennamen für die Warteschlange zurück', () => {
    expect(hashFuer('warteschlange')).toBe('warteschlange');
  });
});
