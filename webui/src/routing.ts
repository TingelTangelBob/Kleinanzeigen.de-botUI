// SPDX-FileCopyrightText: © Anzeigen-Studio contributors
// SPDX-License-Identifier: AGPL-3.0-or-later
//
// Hash-Routing ohne Router. Eine Handvoll Seiten, Unterpunkte über den Rest
// nach dem Schrägstrich: #anzeigen/fremde, #warteschlange. Eine offene Anzeige
// steht als Query im Hash, damit Browser-Zurück und Neuladen denselben Zustand
// wiederherstellen können.

export type Hauptseite = 'uebersicht' | 'anzeigen' | 'neu' | 'warteschlange' | 'einstellungen';
export type AnzeigenHerkunft = 'eigene' | 'fremde';
export type EinstellungsAbschnitt =
  'anzeigen' | 'bot' | 'profile' | 'browser' | 'passwort' | 'darstellung';

export interface Route {
  seite: Hauptseite;
  anzeigen: AnzeigenHerkunft;
  einstellung: EinstellungsAbschnitt;
  anzeigeDatei: string | null;
  anzeigeBearbeiten: boolean;
}

const EINSTELLUNG: EinstellungsAbschnitt[] = [
  'anzeigen', 'bot', 'profile', 'browser', 'passwort', 'darstellung',
];

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

  const [pfad, query = ''] = roh.split('?');
  const [seiteRoh, rest = ''] = pfad.split('/');
  if (seiteRoh === 'anzeigen') {
    const parameter = new URLSearchParams(query);
    const anzeigeDatei = parameter.get('datei');
    return {
      seite: 'anzeigen',
      anzeigen: rest === 'fremde' ? 'fremde' : 'eigene',
      einstellung: 'bot',
      anzeigeDatei,
      anzeigeBearbeiten: anzeigeDatei !== null && parameter.get('bearbeiten') === '1',
    };
  }
  if (seiteRoh === 'neu') {
    return {
      seite: 'neu', anzeigen: 'eigene', einstellung: 'bot',
      anzeigeDatei: null, anzeigeBearbeiten: false,
    };
  }
  if (seiteRoh === 'warteschlange') {
    return {
      seite: 'warteschlange', anzeigen: 'eigene', einstellung: 'bot',
      anzeigeDatei: null, anzeigeBearbeiten: false,
    };
  }
  if (seiteRoh === 'einstellungen') {
    const abschnitt = (EINSTELLUNG as string[]).includes(rest)
      ? (rest as EinstellungsAbschnitt)
      : 'bot';
    return {
      seite: 'einstellungen', anzeigen: 'eigene', einstellung: abschnitt,
      anzeigeDatei: null, anzeigeBearbeiten: false,
    };
  }
  return {
    seite: 'uebersicht', anzeigen: 'eigene', einstellung: 'bot',
    anzeigeDatei: null, anzeigeBearbeiten: false,
  };
}

export function hashFuer(seite: Hauptseite, rest?: string): string {
  if (seite === 'anzeigen') return `anzeigen/${rest === 'fremde' ? 'fremde' : 'eigene'}`;
  if (seite === 'einstellungen') {
    if (!rest || rest === 'bot') return 'einstellungen';
    return `einstellungen/${rest}`;
  }
  return seite;
}

/** Hash für die Detailansicht einer Anzeige, optional bereits im Editiermodus. */
export function hashFuerAnzeige(
  herkunft: AnzeigenHerkunft,
  datei: string,
  bearbeiten = false,
): string {
  const parameter = new URLSearchParams({ datei });
  if (bearbeiten) parameter.set('bearbeiten', '1');
  return `anzeigen/${herkunft}?${parameter.toString()}`;
}
