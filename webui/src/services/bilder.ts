// SPDX-FileCopyrightText: © Anzeigen-Studio contributors
// SPDX-License-Identifier: AGPL-3.0-or-later
//
// Große Bilder vor dem Hochladen verkleinern (AP-2.6).
//
// Warum im Browser und nicht im Backend: Ein Handyfoto bringt heute 15 bis
// 25 MB mit. Verkleinert der Server, muss diese Menge erst durchs Netz, durch
// nginx und in den Arbeitsspeicher - für ein Bild, das Kleinanzeigen ohnehin
// auf Anzeigengröße herunterrechnet. Verkleinert der Browser, geht ein Bruchteil
// davon über die Leitung, und das Backend braucht keine Bildbibliothek.
//
// GIF bleibt unangetastet: Ein Canvas-Durchlauf würde eine Animation auf ihr
// erstes Einzelbild reduzieren. Lieber unverkleinert hochladen als still
// beschädigen.

/** Längste Kante, auf die verkleinert wird. Darüber sieht Kleinanzeigen nichts mehr. */
export const MAX_KANTE = 1920;

/** Ab dieser Dateigröße wird überhaupt verkleinert. Darunter lohnt es nicht. */
export const VERKLEINERN_AB_BYTES = 2 * 1024 * 1024;

/** Bildqualität beim Neukodieren. 0.85 ist die übliche Grenze, ab der man nichts sieht. */
const QUALITAET = 0.85;

export interface Groesse {
  breite: number;
  hoehe: number;
}

/**
 * Rechnet die Zielgröße unter Beibehaltung des Seitenverhältnisses aus.
 *
 * Getrennt von allem Canvas-Kram, weil genau hier die Fehler sitzen - beim
 * Runden, beim Hochkantbild und beim Bild, das schon klein genug ist.
 */
export function zielgroesse(breite: number, hoehe: number, maxKante = MAX_KANTE): Groesse {
  if (breite <= 0 || hoehe <= 0) return { breite: 0, hoehe: 0 };
  const laengste = Math.max(breite, hoehe);
  if (laengste <= maxKante) return { breite, hoehe };

  const faktor = maxKante / laengste;
  return {
    // Mindestens 1: Ein extrem schmales Bild darf keine Kante der Länge 0 bekommen.
    breite: Math.max(1, Math.round(breite * faktor)),
    hoehe: Math.max(1, Math.round(hoehe * faktor)),
  };
}

/** Ob diese Datei überhaupt verkleinert werden soll. */
export function sollVerkleinern(datei: File, abBytes = VERKLEINERN_AB_BYTES): boolean {
  if (datei.type === 'image/gif') return false;
  return datei.size > abBytes;
}

/**
 * Verkleinert ein Bild, wenn es sich lohnt - sonst kommt es unverändert zurück.
 *
 * Schlägt irgendetwas fehl (kein Canvas, kaputte Datei, Speicher), wird das
 * Original zurückgegeben. Ein nicht verkleinertes Bild ist ein kleiner Nachteil,
 * ein abgebrochener Upload ein großer.
 */
export async function verkleinern(datei: File): Promise<File> {
  if (!sollVerkleinern(datei)) return datei;

  try {
    const bild = await createImageBitmap(datei);
    const ziel = zielgroesse(bild.width, bild.height);
    if (ziel.breite === bild.width && ziel.hoehe === bild.height) {
      bild.close();
      return datei;
    }

    const flaeche = document.createElement('canvas');
    flaeche.width = ziel.breite;
    flaeche.height = ziel.hoehe;
    const stift = flaeche.getContext('2d');
    if (!stift) return datei;

    stift.drawImage(bild, 0, 0, ziel.breite, ziel.hoehe);
    bild.close();

    const klotz = await new Promise<Blob | null>(fertig => {
      flaeche.toBlob(fertig, 'image/jpeg', QUALITAET);
    });
    if (!klotz || klotz.size >= datei.size) return datei;

    return new File([klotz], datei.name.replace(/\.[^.]+$/, '') + '.jpg', {
      type: 'image/jpeg',
      lastModified: datei.lastModified,
    });
  } catch {
    return datei;
  }
}
