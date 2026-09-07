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
import { Archive, LayoutDashboard, ListOrdered, LogOut, Menu, Settings, Sparkles, Tag, User, Users, X } from 'lucide-react';
import type { LucideIcon } from 'lucide-react';
import { api } from '../services/api';
import { useAuth } from '../context/useAuth';
import { useProfil } from '../context/useProfil';
import type { Route } from '../routing';
import { hashFuer } from '../routing';
import type { JobZustand } from '../types';
import { useThema } from '../hooks/useThema';
import { KopfAktionenKontext } from '../context/kopfAktionenKontext';
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
    if (route.anzeigeDatei !== null) {
      return route.anzeigeBearbeiten ? 'Anzeige bearbeiten' : 'Anzeige ansehen';
    }
    if (route.anzeigen === 'fremde') return 'Von anderen';
    if (route.anzeigen === 'archiv') return 'Archiv';
    return 'Meine Anzeigen';
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
  // Slots für die Seiten-Aktionsknöpfe: `kopfZiel` sitzt in der Topleiste (ab
  // md), `kopfZielMobil` als eigene Zeile darunter (unter md, weil die
  // Topleiste auf ~375 px zu eng ist). Die Seite füllt einen davon per Portal
  // (useKopfAktionen); leer bleiben beide unsichtbar.
  const [kopfZiel, setKopfZiel] = useState<HTMLElement | null>(null);
  const [kopfZielMobil, setKopfZielMobil] = useState<HTMLElement | null>(null);
  // AP-2.55: Profilname in der Topbar nur zeigen, wenn der Aktions-Slot leer
  // ist. Mit Holen/⋯ bleibt sonst auf ~375 px vom Seitentitel nur „Mei…".
  const [kopfHatInhalt, setKopfHatInhalt] = useState(false);

  // Beim Seitenwechsel das Mobilmenü schließen - sonst verdeckt es die Seite,
  // auf die man gerade gewechselt ist.
  useEffect(() => {
    setMenuOffen(false);
  }, [route]);

  useEffect(() => {
    if (!kopfZiel) {
      setKopfHatInhalt(false);
      return;
    }
    const sync = () => setKopfHatInhalt(kopfZiel.childElementCount > 0);
    sync();
    const beobachter = new MutationObserver(sync);
    beobachter.observe(kopfZiel, { childList: true });
    return () => beobachter.disconnect();
  }, [kopfZiel]);

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

        {/* Kein `overflow-y-auto` und kein `flex-1` mehr (AP-2.17). Die
            Hauptnav inkl. Anzeigen-Gruppe bleibt unter einer Viewport-Höhe;
            der Scrollbalken konnte hier nie etwas freilegen. Nach unten
            geschoben wird der Fuß von seinem eigenen `mt-auto`, und das
            Auffangnetz für wirklich flache Fenster sitzt an `.sidebar-schale`. */}
        {/*
          Nav-Ordnung AP-2.58: Übersicht (Dashboard), Warteschlange, dann die
          Anzeigen-Gruppe (Meine / Von anderen / Neue Anzeige / Archiv) —
          dieselbe visuelle Gruppierung wie `nav-gruppe` + `nav-unter` oben und
          Einstellungen vs. Abmelden unten (Randlinie). Einstellungen/Abmelden
          bleiben im Fuß (AP-2.49).
        */}
        <nav className="px-2 py-1">
          <NavKnopf
            aktiv={route.seite === 'uebersicht'}
            icon={LayoutDashboard}
            label="Übersicht"
            onClick={() => wechseln('uebersicht')}
          />
          <NavKnopf
            aktiv={route.seite === 'warteschlange'}
            icon={ListOrdered}
            label="Warteschlange"
            badge={aktiveLaeufe}
            onClick={() => wechseln('warteschlange')}
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
          <NavKnopf
            aktiv={route.seite === 'neu'}
            icon={Sparkles}
            label="Neue Anzeige"
            unter
            onClick={() => wechseln('neu')}
          />
          <NavKnopf
            aktiv={anzeigenAktiv && route.anzeigen === 'archiv'}
            icon={Archive}
            label="Archiv"
            unter
            onClick={() => wechseln(hashFuer('anzeigen', 'archiv'))}
          />
        </nav>

        {/* Fuß unten (AP-2.49): Einstellungen kleben mit `mt-auto` am unteren
            Rand, Abmelden darunter mit Trennlinie (wie Einstellungen vs.
            Profil-/Konto-Aktion). Warteschlange sitzt seit AP-2.58 unter der
            Übersicht in der Hauptnav. */}
        <div className="safe-unten mt-auto p-2">
          <NavKnopf
            aktiv={route.seite === 'einstellungen'}
            icon={Settings}
            label="Einstellungen"
            onClick={() => wechseln('einstellungen')}
          />
          <div className="mt-1 pt-1" style={{ borderTop: '1px solid var(--sidebar-rand)' }}>
            <button
              type="button"
              onClick={() => void abmelden()}
              className="nav-link"
            >
              <LogOut className="h-4 w-4 flex-shrink-0" />
              <span className="truncate">Abmelden{status?.name ? ` (${status.name})` : ''}</span>
            </button>
          </div>
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
          className="topbar safe-oben sticky top-0 z-20 flex items-center gap-2 px-3 sm:gap-3 sm:px-4 lg:px-8"
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
          {/* flex-1 + min-w unter sm: Titel bekommt Vorrang vor Aktionen/Glocke
              (AP-2.55), statt auf „Mei…" zusammenzuschrumpfen. */}
          <span
            className="min-w-[7.5rem] flex-1 truncate font-semibold tracking-tight sm:min-w-0 sm:flex-initial"
            style={{ color: 'var(--text-stark)' }}
            title={seitenTitel(route)}
          >
            {seitenTitel(route)}
          </span>
          {/* Aktionsknöpfe der Seite (Portal-Ziel ab md), dann die Glocke mit
              dezenter Trennlinie davor. Ist der Slot leer, verschwinden Slot
              und Linie. Unter md portalen die Aktionen in `.kopf-aktionen-mobil`
              (eigene Zeile unter der Leiste). */}
          <div ref={setKopfZiel} className="kopf-aktionen hidden md:flex" />
          <div className="topbar-glocke ml-auto flex min-w-0 items-center gap-2">
            <Glocke aufZiel={wechseln} />
            {aktiv && !kopfHatInhalt && (
              <span
                className="topbar-profilname hidden truncate text-sm md:block lg:hidden"
                style={{ color: 'var(--text-schwach)' }}
              >
                {aktiv.anzeigename}
              </span>
            )}
          </div>
        </header>

        {/* Seiten-Aktionen unter md: eigene Zeile unter der Topleiste. Leer → weg. */}
        <div ref={setKopfZielMobil} className="kopf-aktionen-mobil md:hidden" />

        <main className="min-w-0 flex-1 overflow-x-hidden px-4 py-6 sm:px-8 sm:py-8">
          <KopfAktionenKontext.Provider value={{ topbar: kopfZiel, mobil: kopfZielMobil }}>
            {children}
          </KopfAktionenKontext.Provider>
        </main>
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
