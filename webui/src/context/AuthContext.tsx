// SPDX-FileCopyrightText: © Anzeigen-Studio contributors
// SPDX-License-Identifier: AGPL-3.0-or-later
//
// Anmeldezustand der Oberfläche.
//
// Muster übernommen aus SoloOffice (AGPL-3.0-or-later); Inhalt an die
// Endpunkte dieses Projekts angepasst.

import { useCallback, useEffect, useMemo, useState, type ReactNode } from 'react';
import { api, ApiFehler } from '../services/api';
import type { AuthStatus } from '../types';
import { AuthKontext, type AuthWert } from './authKontext';

export function AuthProvider({ children }: { children: ReactNode }) {
  const [status, setStatus] = useState<AuthStatus | null>(null);
  const [laedt, setLaedt] = useState(true);

  const neuLaden = useCallback(async () => {
    try {
      setStatus(await api.auth.status());
    } catch (fehler) {
      // Backend nicht erreichbar: Wir wissen nichts. Das ist etwas anderes als
      // "nicht angemeldet" und darf in der Oberfläche nicht so aussehen.
      if (fehler instanceof ApiFehler && fehler.status === 0) {
        setStatus(null);
      } else {
        setStatus({ eingerichtet: false, angemeldet: false, name: null });
      }
    } finally {
      setLaedt(false);
    }
  }, []);

  useEffect(() => {
    void neuLaden();
  }, [neuLaden]);

  const wert = useMemo<AuthWert>(() => ({
    status,
    laedt,
    anmelden: async (name, passwort) => setStatus(await api.auth.anmelden(name, passwort)),
    einrichten: async (name, passwort) => setStatus(await api.auth.einrichten(name, passwort)),
    abmelden: async () => {
      await api.auth.abmelden();
      await neuLaden();
    },
    neuLaden,
  }), [status, laedt, neuLaden]);

  return <AuthKontext.Provider value={wert}>{children}</AuthKontext.Provider>;
}
