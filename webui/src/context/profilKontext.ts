// SPDX-FileCopyrightText: © Anzeigen-Studio contributors
// SPDX-License-Identifier: AGPL-3.0-or-later
//
// Nur der Kontext und sein Typ - getrennt von der Komponente, damit Fast
// Refresh funktioniert (gleiche Aufteilung wie beim Anmeldezustand).

import { createContext } from 'react';
import type { Profil } from '../types';

export interface ProfilWert {
  profile: Profil[];
  /** Das gerade gewählte Profil, oder null solange keins existiert. */
  aktiv: Profil | null;
  laedt: boolean;
  /**
   * Warum die Liste leer ist, falls sie es wegen einer Störung ist. Getrennt
   * von `profile.length === 0`, weil beides sonst gleich aussieht - und ein
   * Fehler, der wie ein gültiger Leerzustand aussieht, wird nicht gemeldet.
   */
  fehler: string | null;
  waehlen: (slug: string) => void;
  neuLaden: () => Promise<void>;
}

export const ProfilKontext = createContext<ProfilWert | null>(null);
