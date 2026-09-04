// SPDX-FileCopyrightText: © Anzeigen-Studio contributors
// SPDX-License-Identifier: AGPL-3.0-or-later
//
// Rückfrage vor dem lokalen Löschen und optionalen Plattform-Löschen
// (AP-2.20/AP-3.13).
//
// Eigene Datei, weil ihn zwei Stellen brauchen: die Sammelaktion in der Liste
// und das Einzellöschen im Editor. Der Editor liegt seinerseits in der Liste,
// ein Import zwischen beiden wäre ein Zirkel.

import { AlertTriangle, Trash2 } from 'lucide-react';
import type { BestandsAnzeige } from '../types';

/**
 * Rückfrage vor dem Löschen (AP-2.20).
 *
 * Der Dialog muss drei Dinge leisten, und das zweite ist das wichtigere:
 * Er zeigt, **welche** Anzeigen gehen, und er sagt unmissverständlich, dass
 * auf kleinanzeigen.de standardmäßig nichts passiert. Nur bei einer einzelnen
 * eigenen Anzeige kann die Plattform-Löschung ausdrücklich dazugeschaltet
 * werden. So bleibt „Löschen" ein einziger, nachvollziehbarer Vorgang.
 */
export function LoeschDialog({
  anzeigen, laeuft, aufAbbrechen, aufLoeschen,
  onlineLoeschbar = false, onlineGewaehlt = false,
  aufOnlineGewaehlt, onlineGesperrt = false,
}: {
  anzeigen: BestandsAnzeige[];
  laeuft: boolean;
  aufAbbrechen: () => void;
  aufLoeschen: () => void;
  /** Nur bei einer eigenen Anzeige mit bekannter Plattform-ID. */
  onlineLoeschbar?: boolean;
  onlineGewaehlt?: boolean;
  aufOnlineGewaehlt?: (wert: boolean) => void;
  /** Ungespeicherte Eingaben dürfen nicht als Plattform-Löschung eingereiht werden. */
  onlineGesperrt?: boolean;
}) {
  const mehrere = anzeigen.length > 1;
  const bilder = anzeigen.reduce((summe, a) => summe + a.bilder, 0);
  const loeschtAuchOnline = onlineLoeschbar && onlineGewaehlt && !mehrere;

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
            <li key={a.datei} className="flex items-baseline justify-between gap-3 py-0.5 text-stark">
              <span className="min-w-0 truncate">{a.titel}</span>
              {onlineLoeschbar && a.id !== null && (
                <span className="flex-shrink-0 text-xs text-leise">#{a.id}</span>
              )}
            </li>
          ))}
        </ul>

        <p role="alert" className="hinweis hinweis-warn mb-3 flex items-start gap-2">
          <AlertTriangle className="mt-0.5 h-4 w-4 flex-shrink-0" aria-hidden />
          {loeschtAuchOnline ? (
            <span>
              <span className="font-medium">Lokal und auf kleinanzeigen.de löschen.</span>{' '}
              Die lokale Kopie wird entfernt und ein gezielter Lauf mit der Anzeigennummer
              eingereiht. Das lässt sich nicht rückgängig machen; prüfe den öffentlichen Link
              danach mit dem Mini-Skript.
            </span>
          ) : (
            <span>
              <span className="font-medium">Nur auf diesem Rechner, nicht auf kleinanzeigen.de.</span>{' '}
              {mehrere ? 'Anzeigen, die dort online stehen, bleiben online' : 'Steht die Anzeige dort online, bleibt sie online'}
              {' '}– nur die lokale Kopie ist weg. Rückgängig machen lässt sich das nicht;
              ein erneuter Download holt sie zurück, sofern sie noch auf der Plattform steht.
            </span>
          )}
        </p>

        {onlineLoeschbar && !mehrere && (
          <div className="mb-4">
            <label className="flex items-start gap-2 text-sm text-normal">
              <input
                type="checkbox"
                checked={onlineGewaehlt}
                disabled={laeuft || onlineGesperrt}
                onChange={ereignis => aufOnlineGewaehlt?.(ereignis.target.checked)}
                className="mt-0.5 h-4 w-4 flex-shrink-0"
              />
              <span>Zusätzlich auf kleinanzeigen.de löschen</span>
            </label>
            {onlineGesperrt && (
              <p className="mt-1 pl-6 text-xs text-leise">
                Erst speichern, damit genau der gespeicherte Stand mit seiner Anzeigennummer
                gelöscht werden kann.
              </p>
            )}
          </div>
        )}

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
            {laeuft ? 'Löscht …' : mehrere ? 'Lokal löschen' : 'Löschen'}
          </button>
        </div>
      </div>
    </div>
  );
}
