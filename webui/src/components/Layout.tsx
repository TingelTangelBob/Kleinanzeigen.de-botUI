// SPDX-FileCopyrightText: © Anzeigen-Studio contributors
// SPDX-License-Identifier: AGPL-3.0-or-later
//
// App-Schale mit Seitenleiste (AP-2.1).
//
// Aufbau übernommen aus SoloOffice (AGPL-3.0-or-later): Seitenleiste mit
// Mobilmenü, gespeicherter Einklappzustand, Hash-Routing ohne Router.
// Gekürzt auf das, was dieses Projekt braucht - die Breitenverstellung und die
// globale Suche aus SoloOffice fehlen bewusst, solange es nichts zu durchsuchen
// gibt.

import { useEffect, useState, type ReactNode } from 'react';
import { Briefcase, LayoutDashboard, ListTree, LogOut, Menu, Monitor, Moon, Sparkles, Sun, Users, X } from 'lucide-react';
import type { LucideIcon } from 'lucide-react';
import { useAuth } from '../context/useAuth';
import { useProfil } from '../context/useProfil';

export type Seite = 'uebersicht' | 'bestand' | 'neu' | 'profile' | 'jobs' | 'browsersicht';

interface NavEintrag {
  id: Seite;
  label: string;
  icon: LucideIcon;
}

const NAV: NavEintrag[] = [
  { id: 'uebersicht', label: 'Übersicht', icon: LayoutDashboard },
  { id: 'bestand', label: 'Anzeigen', icon: ListTree },
  { id: 'neu', label: 'Neue Anzeige', icon: Sparkles },
  { id: 'jobs', label: 'Läufe', icon: Briefcase },
  { id: 'profile', label: 'Profile', icon: Users },
  { id: 'browsersicht', label: 'Browsersicht', icon: Monitor },
];

const THEME_SCHLUESSEL = 'anzeigen-studio-theme';

function themaLesen(): 'hell' | 'dunkel' {
  if (typeof window === 'undefined') return 'hell';
  const gespeichert = window.localStorage.getItem(THEME_SCHLUESSEL);
  if (gespeichert === 'hell' || gespeichert === 'dunkel') return gespeichert;
  return window.matchMedia?.('(prefers-color-scheme: dark)').matches ? 'dunkel' : 'hell';
}

interface LayoutProps {
  seite: Seite;
  aufSeitenwechsel: (seite: Seite) => void;
  children: ReactNode;
}

