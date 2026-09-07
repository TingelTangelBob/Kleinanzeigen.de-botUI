// SPDX-FileCopyrightText: © Anzeigen-Studio contributors
// SPDX-License-Identifier: AGPL-3.0-or-later
//
// Eine Anzeige als Zeile mit Vorschaubild (AP-2.2).
//
// Das Vorschaubild ist nicht Zierde: In einer Liste von zwanzig Anzeigen ist
// das Bild das, woran man seine Anzeige erkennt - nicht der Titel, den man
// selbst getippt hat und der bei drei Webcams dreimal ähnlich klingt.
//
// UI-Anpassung 2026-09-09: kompakte Mobilzeile (~100 px). Bild 72 px, Titel
// einzeilig, Preis mobil neben dem Titel, Metazeile ohne Datum und mit
// nowrap-Tokens - vorher brach sie Wort für Wort um.

import { useEffect, useRef, useState } from 'react';
import { AlertTriangle, ArrowLeftRight, Eye, ImageOff, MoreVertical, Pencil, RefreshCw } from 'lucide-react';
import type { BestandsAnzeige } from '../types';
import { api } from '../services/api';
import { titelFuerAnzeige } from '../titel';

/** Klartext für die Kennungen aus der Verlustanalyse (docs/RUNDLAUF.md). */
const HINWEIS_TEXT: Record<string, string> = {
  versand_ohne_paket: 'Versand ohne Paket',
  direktkauf_ohne_paket: 'Direkt kaufen ohne Paket',
  versand_gemischte_groessen: 'Pakete mehrerer Größen',
  ohne_bild: 'Ohne Bild',
};

const HINWEIS_ERKLAERUNG: Record<string, string> = {
  versand_ohne_paket:
    'Der Versandpreis gehört zu keinem Kleinanzeigen-Paket. Beim Hochladen fehlt die Versandangabe.',
  direktkauf_ohne_paket:
    'Direkt kaufen ist gesetzt, aber kein Versandpaket ausgewählt. Der Bot kann die Anzeige so nicht einstellen.',
  versand_gemischte_groessen:
    'Die Versandpakete gehören zu mehreren Größen. Kleinanzeigen lässt nur eine Größe zu - beim Veröffentlichen bricht der Lauf im Versanddialog ab.',
  ohne_bild: 'Zu dieser Anzeige liegt kein Bild vor.',
};

function preisText(anzeige: BestandsAnzeige): string {
  if (anzeige.preistyp === 'GIVE_AWAY') return 'Zu verschenken';
  if (anzeige.preis === null) return '—';
  // Glatte Beträge ohne Nachkommastellen, krumme mit zweien (AP-2.18). Vorher
  // stand `minimumFractionDigits: 0` allein da, und 1249,50 € wurde als
  // „1.249,5 €" ausgegeben - ein Preis, den es in dieser Schreibweise nicht
  // gibt. Ein Cent-Betrag hat in Euro zwei Stellen oder keine.
  const glatt = Number.isInteger(anzeige.preis);
  const betrag = anzeige.preis.toLocaleString('de-DE', {
    style: 'currency',
    currency: 'EUR',
    minimumFractionDigits: glatt ? 0 : 2,
    maximumFractionDigits: glatt ? 0 : 2,
  });
  return anzeige.preistyp === 'NEGOTIABLE' ? `${betrag} VB` : betrag;
}

function datumText(iso: string | null): string | null {
  if (!iso) return null;
  const zeitpunkt = new Date(iso);
  if (Number.isNaN(zeitpunkt.getTime())) return null;
  return zeitpunkt.toLocaleDateString('de-DE', { day: '2-digit', month: '2-digit', year: 'numeric' });
}

const SYMBOL = { wiederholen: RefreshCw, stift: Pencil, warnung: AlertTriangle };

function Merkmal({ daten }: { daten: MerkmalDaten }) {
  const Symbol = daten.symbol ? SYMBOL[daten.symbol] : null;
  return (
    <span title={daten.titel} className={`merkmal merkmal-${daten.ton}`}>
      {Symbol && <Symbol className="h-3 w-3" aria-hidden />}
      {daten.text}
    </span>
  );
}

