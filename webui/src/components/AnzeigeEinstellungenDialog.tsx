// SPDX-FileCopyrightText: © Anzeigen-Studio contributors
// SPDX-License-Identifier: AGPL-3.0-or-later
//
// Studio-Einstellungen einer einzelnen Anzeige (2026-09-07).
//
// „Anzeige bearbeiten" zeigt nur, was von kleinanzeigen.de kommt. Was das
// Studio selbst steuert - ob die Anzeige mitgeführt wird und in welchem Abstand
// sie zur Neueinstellung fällig wird - liegt hinter dem Zahnrad. Die Werte
// stehen weiter in der Anzeigendatei (`active`, `republication_interval`, beide
// in `aenderbar`) und werden über die normale Speichern-Leiste des Editors
// geschrieben; dieser Dialog reicht die Änderung nur durch.

import { Settings, X } from 'lucide-react';

interface Props {
  aktiv: boolean;
  /** Tage bis zur Neueinstellung, oder null wenn die Datei nichts setzt. */
  intervall: number | null;
  bearbeitbar: boolean;
  aufAenderung: (feld: 'active' | 'republication_interval', wert: unknown) => void;
  aufSchliessen: () => void;
}

export function AnzeigeEinstellungenDialog({
  aktiv, intervall, bearbeitbar, aufAenderung, aufSchliessen,
}: Props) {
  return (
    <div
      className="fixed inset-0 z-50 flex items-end justify-center bg-black/40 p-4 sm:items-center"
      onMouseDown={ereignis => { if (ereignis.target === ereignis.currentTarget) aufSchliessen(); }}
    >
      <div role="dialog" aria-modal="true" aria-labelledby="anzeige-einst-titel" className="dialog">
        <div className="mb-3 flex items-start gap-3">
          <Settings className="mt-0.5 h-5 w-5 flex-shrink-0 text-primary-custom" aria-hidden />
          <div className="min-w-0 flex-1">
            <h2 id="anzeige-einst-titel" className="font-semibold text-stark">
              Studio-Einstellungen dieser Anzeige
            </h2>
            <p className="mt-1 text-sm text-normal">
              Gilt nur für diese Anzeige und wird mit „Speichern" übernommen. Diese Angaben
              stehen nicht auf kleinanzeigen.de – sie steuern, wie das Studio die Anzeige führt.
            </p>
          </div>
          <button
            type="button"
            onClick={aufSchliessen}
            aria-label="Schließen"
            className="btn-icon flex-shrink-0"
          >
            <X className="h-4 w-4" aria-hidden />
          </button>
        </div>

        <div className="space-y-4">
          <label className="flex items-start gap-2 text-sm text-normal">
            <input
              type="checkbox"
              checked={aktiv}
              disabled={!bearbeitbar}
              onChange={e => aufAenderung('active', e.target.checked)}
              className="mt-0.5 h-4 w-4 flex-shrink-0"
            />
            <span>
              Aktiv
              <span className="mt-0.5 block text-xs text-leise">
                Ausgeschaltet lässt das Studio die Anzeige bei Sammelläufen aus.
              </span>
            </span>
          </label>

          <label className="block sm:max-w-xs">
            <span className="beschriftung">Abstand zur Neueinstellung (Tage)</span>
            <input
              type="number"
              step="1"
              min="1"
              value={intervall ?? ''}
              readOnly={!bearbeitbar}
              onChange={e => {
                const roh = e.target.value.trim();
                if (roh === '') {
                  aufAenderung('republication_interval', null);
                  return;
                }
                const zahl = Number.parseInt(roh, 10);
                aufAenderung('republication_interval', Number.isFinite(zahl) ? zahl : null);
              }}
              className="feld mt-1"
            />
            <span className="mt-1 block text-xs text-leise">
              Leer lassen nutzt den Standard aus{' '}
              <a href="#einstellungen/anzeigen" className="font-medium underline">
                Einstellungen › Anzeigen
              </a>.
            </span>
          </label>
        </div>

        <div className="mt-5 flex justify-end">
          <button type="button" onClick={aufSchliessen} className="btn-ghost">
            Schließen
          </button>
        </div>
      </div>
    </div>
  );
}
