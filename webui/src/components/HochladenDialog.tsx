// SPDX-FileCopyrightText: © Anzeigen-Studio contributors
// SPDX-License-Identifier: AGPL-3.0-or-later
//
// Rückfrage vor dem Hochladen einer Anzeige (AP-3.3).
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
    return <p className="mb-4 text-sm text-gray-500">Vergleich wird geladen …</p>;
  }

  // Ein Fehler hier darf das Hochladen nicht blockieren: Der Vergleich ist
  // zusätzliche Auskunft, nicht Voraussetzung.
  if (fehler || !vergleich) {
    return (
      <p className="mb-4 text-sm text-gray-600">
        Der Vergleich mit dem letzten Stand ist nicht verfügbar. Hochladen geht trotzdem.
      </p>
    );
  }

  if (vergleich.stand_von === null) {
    return (
      <p className="mb-4 rounded border border-gray-200 bg-gray-50 p-3 text-sm text-gray-700">
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
      <p className="mb-4 rounded border border-gray-200 bg-gray-50 p-3 text-sm text-gray-700">
        Gegenüber dem Stand von {gemerkt} hat sich nichts geändert. Der Lauf würde dieselben
        Werte noch einmal schreiben.
      </p>
    );
  }

  return (
    <div className="mb-4 rounded border border-amber-200 bg-amber-50 p-3">
      <p className="mb-2 text-sm font-medium text-amber-900">
        {vergleich.unterschiede.length === 1
          ? 'Ein Feld ändert sich'
          : `${vergleich.unterschiede.length} Felder ändern sich`}
        {' '}– gegenüber dem Stand von {gemerkt}:
      </p>
      <ul className="space-y-1 text-sm">
        {vergleich.unterschiede.map(u => (
          <li key={u.feld} className="flex flex-wrap items-baseline gap-x-2">
            <span className="text-gray-700">{u.beschriftung}:</span>
            <span className="text-gray-500 line-through">{u.vorher}</span>
            <span aria-hidden className="text-gray-400">→</span>
            <span className="font-medium text-gray-900">{u.jetzt}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

export function HochladenDialog({ anzeige, profil, laeuft, aufAbbrechen, aufBestaetigen }: Props) {
  return (
    <div className="fixed inset-0 z-50 flex items-end justify-center bg-black/40 p-4 sm:items-center">
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="hochladen-titel"
        className="max-h-[85vh] w-full max-w-lg overflow-y-auto rounded-lg bg-white p-5 shadow-xl"
      >
        <h2 id="hochladen-titel" className="mb-1 font-semibold text-gray-900">
          Auf kleinanzeigen.de aktualisieren
        </h2>
        <p className="mb-4 text-sm text-gray-700">
          Der Bot meldet sich an, öffnet diese Anzeige und schreibt den hier gespeicherten
          Stand hinein.
        </p>

        <dl className="mb-4 space-y-1 rounded border border-gray-200 bg-gray-50 p-3 text-sm">
          <div className="flex justify-between gap-3">
            <dt className="text-gray-600">Anzeige</dt>
            <dd className="min-w-0 truncate text-gray-900">{anzeige.titel}</dd>
          </div>
          <div className="flex justify-between gap-3">
            <dt className="text-gray-600">Nummer</dt>
            <dd className="text-gray-900">{anzeige.id}</dd>
          </div>
          <div className="flex justify-between gap-3">
            <dt className="text-gray-600">Preis</dt>
            <dd className="text-gray-900">{preisZeile(anzeige)}</dd>
          </div>
          <div className="flex justify-between gap-3">
            <dt className="text-gray-600">Versand</dt>
            <dd className="min-w-0 truncate text-gray-900">
              {anzeige.versandpakete.length > 0
                ? anzeige.versandpakete.join(', ')
                : anzeige.versandart === 'PICKUP' ? 'nur Abholung' : 'kein Paket'}
            </dd>
          </div>
          <div className="flex justify-between gap-3">
            <dt className="text-gray-600">Bilder</dt>
            <dd className="text-gray-900">{anzeige.bilder}</dd>
          </div>
        </dl>

        <Vergleichsteil profil={profil} datei={anzeige.datei} />

        <div className="mb-4 flex items-start gap-2 rounded border border-blue-200 bg-blue-100 p-3 text-sm text-blue-900">
          <Info className="mt-0.5 h-4 w-4 flex-shrink-0" aria-hidden />
          <p>
            Die Anzeige wird <span className="font-medium">bearbeitet, nicht neu eingestellt</span>.
            Anzeigennummer, Aufrufe, Merker und das Alter bleiben erhalten.
          </p>
        </div>

        <p className="mb-4 text-xs text-gray-600">
          Verglichen wird mit dem letzten Stand, den der Bot geschrieben hat – hat jemand die
          Anzeige seither auf kleinanzeigen.de selbst bearbeitet, weiß das hier niemand.
          Überschrieben wird in jedem Fall mit dem Stand von hier. Der Lauf erscheint
          anschließend unter „Läufe" und lässt sich dort mitlesen und abbrechen.
        </p>

        <div className="flex flex-col-reverse gap-2 sm:flex-row sm:justify-end">
          <button
            type="button"
            onClick={aufAbbrechen}
            disabled={laeuft}
            className="rounded border border-gray-300 px-4 py-2 text-sm text-gray-700 hover:bg-gray-50"
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
            {laeuft ? 'Wird eingereiht …' : 'Jetzt aktualisieren'}
          </button>
        </div>
      </div>
    </div>
  );
}
