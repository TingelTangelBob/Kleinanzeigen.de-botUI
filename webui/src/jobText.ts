// SPDX-FileCopyrightText: © Anzeigen-Studio contributors
// SPDX-License-Identifier: AGPL-3.0-or-later
//
// Gemeinsame Beschriftung der Bot-Befehle und der Anzeige-Bezug eines Laufs.
// Eine Quelle, damit derselbe Lauf in der Warteschlange (AP-2.31), in der
// Glocke (AP-2.30) und auf dem Dashboard (AP-2.29) gleich heißt und dieselbe
// Anzeige nennt.

import {
  ArrowUpFromLine, CheckCircle2, Download, Play, RefreshCw, Stethoscope, Trash2, Upload,
} from 'lucide-react';
import type { LucideIcon } from 'lucide-react';
import type { BestandsAnzeige, Job } from './types';

const BEFEHL_TEXT: Record<string, string> = {
  verify: 'Prüfen',
  diagnose: 'Diagnose',
  download: 'Herunterladen',
  publish: 'Veröffentlichen',
  update: 'Aktualisieren',
  extend: 'Verlängern',
  delete: 'Löschen',
};

/** Lesbarer Name eines Bot-Befehls; unbekannte Befehle bleiben, wie sie sind. */
export function befehlText(befehl: string): string {
  return BEFEHL_TEXT[befehl] ?? befehl;
}

/**
 * Ein Symbol je Bot-Befehl (AP-2.32). Steht in der Warteschlange und auf dem
 * Dashboard links vor dem Anzeigentitel und ersetzt dort das zweite große
 * Text-Label. Unbekannte Befehle bekommen ein neutrales „läuft"-Dreieck.
 */
const BEFEHL_ICON: Record<string, LucideIcon> = {
  verify: CheckCircle2,
  diagnose: Stethoscope,
  download: Download,
  publish: Upload,
  update: RefreshCw,
  extend: ArrowUpFromLine,
  delete: Trash2,
};

export function befehlIcon(befehl: string): LucideIcon {
  return BEFEHL_ICON[befehl] ?? Play;
}

/** Zerlegt `--ads=1234,5678` aus den Job-Argumenten in Anzeigennummern. */
function anzeigenIds(argumente: string[]): number[] {
  for (const arg of argumente) {
    const treffer = /^--ads=(.+)$/.exec(arg);
    if (!treffer) continue;
    return treffer[1]
      .split(',')
      .map(teil => Number.parseInt(teil.trim(), 10))
      .filter(nummer => Number.isFinite(nummer));
  }
  return [];
}

/**
 * Welche Anzeige ein Lauf betraf (AP-2.29). Der Bezug steckt schon in den
 * Job-Metadaten: `anzeigen_glob` (`./<ordner>/<datei>.yaml`) beim Hochladen
 * einer einzelnen Anzeige, sonst `--ads=<id>` in den Argumenten. Nur wenn wir
 * die Anzeige im Bestand wiederfinden, zeigen wir ihren Titel; sonst die nackte
 * Kennung. `null` heißt: der Lauf galt dem ganzen Profil (z. B. „Herunterladen").
 *
 * `bestand` darf leer sein - dann bleibt es bei der nackten Kennung.
 */
export function anzeigeBezug(job: Job, bestand: BestandsAnzeige[]): string | null {
  const datei = job.anzeigen_glob?.replace(/^\.\//, '') ?? null;
  if (datei) {
    const treffer = bestand.find(a => a.datei === datei);
    if (treffer) return treffer.id ? `${treffer.titel} · #${treffer.id}` : treffer.titel;
    const teile = datei.split('/');
    return teile[teile.length - 2] ?? datei;
  }
  const ids = anzeigenIds(job.argumente);
  if (ids.length === 0) return null;
  if (ids.length === 1) {
    const treffer = bestand.find(a => a.id === ids[0]);
    return treffer ? `${treffer.titel} · #${ids[0]}` : `Anzeige #${ids[0]}`;
  }
  return `${ids.length} Anzeigen`;
}
