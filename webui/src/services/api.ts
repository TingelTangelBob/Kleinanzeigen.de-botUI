// SPDX-FileCopyrightText: © Anzeigen-Studio contributors
// SPDX-License-Identifier: AGPL-3.0-or-later
//
// API-Client.
//
// Eine Stelle für alle Aufrufe, damit Fehlerbehandlung und Sitzungsverlust
// nicht an zwanzig Orten einzeln behandelt werden müssen.

import type {
  AuthStatus, BestandsAnzeige, Gesundheit, Job, LogZeile, Profil, ZugangStatus,
} from '../types';

/** Fehler mit der deutschen Meldung des Backends. */
export class ApiFehler extends Error {
  constructor(
    meldung: string,
    readonly status: number,
    readonly feld?: string,
  ) {
    super(meldung);
    this.name = 'ApiFehler';
  }

  /** Die Sitzung ist abgelaufen oder es wurde nie eine aufgebaut. */
  get nichtAngemeldet(): boolean {
    return this.status === 401;
  }

  /** Die Anwendung ist noch nicht eingerichtet. */
  get nichtEingerichtet(): boolean {
    return this.status === 409 && this.message.includes('eingerichtet');
  }
}

async function anfrage<T>(pfad: string, optionen: RequestInit = {}): Promise<T> {
  let antwort: Response;
  try {
    antwort = await fetch(`/api${pfad}`, {
      ...optionen,
      headers: {
        ...(optionen.body ? { 'Content-Type': 'application/json' } : {}),
        ...optionen.headers,
      },
      // Sitzungscookie mitschicken.
      credentials: 'same-origin',
    });
  } catch {
    // Netzfehler sehen für den Nutzer anders aus als ein Serverfehler und
    // brauchen eine eigene Meldung.
    throw new ApiFehler('Das Backend ist nicht erreichbar.', 0);
  }

  if (antwort.status === 204) return undefined as T;

  const text = await antwort.text();
  let daten: unknown = null;
  if (text) {
    try {
      daten = JSON.parse(text);
    } catch {
      daten = null;
    }
  }

  if (!antwort.ok) {
    const fehler = (daten as { fehler?: { meldung?: string; feld?: string } } | null)?.fehler;
    throw new ApiFehler(
      fehler?.meldung ?? `Unerwarteter Fehler (HTTP ${antwort.status}).`,
      antwort.status,
      fehler?.feld,
    );
  }

  return daten as T;
}

const json = (koerper: unknown): RequestInit => ({ body: JSON.stringify(koerper) });

export const api = {
  gesundheit: () => anfrage<Gesundheit>('/health'),

  auth: {
    status: () => anfrage<AuthStatus>('/auth/status'),
    einrichten: (name: string, passwort: string) =>
      anfrage<AuthStatus>('/auth/einrichten', { method: 'POST', ...json({ name, passwort }) }),
    anmelden: (name: string, passwort: string) =>
      anfrage<AuthStatus>('/auth/anmelden', { method: 'POST', ...json({ name, passwort }) }),
    abmelden: () => anfrage<void>('/auth/abmelden', { method: 'POST' }),
    passwortAendern: (alt: string, neu: string) =>
      anfrage<void>('/auth/passwort', { method: 'POST', ...json({ alt, neu }) }),
  },

  profile: {
    liste: () => anfrage<Profil[]>('/profile'),
    anlegen: (slug: string, anzeigename: string) =>
      anfrage<Profil>('/profile', { method: 'POST', ...json({ slug, anzeigename }) }),
    umbenennen: (slug: string, anzeigename: string) =>
      anfrage<Profil>(`/profile/${encodeURIComponent(slug)}`, {
        method: 'PATCH', ...json({ anzeigename }),
      }),
    loeschen: (slug: string, mitDaten: boolean) =>
      anfrage<void>(
        `/profile/${encodeURIComponent(slug)}?mit_daten=${mitDaten ? 'true' : 'false'}`,
        { method: 'DELETE' },
      ),
    zugang: (slug: string) =>
      anfrage<ZugangStatus | null>(`/profile/${encodeURIComponent(slug)}/zugang`),
    zugangSetzen: (slug: string, benutzername: string, passwort: string | null) =>
      anfrage<ZugangStatus>(`/profile/${encodeURIComponent(slug)}/zugang`, {
        method: 'PUT', ...json({ benutzername, passwort }),
      }),
    zugangEntfernen: (slug: string) =>
      anfrage<void>(`/profile/${encodeURIComponent(slug)}/zugang`, { method: 'DELETE' }),
  },

  bestand: {
    liste: (profil: string) =>
      anfrage<BestandsAnzeige[]>(`/bestand?profil=${encodeURIComponent(profil)}`),
    lokaleAenderungen: (profil: string) =>
      anfrage<BestandsAnzeige[]>(`/bestand/lokale-aenderungen?profil=${encodeURIComponent(profil)}`),
    /** Kein anfrage(): Das Bild hängt direkt im src-Attribut. */
    bildUrl: (profil: string, datei: string, name: string) =>
      `/api/bestand/bild?profil=${encodeURIComponent(profil)}`
      + `&datei=${encodeURIComponent(datei)}&name=${encodeURIComponent(name)}`,
  },

  jobs: {
    liste: (profil?: string) =>
      anfrage<Job[]>(`/jobs${profil ? `?profil=${encodeURIComponent(profil)}` : ''}`),
    einzeln: (id: number) => anfrage<Job>(`/jobs/${id}`),
    starten: (profil: string, befehl: string, argumente: string[] = []) =>
      anfrage<Job>('/jobs', { method: 'POST', ...json({ profil, befehl, argumente }) }),
    abbrechen: (id: number) => anfrage<unknown>(`/jobs/${id}/abbrechen`, { method: 'POST' }),
    eingabe: (id: number, text = '') =>
      anfrage<unknown>(`/jobs/${id}/eingabe`, { method: 'POST', ...json({ text }) }),
    log: (id: number, abId = 0) => anfrage<LogZeile[]>(`/jobs/${id}/log?ab_id=${abId}`),
    stromUrl: (id: number, abId = 0) => `/api/jobs/${id}/strom?ab_id=${abId}`,
  },
};
