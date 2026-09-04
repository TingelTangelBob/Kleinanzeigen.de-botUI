// SPDX-FileCopyrightText: © Anzeigen-Studio contributors
// SPDX-License-Identifier: AGPL-3.0-or-later
//
// Sicherung, Export und Import eines Profils (AP-3.6).
//
// Eigene Datei statt eines weiteren Blocks in EinstellungenSeite.tsx: Der
// Import ist ein Massenvorgang mit eigenem Zustand (Datei gewählt, Vorschau
// geholt, eingespielt, Protokoll da), und der gehört nicht in eine Datei, die
// ohnehin schon vierzig Formularfelder verwaltet.
//
// Der Ablauf ist bewusst dreistufig: Datei wählen → ANSEHEN → einspielen.
// Ein Import ohne Vorschau wäre ein Knopf, hinter dem sich der Bestand
// verändert, ohne dass vorher jemand sagen konnte, was passiert.
//
// Was hier NICHT passiert: Es geht nichts auf kleinanzeigen.de. Der Import
// legt Dateien ab; was davon online geht, entscheidet ein eigener Lauf.

import { useState } from 'react';
import { AlertTriangle, Archive, Check, Download, Upload } from 'lucide-react';
import { api, ApiFehler } from '../services/api';
import type { ArchivErgebnis, ArchivVorschau } from '../types';

/** Höchstzahl Pfade, die eine Liste einzeln zeigt. Darüber wird gezählt. */
const NAMEN_GRENZE = 8;

function Pfadliste({ titel, pfade }: { titel: string; pfade: string[] }) {
  if (pfade.length === 0) return null;
  const sichtbar = pfade.slice(0, NAMEN_GRENZE);
  return (
    <div className="mt-2">
      <p className="text-xs font-medium text-stark">{titel} ({pfade.length})</p>
      <ul className="mt-1 space-y-0.5">
        {sichtbar.map(pfad => (
          <li key={pfad} className="truncate text-xs text-leise" title={pfad}>{pfad}</li>
        ))}
        {pfade.length > sichtbar.length && (
          <li className="text-xs text-leise">… und {pfade.length - sichtbar.length} weitere</li>
        )}
      </ul>
    </div>
  );
}

