// SPDX-FileCopyrightText: © Anzeigen-Studio contributors
// SPDX-License-Identifier: AGPL-3.0-or-later

import { useContext } from 'react';
import { ProfilKontext, type ProfilWert } from './profilKontext';

export function useProfil(): ProfilWert {
  const wert = useContext(ProfilKontext);
  if (!wert) throw new Error('useProfil muss innerhalb von ProfilProvider stehen');
  return wert;
}
