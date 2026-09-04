// SPDX-FileCopyrightText: © Anzeigen-Studio contributors
// SPDX-License-Identifier: AGPL-3.0-or-later
//
// Nur der Kontext und seine Typen - getrennt von der Komponente, damit Fast
// Refresh funktioniert (gleiche Aufteilung wie beim Profil- und Anmeldezustand).
//
// Meldungen sind die Tipps, Hinweise und Warnungen einer Seite (AP-2.30). Sie
// standen bis hierher als vollbreite Banner im Seiteninhalt und fraßen Höhe.
// Jetzt sammelt sie die Glocke in der Kopfleiste - eine Stelle, ein Ton je
// Schwere, wegklickbar wo es eine Bedienhilfe ist.

import { createContext } from 'react';

export type MeldungTon = 'tipp' | 'hinweis' | 'warnung';

export interface Meldung {
  /** Stabile Kennung. Tipps/Hinweise merken sich das Wegklicken darüber. */
  id: string;
  ton: MeldungTon;
  titel: string;
  text: string;
}

export interface MeldungenWert {
  /** Sichtbare Meldungen, Warnungen zuerst, dann Hinweise, dann Tipps. */
  meldungen: Meldung[];
  /**
   * Ersetzt die Meldungen einer Quelle vollständig. Jede Seite meldet unter
   * eigenem Schlüssel; beim Verlassen ruft sie `melden(quelle, [])`.
   */
  melden: (quelle: string, liste: Meldung[]) => void;
  /**
   * Blendet eine Meldung aus. Tipps und Hinweise bleiben über Neuladen weg
   * (localStorage, dieselbe Ablage wie beim `Hinweis`-Banner); eine Warnung
   * kommt wieder, sobald die Seite sie erneut meldet.
   */
  abweisen: (id: string) => void;
}

export const MeldungenKontext = createContext<MeldungenWert | null>(null);
