// SPDX-FileCopyrightText: © Anzeigen-Studio contributors
// SPDX-License-Identifier: AGPL-3.0-or-later
//
// Das „Gelöscht •"-Präfix aus heruntergeladenen Titeln (AP-2.35).
//
// Kleinanzeigen.de stellt dem Titel einer nicht mehr aktiven Anzeige auf der
// Übersichtsseite „Gelöscht •" voran. `extract.py` übernimmt den Titel
// wörtlich - das Präfix landet also in der YAML und damit in jedem Feld, das
// den Titel zeigt.
//
// Es gehört dort nicht hin, und zwar aus zwei Gründen:
//
//   1. Es ist keine Eigenschaft der Anzeige, sondern eine Dekoration der
//      Listenansicht. Wer die Anzeige wieder hochlädt, stellt sonst eine
//      Anzeige namens „Gelöscht • Japanischer Ahorn …" online.
//   2. Es frisst 11 der 65 erlaubten Zeichen.
//
// Deshalb wird es überall entfernt, wo ein Titel gezeigt wird - unabhängig
// davon, ob die Anzeige als gelöscht erkannt wurde. Die frühere Fassung
// entfernte es nur bei `geloescht === true`; das griff bei fremden Anzeigen
// nicht, denn `geloescht` gilt laut AP-3.10 nur für eigene. Genau so stand es
// dann im Titelfeld des Editors.

const GELOESCHT_TITEL_PREFIX = /^Gelöscht\s*[•·]\s*/u;

/** Ob der Titel die Dekoration der Plattform trägt. */
export function hatGeloeschtPraefix(titel: string): boolean {
  return GELOESCHT_TITEL_PREFIX.test(titel);
}

/**
 * Der Titel ohne Plattform-Dekoration.
 *
 * Ändert die gespeicherte Datei nicht - wer das Präfix loswerden will, muss
 * es im Editor entfernen und speichern. Diese Funktion sorgt nur dafür, dass
 * es nirgends als Teil des Titels gelesen wird.
 */
export function titelFuerAnzeige(titel: string): string {
  return titel.replace(GELOESCHT_TITEL_PREFIX, '');
}
