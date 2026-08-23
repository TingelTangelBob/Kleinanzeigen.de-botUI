// SPDX-FileCopyrightText: © Anzeigen-Studio contributors
// SPDX-License-Identifier: AGPL-3.0-or-later
//
// Typen der API. Handgeschrieben und bewusst nah an den Pydantic-Modellen des
// Backends gehalten - eine Abweichung fällt beim Typcheck auf, nicht erst zur
// Laufzeit.

export interface AuthStatus {
  eingerichtet: boolean;
  angemeldet: boolean;
  name: string | null;
}

export interface Profil {
  slug: string;
  anzeigename: string;
  angelegt_am: string;
  geaendert_am: string;
}

export interface ZugangStatus {
  benutzername: string;
  passwort_hinterlegt: boolean;
  geaendert_am: string;
}

/** Muss zu JobZustand im Backend passen. */
export type JobZustand =
  | 'wartet'
  | 'laeuft'
  | 'braucht_eingabe'
  | 'fertig'
  | 'pruefen'
  | 'gescheitert'
  | 'abgebrochen';

export interface Job {
  id: number;
  profil_slug: string;
  befehl: string;
  argumente: string[];
  zustand: JobZustand;
  eingereicht_am: string;
  gestartet_am: string | null;
  beendet_am: string | null;
  rueckgabecode: number | null;
  aufmerksamkeit: string[];
  eingriff: string | null;
  meldung: string | null;
  /** Bis wann der Lauf absichtlich wartet (ISO-8601), und warum. */
  wartet_bis: string | null;
  wartegrund: string | null;
}

export interface LogZeile {
  id: number;
  zeitpunkt: string;
  stufe: 'debug' | 'info' | 'warnung' | 'fehler';
  text: string;
}

export interface Gesundheit {
  status: string;
  version: string;
  dev_mode: boolean;
  missing_config: string[];
}
