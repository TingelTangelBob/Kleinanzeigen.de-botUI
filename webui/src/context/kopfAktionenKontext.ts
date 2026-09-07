// SPDX-FileCopyrightText: © Anzeigen-Studio contributors
// SPDX-License-Identifier: AGPL-3.0-or-later
//
// Aktionsknöpfe einer Seite in der App-Topleiste (2026-09-07).
//
// Statt dass jede Seite ihre Knöpfe („Vom Konto holen", „Neu einlesen" …) in
// einen eigenen Kopfbereich setzt, rendert sie sie per Portal in einen festen
// Slot links neben der Glocke. Eine Stelle für alle Seiten, mit dezenter
// Abtrennung zur Glocke.
//
// Portal statt serialisierter Beschreibung wie bei den Meldungen: Aktionen
// tragen lebende Handler und JSX, kein reiner Datensatz. Die Seite behält damit
// die volle Kontrolle über Zustand und Aussehen ihrer Knöpfe.

import { createContext, useContext, type ReactNode } from 'react';
import { createPortal } from 'react-dom';

/** Das DOM-Element des Topleisten-Slots, oder null solange die Schale fehlt. */
export const KopfAktionenKontext = createContext<HTMLElement | null>(null);

/**
 * Rendert `inhalt` in den Topleisten-Slot. Rückgabe in das JSX der Seite
 * einhängen (sie ist ein Portal-Knoten oder null). Beim Verlassen der Seite
 * räumt React das Portal von selbst ab.
 */
export function useKopfAktionen(inhalt: ReactNode): ReactNode {
  const ziel = useContext(KopfAktionenKontext);
  return ziel ? createPortal(inhalt, ziel) : null;
}
