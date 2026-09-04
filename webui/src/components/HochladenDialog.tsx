// SPDX-FileCopyrightText: © Anzeigen-Studio contributors
// SPDX-License-Identifier: AGPL-3.0-or-later
//
// Rückfrage vor dem Hochladen einer Anzeige (AP-3.3, AP-3.8).
//
// Der erste Vorgang der Oberfläche, der etwas auf kleinanzeigen.de verändert.
// Deshalb steht hier ausdrücklich, was passiert und was nicht - und zwar
// vorher, nicht als Meldung danach.
//
// Seit AP-3.5 zeigt er auch, WAS sich ändert. Die Vergleichsfassung ist die
// Datei in dem Moment, in dem der Bot sie zuletzt geschrieben hat - beim
// Herunterladen oder nach dem letzten Hochladen. Kennt das Backend keinen
// solchen Moment, wird kein Unterschied behauptet, sondern gesagt, dass keiner
// bekannt ist. Das war schon vorher die Regel und bleibt es.

import { useEffect, useState } from 'react';
import { ArrowUpFromLine, Info } from 'lucide-react';
import { api } from '../services/api';
import type { BestandsAnzeige, Vergleich } from '../types';

interface Props {
  anzeige: BestandsAnzeige;
  profil: string;
  laeuft: boolean;
  aufAbbrechen: () => void;
  aufBestaetigen: () => void;
}

/** „2026-08-27T17:17:51+00:00" → „27.08.2026, 19:17". */
function zeitpunkt(iso: string): string {
  const wert = new Date(iso);
  if (Number.isNaN(wert.getTime())) return iso;
  return wert.toLocaleString('de-DE', {
    day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit',
  });
}

const QUELLE_TEXT: Record<string, string> = {
  download: 'heruntergeladen',
  update: 'hochgeladen',
  publish: 'veröffentlicht',
};

function preisZeile(anzeige: BestandsAnzeige): string {
  if (anzeige.preistyp === 'GIVE_AWAY') return 'Zu verschenken';
  if (anzeige.preis === null) return 'kein Preis';
  const betrag = anzeige.preis.toLocaleString('de-DE', { style: 'currency', currency: 'EUR' });
  return anzeige.preistyp === 'NEGOTIABLE' ? `${betrag} (VB)` : betrag;
}

/**
 * Der Unterschied zum letzten bekannten Stand der Plattform (AP-3.5).
 *
 * Drei Fälle, und alle drei sind verschieden: Es ist noch kein Abgleich
 * bekannt, es gibt keinen Unterschied, oder es gibt einen. Der erste Fall darf
 * nicht wie der zweite aussehen — „nichts geändert" wäre dann eine Behauptung
 * über etwas, das niemand weiß.
 */
