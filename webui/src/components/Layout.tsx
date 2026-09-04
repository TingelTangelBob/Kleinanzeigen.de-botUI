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
import { LayoutDashboard, ListOrdered, LogOut, Menu, Settings, Sparkles, Tag, User, Users, X } from 'lucide-react';
import type { LucideIcon } from 'lucide-react';
import { api } from '../services/api';
import { useAuth } from '../context/useAuth';
import { useProfil } from '../context/useProfil';
import type { Route } from '../routing';
import { hashFuer } from '../routing';
import type { JobZustand } from '../types';
import { useThema } from '../hooks/useThema';
import { Glocke } from './Glocke';

const AKTIVE_ZUSTAENDE = new Set<JobZustand>(['wartet', 'laeuft', 'braucht_eingabe']);

/**
 * Wie viele Läufe gerade aktiv sind - für den Zähler am Nav-Punkt
 * „Warteschlange" (AP-2.31). Eigener leiser Takt, dieselbe Quelle wie Glocke
 * und Warteschlangen-Seite. Fehler bleiben still: ein fehlender Zähler ist
 * kein Grund für eine Meldung in der Seitenleiste.
 */
function useAktiveLaufAnzahl(): number {
  const [anzahl, setAnzahl] = useState(0);
  useEffect(() => {
    let tot = false;
    const laden = async () => {
      try {
        const liste = await api.jobs.liste();
        if (!tot) setAnzahl(liste.filter(j => AKTIVE_ZUSTAENDE.has(j.zustand)).length);
      } catch {
        if (!tot) setAnzahl(0);
      }
    };
    void laden();
    const timer = window.setInterval(() => void laden(), 3000);
    return () => { tot = true; window.clearInterval(timer); };
  }, []);
  return anzahl;
}

/** @deprecated Nur noch Alias für ältere Importe; Routing läuft über routing.ts. */
export type Seite = Route['seite'] | 'bestand' | 'profile' | 'jobs' | 'browsersicht';

interface LayoutProps {
  route: Route;
  aufZiel: (ziel: string) => void;
  children: ReactNode;
}

function seitenTitel(route: Route): string {
  if (route.seite === 'uebersicht') return 'Übersicht';
  if (route.seite === 'anzeigen') {
    return route.anzeigen === 'fremde' ? 'Von anderen' : 'Meine Anzeigen';
  }
  if (route.seite === 'neu') return 'Neue Anzeige';
  if (route.seite === 'warteschlange') return 'Warteschlange';
  return 'Einstellungen';
}

