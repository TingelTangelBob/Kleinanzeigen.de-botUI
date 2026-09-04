// SPDX-FileCopyrightText: © Anzeigen-Studio contributors
// SPDX-License-Identifier: AGPL-3.0-or-later
//
// Rückfrage vor dem lokalen Löschen (AP-2.20).
//
// Eigene Datei, weil ihn zwei Stellen brauchen: die Sammelaktion in der Liste
// und das Einzellöschen im Editor. Der Editor liegt seinerseits in der Liste,
// ein Import zwischen beiden wäre ein Zirkel.

import { AlertTriangle, Trash2 } from 'lucide-react';
import type { BestandsAnzeige } from '../types';

/**
 * Rückfrage vor dem Löschen (AP-2.20).
 *
 * Der Dialog muss zwei Dinge leisten, und das zweite ist das wichtigere:
 * Er zeigt, **welche** Anzeigen gehen, und er sagt unmissverständlich, dass
 * auf kleinanzeigen.de nichts passiert. Wer hier „Löschen" liest und an die
 * Plattform denkt, verliert entweder seine lokale Arbeit oder glaubt, eine
 * Anzeige sei offline, die weiter online steht.
 */
export function LoeschDialog({
  anzeigen, laeuft, aufAbbrechen, aufLoeschen,
}: {
  anzeigen: BestandsAnzeige[];
  laeuft: boolean;
  aufAbbrechen: () => void;
  aufLoeschen: () => void;
}) {
  const mehrere = anzeigen.length > 1;
  const bilder = anzeigen.reduce((summe, a) => summe + a.bilder, 0);

  return (
    <div className="fixed inset-0 z-50 flex items-end justify-center bg-black/40 p-4 sm:items-center">
      <div role="dialog" aria-modal="true" aria-labelledby="loeschen-titel" className="dialog">
        <div className="mb-3 flex items-start gap-3">
          <Trash2 className="mt-0.5 h-5 w-5 flex-shrink-0" style={{ color: 'var(--hinweis-fehler-text)' }} aria-hidden />
          <div className="min-w-0">
            <h2 id="loeschen-titel" className="font-semibold text-stark">
              {mehrere ? `${anzeigen.length} Anzeigen löschen?` : 'Anzeige löschen?'}
            </h2>
            <p className="mt-1 text-sm text-normal">
              {mehrere ? 'Diese Anzeigen werden' : 'Diese Anzeige wird'} samt{' '}
              {bilder === 1 ? 'einem Bild' : `${bilder} Bildern`} von der Platte entfernt.
            </p>
          </div>
        </div>

        <ul
          className="mb-3 max-h-48 overflow-y-auto rounded-xl p-2 text-sm"
          style={{ background: 'var(--canvas)', border: '1px solid var(--karte-rand)' }}
        >
          {anzeigen.map(a => (
            <li key={a.datei} className="truncate py-0.5 text-stark">{a.titel}</li>
          ))}
        </ul>

        <p role="alert" className="hinweis hinweis-warn mb-4 flex items-start gap-2">
          <AlertTriangle className="mt-0.5 h-4 w-4 flex-shrink-0" aria-hidden />
          <span>
            <span className="font-medium">Nur auf diesem Rechner, nicht auf kleinanzeigen.de.</span>{' '}
            {mehrere ? 'Anzeigen, die dort online stehen, bleiben online' : 'Steht die Anzeige dort online, bleibt sie online'}
            {' '}– nur die lokale Kopie ist weg. Rückgängig machen lässt sich das nicht;
            ein erneuter Download holt {mehrere ? 'sie' : 'sie'} zurück, sofern
            {mehrere ? ' sie noch' : ' sie noch'} auf der Plattform {mehrere ? 'stehen' : 'steht'}.
          </span>
        </p>

        <div className="flex flex-col-reverse gap-2 sm:flex-row sm:justify-end">
          <button type="button" onClick={aufAbbrechen} disabled={laeuft} className="btn-ghost">
            Abbrechen
          </button>
          <button
            type="button"
            onClick={aufLoeschen}
            disabled={laeuft}
            className="btn-primaer disabled:opacity-60"
            style={{ background: 'var(--status-fehler)', color: '#fff' }}
          >
            <Trash2 className="h-4 w-4" aria-hidden />
            {laeuft ? 'Löscht …' : 'Lokal löschen'}
          </button>
        </div>
      </div>
    </div>
  );
}