function Vergleichsteil({ profil, datei }: { profil: string; datei: string }) {
  const [vergleich, setVergleich] = useState<Vergleich | null>(null);
  const [laedt, setLaedt] = useState(true);
  const [fehler, setFehler] = useState(false);

  useEffect(() => {
    let verworfen = false;
    setLaedt(true);
    api.bestand.vergleich(profil, datei)
      .then(ergebnis => { if (!verworfen) setVergleich(ergebnis); })
      .catch(() => { if (!verworfen) setFehler(true); })
      .finally(() => { if (!verworfen) setLaedt(false); });
    return () => { verworfen = true; };
  }, [profil, datei]);

  if (laedt) {
    return <p className="mb-4 text-sm text-leise">Vergleich wird geladen …</p>;
  }

  // Ein Fehler hier darf das Hochladen nicht blockieren: Der Vergleich ist
  // zusätzliche Auskunft, nicht Voraussetzung.
  if (fehler || !vergleich) {
    return (
      <p className="mb-4 text-sm text-leise">
        Der Vergleich mit dem letzten Stand ist nicht verfügbar. Hochladen geht trotzdem.
      </p>
    );
  }

  if (vergleich.stand_von === null) {
    return (
      <p className="karte mb-4 p-3 text-sm text-normal">
        Für diese Anzeige ist noch kein Abgleich mit der Plattform bekannt – es lässt sich
        deshalb nicht sagen, was sich ändert. Nach diesem Lauf ist er bekannt.
      </p>
    );
  }

  const gemerkt = `${zeitpunkt(vergleich.stand_von)}${
    vergleich.quelle && QUELLE_TEXT[vergleich.quelle]
      ? ` ${QUELLE_TEXT[vergleich.quelle]}`
      : ''
  }`;

  if (vergleich.unterschiede.length === 0) {
    return (
      <p className="karte mb-4 p-3 text-sm text-normal">
        Gegenüber dem Stand von {gemerkt} hat sich nichts geändert. Der Lauf würde dieselben
        Werte noch einmal schreiben.
      </p>
    );
  }

  return (
    <div className="hinweis hinweis-warn mb-4">
      <p className="mb-2 text-sm font-medium text-amber-900">
        {vergleich.unterschiede.length === 1
          ? 'Ein Feld ändert sich'
          : `${vergleich.unterschiede.length} Felder ändern sich`}
        {' '}– gegenüber dem Stand von {gemerkt}:
      </p>
      <ul className="space-y-1 text-sm">
        {vergleich.unterschiede.map(u => (
          <li key={u.feld} className="flex flex-wrap items-baseline gap-x-2">
            <span className="text-normal">{u.beschriftung}:</span>
            <span className="text-leise line-through">{u.vorher}</span>
            <span aria-hidden className="text-leise">→</span>
            <span className="font-medium text-stark">{u.jetzt}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

export function HochladenDialog({ anzeige, profil, laeuft, aufAbbrechen, aufBestaetigen }: Props) {
  // Die Anzeigennummer entscheidet, welcher Vorgang das ist (AP-3.8) - dieselbe
  // Bedingung wie im Backend. Ohne Nummer war die Anzeige nie online; es gibt
  // nichts zu bearbeiten, also wird eingestellt.
  const neu = anzeige.id === null;

  return (
    <div className="fixed inset-0 z-50 flex items-end justify-center bg-black/40 p-4 sm:items-center">
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="hochladen-titel"
        className="dialog"
      >
        <h2 id="hochladen-titel" className="mb-1 font-semibold text-stark">
          {neu ? 'Neu auf kleinanzeigen.de einstellen' : 'Auf kleinanzeigen.de aktualisieren'}
        </h2>
        <p className="mb-4 text-sm text-normal">
          {neu
            ? 'Der Bot meldet sich an, füllt das Aufgabeformular mit dem hier gespeicherten Stand und stellt die Anzeige ein.'
            : 'Der Bot meldet sich an, öffnet diese Anzeige und schreibt den hier gespeicherten Stand hinein.'}
        </p>

        <dl className="karte mb-4 space-y-1 p-3 text-sm">
          <div className="flex justify-between gap-3">
            <dt className="text-leise">Anzeige</dt>
            <dd className="min-w-0 truncate text-stark">{anzeige.titel}</dd>
          </div>
          <div className="flex justify-between gap-3">
            <dt className="text-leise">Nummer</dt>
            <dd className="text-stark">
              {neu ? 'noch keine – wird beim Einstellen vergeben' : anzeige.id}
            </dd>
          </div>
          <div className="flex justify-between gap-3">
            <dt className="text-leise">Preis</dt>
            <dd className="text-stark">{preisZeile(anzeige)}</dd>
          </div>
          <div className="flex justify-between gap-3">
            <dt className="text-leise">Versand</dt>
            <dd className="min-w-0 truncate text-stark">
              {anzeige.versandpakete.length > 0
                ? anzeige.versandpakete.join(', ')
                : anzeige.versandart === 'PICKUP' ? 'nur Abholung' : 'kein Paket'}
            </dd>
          </div>
          <div className="flex justify-between gap-3">
            <dt className="text-leise">Bilder</dt>
            <dd className="text-stark">{anzeige.bilder}</dd>
          </div>
        </dl>

        {/* Ein Vergleich mit dem letzten Plattformstand ergibt nur Sinn, wenn es
            einen gibt. Bei einer nie veröffentlichten Anzeige gibt es keinen. */}
        {!neu && <Vergleichsteil profil={profil} datei={anzeige.datei} />}

        <div className="hinweis mb-4 flex items-start gap-2">
          <Info className="mt-0.5 h-4 w-4 flex-shrink-0" aria-hidden />
          {neu ? (
            <p>
              Die Anzeige wird <span className="font-medium">neu eingestellt</span>. Sie ist
              danach öffentlich sichtbar und bekommt ihre Anzeigennummer. Bestehende
              Anzeigen bleiben unberührt – auch eine gleichnamige wird nicht ersetzt.
            </p>
          ) : (
            <p>
              Die Anzeige wird <span className="font-medium">bearbeitet, nicht neu eingestellt</span>.
              Anzeigennummer, Aufrufe, Merker und das Alter bleiben erhalten.
            </p>
          )}
        </div>

        <p className="mb-4 text-xs text-leise">
          {neu
            ? 'Der Lauf sieht nur diese eine Datei – kein anderer Entwurf geht mit online. '
            : 'Verglichen wird mit dem letzten Stand, den der Bot geschrieben hat – hat jemand die '
              + 'Anzeige seither auf kleinanzeigen.de selbst bearbeitet, weiß das hier niemand. '
              + 'Überschrieben wird in jedem Fall mit dem Stand von hier. '}
          Der Lauf erscheint anschließend unter „Läufe" und lässt sich dort mitlesen und abbrechen.
        </p>

        <div className="flex flex-col-reverse gap-2 sm:flex-row sm:justify-end">
          <button
            type="button"
            onClick={aufAbbrechen}
            disabled={laeuft}
            className="btn-ghost"
          >
            Abbrechen
          </button>
          <button
            type="button"
            onClick={aufBestaetigen}
            disabled={laeuft}
            className="flex items-center justify-center gap-2 rounded bg-primary-custom px-4 py-2
                       text-sm font-medium disabled:cursor-not-allowed disabled:opacity-60"
          >
            <ArrowUpFromLine className="h-4 w-4" aria-hidden />
            {laeuft
              ? 'Wird eingereiht …'
              : neu ? 'Jetzt veröffentlichen' : 'Jetzt aktualisieren'}
          </button>
        </div>
      </div>
    </div>
  );
}
