// SPDX-FileCopyrightText: © Anzeigen-Studio contributors
// SPDX-License-Identifier: AGPL-3.0-or-later
//
// Versandart und Versandpaket auswählen (AP-2.7, AP-2.23, AP-2.40).
// UI-Anpassung 2026-09-07: Optionsnamen ohne Unterstrich anzeigen; Chip-Inhalt
//   vertikal zentriert (siehe `.vp-chip` in index.css).
//
// Die Oberfläche führt bewusst in zwei Schritten durch die Auswahl: zuerst
// eine Paketgröße oder Abholung, danach die konkreten Optionen dieser Größe.
// So ist vor dem Veröffentlichen sichtbar, welche Angabe noch fehlt.
// Individueller Versand ist kein eigener Weg mehr; die Plattform unterstützt
// dafür nur noch die vorgegebenen Paketoptionen.

import { useEffect, useState } from 'react';
import { AlertTriangle } from 'lucide-react';
import { api } from '../services/api';
import type { Versandpaket } from '../types';

const GROESSEN = ['Klein', 'Mittel', 'Groß'] as const;
type Groesse = typeof GROESSEN[number];

const VERSANDAUSWAHLEN: Array<{ wert: Groesse | 'PICKUP'; label: string }> = [
  { wert: 'Klein', label: 'Klein' },
  { wert: 'Mittel', label: 'Mittel' },
  { wert: 'Groß', label: 'Groß' },
  { wert: 'PICKUP', label: 'Abholung' },
];

const GROESSEN_SPEICHER_PREFIX = 'anzeigen-studio:versand-groesse:';

function gespeicherteGroesse(schluessel?: string): Groesse | null {
  if (!schluessel || typeof window === 'undefined') return null;
  try {
    const wert = window.localStorage.getItem(
      GROESSEN_SPEICHER_PREFIX + encodeURIComponent(schluessel),
    );
    return wert && GROESSEN.includes(wert as Groesse) ? wert as Groesse : null;
  } catch {
    return null;
  }
}

function groesseSpeichern(schluessel: string | undefined, groesse: Groesse | null): void {
  if (!schluessel || typeof window === 'undefined') return;
  try {
    const key = GROESSEN_SPEICHER_PREFIX + encodeURIComponent(schluessel);
    if (groesse === null) window.localStorage.removeItem(key);
    else window.localStorage.setItem(key, groesse);
  } catch {
    // Private Fenster oder volle Speicher dürfen die Auswahl nicht brechen.
  }
}

function AnbieterLogo({ anbieter }: { anbieter: string }) {
  const name = anbieter.trim() || 'Versand';
  return (
    <span className="vp-anbieter-logo" data-anbieter={name} aria-hidden="true">
      {name}
    </span>
  );
}

interface Props {
  gewaehlt: string[];
  versandkosten: number | null;
  direktKaufen: boolean;
  versandart?: string;
  aufAenderung: (pakete: string[]) => void;
  bearbeitbar?: boolean;
  /** Der Schalter gehört fachlich zur Versandentscheidung. */
  aufDirektKaufen?: (wert: boolean) => void;
  aufVersandart?: (wert: 'SHIPPING' | 'PICKUP') => void;
  /** Meldet dem Editor, ob die gewählten Optionen aus dem Katalog stammen. */
  aufGueltigkeit?: (wert: boolean) => void;
  /** Stabiler Schlüssel der Anzeige für die reine Zwischenwahl der Paketgröße. */
  speicherSchluessel?: string;
}

function preisText(preis: number | null): string {
  if (preis === null) return '';
  return preis.toLocaleString('de-DE', { style: 'currency', currency: 'EUR' });
}

/**
 * Anzeigename einer Versandoption ohne Unterstrich (`Hermes_Päckchen` →
 * `Hermes Päckchen`). Der rohe Katalogwert (`paket.wert`) bleibt überall sonst
 * unverändert - er ist der Schlüssel gegen die Bot-Auswahl.
 */
function anzeigeName(wert: string): string {
  return wert.replace(/_/g, ' ');
}