/**
 * So viele Merkmale zeigt eine Zeile; der Rest wandert in ein „+n"-Zeichen
 * (AP-2.18).
 *
 * Ohne Deckel wuchs eine Anzeige mit vier Hinweisen plus „Fällig" und „Lokal
 * geändert" auf 375 px zu einer 298 px hohen Zeile mit sechs Merkmalzeilen
 * unter einem 96-px-Bild - die Liste war nicht mehr überfliegbar. Drei ist die
 * Zahl, bei der ab 768 px noch alles in eine Zeile passt und auf dem Handy
 * höchstens drei Zeilen entstehen. Verloren geht nichts: Das „+n" trägt die
 * übrigen im Titel, und die Anzeige selbst zeigt sie vollständig.
 */
const MERKMALE_SICHTBAR = 3;

interface Props {
  anzeige: BestandsAnzeige;
  profil: string;
  aufKlick?: (anzeige: BestandsAnzeige) => void;
  aufOeffnen?: (anzeige: BestandsAnzeige) => void;
  aufAktualisieren?: (anzeige: BestandsAnzeige) => void;
  /** Herkunft wechseln: eigene ↔ Von anderen (AP-2.50). */
  aufUmsortieren?: (anzeige: BestandsAnzeige) => void;
}

interface MerkmalDaten {
  schluessel: string;
  text: string;
  ton: 'grau' | 'gelb' | 'blau' | 'rot';
  titel?: string;
  symbol?: 'wiederholen' | 'stift' | 'warnung';
}

/** Alle Merkmale der Anzeige in Anzeigereihenfolge - Dringendes zuerst. */
function merkmaleVon(anzeige: BestandsAnzeige): MerkmalDaten[] {
  const liste: MerkmalDaten[] = [];
  if (anzeige.unlesbar) {
    liste.push({
      schluessel: 'unlesbar', text: 'Nicht lesbar', ton: 'rot',
      titel: anzeige.unlesbar, symbol: 'warnung',
    });
  }
  if (anzeige.art === 'WANTED') liste.push({ schluessel: 'gesuch', text: 'Gesuch', ton: 'blau' });
  if (anzeige.geloescht) {
    liste.push({
      schluessel: 'geloescht', text: 'Gelöscht', ton: 'rot',
      titel: 'Auf kleinanzeigen.de nicht mehr aktiv. Gelöscht, pausiert oder in '
        + 'Prüfung – das unterscheidet der Download nicht. Die lokale Kopie bleibt.',
    });
  } else if (!anzeige.aktiv) {
    liste.push({ schluessel: 'inaktiv', text: 'Inaktiv', ton: 'grau' });
  }
  // Bei einer auf der Plattform nicht mehr aktiven Anzeige (AP-3.10) tragen
  // „Fällig" und „Lokal geändert" nichts bei: neu einstellen lässt sich nichts,
  // und neben „Gelöscht" verwirrt der Änderungshinweis nur. Die Zeile bleibt
  // dann bei „Gelöscht".
  if (!anzeige.geloescht) {
    if (anzeige.faellig) {
      liste.push({
        schluessel: 'faellig', text: 'Fällig', ton: 'blau', symbol: 'wiederholen',
        titel: 'Der eingestellte Abstand zur letzten Veröffentlichung ist erreicht.',
      });
    }
    if (anzeige.lokal_geaendert) {
      liste.push({
        schluessel: 'geaendert', text: 'Lokal geändert', ton: 'gelb', symbol: 'stift',
        titel: 'Lokal geändert. Ein erneutes Herunterladen würde die Änderung überschreiben.',
      });
    }
  }
  for (const h of anzeige.hinweise) {
    liste.push({
      schluessel: h, text: HINWEIS_TEXT[h] ?? h, ton: 'gelb', titel: HINWEIS_ERKLAERUNG[h],
    });
  }
  return liste;
}

function umsortierenLabel(anzeige: BestandsAnzeige, titel: string): { aria: string; titel: string; menue: string } {
  if (anzeige.herkunft === 'eigene') {
    return {
      aria: '„' + titel + '“ nach „Von anderen“ verschieben',
      titel: 'Nach „Von anderen“ verschieben',
      menue: 'Nach „Von anderen“',
    };
  }
  return {
    aria: '„' + titel + '“ zu meinen Anzeigen',
    titel: 'Zu meinen Anzeigen',
    menue: 'Zu meinen Anzeigen',
  };
}

