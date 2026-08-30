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
import { api, ApiFehler } from '../services/api';
import type { Profil } from '../types';
import { ProfilKontext, type ProfilWert } from './profilKontext';
import { useAuth } from './useAuth';

const SCHLUESSEL = 'anzeigen-studio-profil';

function gemerktesProfil(): string | null {
  if (typeof window === 'undefined') return null;
  return window.localStorage.getItem(SCHLUESSEL);
}

export function ProfilProvider({ children }: { children: ReactNode }) {
  // Der Abruf hängt am Anmeldezustand. Vorher lud dieser Provider EINMAL beim
  // Einhängen - und das war vor der Anmeldung, weil er die Anmeldeseite mit
  // umschließt. `/api/profile` antwortete mit 401, die Liste blieb leer, und
  // danach fragte niemand mehr nach. Wer sich anmeldete, sah deshalb „Noch
  // kein Profil angelegt", obwohl das Profil existierte; erst ein
  // vollständiges Neuladen der Seite half. Ein Hash-Wechsel nicht - die
  // Anwendung wird dabei nicht neu gestartet.
  const { status } = useAuth();
  const angemeldet = status?.angemeldet ?? false;

  const [profile, setProfile] = useState<Profil[]>([]);
  const [slug, setSlug] = useState<string | null>(gemerktesProfil);
  const [laedt, setLaedt] = useState(true);
  const [fehler, setFehler] = useState<string | null>(null);

  const neuLaden = useCallback(async () => {
    setLaedt(true);
    setFehler(null);
    try {
      const liste = await api.profile.liste();
      setProfile(liste);
      setSlug(vorher => {
        // Das gemerkte Profil kann gelöscht worden sein. Dann still auf das
        // erste vorhandene wechseln statt auf einen leeren Zustand zu zeigen.
        if (vorher && liste.some(p => p.slug === vorher)) return vorher;
        return liste[0]?.slug ?? null;
      });
    } catch (ursache) {
      // Ein fehlgeschlagener Abruf ist KEIN leerer Bestand. Genau diese
      // Gleichsetzung war der sichtbare Teil des Fehlers: Der 401 kam als
      // „du hast noch kein Profil" auf den Bildschirm - eine Störung, die
      // aussah wie ein gültiger Zustand, und deshalb niemanden alarmierte.
      setProfile([]);
      setFehler(ursache instanceof ApiFehler
        ? ursache.message
        : 'Die Profile ließen sich nicht laden.');
    } finally {
      setLaedt(false);
    }
  }, []);

  useEffect(() => {
    if (!angemeldet) {
      // Abgemeldet wird die Liste geleert, nicht bloß nicht neu geholt: Sonst
      // stünden nach dem Abmelden die Profile des vorigen Benutzers noch da.
      setProfile([]);
      setFehler(null);
      setLaedt(false);
      return;
    }
    void neuLaden();
  }, [angemeldet, neuLaden]);

  useEffect(() => {
    if (slug) window.localStorage.setItem(SCHLUESSEL, slug);
  }, [slug]);

  const wert = useMemo<ProfilWert>(() => ({
    profile,
    aktiv: profile.find(p => p.slug === slug) ?? null,
    laedt,
    fehler,
    waehlen: setSlug,
    neuLaden,
  }), [profile, slug, laedt, fehler, neuLaden]);

  return <ProfilKontext.Provider value={wert}>{children}</ProfilKontext.Provider>;
}
