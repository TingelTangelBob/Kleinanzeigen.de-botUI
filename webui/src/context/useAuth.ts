// SPDX-FileCopyrightText: © Anzeigen-Studio contributors
// SPDX-License-Identifier: AGPL-3.0-or-later

import { useContext } from 'react';
import { AuthKontext, type AuthWert } from './authKontext';

export function useAuth(): AuthWert {
  const wert = useContext(AuthKontext);
  if (!wert) throw new Error('useAuth muss innerhalb von AuthProvider stehen');
  return wert;
}
