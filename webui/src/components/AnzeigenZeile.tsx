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
  const betrag = anzeige.preis.toLocaleString('de-DE', {
    style: 'currency', currency: 'EUR', minimumFractionDigits: 0, maximumFractionDigits: 2,
  });
  return anzeige.preistyp === 'NEGOTIABLE' ? `${betrag} VB` : betrag;
}

function datumText(iso: string | null): string | null {
  if (!iso) return null;
  const zeitpunkt = new Date(iso);
  if (Number.isNaN(zeitpunkt.getTime())) return null;
  return zeitpunkt.toLocaleDateString('de-DE', { day: '2-digit', month: '2-digit', year: 'numeric' });
}

function Merkmal({ text, ton, titel }: { text: string; ton: 'grau' | 'gelb' | 'blau' | 'rot'; titel?: string }) {
  const toene = {
    grau: 'bg-gray-100 text-gray-700',
    gelb: 'bg-amber-100 text-amber-900',
    blau: 'bg-blue-100 text-blue-800',
    rot: 'bg-red-100 text-red-800',
  };
  return (
    <span title={titel} className={`rounded px-1.5 py-0.5 text-xs font-medium ${toene[ton]}`}>
      {text}
    </span>
  );
}

interface Props {
  anzeige: BestandsAnzeige;
  profil: string;
  aufKlick?: (anzeige: BestandsAnzeige) => void;
}

export function AnzeigenZeile({ anzeige, profil, aufKlick }: Props) {
  const bildUrl = anzeige.vorschaubild
    ? api.bestand.bildUrl(profil, anzeige.datei, anzeige.vorschaubild)
    : null;

  const inhalt = (
    <>
      <div className="h-16 w-16 flex-shrink-0 overflow-hidden rounded border border-gray-200 bg-gray-50">
        {bildUrl ? (
          <img
            src={bildUrl}
            alt=""
            loading="lazy"
            className="h-full w-full object-cover"
          />
        ) : (
          <div className="flex h-full w-full items-center justify-center text-gray-400">
            <ImageOff className="h-6 w-6" aria-hidden />
          </div>
        )}
      </div>

      <div className="min-w-0 flex-1">
        <div className="flex items-start justify-between gap-3">
          <span className="truncate font-medium text-gray-900">{anzeige.titel}</span>
          <span className="flex-shrink-0 whitespace-nowrap font-semibold text-gray-900">
            {preisText(anzeige)}
          </span>
        </div>

        <div className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-gray-600">
          {anzeige.id !== null && <span>Nr. {anzeige.id}</span>}
          {anzeige.bilder > 0 && <span>{anzeige.bilder} {anzeige.bilder === 1 ? 'Bild' : 'Bilder'}</span>}
          {datumText(anzeige.erstellt_am) && <span>seit {datumText(anzeige.erstellt_am)}</span>}
          {anzeige.neueinstellung_am && !anzeige.faellig && (
            <span>neu am {datumText(anzeige.neueinstellung_am)}</span>
          )}
        </div>

        <div className="mt-1.5 flex flex-wrap items-center gap-1.5">
          {anzeige.art === 'WANTED' && <Merkmal text="Gesuch" ton="blau" />}
          {!anzeige.aktiv && <Merkmal text="Inaktiv" ton="grau" />}
          {anzeige.faellig && (
            <span
              title="Der eingestellte Abstand zur letzten Veröffentlichung ist erreicht."
              className="inline-flex items-center gap-1 rounded bg-blue-100 px-1.5 py-0.5 text-xs font-medium text-blue-800"
            >
              <RefreshCw className="h-3 w-3" aria-hidden />
              Fällig
            </span>
          )}
          {anzeige.lokal_geaendert && (
            <span
              title="Lokal geändert. Ein erneutes Herunterladen würde die Änderung überschreiben."
              className="inline-flex items-center gap-1 rounded bg-amber-100 px-1.5 py-0.5 text-xs font-medium text-amber-900"
            >
              <Pencil className="h-3 w-3" aria-hidden />
              Lokal geändert
            </span>
          )}
          {anzeige.hinweise.map(h => (
            <Merkmal
              key={h}
              text={HINWEIS_TEXT[h] ?? h}
              titel={HINWEIS_ERKLAERUNG[h]}
              ton="gelb"
            />
          ))}
          {anzeige.unlesbar && (
            <span
              title={anzeige.unlesbar}
              className="inline-flex items-center gap-1 rounded bg-red-100 px-1.5 py-0.5 text-xs font-medium text-red-800"
            >
              <AlertTriangle className="h-3 w-3" aria-hidden />
              Nicht lesbar
            </span>
          )}
        </div>
      </div>
    </>
  );

  if (!aufKlick) {
    return <div className="flex items-start gap-3 p-3">{inhalt}</div>;
  }

  return (
    <button
      type="button"
      onClick={() => aufKlick(anzeige)}
      className="flex w-full items-start gap-3 p-3 text-left hover:bg-gray-50"
    >
      {inhalt}
    </button>
  );
}
