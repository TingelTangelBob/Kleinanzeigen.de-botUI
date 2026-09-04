// SPDX-FileCopyrightText: © Anzeigen-Studio contributors
// SPDX-License-Identifier: AGPL-3.0-or-later
//
// Eine Anzeige als Zeile mit Vorschaubild (AP-2.2).
//
// Das Vorschaubild ist nicht Zierde: In einer Liste von zwanzig Anzeigen ist
// das Bild das, woran man seine Anzeige erkennt - nicht der Titel, den man
// selbst getippt hat und der bei drei Webcams dreimal ähnlich klingt.

import { AlertTriangle, ImageOff, Pencil, RefreshCw } from 'lucide-react';
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
  for (const h of anzeige.hinweise) {
    liste.push({
      schluessel: h, text: HINWEIS_TEXT[h] ?? h, ton: 'gelb', titel: HINWEIS_ERKLAERUNG[h],
    });
  }
  return liste;
}

export function AnzeigenZeile({ anzeige, profil, aufKlick }: Props) {
  const bildUrl = anzeige.vorschaubild
    ? api.bestand.bildUrl(profil, anzeige.datei, anzeige.vorschaubild)
    : null;

  const merkmale = merkmaleVon(anzeige);
  const gezeigt = merkmale.slice(0, MERKMALE_SICHTBAR);
  const versteckt = merkmale.slice(MERKMALE_SICHTBAR);
  const titel = titelFuerAnzeige(anzeige.titel);

  const inhalt = (
    <>
      <div
        className="h-24 w-24 flex-shrink-0 overflow-hidden rounded-xl sm:h-28 sm:w-28"
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
        <div className="flex items-start justify-between gap-3">
          {/* Bis 768 px zwei Zeilen statt einer abgeschnittenen (AP-2.18): auf
              375 px blieben von „Fahrradanhänger Croozer Kid for 2 mit …" sonst
              vierzehn Zeichen übrig, und genau der Titel ist das, woran man die
              Anzeige wiedererkennt. Ab 768 wird abgeschnitten, damit alle
              Zeilen der Liste gleich hoch bleiben. */}
          <span className="line-clamp-2 text-[15px] font-semibold tracking-tight text-stark sm:text-base md:line-clamp-none md:truncate">
            {titel}
          </span>
          <span className="flex-shrink-0 whitespace-nowrap text-[15px] font-semibold tracking-tight text-stark sm:text-base">
            {preisText(anzeige)}
          </span>
        </div>

        <div className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-leise">
          {anzeige.id !== null && <span>Nr. {anzeige.id}</span>}
          {anzeige.bilder > 0 && <span>{anzeige.bilder} {anzeige.bilder === 1 ? 'Bild' : 'Bilder'}</span>}
          {datumText(anzeige.erstellt_am) && <span>seit {datumText(anzeige.erstellt_am)}</span>}
          {anzeige.neueinstellung_am && !anzeige.faellig && (
            <span>neu am {datumText(anzeige.neueinstellung_am)}</span>
          )}
        </div>

        {merkmale.length > 0 && (
          <div className="mt-2 flex flex-wrap items-center gap-1.5">
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

  if (!aufKlick) {
    return <div className="zeile">{inhalt}</div>;
  }

  return (
    <button
      type="button"
      onClick={() => aufKlick(anzeige)}
      className="zeile"
    >
      {inhalt}
    </button>
  );
}
