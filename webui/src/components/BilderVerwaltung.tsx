// SPDX-FileCopyrightText: © Anzeigen-Studio contributors
// SPDX-License-Identifier: AGPL-3.0-or-later
//
// Bilder einer Anzeige: hinzufügen, sortieren, ersetzen, entfernen (AP-2.6).
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

import { useState, type DragEvent } from 'react';
import {
  DndContext, KeyboardSensor, PointerSensor, closestCenter,
  useSensor, useSensors, type DragEndEvent,
} from '@dnd-kit/core';
import {
  SortableContext, arrayMove, rectSortingStrategy,
  sortableKeyboardCoordinates, useSortable,
} from '@dnd-kit/sortable';
import { CSS } from '@dnd-kit/utilities';
import { GripVertical, ImagePlus, RefreshCw, Trash2 } from 'lucide-react';
import { api, ApiFehler } from '../services/api';
import { verkleinern } from '../services/bilder';

/** Dieselben Formate, die das Backend annimmt. */
export const ERLAUBTE_TYPEN = 'image/jpeg,image/png,image/gif';

interface Props {
  profil: string;
  datei: string;
  bilder: string[];
  aufAenderung: (bilder: string[]) => void;
}

function Kachel({
  profil, datei, name, erstes, aufEntfernen, aufErsetzen,
}: {
  profil: string; datei: string; name: string; erstes: boolean;
  aufEntfernen: (name: string) => void;
  aufErsetzen: (name: string, ersatz: File) => void;
}) {
  const { attributes, listeners, setNodeRef, transform, transition, isDragging } = useSortable({ id: name });

  return (
    <div
      ref={setNodeRef}
      style={{ transform: CSS.Transform.toString(transform), transition }}
      className={`relative overflow-hidden rounded border border-gray-200 bg-white
                  ${isDragging ? 'z-10 opacity-80 shadow-lg' : ''}`}
    >
      <img
        src={api.bestand.bildUrl(profil, datei, name)}
        alt=""
        loading="lazy"
        className="h-24 w-24 object-cover"
      />

      {erstes && (
        <span className="absolute left-0 top-0 bg-primary-custom px-1.5 py-0.5 text-xs font-medium">
          Titelbild
        </span>
      )}

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
    </div>
  );
}

export function BilderVerwaltung({ profil, datei, bilder, aufAenderung }: Props) {
  const [fehler, setFehler] = useState<string | null>(null);
  const [laeuft, setLaeuft] = useState(false);
  const [ueberZone, setUeberZone] = useState(false);

  const sensoren = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 4 } }),
    useSensor(KeyboardSensor, { coordinateGetter: sortableKeyboardCoordinates }),
  );

  const melden = (ursache: unknown) => {
    setFehler(ursache instanceof ApiFehler ? ursache.message : 'Unbekannter Fehler.');
  };

  const sortieren = async (ereignis: DragEndEvent) => {
    const { active, over } = ereignis;
    if (!over || active.id === over.id) return;
    const alt = bilder.indexOf(String(active.id));
    const neu = bilder.indexOf(String(over.id));
    if (alt < 0 || neu < 0) return;

    const sortiert = arrayMove(bilder, alt, neu);
    aufAenderung(sortiert);  // sofort zeigen, danach bestätigen lassen
    setFehler(null);
    try {
      await api.bestand.speichern(profil, datei, { images: sortiert });
    } catch (ursache) {
      aufAenderung(bilder);  // zurück auf die alte Reihenfolge
      melden(ursache);
    }
  };

  const hochladen = async (dateien: Iterable<File> | null): Promise<string[]> => {
    const gewaehlt = dateien ? Array.from(dateien) : [];
    if (gewaehlt.length === 0) return [];
    setFehler(null);
    setLaeuft(true);
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
      setLaeuft(false);
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
    const platz = bilder.indexOf(name);
    if (platz < 0) return;

    const neue = await hochladen([ersatz]);
    if (neue.length === 0) return;
    const neuerName = neue[0];

    try {
      await api.bestand.bildEntfernen(profil, datei, name);

      const sortiert = bilder.filter(b => b !== name);
      sortiert.splice(platz, 0, neuerName);

      aufAenderung(sortiert);
      await api.bestand.speichern(profil, datei, { images: sortiert });
    } catch (ursache) {
      melden(ursache);
    }
  };

  const entfernen = async (name: string) => {
    setFehler(null);
    try {
      await api.bestand.bildEntfernen(profil, datei, name);
      aufAenderung(bilder.filter(b => b !== name));
    } catch (ursache) {
      melden(ursache);
    }
  };

  // Nur Dateien annehmen. Ohne die Prüfung landet auch ein aus der Liste
  // gezogenes Bild in der Ablegezone, und dnd-kit sortiert dann ins Leere.
  const enthaeltDateien = (e: DragEvent) => e.dataTransfer.types.includes('Files');

  return (
    <fieldset
      onDragOver={e => { if (enthaeltDateien(e)) { e.preventDefault(); setUeberZone(true); } }}
      onDragLeave={() => setUeberZone(false)}
      onDrop={e => {
        if (!enthaeltDateien(e)) return;
        e.preventDefault();
        setUeberZone(false);
        void hochladen(e.dataTransfer.files);
      }}
      className={`rounded border p-3 transition-colors
                  ${ueberZone ? 'border-primary-custom bg-green-50' : 'border-gray-200'}`}
    >
      <legend className="px-1 text-sm font-medium text-gray-700">
        Bilder ({bilder.length})
      </legend>

      {fehler && (
        <p role="alert" className="mb-2 rounded border border-red-200 bg-red-50 p-2 text-sm text-red-800">
          {fehler}
        </p>
      )}

      {bilder.length > 0 && (
        <DndContext sensors={sensoren} collisionDetection={closestCenter} onDragEnd={e => void sortieren(e)}>
          <SortableContext items={bilder} strategy={rectSortingStrategy}>
            <div className="mb-3 flex flex-wrap gap-2">
              {bilder.map((name, i) => (
                <Kachel
                  key={name}
                  profil={profil}
                  datei={datei}
                  name={name}
                  erstes={i === 0}
                  aufEntfernen={n => void entfernen(n)}
                  aufErsetzen={(n, f) => void ersetzen(n, f)}
                />
              ))}
            </div>
          </SortableContext>
        </DndContext>
      )}

      <label className="inline-flex cursor-pointer items-center gap-2 rounded border border-gray-300
                        px-3 py-2 text-sm text-gray-700 hover:bg-gray-50">
        <ImagePlus className="h-4 w-4" aria-hidden />
        {laeuft ? 'Wird hochgeladen …' : 'Bilder hinzufügen'}
        <input
          type="file"
          accept={ERLAUBTE_TYPEN}
          multiple
          disabled={laeuft}
          onChange={e => { void hochladen(e.target.files); e.target.value = ''; }}
          className="sr-only"
        />
      </label>

      <p className="mt-2 text-xs text-gray-500">
        Das erste Bild ist das Titelbild. Ziehen ändert die Reihenfolge, und Dateien lassen
        sich direkt auf diesen Bereich ablegen. Erlaubt sind JPEG, PNG und GIF; große Bilder
        werden vor dem Hochladen verkleinert. Hinzufügen, Ersetzen, Sortieren und Entfernen
        wirken sofort – nicht erst beim Speichern.
      </p>
    </fieldset>
  );
}