export function Layout({ route, aufZiel, children }: LayoutProps) {
  const { status, abmelden } = useAuth();
  const { profile, aktiv, waehlen } = useProfil();
  const [menuOffen, setMenuOffen] = useState(false);
  // Nur noch das effektive Erscheinungsbild fürs `data-theme` am `#app-shell`.
  // Die Theme-*Wahl* sitzt seit AP-2.32 allein unter Einstellungen › Darstellung.
  const { effektiv: themaEffektiv } = useThema();
  const aktiveLaeufe = useAktiveLaufAnzahl();

  // Beim Seitenwechsel das Mobilmenü schließen - sonst verdeckt es die Seite,
  // auf die man gerade gewechselt ist.
  useEffect(() => {
    setMenuOffen(false);
  }, [route]);

  // Der Seitentitel steht seit AP-2.33 direkt in der Kopfleiste. Die Seiten
  // behalten dafür einen semantischen, visuell versteckten h1.
  useEffect(() => {
    document.title = `${seitenTitel(route)} · Anzeigen-Studio`;
  }, [route]);

  const wechseln = (ziel: string) => {
    window.location.hash = ziel;
    aufZiel(ziel);
  };

  const anzeigenAktiv = route.seite === 'anzeigen';

  return (
    <div
      id="app-shell"
      data-theme={themaEffektiv === 'dunkel' ? 'dark' : 'light'}
      className="flex min-h-screen"
      style={{ background: 'var(--canvas)', color: 'var(--text)' }}
    >
      {menuOffen && (
        <button
          type="button"
          aria-label="Menü schließen"
          onClick={() => setMenuOffen(false)}
          className="fixed inset-0 z-30 bg-black/40 lg:hidden"
        />
      )}

      {/*
        Ab lg klebt die Leiste am oberen Rand und ist genau ein Bildschirm hoch
        (AP-2.17). Vorher war sie `static` und wurde als Flex-Kind auf die
        Dokumenthöhe gedehnt: auf den Einstellungen 1682 px statt 800. Damit lag
        der Fuß mit Theme und Abmelden 775 px unterhalb des Sichtfelds - man kam
        nur ans Abmelden, indem man die ganze Seite nach unten scrollte. Dazu
        stand zwischen Navigation und Fuß ein leeres, dunkelgrünes Feld.
        `inset-y-auto` nimmt das `bottom: 0` der mobilen Schublade zurück; ein
        klebendes Element mit oberer *und* unterer Kante klebt sonst an beiden.
      */}
      <aside
        className={`sidebar-schale fixed inset-y-0 left-0 z-40 flex w-60 flex-col
                    transition-transform duration-200
                    lg:sticky lg:inset-y-auto lg:top-0 lg:h-screen lg:translate-x-0
                    ${menuOffen ? 'translate-x-0' : '-translate-x-full'}`}
      >
        <div className="safe-oben flex items-start justify-between gap-2 px-4 py-5">
          <div className="min-w-0">
            <div className="flex items-center gap-2.5">
              <span className="marke" aria-hidden>
                <Tag className="h-4 w-4" />
              </span>
              <span className="truncate text-[15px] font-semibold tracking-tight text-white">
                Anzeigen-Studio
              </span>
            </div>
            {profile.length > 1 ? (
              <select
                value={aktiv?.slug ?? ''}
                onChange={e => waehlen(e.target.value)}
                aria-label="Profil wählen"
                className="feld mt-3"
                style={{
                  background: 'var(--sidebar-aktiv)',
                  color: 'var(--sidebar-text)',
                  borderColor: 'var(--sidebar-rand)',
                }}
              >
                {profile.map(p => (
                  <option key={p.slug} value={p.slug}>{p.anzeigename}</option>
                ))}
              </select>
            ) : aktiv ? (
              <p className="mt-2 truncate text-xs" style={{ color: 'var(--sidebar-text-schwach)' }}>
                {aktiv.anzeigename}
              </p>
            ) : null}
          </div>
          <button
            type="button"
            onClick={() => setMenuOffen(false)}
            aria-label="Menü schließen"
            className="rounded p-1 lg:hidden"
            style={{ color: 'var(--sidebar-text-schwach)' }}
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        {/* Kein `overflow-y-auto` und kein `flex-1` mehr (AP-2.17). Fünf
            Einträge und eine Gruppenzeile sind rund 280 px hoch; der
            Scrollbalken konnte hier nie etwas freilegen, stand aber auf
            Systemen mit dauerhaft sichtbaren Balken immer da. Nach unten
            geschoben wird der Fuß jetzt von seinem eigenen `mt-auto`, und das
            Auffangnetz für wirklich flache Fenster sitzt an `.sidebar-schale`. */}
        <nav className="px-2 py-1">
          <NavKnopf
            aktiv={route.seite === 'uebersicht'}
            icon={LayoutDashboard}
            label="Übersicht"
            onClick={() => wechseln('uebersicht')}
          />

          <p className="nav-gruppe">Anzeigen</p>
          <NavKnopf
            aktiv={anzeigenAktiv && route.anzeigen === 'eigene'}
            icon={User}
            label="Meine Anzeigen"
            unter
            onClick={() => wechseln(hashFuer('anzeigen', 'eigene'))}
          />
          <NavKnopf
            aktiv={anzeigenAktiv && route.anzeigen === 'fremde'}
            icon={Users}
            label="Von anderen"
            unter
            onClick={() => wechseln(hashFuer('anzeigen', 'fremde'))}
          />

          <div className="mt-4">
            <NavKnopf
              aktiv={route.seite === 'neu'}
              icon={Sparkles}
              label="Neue Anzeige"
              onClick={() => wechseln('neu')}
            />
            {/* Ein Menüpunkt für die Läufe (AP-2.31): die frühere Mini-Liste
                unter der Nav ist weg, der Zähler zeigt nur an, wenn gerade
                etwas läuft oder wartet. */}
            <NavKnopf
              aktiv={route.seite === 'warteschlange'}
              icon={ListOrdered}
              label="Warteschlange"
              badge={aktiveLaeufe}
              onClick={() => wechseln('warteschlange')}
            />
            <NavKnopf
              aktiv={route.seite === 'einstellungen'}
              icon={Settings}
              label="Einstellungen"
              onClick={() => wechseln('einstellungen')}
            />
          </div>
        </nav>

        {/* `mt-auto` hält den Fuß auch dann unten, wenn die Navigation darüber
            einmal nicht mehr wachsen sollte. Nur noch Abmelden hier (AP-2.32):
            Die Theme-Wahl ist nach Einstellungen › Darstellung gewandert -
            ein Ort statt zwei. */}
        <div className="safe-unten mt-auto p-2" style={{ borderTop: '1px solid var(--sidebar-rand)' }}>
          <button
            type="button"
            onClick={() => void abmelden()}
            className="nav-link"
          >
            <LogOut className="h-4 w-4 flex-shrink-0" />
            <span className="truncate">Abmelden{status?.name ? ` (${status.name})` : ''}</span>
          </button>
        </div>
      </aside>

      <div className="flex min-w-0 flex-1 flex-col">
        {/*
          Der Seitentitel sitzt seit AP-2.33 nach dem Menü-Button. Auf Mobil
          ersetzt er den Produktnamen, damit nicht zweimal dieselbe Orientierung
          in der schmalen Leiste steht. Im Editor bleibt der Anzeigentitel die
          sichtbare h1 und ist damit kein Duplikat des Seitentitels.

          Übrig bleibt eine schmale Statuszeile mit der Lauf-Glocke (AP-2.25):
          Lauf-Meldungen sammeln sich dort statt als Vollbreite-Banner auf den
          Seiten. Sie klebt oben mit - ein Lauf, der den Menschen braucht,
          steht als eigene Pille daneben und darf nicht wegscrollen, sobald man
          in einer langen Seite nach unten geht.

          Die Höhe ist über `.topbar` fest auf `--topbar-hoehe` gelegt (AP-2.26):
          Glocke mit oder ohne Badge, die Eingriff-Pille und künftige
          Status-Chips tauschen sich aus, ohne die Leiste - und damit Sidebar
          und Hauptfläche - springen zu lassen. Kein `py-*` mehr, sonst würde
          ein höheres Kind den Slot doch wieder aufziehen.
        */}
        <header
          className="topbar safe-oben sticky top-0 z-20 flex items-center gap-3 px-4 lg:px-8"
          style={{ background: 'var(--karte)', borderBottom: '1px solid var(--karte-rand)' }}
        >
          <button
            type="button"
            onClick={() => setMenuOffen(true)}
            aria-label="Menü öffnen"
            className="btn-leise -ml-1 lg:hidden"
          >
            <Menu className="h-6 w-6" />
          </button>
          <span className="min-w-0 truncate font-semibold tracking-tight" style={{ color: 'var(--text-stark)' }}>
            {seitenTitel(route)}
          </span>
          <div className="ml-auto flex min-w-0 items-center gap-2">
            <Glocke aufZiel={wechseln} />
            {aktiv && (
              <span className="truncate text-sm lg:hidden" style={{ color: 'var(--text-schwach)' }}>
                {aktiv.anzeigename}
              </span>
            )}
          </div>
        </header>

        <main className="min-w-0 flex-1 overflow-x-hidden px-6 py-6 sm:px-8 sm:py-8">{children}</main>
      </div>
    </div>
  );
}

function NavKnopf({
  aktiv, icon: Icon, label, unter, badge, onClick,
}: {
  aktiv: boolean;
  icon: LucideIcon;
  label: string;
  unter?: boolean;
  /** Zahl rechts am Eintrag; 0 oder undefined blendet sie aus. */
  badge?: number;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-current={aktiv ? 'page' : undefined}
      className={`nav-link mb-0.5 ${unter ? 'nav-unter' : ''} ${aktiv ? 'nav-link-aktiv' : ''}`}
    >
      <Icon className="h-4 w-4 flex-shrink-0" />
      <span className="truncate">{label}</span>
      {badge ? (
        <span className="nav-zaehler" aria-label={`${badge} aktiv`}>{badge}</span>
      ) : null}
    </button>
  );
}
