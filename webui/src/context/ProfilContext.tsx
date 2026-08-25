// SPDX-FileCopyrightText: © Anzeigen-Studio contributors
// SPDX-License-Identifier: AGPL-3.0-or-later
//
// Das aktive Profil, für die ganze Oberfläche (AP-2.10).
//
// Vorher wählte jede Seite ihr Profil selbst. Das ging, solange es eine Seite
// gab, die Läufe startet. Sobald Bestand und Übersicht dazukommen, wäre es drei
// Auswahlfelder, die auseinanderlaufen können - und der Nutzer müsste raten,
// welches gerade gilt.
//
// Die Wahl bleibt über einen Neustart erhalten: Wer mit zwei Konten arbeitet,
// will nicht nach jedem Laden wieder umschalten.

import { useCallback, useEffect, useMemo, useState, type ReactNode } from 'react';
import { api } from '../services/api';
import type { Profil } from '../types';
import { ProfilKontext, type ProfilWert } from './profilKontext';

const SCHLUESSEL = 'anzeigen-studio-profil';

function gemerktesProfil(): string | null {
  if (typeof window === 'undefined') return null;
  return window.localStorage.getItem(SCHLUESSEL);
}

export function ProfilProvider({ children }: { children: ReactNode }) {
  const [profile, setProfile] = useState<Profil[]>([]);
  const [slug, setSlug] = useState<string | null>(gemerktesProfil);
  const [laedt, setLaedt] = useState(true);

  const neuLaden = useCallback(async () => {
    try {
      const liste = await api.profile.liste();
      setProfile(liste);
      setSlug(vorher => {
        // Das gemerkte Profil kann gelöscht worden sein. Dann still auf das
        // erste vorhandene wechseln statt auf einen leeren Zustand zu zeigen.
        if (vorher && liste.some(p => p.slug === vorher)) return vorher;
        return liste[0]?.slug ?? null;
      });
    } finally {
      setLaedt(false);
    }
  }, []);

  useEffect(() => {
    void neuLaden();
  }, [neuLaden]);

  useEffect(() => {
    if (slug) window.localStorage.setItem(SCHLUESSEL, slug);
  }, [slug]);

  const wert = useMemo<ProfilWert>(() => ({
    profile,
    aktiv: profile.find(p => p.slug === slug) ?? null,
    laedt,
    waehlen: setSlug,
    neuLaden,
  }), [profile, slug, laedt, neuLaden]);

  return <ProfilKontext.Provider value={wert}>{children}</ProfilKontext.Provider>;
}
