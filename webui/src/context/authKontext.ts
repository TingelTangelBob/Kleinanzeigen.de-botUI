// SPDX-FileCopyrightText: © Anzeigen-Studio contributors
// SPDX-License-Identifier: AGPL-3.0-or-later
//
// Nur der Kontext und sein Typ. Eigene Datei, damit AuthContext.tsx
// ausschliesslich Komponenten exportiert - sonst funktioniert Fast Refresh im
// Entwicklungsbetrieb nicht.

import { createContext } from 'react';
import type { AuthStatus } from '../types';

export interface AuthWert {
  /** null, solange der Zustand noch geladen wird oder das Backend schweigt. */
  status: AuthStatus | null;
  laedt: boolean;
  anmelden: (name: string, passwort: string) => Promise<void>;
  einrichten: (name: string, passwort: string) => Promise<void>;
  abmelden: () => Promise<void>;
  neuLaden: () => Promise<void>;
}

export const AuthKontext = createContext<AuthWert | null>(null);
