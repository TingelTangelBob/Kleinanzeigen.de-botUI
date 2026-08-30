// SPDX-FileCopyrightText: © Anzeigen-Studio contributors
// SPDX-License-Identifier: AGPL-3.0-or-later
//
// API-Client.
//
// Eine Stelle für alle Aufrufe, damit Fehlerbehandlung und Sitzungsverlust
// nicht an zwanzig Orten einzeln behandelt werden müssen.

import type {
  AnzeigeInhalt, AuthStatus, BestandsAnzeige, Gesundheit, Job, Kategorie, LogZeile,
  KiAnlegenAntwort, KiEntwurfAntwort, KiStatus,
  Profil, SpeichernAusgabe, Vergleich, Versandpaket, Vorlage, ZugangStatus,
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
        // Nur bei JSON selbst setzen. Bei FormData muss der Browser den
        // Content-Type bestimmen - er hängt das Trennzeichen an, ohne das der
        // Server den Rumpf nicht zerlegen kann.
        ...(typeof optionen.body === 'string' ? { 'Content-Type': 'application/json' } : {}),
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
    anzeige: (profil: string, datei: string) =>
      anfrage<AnzeigeInhalt>(
        `/bestand/anzeige?profil=${encodeURIComponent(profil)}&datei=${encodeURIComponent(datei)}`,
      ),
    speichern: (profil: string, datei: string, felder: Record<string, unknown>) =>
      anfrage<SpeichernAusgabe>(`/bestand/anzeige?profil=${encodeURIComponent(profil)}`, {
        method: 'PUT', ...json({ datei, felder }),
      }),
    /** Was sich beim Hochladen gegenüber dem letzten Abgleich ändern würde (AP-3.5). */
    vergleich: (profil: string, datei: string) =>
      anfrage<Vergleich>(
        `/bestand/vergleich?profil=${encodeURIComponent(profil)}&datei=${encodeURIComponent(datei)}`,
      ),

    /** Legt eine Kopie als neuen Entwurf an - nur lokal (AP-3.3). */
    duplizieren: (profil: string, datei: string) =>
      anfrage<BestandsAnzeige>(`/bestand/duplizieren?profil=${encodeURIComponent(profil)}`, {
        method: 'POST', ...json({ datei }),
      }),

    /** Alle Vorlagen des Profils (AP-3.3). Eigene Liste, kein Teil des Bestands. */
    vorlagen: (profil: string) =>
      anfrage<Vorlage[]>(`/bestand/vorlagen?profil=${encodeURIComponent(profil)}`),

    /** Macht aus einer Anzeige eine Vorlage. Die Anzeige bleibt, wie sie ist. */
    alsVorlage: (profil: string, datei: string) =>
      anfrage<Vorlage>(`/bestand/vorlagen?profil=${encodeURIComponent(profil)}`, {
        method: 'POST', ...json({ datei }),
      }),

    /** Erzeugt aus einer Vorlage eine neue Anzeige. Die Vorlage bleibt liegen. */
    vorlageAnwenden: (profil: string, datei: string) =>
      anfrage<BestandsAnzeige>(`/bestand/vorlagen/anwenden?profil=${encodeURIComponent(profil)}`, {
        method: 'POST', ...json({ datei }),
      }),

    vorlageEntfernen: (profil: string, datei: string) =>
      anfrage<void>(
        `/bestand/vorlagen?profil=${encodeURIComponent(profil)}&datei=${encodeURIComponent(datei)}`,
        { method: 'DELETE' },
      ),

    /** Liest Anzeigennummern aus eingefügtem Text - ohne etwas zu tun (AP-3.7). */
    linksLesen: (profil: string, text: string) =>
      anfrage<{ neu: number[]; schon_vorhanden: number[]; unlesbare_zeilen: string[] }>(
        `/bestand/links-lesen?profil=${encodeURIComponent(profil)}`,
        { method: 'POST', ...json({ text }) },
      ),
    nachladen: (profil: string, text: string) =>
      anfrage<{ job_id: number; nummern: number[] }>(
        `/bestand/nachladen?profil=${encodeURIComponent(profil)}`,
        { method: 'POST', ...json({ text }) },
      ),

    /** Reiht einen Lauf ein, der genau diese Anzeige aktualisiert (AP-3.3). */
    hochladen: (profil: string, datei: string) =>
      anfrage<{ job_id: number; anzeige: BestandsAnzeige }>(
        `/bestand/hochladen?profil=${encodeURIComponent(profil)}`,
        { method: 'POST', ...json({ datei }) },
      ),

    bildHochladen: async (profil: string, datei: string, bild: File) => {
      const formular = new FormData();
      formular.append('bild', bild);
      // Kein json()-Rumpf: FormData setzt den Content-Type samt Trennzeichen
      // selbst. Wer ihn hier von Hand setzt, zerstört genau das.
      return anfrage<{ name: string; kopf: BestandsAnzeige }>(
        `/bestand/bild?profil=${encodeURIComponent(profil)}&datei=${encodeURIComponent(datei)}`,
        { method: 'POST', body: formular },
      );
    },
    bildEntfernen: (profil: string, datei: string, name: string) =>
      anfrage<BestandsAnzeige>(
        `/bestand/bild?profil=${encodeURIComponent(profil)}`
        + `&datei=${encodeURIComponent(datei)}&name=${encodeURIComponent(name)}`,
        { method: 'DELETE' },
      ),

    /** Kein anfrage(): Das Bild hängt direkt im src-Attribut. */
    bildUrl: (profil: string, datei: string, name: string) =>
      `/api/bestand/bild?profil=${encodeURIComponent(profil)}`
      + `&datei=${encodeURIComponent(datei)}&name=${encodeURIComponent(name)}`,
  },

  ki: {
    status: () => anfrage<KiStatus>('/ki/status'),
    schluesselSetzen: (apiSchluessel: string) =>
      anfrage<KiStatus>('/ki/schluessel', { method: 'PUT', ...json({ api_schluessel: apiSchluessel }) }),
    schluesselEntfernen: () => anfrage<KiStatus>('/ki/schluessel', { method: 'DELETE' }),

    /**
     * Der einzige Aufruf, der Geld kostet. Bewusst über XHR statt fetch: Nur
     * so lässt sich der Fortschritt des Hochladens melden, und bei mehreren
     * Handyfotos ist genau das die längste sichtbare Wartezeit.
     */
    entwurf: (profil: string, dateien: File[], aufFortschritt?: (anteil: number) => void) =>
      new Promise<KiEntwurfAntwort>((erfuellen, ablehnen) => {
        const daten = new FormData();
        daten.append('profil', profil);
        dateien.forEach(datei => daten.append('bilder', datei));

        const xhr = new XMLHttpRequest();
        xhr.open('POST', '/api/ki/entwurf');
        xhr.withCredentials = true;
        xhr.upload.onprogress = ereignis => {
          if (ereignis.lengthComputable && aufFortschritt) {
            aufFortschritt(ereignis.loaded / ereignis.total);
          }
        };
        xhr.onload = () => {
          let inhalt: unknown = null;
          try {
            inhalt = JSON.parse(xhr.responseText) as unknown;
          } catch {
            inhalt = null;
          }
          if (xhr.status >= 200 && xhr.status < 300) {
            erfuellen(inhalt as KiEntwurfAntwort);
            return;
          }
          const fehler = (inhalt as { fehler?: { meldung?: string; feld?: string } } | null)?.fehler;
          ablehnen(new ApiFehler(
            fehler?.meldung ?? 'Der Entwurf ist gescheitert.', xhr.status, fehler?.feld,
          ));
        };
        xhr.onerror = () => ablehnen(new ApiFehler('Das Backend ist nicht erreichbar.', 0));
        xhr.send(daten);
      }),

    /** Legt die Anzeige lokal an. Kein Anbieteraufruf, keine Kosten. */
    anlegen: (
      profil: string,
      entwurf: unknown,
      antworten: Record<string, string>,
      dateien: File[],
      wahl: {
        kategorie?: string | null;
        versandpakete?: string[];
        preis?: number | null;
      } = {},
    ) => {
      const daten = new FormData();
      daten.append('profil', profil);
      daten.append('entwurf_json', JSON.stringify(entwurf));
      daten.append('antworten_json', JSON.stringify(antworten));
      // Nur mitschicken, was der Mensch angeklickt hat (AP-4.5/4.6).
      if (wahl.kategorie) daten.append('kategorie', wahl.kategorie);
      // Die geschätzte Spanne steht bewusst NICHT hier: Sie ist eine
      // Einordnung, keine Angabe. Was mitgeht, hat jemand ausgewählt.
      if (wahl.preis != null) daten.append('preis', String(wahl.preis));
      if (wahl.versandpakete?.length) {
        daten.append('versandpakete_json', JSON.stringify(wahl.versandpakete));
      }
      dateien.forEach(datei => daten.append('bilder', datei));
      return anfrage<KiAnlegenAntwort>('/ki/anlegen', { method: 'POST', body: daten });
    },
  },

  katalog: {
    kategorien: () => anfrage<Kategorie[]>('/katalog/kategorien'),
    versandpakete: () => anfrage<Versandpaket[]>('/katalog/versandpakete'),
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
