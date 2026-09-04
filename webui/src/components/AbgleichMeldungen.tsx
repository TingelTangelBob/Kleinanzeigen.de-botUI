// SPDX-FileCopyrightText: © Anzeigen-Studio contributors
// SPDX-License-Identifier: AGPL-3.0-or-later
//
// Befunde des täglichen Abgleichs in die Glocke (AP-3.12).
//
// Rendert nichts. Die Komponente hängt neben dem Seiteninhalt im
// `MeldungenProvider` und meldet dort unter dem Schlüssel `abgleich`, was das
// Backend gefunden hat - die Glocke zeigt es dann wie jede andere Meldung
// (AP-2.30). So braucht die Glocke selbst keine zweite Datenquelle.
//
// Warum nicht die Seiten das melden lassen, wie sonst: Der Abgleich läuft im
// Hintergrund und gehört zu keiner Seite. Wer gerade den Editor offen hat,
// soll trotzdem erfahren, dass über Nacht eine Anzeige verschwunden ist.
//
// Wegklicken merkt sich der Provider in localStorage (`hinweis` und `tipp`).
// Eine Fehlschlag-Warnung lässt sich nicht dauerhaft wegklicken - sie
// verschwindet serverseitig, sobald ein Abgleich wieder durchläuft.

import { useEffect, useState } from 'react';
import { api } from '../services/api';
import { useMeldungenQuelle } from '../context/useMeldungen';
import type { Meldung } from '../context/meldungenKontext';
import type { AbgleichMeldung } from '../types';

/** Abstand der Abfrage. Ein Lauf am Tag - Sekundentakt wäre hier sinnlos. */
const TAKT_MS = 60_000;

function zeitText(iso: string): string {
  const zeitpunkt = new Date(iso);
  if (Number.isNaN(zeitpunkt.getTime())) return '';
  return zeitpunkt.toLocaleString('de-DE', {
    day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit',
  });
}

/** Wandelt einen Befund in eine Glocken-Meldung. */
function alsMeldung(m: AbgleichMeldung, mehrereProfile: boolean): Meldung {
  const wann = zeitText(m.zeitpunkt);
  const wer = mehrereProfile ? `${m.profil_name} · ` : '';
  return {
    // Stabil über Neuladen hinweg - daran hängt das gemerkte Wegklicken.
    id: `abgleich-${m.id}`,
    ton: m.art === 'fehlschlag' ? 'warnung' : 'hinweis',
    titel: m.titel,
    text: `${wer}${m.text}${wann ? ` (${wann})` : ''}`,
  };
}

export function AbgleichMeldungen() {
  const [befunde, setBefunde] = useState<AbgleichMeldung[]>([]);

  useEffect(() => {
    let tot = false;
    const laden = async () => {
      try {
        const liste = await api.abgleich.meldungen();
        if (!tot) setBefunde(liste);
      } catch {
        // Ein nicht erreichbares Backend meldet sich an anderer Stelle laut
        // genug. Hier still bleiben statt eine zweite Fehlerzeile zu erzeugen.
        if (!tot) setBefunde([]);
      }
    };
    void laden();
    const timer = window.setInterval(() => void laden(), TAKT_MS);
    return () => { tot = true; window.clearInterval(timer); };
  }, []);

  const mehrereProfile = new Set(befunde.map(m => m.profil)).size > 1;
  useMeldungenQuelle('abgleich', befunde.map(m => alsMeldung(m, mehrereProfile)));

  return null;
}
