// SPDX-FileCopyrightText: © Anzeigen-Studio contributors
// SPDX-License-Identifier: AGPL-3.0-or-later
//
// Bilder einer Anzeige: hinzufügen, sortieren, ersetzen, entfernen (AP-2.6).
// UI-Anpassung 2026-09-04: Ab drei Bildern automatisch zweispaltig darstellen.
//
// Anders als der Rest des Editors wirken diese drei sofort und nicht erst beim
// Speichern. Grund: Sie fassen Dateien an. Ein „Speichern", nach dem eine
// hochgeladene Datei wieder verschwindet, wäre schwerer zu erklären als eine
// Änderung, die gleich gilt.
//
// Die Reihenfolge zählt: Das erste Bild ist bei Kleinanzeigen das Titelbild.
// Deshalb ist sie ziehbar und nicht nur eine Liste.
//
// Erlaubt sind JPEG, PNG und GIF - dieselben Formate, die das Backend annimmt
// und die der Bot beim Hochladen wieder lesen kann. WebP steht bewusst nicht
// dabei; siehe `bilder.ERLAUBTE_FORMATE` im Backend.
//
// Große Bilder werden vor dem Hochladen im Browser verkleinert. Ein Handyfoto
// mit 20 MB käme sonst gar nicht erst durch.

import { useEffect, useRef, useState, type DragEvent } from 'react';
import {
  DndContext, KeyboardSensor, PointerSensor, closestCenter,
  useSensor, useSensors, type DragEndEvent,
} from '@dnd-kit/core';
import {
  SortableContext, arrayMove, sortableKeyboardCoordinates,
  rectSortingStrategy, useSortable, verticalListSortingStrategy,
} from '@dnd-kit/sortable';
import { CSS } from '@dnd-kit/utilities';
import { GripVertical, ImagePlus, RefreshCw, Trash2, X } from 'lucide-react';
import { api, ApiFehler } from '../services/api';
import { verkleinern } from '../services/bilder';
import { InfoTip } from './InfoTip';

const HILFE = 'Das erste Bild ist das Titelbild. Ziehen ändert die Reihenfolge, '
  + 'und Dateien lassen sich direkt auf diesen Bereich ablegen. Erlaubt sind JPEG, '
  + 'PNG und GIF; große Bilder werden vor dem Hochladen verkleinert. Hinzufügen, '
  + 'Ersetzen, Sortieren und Entfernen wirken sofort – nicht erst beim Speichern.';

/** Dieselben Formate, die das Backend annimmt. */
export const ERLAUBTE_TYPEN = 'image/jpeg,image/png,image/gif';

interface Props {
  profil: string;
  datei: string;
  bilder: string[];
  aufAenderung: (bilder: string[]) => void;
  bearbeitbar?: boolean;
}

function Kachel({
  profil, datei, name, erstes, bearbeitbar, aufEntfernen, aufErsetzen, aufVorschau,
}: {
  profil: string; datei: string; name: string; erstes: boolean;
  bearbeitbar: boolean;
  aufEntfernen: (name: string) => void;
  aufErsetzen: (name: string, ersatz: File) => void;
  aufVorschau: (name: string) => void;
}) {
  const { attributes, listeners, setNodeRef, transform, transition, isDragging } = useSortable({ id: name });

  return (
    <div
      ref={setNodeRef}
      style={{ transform: CSS.Transform.toString(transform), transition }}
      className={`relative overflow-hidden karte
                  ${isDragging ? 'z-10 opacity-80 shadow-lg' : ''}`}
    >
      <button
        type="button"
        onClick={() => aufVorschau(name)}
        aria-label={`${name} in Vorschau öffnen`}
        className="bild-kachel-knopf"
      >
        <img
          src={api.bestand.bildUrl(profil, datei, name)}
          alt=""
          loading="lazy"
          className="bild-kachel"
        />
      </button>

      {erstes && (
        <span className="absolute left-0 top-0 bg-primary-custom px-1.5 py-0.5 text-xs font-medium">
          Titelbild
        </span>
      )}

      {bearbeitbar && (
        <>
          <button
            type="button"
            {...attributes}
            {...listeners}
            aria-label={`${name} verschieben`}
            className="absolute bottom-0 left-0 cursor-grab bg-black/50 p-1 text-white"
          >
            <GripVertical className="h-4 w-4" aria-hidden />
          </button>

          <label
            title="Durch ein anderes Bild ersetzen"
            className="absolute bottom-0 right-7 cursor-pointer bg-black/50 p-1 text-white hover:bg-black/70"
          >
            <RefreshCw className="h-4 w-4" aria-hidden />
            <span className="sr-only">{`${name} ersetzen`}</span>
            <input
              type="file"
              accept={ERLAUBTE_TYPEN}
              onChange={e => {
                const gewaehlt = e.target.files?.[0];
                e.target.value = '';
                if (gewaehlt) aufErsetzen(name, gewaehlt);
              }}
              className="sr-only"
            />
          </label>

          <button
            type="button"
            onClick={() => aufEntfernen(name)}
            aria-label={`${name} entfernen`}
            className="absolute bottom-0 right-0 bg-black/50 p-1 text-white hover:bg-red-700"
          >
            <Trash2 className="h-4 w-4" aria-hidden />
          </button>
        </>
      )}
    </div>
  );
}

