// SPDX-FileCopyrightText: © Anzeigen-Studio contributors
// SPDX-License-Identifier: AGPL-3.0-or-later
//
// Hash-Routing ohne Router. Eine Handvoll Seiten, Unterpunkte über den Rest
// nach dem Schrägstrich: #anzeigen/fremde, #warteschlange.

export type Hauptseite = 'uebersicht' | 'anzeigen' | 'neu' | 'warteschlange' | 'einstellungen';
export type AnzeigenHerkunft = 'eigene' | 'fremde';
export type EinstellungsAbschnitt = 'bot' | 'profile' | 'browser' | 'passwort' | 'darstellung';

export interface Route {
  seite: Hauptseite;
  anzeigen: AnzeigenHerkunft;
  einstellung: EinstellungsAbschnitt;
}

const EINSTELLUNG: EinstellungsAbschnitt[] = ['bot', 'profile', 'browser', 'passwort', 'darstellung'];

/** Alte Top-Level-Hashes, die es in der Nav nicht mehr gibt. */
const ALIAS: Record<string, string> = {
  bestand: 'anzeigen/eigene',
  jobs: 'warteschlange',
  profile: 'einstellungen/profile',
  browsersicht: 'einstellungen/browser',
};

/**
 * Ganze Pfade, die umgelenkt werden (AP-2.31). Die Läufe lagen bis hier als
 * Unterpunkt `einstellungen/laeufe`; Glocke, Dashboard und Editor verweisen
 * noch darauf. Der Menüpunkt heißt jetzt „Warteschlange" und liegt eine Ebene
 * höher - die alten Links sollen nicht ins Leere laufen.
 */
const PFAD_ALIAS: Record<string, string> = {
  'einstellungen/laeufe': 'warteschlange',
};

export function routeAusHash(hash = typeof window === 'undefined' ? '' : window.location.hash): Route {
  let roh = hash.replace(/^#/, '').replace(/^\//, '');
  const kopf = roh.split('/')[0] ?? '';
  if (kopf in ALIAS) roh = ALIAS[kopf];
  if (roh in PFAD_ALIAS) roh = PFAD_ALIAS[roh];

  const [seiteRoh, rest = ''] = roh.split('/');
  if (seiteRoh === 'anzeigen') {
    return {
      seite: 'anzeigen',
      anzeigen: rest === 'fremde' ? 'fremde' : 'eigene',
      einstellung: 'bot',
    };
  }
  if (seiteRoh === 'neu') {
    return { seite: 'neu', anzeigen: 'eigene', einstellung: 'bot' };
  }
  if (seiteRoh === 'warteschlange') {
    return { seite: 'warteschlange', anzeigen: 'eigene', einstellung: 'bot' };
  }
  if (seiteRoh === 'einstellungen') {
    const abschnitt = (EINSTELLUNG as string[]).includes(rest)
      ? (rest as EinstellungsAbschnitt)
      : 'bot';
    return { seite: 'einstellungen', anzeigen: 'eigene', einstellung: abschnitt };
  }
  return { seite: 'uebersicht', anzeigen: 'eigene', einstellung: 'bot' };
}

export function hashFuer(seite: Hauptseite, rest?: string): string {
  if (seite === 'anzeigen') return `anzeigen/${rest === 'fremde' ? 'fremde' : 'eigene'}`;
  if (seite === 'einstellungen') {
    if (!rest || rest === 'bot') return 'einstellungen';
    return `einstellungen/${rest}`;
  }
  return seite;
}
