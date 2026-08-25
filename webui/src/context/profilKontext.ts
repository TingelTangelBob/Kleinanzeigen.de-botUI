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
  waehlen: (slug: string) => void;
  neuLaden: () => Promise<void>;
}

export const ProfilKontext = createContext<ProfilWert | null>(null);
