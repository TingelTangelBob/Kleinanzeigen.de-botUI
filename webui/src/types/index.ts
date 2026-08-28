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
  /**
   * Woran der Lauf gerade ist (AP-2.8) — Kennung, fertiger Text und seit wann.
   * Reine Anzeige. `null` heißt nur, dass noch nichts erkannt wurde.
   */
  phase: string | null;
  phase_text: string | null;
  phase_seit: string | null;
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

/** Eine Anzeige, wie sie auf der Platte liegt (AP-3.2). */
export interface BestandsAnzeige {
  datei: string;
  ordner: string;
  titel: string;
  id: number | null;
  art: string;
  aktiv: boolean;
  kategorie: string | null;
  preis: number | null;
  preistyp: string | null;
  versandart: string | null;
  versandkosten: number | null;
  versandpakete: string[];
  direkt_kaufen: boolean;
  bilder: number;
  vorschaubild: string | null;
  erstellt_am: string | null;
  aktualisiert_am: string | null;
  neueinstellung_am: string | null;
  faellig: boolean;
  lokal_geaendert: boolean;
  /** Kennungen aus der Verlustanalyse, siehe docs/RUNDLAUF.md. */
  hinweise: string[];
  unlesbar: string | null;
}

/** Eine Anzeige mit allen Feldern - Grundlage des Editors (AP-2.5). */
export interface AnzeigeInhalt {
  kopf: BestandsAnzeige;
  felder: Record<string, unknown>;
  aenderbar: string[];
}

export interface SpeichernAusgabe {
  kopf: BestandsAnzeige;
  /** Was dem Veröffentlichen im Weg stünde - kein Grund, nicht zu speichern. */
  hinweise: string[];
}

export interface Unterschied {
  feld: string;
  beschriftung: string;
  vorher: string;
  jetzt: string;
}

/** Was sich seit dem letzten Abgleich mit der Plattform geändert hat (AP-3.5). */
export interface Vergleich {
  /**
   * Wann die Datei zuletzt mit der Plattform übereinstimmte, und wodurch.
   * `null` heißt: kein Abgleich bekannt — dann wird kein Unterschied behauptet.
   */
  stand_von: string | null;
  quelle: string | null;
  unterschiede: Unterschied[];
}

/** Nachschlagewerke für den Editor (AP-2.7). */
export interface Kategorie {
  name: string;
  wert: string;
}

export interface Versandpaket {
  wert: string;
  anbieter: string;
  groesse: string;
  /** Tagespreis der Plattform, oder null wenn sie nicht erreichbar war. */
  preis: number | null;
}

// ------------------------------------------------------------------ KI (Phase 4)

export interface KiStatus {
  hinterlegt: boolean;
  endet_auf: string | null;
  geaendert_am: string | null;
  modell: string;
  bildkante: number;
  /** Verbrauch des laufenden Kalendermonats und die Grenze dafür (AP-4.7). */
  verbrauch_usd: number;
  budget_usd: number;
  verbrauch_aufrufe: number;
}

export interface KiOption {
  text: string;
  wert: string;
}

/** Eine Rückfrage des Modells. `feld` sagt, worauf die Antwort wirkt. */
export interface KiFrage {
  id: string;
  frage: string;
  feld: 'titel' | 'beschreibung' | 'zustand' | 'preis';
  freitext_erlaubt: boolean;
  optionen: KiOption[];
}

export interface KiKategorieVorschlag {
  wert: string;
  name: string;
}

export interface KiVersandVorschlag {
  wert: string;
  groesse: string;
  preis: number | null;
}

export interface KiEntwurf {
  titel: string;
  beschreibung: string;
  zustand: string | null;
  zustand_text: string | null;
  kategorie: string | null;
  preis_euro: number | null;
  preis_begruendung: string | null;
  sicherheit: 'hoch' | 'mittel' | 'niedrig';
  fragen: KiFrage[];
  /** Gegen den echten Katalog abgeglichen (AP-4.5) - was hier steht, gibt es. */
  kategorie_vorschlaege: KiKategorieVorschlag[];
  versandgroesse: string | null;
  versand_vorschlaege: KiVersandVorschlag[];
}

export interface KiKosten {
  modell: string;
  token_eingabe: number;
  token_ausgabe: number;
  usd: number;
  bilder_gesendet: number;
  bytes_gesendet: number;
  /** Wie viele eigene Anzeigentexte den Ton vorgegeben haben. 0 = Standardstil. */
  stil_eigene_texte: number;
  verbrauch_usd: number;
  budget_usd: number;
}

export interface KiEntwurfAntwort {
  entwurf: KiEntwurf;
  kosten: KiKosten;
}

export interface KiAnlegenAntwort {
  datei: string;
  titel: string;
  bilder: number;
}
