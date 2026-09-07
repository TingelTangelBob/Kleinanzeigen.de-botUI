// SPDX-FileCopyrightText: © Anzeigen-Studio contributors
// SPDX-License-Identifier: AGPL-3.0-or-later
//
// Aktionsknöpfe einer Seite in der App-Chrome (2026-09-07, mobil 2026-09-09).
//
// Statt dass jede Seite ihre Knöpfe („Vom Konto holen", „Neu einlesen" …) in
// einen eigenen Kopfbereich setzt, rendert sie sie per Portal in einen festen
// Slot. Es gibt zwei Slots:
//
//   * `topbar` – rechts in der App-Topleiste, links neben der Glocke (ab md).
//   * `mobil`  – eine eigene Zeile direkt unter der Topleiste (unter md). Die
//     Topleiste ist auf ~375 px zu eng für Titel + Knopf + Glocke.
//
// `useKopfAktionen` wählt den Slot nach der Fensterbreite. Portal statt
// serialisierter Beschreibung wie bei den Meldungen: Aktionen tragen lebende
// Handler und JSX, kein reiner Datensatz.

import { createContext, useContext, type ReactNode } from 'react';
import { createPortal } from 'react-dom';
import { useIstMobil } from '../hooks/useMedienabfrage';

export interface KopfAktionenZiele {
  /** Slot in der Topleiste (ab md). */
  topbar: HTMLElement | null;
  /** Slot als eigene Zeile unter der Topleiste (unter md). */
  mobil: HTMLElement | null;
}

export const KopfAktionenKontext = createContext<KopfAktionenZiele>({ topbar: null, mobil: null });

/**
 * Rendert `inhalt` in den passenden Kopf-Slot (Topleiste ab md, eigene Zeile
 * darunter). Rückgabe in das JSX der Seite einhängen (Portal-Knoten oder null).
 */
export function useKopfAktionen(inhalt: ReactNode): ReactNode {
  const { topbar, mobil } = useContext(KopfAktionenKontext);
  const istMobil = useIstMobil();
  const ziel = istMobil ? mobil : topbar;
  return ziel ? createPortal(inhalt, ziel) : null;
}