/**
 * Zeilenaktionen: Icon-Reihe ab md (AP-2.50), ⋯-Menü darunter (AP-2.54).
 * Schließen bei Klick daneben und Escape – dieselbe Sprache wie der Bestandskopf.
 */
function ZeileAktionen({
  titel, anzeige, aufOeffnen, aufAktualisieren, aufUmsortieren,
}: {
  titel: string;
  anzeige: BestandsAnzeige;
  aufOeffnen?: (anzeige: BestandsAnzeige) => void;
  aufAktualisieren?: (anzeige: BestandsAnzeige) => void;
  aufUmsortieren?: (anzeige: BestandsAnzeige) => void;
}) {
  const [menueOffen, setMenueOffen] = useState(false);
  const menueRef = useRef<HTMLDivElement>(null);
  const umsortieren = aufUmsortieren ? umsortierenLabel(anzeige, titel) : null;

  useEffect(() => {
    if (!menueOffen) return undefined;
    const ausserhalb = (ereignis: MouseEvent) => {
      if (menueRef.current && !menueRef.current.contains(ereignis.target as Node)) {
        setMenueOffen(false);
      }
    };
    const escape = (ereignis: KeyboardEvent) => {
      if (ereignis.key === 'Escape') setMenueOffen(false);
    };
    document.addEventListener('mousedown', ausserhalb);
    document.addEventListener('keydown', escape);
    return () => {
      document.removeEventListener('mousedown', ausserhalb);
      document.removeEventListener('keydown', escape);
    };
  }, [menueOffen]);

  return (
    <div className="zeile-aktionen">
      <div className="zeile-aktionen-reihe hidden md:flex">
        {aufAktualisieren && (
          <button
            type="button"
            onClick={() => aufAktualisieren(anzeige)}
            aria-label={'„' + titel + '“ aktualisieren'}
            title="Anzeige aktualisieren"
            className="btn-icon zeile-aktualisieren"
          >
            <RefreshCw className="h-4 w-4" aria-hidden />
          </button>
        )}
        {aufOeffnen && (
          <button
            type="button"
            onClick={() => aufOeffnen(anzeige)}
            aria-label={'„' + titel + '“ öffnen'}
            title="Anzeige öffnen"
            className="btn-icon zeile-oeffnen"
          >
            <Eye className="h-4 w-4" aria-hidden />
          </button>
        )}
        {aufUmsortieren && umsortieren && (
          <button
            type="button"
            onClick={() => aufUmsortieren(anzeige)}
            aria-label={umsortieren.aria}
            title={umsortieren.titel}
            className="btn-icon zeile-umsortieren"
          >
            <ArrowLeftRight className="h-4 w-4" aria-hidden />
          </button>
        )}
      </div>

      <div ref={menueRef} className="plattform-menue zeile-aktionen-menue md:hidden">
        <button
          type="button"
          className="btn-icon"
          aria-haspopup="menu"
          aria-expanded={menueOffen}
          aria-label={'Aktionen für „' + titel + '“'}
          title="Weitere Aktionen"
          onClick={() => setMenueOffen(o => !o)}
        >
          <MoreVertical className="h-4 w-4" aria-hidden />
        </button>
        {menueOffen && (
          <div
            className="plattform-menue-panel"
            role="menu"
            aria-label={'Aktionen für „' + titel + '“'}
          >
            {aufAktualisieren && (
              <button
                type="button"
                role="menuitem"
                onClick={() => { setMenueOffen(false); aufAktualisieren(anzeige); }}
              >
                <RefreshCw className="h-4 w-4" aria-hidden />
                Aktualisieren
              </button>
            )}
            {aufOeffnen && (
              <button
                type="button"
                role="menuitem"
                onClick={() => { setMenueOffen(false); aufOeffnen(anzeige); }}
              >
                <Eye className="h-4 w-4" aria-hidden />
                Öffnen
              </button>
            )}
            {aufUmsortieren && umsortieren && (
              <button
                type="button"
                role="menuitem"
                onClick={() => { setMenueOffen(false); aufUmsortieren(anzeige); }}
              >
                <ArrowLeftRight className="h-4 w-4" aria-hidden />
                {umsortieren.menue}
              </button>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

export function AnzeigenZeile({
  anzeige, profil, aufKlick, aufOeffnen, aufAktualisieren, aufUmsortieren,
}: Props) {
  const bildUrl = anzeige.vorschaubild
    ? api.bestand.bildUrl(profil, anzeige.datei, anzeige.vorschaubild)
    : null;

  const merkmale = merkmaleVon(anzeige);
  const gezeigt = merkmale.slice(0, MERKMALE_SICHTBAR);
  const versteckt = merkmale.slice(MERKMALE_SICHTBAR);
  const titel = titelFuerAnzeige(anzeige.titel);

  const zeilenInhalt = (
    <>
      <div
        className="h-[72px] w-[72px] flex-shrink-0 overflow-hidden rounded-xl sm:h-28 sm:w-28"
        style={{ background: 'var(--canvas)', border: '1px solid var(--karte-rand)' }}
      >
        {bildUrl ? (
          <img
            src={bildUrl}
            alt=""
            loading="lazy"
            className="h-full w-full object-cover"
          />
        ) : (
          <div className="flex h-full w-full items-center justify-center text-leise">
            <ImageOff className="h-7 w-7" aria-hidden />
          </div>
        )}
      </div>

      <div className="min-w-0 flex-1">
        {/* Kompakte Mobilzeile (2026-09-09): Titel einzeilig gekürzt, der Preis
            steht mobil rechts daneben (rechts in der Zeile sitzt unter md nur
            das ⋯-Menü). Ab md trägt `.zeile-rechts` den Preis wie bisher
            (AP-2.59), und der Titel wird dort abgeschnitten. */}
        <div className="flex items-baseline justify-between gap-2">
          <span className="truncate text-[15px] font-semibold tracking-tight text-stark sm:text-base">
            {titel}
          </span>
          <span className="zeile-preis-mobil flex-shrink-0 md:hidden">{preisText(anzeige)}</span>
        </div>

        <div className="mt-0.5 flex flex-wrap items-center gap-x-3 gap-y-0.5 text-xs text-leise">
          {anzeige.id !== null && <span className="whitespace-nowrap">Nr. {anzeige.id}</span>}
          {anzeige.bilder > 0 && (
            <span className="whitespace-nowrap">
              {anzeige.bilder} {anzeige.bilder === 1 ? 'Bild' : 'Bilder'}
            </span>
          )}
          {datumText(anzeige.erstellt_am) && (
            <span className="hidden whitespace-nowrap sm:inline">seit {datumText(anzeige.erstellt_am)}</span>
          )}
          {anzeige.neueinstellung_am && !anzeige.faellig && (
            <span className="hidden whitespace-nowrap sm:inline">
              neu am {datumText(anzeige.neueinstellung_am)}
            </span>
          )}
        </div>

        {merkmale.length > 0 && (
          <div className="mt-1.5 flex flex-wrap items-center gap-1.5">
            {gezeigt.map(m => <Merkmal key={m.schluessel} daten={m} />)}
            {versteckt.length > 0 && (
              <span
                className="merkmal merkmal-grau"
                title={versteckt.map(m => m.text).join(' · ')}
              >
                +{versteckt.length}
              </span>
            )}
          </div>
        )}
      </div>
    </>
  );

  const hatAktionen = Boolean(aufOeffnen || aufAktualisieren || aufUmsortieren);

  return (
    <div className="zeile">
      {aufKlick ? (
        <button
          type="button"
          onClick={() => aufKlick(anzeige)}
          className="zeile-inhalt zeile-klick"
        >
          {zeilenInhalt}
        </button>
      ) : (
        <div className="zeile-inhalt">{zeilenInhalt}</div>
      )}
      {/*
        Rechte Spalte: Preis über den Aktionen, Spalte vertikal zentriert
        zur Zeile (AP-2.59). Vorher lag der Preis neben dem Titel (oben) und
        die Icon-Knöpfe tiefer – optisch zwei getrennte Höhen. Ab md: drei
        Icon-Knöpfe in einer Reihe (AP-2.50); darunter ⋯-Menü (AP-2.54).
      */}
      <div className="zeile-rechts">
        {/* Preis steht mobil neben dem Titel; hier nur ab md. */}
        <span className="zeile-preis hidden md:block">{preisText(anzeige)}</span>
        {hatAktionen && (
          <ZeileAktionen
            titel={titel}
            anzeige={anzeige}
            aufOeffnen={aufOeffnen}
            aufAktualisieren={aufAktualisieren}
            aufUmsortieren={aufUmsortieren}
          />
        )}
      </div>
    </div>
  );
}
