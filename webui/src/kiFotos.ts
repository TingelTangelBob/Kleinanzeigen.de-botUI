// SPDX-FileCopyrightText: © Anzeigen-Studio contributors
// SPDX-License-Identifier: AGPL-3.0-or-later
//
// Fotoprüfung und Gruppenbildung für die KI-Erkennung.
// Neue Datei, Anzeigen-Studio, 2026-09-30 (Stapel-Erkennung).
//
// Steht außerhalb der Komponenten, weil Einzel- und Stapel-Erkennung dieselbe
// Regel brauchen: Was der Bot später nicht hochladen kann, wird gar nicht
// erst an den Anbieter geschickt.

/** Was der Bot beim Hochladen später wieder lesen kann. HEIC gehört nicht dazu. */
export const ERLAUBTE_TYPEN = ['image/jpeg', 'image/png', 'image/gif'];

/** Trennt brauchbare Fotos von unbrauchbaren und formuliert die Meldung dazu. */
export function fotosPruefen(gewaehlt: File[]): { brauchbar: File[]; fehler: string | null } {
  const unbrauchbar = gewaehlt.filter(datei => !ERLAUBTE_TYPEN.includes(datei.type));
  let fehler: string | null = null;
  if (unbrauchbar.length > 0) {
    const heic = unbrauchbar.some(d => /hei[cf]/i.test(d.type) || /\.hei[cf]$/i.test(d.name));
    fehler = heic
      ? 'HEIC-Fotos vom iPhone kann das Studio noch nicht lesen. In den iPhone-Einstellungen '
        + 'unter Kamera → Formate „Maximale Kompatibilität“ wählen, oder das Foto als JPEG exportieren.'
      : `Nicht lesbar: ${unbrauchbar.map(d => d.name).join(', ')}. Erlaubt sind JPEG, PNG und GIF.`;
  }
  return { brauchbar: gewaehlt.filter(datei => ERLAUBTE_TYPEN.includes(datei.type)), fehler };
}

/**
 * Setzt Gruppenanfänge so, dass je `groesse` Fotos in Reihenfolge eine Anzeige
 * ergeben. Index 0 ist immer ein Anfang.
 */
export function anfaengeJe(anzahl: number, groesse: number): Set<number> {
  const schritt = Math.max(1, groesse);
  const anfaenge = new Set<number>();
  for (let index = 0; index < anzahl; index += schritt) anfaenge.add(index);
  return anfaenge;
}

/** Zerlegt die Fotos an den Gruppenanfängen. Liefert Indexlisten. */
export function gruppenAus(anzahl: number, anfaenge: Set<number>): number[][] {
  const gruppen: number[][] = [];
  for (let index = 0; index < anzahl; index += 1) {
    if (index === 0 || anfaenge.has(index) || gruppen.length === 0) gruppen.push([]);
    gruppen[gruppen.length - 1].push(index);
  }
  return gruppen;
}
