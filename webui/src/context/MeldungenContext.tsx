// SPDX-FileCopyrightText: © Anzeigen-Studio contributors
// SPDX-License-Identifier: AGPL-3.0-or-later
//
// Sammelstelle für Tipps, Hinweise und Warnungen (AP-2.30).
//
// Jede Seite meldet ihre Meldungen unter einem eigenen Schlüssel und ersetzt
// sie bei jeder Änderung komplett; beim Verlassen meldet sie eine leere Liste.
// Die Glocke in der Kopfleiste zeigt, was übrig bleibt. So steht nirgends mehr
// ein vollbreites hohes Banner im Seiteninhalt.

import { useCallback, useMemo, useRef, useState, type ReactNode } from 'react';
import {
  MeldungenKontext, type Meldung, type MeldungenWert,
} from './meldungenKontext';
import { merkeWeggeklickt, weggeklickteKennungen } from '../hooks/useHinweisSichtbar';

const RANG: Record<Meldung['ton'], number> = { warnung: 0, hinweis: 1, tipp: 2 };

/** Tipps und Hinweise merken sich das Wegklicken, eine Warnung nicht. */
function merktSich(ton: Meldung['ton']): boolean {
  return ton !== 'warnung';
}

export function MeldungenProvider({ children }: { children: ReactNode }) {
  // Quelle -> ihre Meldungen. Im Ref, damit `melden` stabil bleibt; ein
  // Zähler stößt das Neuberechnen an, wenn sich wirklich etwas geändert hat.
  const quellen = useRef<Map<string, Meldung[]>>(new Map());
  const [version, setVersion] = useState(0);
  // Diese Sitzung weggeklickt (auch Warnungen). Persistente stehen zusätzlich
  // in localStorage und werden hier beim Start eingelesen.
  const [abgewiesen, setAbgewiesen] = useState<Set<string>>(() => weggeklickteKennungen());

  const melden = useCallback((quelle: string, liste: Meldung[]) => {
    const vorher = quellen.current.get(quelle) ?? [];
    if (JSON.stringify(vorher) === JSON.stringify(liste)) return;
    if (liste.length === 0) quellen.current.delete(quelle);
    else quellen.current.set(quelle, liste);
    setVersion(v => v + 1);
  }, []);

  const abweisen = useCallback((id: string) => {
    for (const liste of quellen.current.values()) {
      const treffer = liste.find(m => m.id === id);
      if (treffer && merktSich(treffer.ton)) merkeWeggeklickt(id);
    }
    setAbgewiesen(vorher => {
      const neu = new Set(vorher);
      neu.add(id);
      return neu;
    });
  }, []);

  const meldungen = useMemo(() => {
    void version;
    const gesehen = new Set<string>();
    const alle: Meldung[] = [];
    for (const liste of quellen.current.values()) {
      for (const m of liste) {
        if (gesehen.has(m.id) || abgewiesen.has(m.id)) continue;
        gesehen.add(m.id);
        alle.push(m);
      }
    }
    return alle.sort((a, b) => RANG[a.ton] - RANG[b.ton]);
  }, [version, abgewiesen]);

  const wert: MeldungenWert = useMemo(
    () => ({ meldungen, melden, abweisen }),
    [meldungen, melden, abweisen],
  );

  return <MeldungenKontext.Provider value={wert}>{children}</MeldungenKontext.Provider>;
}