export function Layout({ seite, aufSeitenwechsel, children }: LayoutProps) {
  const { status, abmelden } = useAuth();
  const { profile, aktiv, waehlen } = useProfil();
  const [menuOffen, setMenuOffen] = useState(false);
  const [thema, setThema] = useState<'hell' | 'dunkel'>(themaLesen);

  useEffect(() => {
    window.localStorage.setItem(THEME_SCHLUESSEL, thema);
  }, [thema]);

  // Beim Seitenwechsel das Mobilmenü schließen - sonst verdeckt es die Seite,
  // auf die man gerade gewechselt ist.
  useEffect(() => {
    setMenuOffen(false);
  }, [seite]);

  const wechseln = (ziel: Seite) => {
    window.location.hash = ziel;
    aufSeitenwechsel(ziel);
  };

  return (
    <div
      id="app-shell"
      data-theme={thema === 'dunkel' ? 'dark' : 'light'}
      className="flex min-h-screen bg-gray-50"
    >
      {/* Overlay hinter dem Mobilmenü. Klick daneben schließt. */}
      {menuOffen && (
        <button
          type="button"
          aria-label="Menü schließen"
          onClick={() => setMenuOffen(false)}
          className="fixed inset-0 z-30 bg-black/40 lg:hidden"
        />
      )}

      <aside
        className={`fixed inset-y-0 left-0 z-40 flex w-64 flex-col border-r border-gray-200
                    bg-white transition-transform duration-200 lg:static lg:translate-x-0
                    ${menuOffen ? 'translate-x-0' : '-translate-x-full'}`}
      >
        <div className="safe-oben flex items-center justify-between border-b border-gray-200 px-4 py-4">
          <span className="font-semibold text-gray-900">Anzeigen-Studio</span>
          <button
            type="button"
            onClick={() => setMenuOffen(false)}
            aria-label="Menü schließen"
            className="rounded p-1 text-gray-500 hover:bg-gray-100 lg:hidden"
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        {/* Globaler Profilumschalter (AP-2.10). Er steht hier oben, weil jede
            Seite darunter sich auf dieses Profil bezieht - eine Auswahl je
            Seite hatte den Nutzer raten lassen, welche gerade gilt.
            Bei genau einem Profil wäre ein Auswahlfeld nur Zierde; dann steht
            dort der Name. */}
        {profile.length > 0 && (
          <div className="border-b border-gray-200 px-4 py-3">
            <span className="mb-1 block text-xs font-medium text-gray-500">Profil</span>
            {profile.length === 1 ? (
              <span className="block truncate text-sm text-gray-900">{aktiv?.anzeigename}</span>
            ) : (
              <select
                value={aktiv?.slug ?? ''}
                onChange={e => waehlen(e.target.value)}
                aria-label="Profil wählen"
                className="w-full rounded border border-gray-300 px-2 py-1.5 text-sm
                           focus:border-primary-custom focus:outline-none focus:ring-1 focus:ring-primary-custom"
              >
                {profile.map(p => (
                  <option key={p.slug} value={p.slug}>{p.anzeigename}</option>
                ))}
              </select>
            )}
          </div>
        )}

        <nav className="flex-1 overflow-y-auto p-2">
          {NAV.map(({ id, label, icon: Icon }) => (
            <button
              key={id}
              type="button"
              onClick={() => wechseln(id)}
              aria-current={seite === id ? 'page' : undefined}
              className={`mb-1 flex w-full items-center gap-3 rounded px-3 py-2 text-left text-sm
                          ${seite === id
                            ? 'bg-primary-custom font-medium'
                            : 'text-gray-700 hover:bg-gray-100'}`}
            >
              <Icon className="h-5 w-5 flex-shrink-0" />
              <span className="truncate">{label}</span>
            </button>
          ))}
        </nav>

        <div className="safe-unten border-t border-gray-200 p-2">
          <button
            type="button"
            onClick={() => setThema(thema === 'hell' ? 'dunkel' : 'hell')}
            className="mb-1 flex w-full items-center gap-3 rounded px-3 py-2 text-left text-sm
                       text-gray-700 hover:bg-gray-100"
          >
            {thema === 'hell'
              ? <Moon className="h-5 w-5 flex-shrink-0" />
              : <Sun className="h-5 w-5 flex-shrink-0" />}
            <span>{thema === 'hell' ? 'Dunkelmodus' : 'Hellmodus'}</span>
          </button>

          <button
            type="button"
            onClick={() => void abmelden()}
            className="flex w-full items-center gap-3 rounded px-3 py-2 text-left text-sm
                       text-gray-700 hover:bg-gray-100"
          >
            <LogOut className="h-5 w-5 flex-shrink-0" />
            <span className="truncate">Abmelden{status?.name ? ` (${status.name})` : ''}</span>
          </button>
        </div>
      </aside>

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="safe-oben flex items-center gap-3 border-b border-gray-200 bg-white px-4 py-3 lg:hidden">
          <button
            type="button"
            onClick={() => setMenuOffen(true)}
            aria-label="Menü öffnen"
            className="rounded p-1 text-gray-700 hover:bg-gray-100"
          >
            <Menu className="h-6 w-6" />
          </button>
          <span className="font-semibold text-gray-900">Anzeigen-Studio</span>
          {aktiv && (
            <span className="ml-auto truncate text-sm text-gray-600">{aktiv.anzeigename}</span>
          )}
        </header>

        {/* min-w-0 verhindert, dass breite Inhalte die ganze Seite aufziehen. */}
        <main className="min-w-0 flex-1 overflow-x-hidden p-4 sm:p-6">{children}</main>
      </div>
    </div>
  );
}