export function VersandpaketWahl({
  gewaehlt,
  versandkosten,
  direktKaufen,
  versandart = 'NOT_APPLICABLE',
  aufAenderung,
  bearbeitbar = true,
  aufDirektKaufen,
  aufVersandart,
  aufGueltigkeit,
  speicherSchluessel,
}: Props) {
  const [pakete, setPakete] = useState<Versandpaket[]>([]);
  const [geladen, setGeladen] = useState(false);
  const [versandartLokal, setVersandartLokal] = useState(versandart);
  const [groesseLokal, setGroesseLokal] = useState<Groesse | null>(
    () => gespeicherteGroesse(speicherSchluessel),
  );

  useEffect(() => {
    setVersandartLokal(versandart);
    if (versandart !== 'SHIPPING') setGroesseLokal(null);
  }, [versandart]);

  useEffect(() => {
    setGroesseLokal(gespeicherteGroesse(speicherSchluessel));
  }, [speicherSchluessel]);

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

  const ausgewaehlteGroesse = gewaehlt
    .map(gruppeVon)
    .find((groesse): groesse is Groesse => GROESSEN.includes(groesse as Groesse))
    ?? null;
  const aktiveGroesse = ausgewaehlteGroesse ?? groesseLokal;
  // Lokal sofort umschalten, damit die Detailstufe nicht auf den nächsten
  // Parent-Render warten muss. Der Effekt oben übernimmt spätere Änderungen
  // aus der gespeicherten Anzeige.
  const aktuelleVersandart = versandartLokal;
  const bekanntePakete = gewaehlt.filter(paket => gruppeVon(paket) !== null);
  const versandAuswahlGueltig = aktuelleVersandart !== 'SHIPPING'
    || (
      geladen
      && bekanntePakete.length > 0
      && bekanntePakete.length === gewaehlt.length
      && new Set(bekanntePakete.map(gruppeVon)).size === 1
    );

  useEffect(() => {
    aufGueltigkeit?.(versandAuswahlGueltig);
  }, [aufGueltigkeit, versandAuswahlGueltig]);

  const versandartWaehlen = (wert: 'SHIPPING' | 'PICKUP') => {
    setVersandartLokal(wert);
    aufVersandart?.(wert);
  };

  const groesseWaehlen = (groesse: Groesse) => {
    setGroesseLokal(groesse);
    groesseSpeichern(speicherSchluessel, groesse);
    versandartWaehlen('SHIPPING');

    // Eine Größe bleibt aktiv; bereits gewählte Optionen derselben Größe
    // bleiben erhalten. Unbekannte Werte werden nicht stillschweigend gelöscht,
    // damit ein manueller YAML-Eintrag nicht durch einen UI-Klick verschwindet.
    const behalten = gewaehlt.filter(p => {
      const andere = gruppeVon(p);
      return andere === null || andere === groesse;
    });
    aufAenderung(behalten);
  };

  const abholungWaehlen = () => {
    setGroesseLokal(null);
    groesseSpeichern(speicherSchluessel, null);
    versandartWaehlen('PICKUP');
    aufDirektKaufen?.(false);
    aufAenderung([]);
  };

  const umschalten = (wert: string) => {
    if (gewaehlt.includes(wert)) {
      aufAenderung(gewaehlt.filter(p => p !== wert));
      return;
    }
    const gruppe = gruppeVon(wert);
    const behalten = gewaehlt.filter(p => {
      const andere = gruppeVon(p);
      return andere === null || andere === gruppe;
    });
    aufAenderung([...behalten, wert]);
  };

  const gruppen = GROESSEN.map(groesse => ({
    groesse,
    liste: pakete.filter(p => p.groesse === groesse),
  }));
  const detailListe = aktiveGroesse
    ? gruppen.find(g => g.groesse === aktiveGroesse)?.liste ?? []
    : [];
  const pickup = aktuelleVersandart === 'PICKUP';
  const versandOhneAuswahl = aktuelleVersandart === 'SHIPPING' && gewaehlt.length === 0;
  const ohnePreise = geladen && pakete.length > 0 && pakete.every(p => p.preis === null);
  const mitPreisen = geladen && pakete.some(p => p.preis !== null);

  return (
    <section className="space-y-3" aria-label="Versand">
      <h3 className="mb-1 text-sm font-semibold text-stark">Versand</h3>

      <div className="flex flex-wrap gap-2" role="group" aria-label="Versandart wählen">
        {VERSANDAUSWAHLEN.map(auswahl => {
          const aktiv = auswahl.wert === 'PICKUP'
            ? pickup
            : aktuelleVersandart === 'SHIPPING' && aktiveGroesse === auswahl.wert;
          return (
            <button
              key={auswahl.wert}
              type="button"
              aria-pressed={aktiv}
              disabled={!bearbeitbar}
              onClick={() => auswahl.wert === 'PICKUP'
                ? abholungWaehlen()
                : groesseWaehlen(auswahl.wert)}
              className={`vp-chip ${aktiv ? 'vp-chip-aktiv' : ''}`}
            >
              <span>{auswahl.label}</span>
            </button>
          );
        })}
      </div>

      {aufDirektKaufen && (
        <div className="border-t pt-3" style={{ borderColor: 'var(--karte-rand)' }}>
          <label className="flex items-start gap-2 text-sm text-normal">
            <input
              type="checkbox"
              checked={direktKaufen}
              disabled={!bearbeitbar || pickup}
              onChange={e => aufDirektKaufen(e.target.checked)}
              className="mt-0.5 h-4 w-4 flex-shrink-0"
            />
            <span>
              Direkt kaufen
              {pickup && <span className="ml-1 text-xs text-leise">(bei Abholung nicht verfügbar)</span>}
            </span>
          </label>
        </div>
      )}

      {aktuelleVersandart === 'SHIPPING' && aktiveGroesse && (
        <div
          className="space-y-2 rounded-xl border p-3"
          style={{ borderColor: 'var(--karte-rand)', background: 'var(--canvas)' }}
        >
          <p className="text-sm font-medium text-stark">
            Optionen für {aktiveGroesse}
          </p>
          {!geladen && <p className="text-sm text-leise">Wird geladen …</p>}
          {geladen && detailListe.length === 0 && (
            <p className="text-sm text-leise">Für diese Größe sind gerade keine Optionen verfügbar.</p>
          )}
          {detailListe.length > 0 && (
            <div className="flex flex-wrap gap-1.5">
              {detailListe.map(paket => {
                const aktiv = gewaehlt.includes(paket.wert);
                return (
                  <button
                    key={paket.wert}
                    type="button"
                    aria-pressed={aktiv}
                    aria-label={anzeigeName(paket.wert)}
                    disabled={!bearbeitbar}
                    onClick={() => umschalten(paket.wert)}
                    className={`vp-chip ${aktiv ? 'vp-chip-aktiv' : ''}`}
                  >
                    <span>{anzeigeName(paket.wert)}</span>
                    {paket.preis !== null && (
                      <span className="vp-chip-preis">{preisText(paket.preis)}</span>
                    )}
                    <AnbieterLogo anbieter={paket.anbieter} />
                  </button>
                );
              })}
            </div>
          )}
        </div>
      )}

      {aktuelleVersandart === 'SHIPPING' && !aktiveGroesse && (
        <p className="flex items-start gap-1.5 text-xs text-amber-900">
          <AlertTriangle className="mt-0.5 h-3.5 w-3.5 flex-shrink-0" aria-hidden />
          <span>Wähle zuerst Klein, Mittel oder Groß und danach eine konkrete Versandoption.</span>
        </p>
      )}

      {versandOhneAuswahl && aktiveGroesse && (
        <p className="flex items-start gap-1.5 text-xs text-amber-900">
          <AlertTriangle className="mt-0.5 h-3.5 w-3.5 flex-shrink-0" aria-hidden />
          <span>Wähle jetzt eine Option für {aktiveGroesse}, bevor du die Anzeige online stellst.</span>
        </p>
      )}

      {aktuelleVersandart === 'SHIPPING' && geladen && gewaehlt.length > 0
        && bekanntePakete.length !== gewaehlt.length && (
        <p className="flex items-start gap-1.5 text-xs text-amber-900">
          <AlertTriangle className="mt-0.5 h-3.5 w-3.5 flex-shrink-0" aria-hidden />
          <span>Mindestens eine gespeicherte Versandoption ist nicht mehr verfügbar. Bitte neu auswählen.</span>
        </p>
      )}

      {aktuelleVersandart === 'SHIPPING' && gewaehlt.length === 0 && versandkosten !== null && (
        <p className="flex items-start gap-1.5 text-xs text-amber-900">
          <AlertTriangle className="mt-0.5 h-3.5 w-3.5 flex-shrink-0" aria-hidden />
          <span>
            Es sind {preisText(versandkosten)} Versandkosten gesetzt, aber noch keine vorgegebene
            Option gewählt.
          </span>
        </p>
      )}

      {aktuelleVersandart === 'SHIPPING' && gewaehlt.length === 0 && direktKaufen && (
        <p className="flex items-start gap-1.5 text-xs text-amber-900">
          <AlertTriangle className="mt-0.5 h-3.5 w-3.5 flex-shrink-0" aria-hidden />
          <span>„Direkt kaufen“ verlangt beim Veröffentlichen eine konkrete Versandoption.</span>
        </p>
      )}

      {geladen && pakete.length === 0 && aktuelleVersandart === 'SHIPPING' && (
        <p className="text-sm text-leise">Die Versandoptionen sind gerade nicht verfügbar.</p>
      )}

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
    </section>
  );
}
