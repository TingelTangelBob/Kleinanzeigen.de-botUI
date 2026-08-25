// SPDX-FileCopyrightText: © Anzeigen-Studio contributors
// SPDX-License-Identifier: AGPL-3.0-or-later
//
// Rückfrage vor dem Hochladen einer Anzeige (AP-3.3).
//
// Der erste Vorgang der Oberfläche, der etwas auf kleinanzeigen.de verändert.
// Deshalb steht hier ausdrücklich, was passiert und was nicht - und zwar
// vorher, nicht als Meldung danach.
//
// Was der Dialog NICHT zeigt, ist ein Vorher-Nachher-Vergleich: Was gerade auf
// der Plattform steht, weiß niemand hier. Das ehrlich zu sagen ist besser, als
// einen Unterschied zu behaupten, der geraten wäre. Ein echter Vergleich
// braucht die Fassung des letzten Hochladens - das ist AP-3.5.

import { ArrowUpFromLine, Info } from 'lucide-react';
import type { BestandsAnzeige } from '../types';

interface Props {
  anzeige: BestandsAnzeige;
  laeuft: boolean;
  aufAbbrechen: () => void;
  aufBestaetigen: () => void;
}

function preisZeile(anzeige: BestandsAnzeige): string {
  if (anzeige.preistyp === 'GIVE_AWAY') return 'Zu verschenken';
  if (anzeige.preis === null) return 'kein Preis';
  const betrag = anzeige.preis.toLocaleString('de-DE', { style: 'currency', currency: 'EUR' });
  return anzeige.preistyp === 'NEGOTIABLE' ? `${betrag} (VB)` : betrag;
}

export function HochladenDialog({ anzeige, laeuft, aufAbbrechen, aufBestaetigen }: Props) {
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

        <div className="mb-4 flex items-start gap-2 rounded border border-blue-200 bg-blue-100 p-3 text-sm text-blue-900">
          <Info className="mt-0.5 h-4 w-4 flex-shrink-0" aria-hidden />
          <p>
            Die Anzeige wird <span className="font-medium">bearbeitet, nicht neu eingestellt</span>.
            Anzeigennummer, Aufrufe, Merker und das Alter bleiben erhalten.
          </p>
        </div>

        <p className="mb-4 text-xs text-gray-600">
          Was gerade auf der Plattform steht, ist hier nicht bekannt – überschrieben wird es in
          jedem Fall mit dem Stand von hier. Der Lauf erscheint anschließend unter „Läufe" und
          lässt sich dort mitlesen und abbrechen.
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