export function BilderVerwaltung({
  profil, datei, bilder, aufAenderung, bearbeitbar = true,
}: Props) {
  const [fehler, setFehler] = useState<string | null>(null);
  const [laeuft, setLaeuft] = useState(false);
  const [ueberZone, setUeberZone] = useState(false);
  const [vorschau, setVorschau] = useState<string | null>(null);
  const schliessenRef = useRef<HTMLButtonElement>(null);

  // Zwei Bilder bleiben als große Einzelbilder gut prüfbar. Ab drei Bildern
  // nutzt das Raster die verfügbare Breite besser und hält die Vorschauen
  // trotzdem quadratisch. Die Regel gilt nach jedem Hinzufügen/Entfernen neu.
  const zweispaltig = bilder.length >= 3;

  const sensoren = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 4 } }),
    useSensor(KeyboardSensor, { coordinateGetter: sortableKeyboardCoordinates }),
  );

  const melden = (ursache: unknown) => {
    setFehler(ursache instanceof ApiFehler ? ursache.message : 'Unbekannter Fehler.');
  };

  useEffect(() => {
    setVorschau(null);
  }, [datei]);

  useEffect(() => {
    if (!vorschau) return;

    const vorherigerFokus = document.activeElement instanceof HTMLElement
      ? document.activeElement
      : null;
    schliessenRef.current?.focus();
    const aufTaste = (ereignis: KeyboardEvent) => {
      if (ereignis.key === 'Escape') setVorschau(null);
    };
    window.addEventListener('keydown', aufTaste);
    return () => {
      window.removeEventListener('keydown', aufTaste);
      vorherigerFokus?.focus();
    };
  }, [vorschau]);

  const sortieren = async (ereignis: DragEndEvent) => {
    if (laeuft) return;
    const { active, over } = ereignis;
    if (!over || active.id === over.id) return;
    const alt = bilder.indexOf(String(active.id));
    const neu = bilder.indexOf(String(over.id));
    if (alt < 0 || neu < 0) return;

    const sortiert = arrayMove(bilder, alt, neu);
    aufAenderung(sortiert);  // sofort zeigen, danach bestätigen lassen
    setFehler(null);
    setLaeuft(true);
    try {
      await api.bestand.speichern(profil, datei, { images: sortiert });
    } catch (ursache) {
      aufAenderung(bilder);  // zurück auf die alte Reihenfolge
      melden(ursache);
    } finally {
      setLaeuft(false);
    }
  };

  const hochladen = async (
    dateien: Iterable<File> | null,
    eigeneSperre = true,
  ): Promise<string[]> => {
    const gewaehlt = dateien ? Array.from(dateien) : [];
    if (gewaehlt.length === 0) return [];
    setFehler(null);
    if (eigeneSperre) setLaeuft(true);
    let liste = bilder;
    const neue: string[] = [];
    try {
      // Nacheinander statt parallel: Der Name jeder Datei hängt davon ab,
      // welche Nummern schon vergeben sind.
      for (const datei_ of gewaehlt) {
        const klein = await verkleinern(datei_);
        const ergebnis = await api.bestand.bildHochladen(profil, datei, klein);
        neue.push(ergebnis.name);
        liste = [...liste, ergebnis.name];
        aufAenderung(liste);
      }
    } catch (ursache) {
      melden(ursache);
    } finally {
      if (eigeneSperre) setLaeuft(false);
    }
    return neue;
  };

  /**
   * Ersetzt ein Bild an Ort und Stelle.
   *
   * Drei Schritte über die vorhandenen Endpunkte statt eines neuen: hochladen,
   * altes entfernen, das neue auf dessen Platz sortieren. Die Reihenfolge ist
   * Absicht - die Sortierprüfung im Backend verlangt, dass vorher und nachher
   * dieselben Bilder stehen, also darf erst danach umsortiert werden.
   */
  const ersetzen = async (name: string, ersatz: File) => {
    if (laeuft) return;
    const platz = bilder.indexOf(name);
    if (platz < 0) return;

    setFehler(null);
    setLaeuft(true);
    try {
      const neue = await hochladen([ersatz], false);
      if (neue.length === 0) return;
      const neuerName = neue[0];
      await api.bestand.bildEntfernen(profil, datei, name);

      const sortiert = bilder.filter(b => b !== name);
      sortiert.splice(platz, 0, neuerName);

      aufAenderung(sortiert);
      await api.bestand.speichern(profil, datei, { images: sortiert });
    } catch (ursache) {
      melden(ursache);
    } finally {
      setLaeuft(false);
    }
  };

  const entfernen = async (name: string) => {
    if (laeuft) return;
    setFehler(null);
    setLaeuft(true);
    try {
      await api.bestand.bildEntfernen(profil, datei, name);
      aufAenderung(bilder.filter(b => b !== name));
    } catch (ursache) {
      melden(ursache);
    } finally {
      setLaeuft(false);
    }
  };

  // Nur Dateien annehmen. Ohne die Prüfung landet auch ein aus der Liste
  // gezogenes Bild in der Ablegezone, und dnd-kit sortiert dann ins Leere.
  const enthaeltDateien = (e: DragEvent) => e.dataTransfer.types.includes('Files');

  return (
    <section
      aria-label={`Bilder (${bilder.length})`}
      aria-disabled={!bearbeitbar}
      onDragOver={e => {
        if (bearbeitbar && enthaeltDateien(e)) {
          e.preventDefault();
          setUeberZone(true);
        }
      }}
      onDragLeave={() => setUeberZone(false)}
      onDrop={e => {
        if (!bearbeitbar || !enthaeltDateien(e)) return;
        e.preventDefault();
        setUeberZone(false);
        void hochladen(e.dataTransfer.files);
      }}
      className={`karte editor-bilder-karte p-4 transition-colors ${ueberZone ? 'dropzone-aktiv' : ''}`}
    >
      {/* Kopf in einer Zeile (Mockup v4): Zähler mit Kurzhilfe links, der
          Hinzufügen-Knopf rechts. Die Textwand darunter ist ins Info-Icon
          gewandert. */}
      <div className="mb-3 flex w-full items-center justify-between gap-2">
        <h2 className="karte-kopf mb-0 flex min-w-0 items-center gap-1">
          Bilder ({bilder.length})
          <InfoTip text={HILFE} label="Hilfe zu den Bildern" />
        </h2>
        {bearbeitbar && (
          <label className="btn-ghost btn-ghost-klein cursor-pointer">
            <ImagePlus className="h-4 w-4" aria-hidden />
            {laeuft ? 'Lädt …' : 'Bilder'}
            <input
              type="file"
              accept={ERLAUBTE_TYPEN}
              multiple
              disabled={laeuft}
              onChange={e => { void hochladen(e.target.files); e.target.value = ''; }}
              className="sr-only"
            />
          </label>
        )}
      </div>

      {fehler && (
        <p role="alert" className="mb-2 hinweis hinweis-fehler">
          {fehler}
        </p>
      )}

      {bilder.length > 0 ? (
        <DndContext
          sensors={sensoren}
          collisionDetection={closestCenter}
          onDragEnd={bearbeitbar && !laeuft ? e => void sortieren(e) : undefined}
        >
          <SortableContext
            items={bilder}
            strategy={zweispaltig ? rectSortingStrategy : verticalListSortingStrategy}
          >
            <div className={`bild-spalte ${zweispaltig ? 'bild-spalte-zweispaltig' : ''}`}>
              {bilder.map((name, i) => (
                <Kachel
                  key={name}
                  profil={profil}
                  datei={datei}
                  name={name}
                  erstes={i === 0}
                  bearbeitbar={bearbeitbar && !laeuft}
                  aufEntfernen={n => void entfernen(n)}
                  aufErsetzen={(n, f) => void ersetzen(n, f)}
                  aufVorschau={setVorschau}
                />
              ))}
            </div>
          </SortableContext>
        </DndContext>
      ) : (
        <p className="px-1 text-xs text-leise">
          {bearbeitbar
            ? 'Noch keine Bilder. Dateien hierher ziehen oder oben „Bilder“ wählen.'
            : 'Keine Bilder vorhanden.'}
        </p>
      )}

      {vorschau && (
        <div
          className="bild-vorschau-overlay"
          onClick={() => setVorschau(null)}
        >
          <div
            className="bild-vorschau-dialog"
            role="dialog"
            aria-modal="true"
            aria-label={`Vorschau von ${vorschau}`}
            onClick={e => e.stopPropagation()}
          >
            <button
              ref={schliessenRef}
              type="button"
              onClick={() => setVorschau(null)}
              aria-label="Vorschau schließen"
              className="btn-icon bild-vorschau-schliessen"
            >
              <X className="h-5 w-5" aria-hidden />
            </button>
            <img
              src={api.bestand.bildUrl(profil, datei, vorschau)}
              alt={`Bild ${vorschau}`}
              loading="eager"
              decoding="async"
              className="bild-vorschau"
            />
          </div>
        </div>
      )}
    </section>
  );
}