export function SicherungAbschnitt({ profil }: { profil: string }) {
  const [datei, setDatei] = useState<File | null>(null);
  const [schau, setSchau] = useState<ArchivVorschau | null>(null);
  const [ergebnis, setErgebnis] = useState<ArchivErgebnis | null>(null);
  const [ersetzen, setErsetzen] = useState(false);
  const [laeuft, setLaeuft] = useState(false);
  const [fehler, setFehler] = useState<string | null>(null);

  const zuruecksetzen = () => {
    setSchau(null);
    setErgebnis(null);
    setErsetzen(false);
    setFehler(null);
  };

  const dateiWaehlen = (gewaehlt: File | null) => {
    setDatei(gewaehlt);
    zuruecksetzen();
  };

  const melden = (e: unknown, ersatz: string) =>
    setFehler(e instanceof ApiFehler ? e.message : ersatz);

  const ansehen = async () => {
    if (!datei) return;
    setLaeuft(true);
    setFehler(null);
    try {
      setSchau(await api.archiv.vorschau(profil, datei));
      setErgebnis(null);
    } catch (e: unknown) {
      melden(e, 'Das Archiv konnte nicht gelesen werden.');
    } finally {
      setLaeuft(false);
    }
  };

  const einspielen = async () => {
    if (!datei) return;
    setLaeuft(true);
    setFehler(null);
    try {
      setErgebnis(await api.archiv.einspielen(profil, datei, ersetzen));
    } catch (e: unknown) {
      melden(e, 'Der Import ist gescheitert.');
    } finally {
      setLaeuft(false);
    }
  };

  return (
    <section className="karte mb-4 p-4">
      <h2 className="flex items-center gap-2 font-medium text-stark">
        <Archive className="h-5 w-5 text-primary-custom" />
        Sicherung
      </h2>
      <p className="lesebreite mt-1 text-sm text-leise">
        Sichert Anzeigen mit Bildern, Vorlagen und die Bot-Einstellungen dieses Profils
        als ZIP. <span className="text-stark">Zugangsdaten, LLM-Schlüssel und das
        Browserprofil gehen nicht mit</span> – ein Archiv landet erfahrungsgemäß in
        einer Cloud.
      </p>

      <a
        href={api.archiv.exportUrl(profil)}
        className="btn-ghost mt-3 inline-flex"
        download
      >
        <Download className="h-4 w-4" aria-hidden />
        Archiv herunterladen
      </a>

      <hr className="my-4 border-t" style={{ borderColor: 'var(--karte-rand)' }} />

      <h3 className="text-sm font-medium text-stark">Archiv einspielen</h3>
      <p className="lesebreite mt-1 text-xs text-leise">
        Erst ansehen, dann einspielen. Vorhandene Dateien bleiben unangetastet, solange
        das Ersetzen nicht ausdrücklich eingeschaltet ist.
      </p>

      <label className="mt-3 block">
        <span className="sr-only">Archivdatei wählen</span>
        <input
          type="file"
          accept=".zip,application/zip"
          onChange={e => dateiWaehlen(e.target.files?.[0] ?? null)}
          className="feld block w-full cursor-pointer py-1.5 text-sm text-leise file:mr-3 file:cursor-pointer file:rounded file:border-0 file:bg-transparent file:px-2 file:py-1 file:text-sm file:font-medium file:text-primary-custom"
        />
      </label>

      {datei && (
        <div className="mt-3 flex flex-wrap items-center gap-2">
          <button
            type="button"
            onClick={() => void ansehen()}
            disabled={laeuft}
            className="btn-ghost disabled:cursor-not-allowed disabled:opacity-60"
          >
            {laeuft && !schau ? 'Liest …' : 'Ansehen'}
          </button>
          {schau && schau.dateien > 0 && !ergebnis && (
            <button
              type="button"
              onClick={() => void einspielen()}
              disabled={laeuft}
              className="btn-primaer disabled:cursor-not-allowed disabled:opacity-60"
            >
              <Upload className="h-4 w-4" aria-hidden />
              {laeuft ? 'Spielt ein …' : 'Einspielen'}
            </button>
          )}
        </div>
      )}

      {schau && !ergebnis && (
        <div className="mt-3 rounded border p-3" style={{ borderColor: 'var(--karte-rand)' }}>
          <p className="text-sm text-normal">
            {schau.dateien === 0
              ? 'Keine übernehmbare Datei im Archiv.'
              : `${schau.dateien} Datei(en): ${schau.anzeigen} Anzeige(n), ${schau.bilder} Bild(er).`}
          </p>
          {schau.doppelt.length > 0 && (
            <label htmlFor="archiv-ersetzen" className="mt-2 flex items-start gap-2">
              <input
                id="archiv-ersetzen"
                type="checkbox"
                checked={ersetzen}
                onChange={e => setErsetzen(e.target.checked)}
                className="mt-1 h-4 w-4"
              />
              <span className="text-xs text-normal">
                Die {schau.doppelt.length} bereits vorhandenen Dateien überschreiben.
                Lokale Änderungen daran gehen dabei verloren.
              </span>
            </label>
          )}
          <Pfadliste titel="Neu" pfade={schau.neu} />
          <Pfadliste titel="Schon vorhanden" pfade={schau.doppelt} />
          {schau.abgewiesen.length > 0 && (
            <>
              <p className="mt-2 flex items-center gap-1 text-xs font-medium text-stark">
                <AlertTriangle className="h-3.5 w-3.5" aria-hidden />
                Nicht übernommen ({schau.abgewiesen.length})
              </p>
              <ul className="mt-1 space-y-0.5">
                {schau.abgewiesen.slice(0, NAMEN_GRENZE).map(zeile => (
                  <li key={zeile} className="text-xs text-leise">{zeile}</li>
                ))}
              </ul>
            </>
          )}
        </div>
      )}

      {ergebnis && (
        <div className="mt-3 rounded border p-3" style={{ borderColor: 'var(--karte-rand)' }}>
          <p className="flex items-center gap-2 text-sm text-normal">
            <Check className="h-4 w-4" aria-hidden />
            {ergebnis.zusammenfassung}
          </p>
          <Pfadliste titel="Übernommen" pfade={ergebnis.geschrieben} />
          <Pfadliste titel="Ersetzt" pfade={ergebnis.ersetzt} />
          <Pfadliste titel="Übersprungen" pfade={ergebnis.uebersprungen} />
          <Pfadliste titel="Abgewiesen" pfade={ergebnis.abgewiesen} />
        </div>
      )}

      {fehler && (
        <p role="alert" className="hinweis hinweis-fehler lesebreite mt-3">{fehler}</p>
      )}
    </section>
  );
}
