// SPDX-FileCopyrightText: © Anzeigen-Studio contributors
// SPDX-License-Identifier: AGPL-3.0-or-later
//
// Versandpakete auswählen (AP-2.7, Optik AP-2.23).
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
// „Direkt kaufen" steht seit AP-2.23 in derselben Karte: Der Schalter verlangt
// beim Veröffentlichen ein Paket, gehört also sichtbar zur selben Entscheidung.
// Die Fachlogik bleibt beim Editor - hier wird nur der bestehende Wert
// angezeigt und über `aufDirektKaufen` zurückgemeldet.
//
// Die Preise stehen dabei, weil sie hier die eigentliche Entscheidungshilfe
// sind. Genau an ihnen hängt auch der Fehler, den die Verlustanalyse gefunden
// hat: Wer eigene Versandkosten gesetzt hat, findet hier keinen passenden
// Eintrag - und sieht am Preis sofort, warum.
//
// Woher die Preise kommen (AP-2.22): jeder Preis wird bei jedem Öffnen live von
// der öffentlichen Preisliste der Plattform geholt - `daten._preise()` ruft
// `gateway.kleinanzeigen.de/postad/api/v1/shipping-options` ab, `versandpakete()`
// hängt den Betrag an den Paketnamen des Bots, die Katalog-API reicht ihn als
// `preis` durch. In dieser Datei steht kein einziger Preiswert. Günstige
// Hermes-Beträge (0,99 / 1,99 / 2,99 €) sind Aktionspreise der Plattform
// (`oldPriceInEuroCent`, `fromPrice`) - deshalb gerade nicht festschreiben,
// sondern live zeigen. Das kurze Label unten sagt das dem Nutzer.

import { useEffect, useState } from 'react';
import { AlertTriangle, Check } from 'lucide-react';
import { api } from '../services/api';
import type { Versandpaket } from '../types';

const GROESSEN = ['Klein', 'Mittel', 'Groß'];

interface Props {
  gewaehlt: string[];
  versandkosten: number | null;
  direktKaufen: boolean;
  aufAenderung: (pakete: string[]) => void;
  /** Optional: wenn gesetzt, steht der „Direkt kaufen"-Schalter in dieser Karte. */
  aufDirektKaufen?: (wert: boolean) => void;
}

function preisText(preis: number | null): string {
  if (preis === null) return '';
  return preis.toLocaleString('de-DE', { style: 'currency', currency: 'EUR' });
}

export function VersandpaketWahl({
  gewaehlt,
  versandkosten,
  direktKaufen,
  aufAenderung,
  aufDirektKaufen,
}: Props) {
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
  const mitPreisen = geladen && pakete.some(p => p.preis !== null);

  const gruppen = GROESSEN.map(groesse => ({
    groesse,
    liste: pakete.filter(p => p.groesse === groesse),
  })).filter(g => g.liste.length > 0);

  return (
    <fieldset className="karte space-y-3 p-4">
      <legend className="px-1 text-sm font-medium text-normal">Versandpakete</legend>

      {aufDirektKaufen && (
        <label className="flex items-center gap-2 text-sm text-normal">
          <input
            type="checkbox"
            checked={direktKaufen}
            onChange={e => aufDirektKaufen(e.target.checked)}
            className="h-4 w-4 flex-shrink-0"
          />
          <span>Direkt kaufen</span>
        </label>
      )}

      <div
        className="space-y-3"
        style={aufDirektKaufen ? { borderTop: '1px solid var(--karte-rand)', paddingTop: '0.75rem' } : undefined}
      >
        {!geladen && <p className="text-sm text-leise">Wird geladen …</p>}

        {geladen && pakete.length === 0 && (
          <p className="text-sm text-leise">Die Liste ist gerade nicht verfügbar.</p>
        )}

        {gruppen.map(({ groesse, liste }) => (
          <div key={groesse}>
            <p className="mb-1.5 text-xs font-medium text-leise">{groesse}</p>
            <div className="flex flex-wrap gap-1.5">
              {liste.map(p => {
                const aktiv = gewaehlt.includes(p.wert);
                return (
                  <button
                    key={p.wert}
                    type="button"
                    aria-pressed={aktiv}
                    onClick={() => umschalten(p.wert)}
                    className={`vp-chip ${aktiv ? 'vp-chip-aktiv' : ''}`}
                  >
                    {aktiv && <Check className="h-3.5 w-3.5 flex-shrink-0" aria-hidden />}
                    <span>{p.wert}</span>
                    {p.preis !== null && (
                      <span className="vp-chip-preis">{preisText(p.preis)}</span>
                    )}
                  </button>
                );
              })}
            </div>
          </div>
        ))}
      </div>

      {ohnePreise && (
        <p className="text-xs text-leise">
          Preise gerade nicht abrufbar – die Auswahl funktioniert trotzdem.
        </p>
      )}

      {mitPreisen && (
        <p className="text-xs text-leise">
          Preise live von Kleinanzeigen; günstige Hermes-Preise sind Aktionen.
        </p>
      )}

      {gemischt && (
        <p className="flex items-start gap-1.5 text-xs text-amber-900">
          <AlertTriangle className="mt-0.5 h-3.5 w-3.5 flex-shrink-0" aria-hidden />
          <span>
            Die Auswahl nennt Pakete aus mehreren Größen ({[...gewaehlteGruppen].join(', ')}).
            Kleinanzeigen lässt nur eine Größe zu – beim Veröffentlichen bricht der Lauf im
            Versanddialog ab. Ein Klick auf ein Paket räumt die übrigen Größen weg.
          </span>
        </p>
      )}

      {gewaehlt.length === 0 && versandkosten !== null && (
        <p className="flex items-start gap-1.5 text-xs text-amber-900">
          <AlertTriangle className="mt-0.5 h-3.5 w-3.5 flex-shrink-0" aria-hidden />
          <span>
            Es sind {preisText(versandkosten)} Versandkosten gesetzt, aber kein Paket gewählt.
            Der Bot kann im Formular nur vordefinierte Pakete auswählen – so lässt sich die
            Anzeige nicht hochladen.
          </span>
        </p>
      )}

      {gewaehlt.length === 0 && direktKaufen && (
        <p className="flex items-start gap-1.5 text-xs text-amber-900">
          <AlertTriangle className="mt-0.5 h-3.5 w-3.5 flex-shrink-0" aria-hidden />
          <span>„Direkt kaufen" verlangt beim Veröffentlichen ein Paket.</span>
        </p>
      )}
    </fieldset>
  );
}
