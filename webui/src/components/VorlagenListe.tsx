// SPDX-FileCopyrightText: © Anzeigen-Studio contributors
// SPDX-License-Identifier: AGPL-3.0-or-later
//
// Die Vorlagenliste (AP-3.3).
//
// Bewusst eine eigene Liste über den Anzeigen und nicht ein Filter in ihnen.
// Eine Vorlage ist keine Anzeige: Sie hat keine Anzeigennummer, wird nie
// fällig, geht nie online. Sie in dieselbe Tabelle zu setzen und per Filter
// zu trennen, würde genau die Verwechslung nahelegen, gegen die das ganze
// Modul gebaut ist.
//
// Der Abschnitt verschwindet vollständig, solange es keine Vorlagen gibt —
// eine leere Überschrift erklärt niemandem, wofür sie da wäre.

import { useCallback, useEffect, useState } from 'react';
import { Files, Plus, Trash2 } from 'lucide-react';
import { api, ApiFehler } from '../services/api';
import type { Vorlage } from '../types';

export function VorlagenListe({
  profil, aufAngewendet,
}: {
  profil: string;
  /** Die neue Anzeige wurde angelegt - die Liste dahinter muss neu gelesen werden. */
  aufAngewendet: (datei: string) => void;
}) {
  const [vorlagen, setVorlagen] = useState<Vorlage[]>([]);
  const [fehler, setFehler] = useState<string | null>(null);
  const [beschaeftigt, setBeschaeftigt] = useState<string | null>(null);
  const [fragtLoeschen, setFragtLoeschen] = useState<Vorlage | null>(null);

  const laden = useCallback(async () => {
    try {
      setVorlagen(await api.bestand.vorlagen(profil));
    } catch (ursache) {
      setFehler(ursache instanceof ApiFehler ? ursache.message : 'Unbekannter Fehler.');
    }
  }, [profil]);

  useEffect(() => {
    void laden();
  }, [laden]);

  const anwenden = async (vorlage: Vorlage) => {
    setBeschaeftigt(vorlage.datei);
    setFehler(null);
    try {
      const neu = await api.bestand.vorlageAnwenden(profil, vorlage.datei);
      aufAngewendet(neu.datei);
    } catch (ursache) {
      setFehler(ursache instanceof ApiFehler ? ursache.message : 'Unbekannter Fehler.');
    } finally {
      setBeschaeftigt(null);
    }
  };

  const entfernen = async (vorlage: Vorlage) => {
    setBeschaeftigt(vorlage.datei);
    setFehler(null);
    try {
      await api.bestand.vorlageEntfernen(profil, vorlage.datei);
      setFragtLoeschen(null);
      await laden();
    } catch (ursache) {
      setFehler(ursache instanceof ApiFehler ? ursache.message : 'Unbekannter Fehler.');
    } finally {
      setBeschaeftigt(null);
    }
  };

  if (vorlagen.length === 0 && !fehler) return null;

  return (
    <section className="mb-6">
      <h2 className="mb-1 flex items-center gap-2 text-sm font-medium text-normal">
        <Files className="h-4 w-4" aria-hidden />
        Vorlagen
      </h2>
      <p className="mb-2 text-xs text-leise">
        Eine Vorlage geht nie online. Angewendet entsteht daraus eine neue Anzeige –
        die Vorlage bleibt und lässt sich beliebig oft wiederverwenden.
      </p>

      {fehler && (
        <p className="mb-2 hinweis hinweis-fehler">
          {fehler}
        </p>
      )}

      {/* Unter sm steht der Titel auf eigener Zeile (AP-2.18): neben „Anwenden"
          und dem Papierkorb blieben ihm auf 375 px rund 110 px, und die Vorlage
          war nur noch an „Vorlage: Möbe…" zu erkennen. */}
      <ul className="liste">
        {vorlagen.map(v => (
          <li key={v.datei} className="flex flex-wrap items-center gap-3 px-4 py-3">
            <div className="min-w-0 flex-1 basis-full sm:basis-auto">
              <p className="truncate text-sm text-stark">{v.titel}</p>
              <p className="text-xs text-leise">
                {v.unlesbar
                  ? `Unlesbar: ${v.unlesbar}`
                  : `${v.bilder} ${v.bilder === 1 ? 'Bild' : 'Bilder'}`}
              </p>
            </div>

            <button
              type="button"
              onClick={() => void anwenden(v)}
              disabled={beschaeftigt !== null || v.unlesbar !== null}
              className="btn-ghost"
            >
              <Plus className="h-4 w-4" aria-hidden />
              {beschaeftigt === v.datei ? 'Wird angelegt …' : 'Anwenden'}
            </button>

            <button
              type="button"
              onClick={() => setFragtLoeschen(v)}
              disabled={beschaeftigt !== null}
              aria-label={`Vorlage „${v.titel}" löschen`}
className="btn-leise"
            >
              <Trash2 className="h-4 w-4" aria-hidden />
            </button>
          </li>
        ))}
      </ul>

      {/* Rückfrage, weil Löschen die Bilder mitnimmt und nicht rückgängig zu
          machen ist. Die Anzeige, aus der die Vorlage entstand, bleibt. */}
      {fragtLoeschen && (
        <div className="hinweis hinweis-warn mt-2">
          <p className="text-sm text-amber-900">
            „{fragtLoeschen.titel}" samt Bildern löschen? Anzeigen bleiben unberührt.
          </p>
          <div className="mt-2 flex gap-2">
            <button
              type="button"
              onClick={() => void entfernen(fragtLoeschen)}
              disabled={beschaeftigt !== null}
className="btn-primaer"
            >
              Löschen
            </button>
            <button
              type="button"
              onClick={() => setFragtLoeschen(null)}
              className="btn-ghost"
            >
              Abbrechen
            </button>
          </div>
        </div>
      )}
    </section>
  );
}
