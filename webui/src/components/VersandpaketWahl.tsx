// SPDX-FileCopyrightText: © Anzeigen-Studio contributors
// SPDX-License-Identifier: AGPL-3.0-or-later
//
// Versandpakete auswählen (AP-2.7).
//
// Mehrfachauswahl, weil die Anzeigendatei eine Liste führt: Kleinanzeigen
// lässt mehrere Pakete derselben Größe zu, und der Käufer wählt eines davon.
//
// „Derselben Größe" ist dabei keine Beschreibung, sondern eine Grenze. Der
// Upstream wirft beim Veröffentlichen `You can only specify shipping options
// for one package size!` (publishing_form.py) - und zwar erst im geöffneten
// Versanddialog, mit halb ausgefülltem Formular. Weder `AdPartial` noch `Ad`
// prüfen die Regel vorher. Sie wird deshalb hier durchgesetzt, wo die Liste
// entsteht: Ein Paket aus einer anderen Größe ersetzt die bisherige Auswahl,
// statt sich dazuzulegen.
//
// Die Preise stehen dabei, weil sie hier die eigentliche Entscheidungshilfe
// sind. Genau an ihnen hängt auch der Fehler, den die Verlustanalyse gefunden
// hat: Wer eigene Versandkosten gesetzt hat, findet hier keinen passenden
// Eintrag - und sieht am Preis sofort, warum.

import { useEffect, useState } from 'react';
import { AlertTriangle } from 'lucide-react';
import { api } from '../services/api';
import type { Versandpaket } from '../types';

const GROESSEN = ['Klein', 'Mittel', 'Groß'];

interface Props {
  gewaehlt: string[];
  versandkosten: number | null;
  direktKaufen: boolean;
  aufAenderung: (pakete: string[]) => void;
}

function preisText(preis: number | null): string {
  if (preis === null) return '';
  return preis.toLocaleString('de-DE', { style: 'currency', currency: 'EUR' });
}

export function VersandpaketWahl({ gewaehlt, versandkosten, direktKaufen, aufAenderung }: Props) {
  const [pakete, setPakete] = useState<Versandpaket[]>([]);
  const [geladen, setGeladen] = useState(false);

  useEffect(() => {
    void (async () => {
      try {
        setPakete(await api.katalog.versandpakete());
      } catch {
        setPakete([]);
      } finally {
        setGeladen(true);
      }
    })();
  }, []);

  /** Die Größengruppe eines Pakets, oder null wenn die Liste es nicht kennt. */
  const gruppeVon = (wert: string): string | null =>
    pakete.find(p => p.wert === wert)?.groesse ?? null;

  const umschalten = (wert: string) => {
    if (gewaehlt.includes(wert)) {
      aufAenderung(gewaehlt.filter(p => p !== wert));
      return;
    }
    // Unbekannte Namen bleiben stehen: Über sie lässt sich nichts sagen, und
    // heruntergeladene Anzeigen tragen mitunter welche. Sie stillschweigend zu
    // löschen wäre der schlechtere von beiden Fehlern.
    const gruppe = gruppeVon(wert);
    const behalten = gewaehlt.filter(p => {
      const andere = gruppeVon(p);
      return andere === null || andere === gruppe;
    });
    aufAenderung([...behalten, wert]);
  };

  // Aus der Datei kann sehr wohl eine gemischte Auswahl kommen - von einem
  // Download oder aus einer von Hand bearbeiteten YAML. Verhindern lässt sich
  // das hier nicht mehr, benennen schon.
  const gewaehlteGruppen = new Set(
    gewaehlt.map(gruppeVon).filter((g): g is string => g !== null),
  );
  const gemischt = gewaehlteGruppen.size > 1;

  const ohnePreise = geladen && pakete.length > 0 && pakete.every(p => p.preis === null);

  return (
    <fieldset className="rounded border border-gray-200 p-3">
      <legend className="px-1 text-sm font-medium text-gray-700">Versandpakete</legend>

      {!geladen && <p className="text-sm text-gray-500">Wird geladen …</p>}

      {geladen && pakete.length === 0 && (
        <p className="text-sm text-gray-600">Die Liste ist gerade nicht verfügbar.</p>
      )}

      {GROESSEN.map(groesse => {
        const gruppe = pakete.filter(p => p.groesse === groesse);
        if (gruppe.length === 0) return null;
        return (
          <div key={groesse} className="mb-3 last:mb-0">
            <p className="mb-1 text-xs font-medium text-gray-500">{groesse}</p>
            <div className="grid gap-1 sm:grid-cols-2">
              {gruppe.map(p => (
                <label key={p.wert} className="flex items-center gap-2 text-sm">
                  <input
                    type="checkbox"
                    checked={gewaehlt.includes(p.wert)}
                    onChange={() => umschalten(p.wert)}
                    className="h-4 w-4 flex-shrink-0"
                  />
                  <span className="min-w-0 flex-1 truncate text-gray-900">{p.wert}</span>
                  <span className="flex-shrink-0 text-gray-600">{preisText(p.preis)}</span>
                </label>
              ))}
            </div>
          </div>
        );
      })}

      {ohnePreise && (
        <p className="mt-2 text-xs text-gray-500">
          Preise gerade nicht abrufbar – die Auswahl funktioniert trotzdem.
        </p>
      )}

      {gemischt && (
        <p className="mt-2 flex items-start gap-1.5 text-xs text-amber-900">
          <AlertTriangle className="mt-0.5 h-3.5 w-3.5 flex-shrink-0" aria-hidden />
          <span>
            Die Auswahl nennt Pakete aus mehreren Größen ({[...gewaehlteGruppen].join(', ')}).
            Kleinanzeigen lässt nur eine Größe zu – beim Veröffentlichen bricht der Lauf im
            Versanddialog ab. Ein Klick auf ein Paket räumt die übrigen Größen weg.
          </span>
        </p>
      )}

      {gewaehlt.length === 0 && versandkosten !== null && (
        <p className="mt-2 flex items-start gap-1.5 text-xs text-amber-900">
          <AlertTriangle className="mt-0.5 h-3.5 w-3.5 flex-shrink-0" aria-hidden />
          <span>
            Es sind {preisText(versandkosten)} Versandkosten gesetzt, aber kein Paket gewählt.
            Der Bot kann im Formular nur vordefinierte Pakete auswählen – so lässt sich die
            Anzeige nicht hochladen.
          </span>
        </p>
      )}

      {gewaehlt.length === 0 && direktKaufen && (
        <p className="mt-2 flex items-start gap-1.5 text-xs text-amber-900">
          <AlertTriangle className="mt-0.5 h-3.5 w-3.5 flex-shrink-0" aria-hidden />
          <span>„Direkt kaufen" verlangt beim Veröffentlichen ein Paket.</span>
        </p>
      )}
    </fieldset>
  );
}
