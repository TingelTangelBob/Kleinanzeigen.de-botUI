// SPDX-FileCopyrightText: © Anzeigen-Studio contributors
// SPDX-License-Identifier: AGPL-3.0-or-later
//
// Anmeldung und Ersteinrichtung.
//
// Muster übernommen aus SoloOffice (AGPL-3.0-or-later); Texte und Ablauf an
// dieses Projekt angepasst.

import { useState, type FormEvent } from 'react';
import { ShieldCheck, Tag } from 'lucide-react';
import { useAuth } from '../context/useAuth';
import { ApiFehler } from '../services/api';

const MIN_PASSWORTLAENGE = 12;

export function AuthSeite({ einrichtung }: { einrichtung: boolean }) {
  const { anmelden, einrichten } = useAuth();
  const [name, setName] = useState('');
  const [passwort, setPasswort] = useState('');
  const [wiederholung, setWiederholung] = useState('');
  const [fehler, setFehler] = useState<string | null>(null);
  const [laeuft, setLaeuft] = useState(false);

  const absenden = async (ereignis: FormEvent) => {
    ereignis.preventDefault();
    setFehler(null);

    if (einrichtung && passwort !== wiederholung) {
      setFehler('Die beiden Passwörter stimmen nicht überein.');
      return;
    }

    setLaeuft(true);
    try {
      if (einrichtung) await einrichten(name, passwort);
      else await anmelden(name, passwort);
    } catch (ursache) {
      setFehler(ursache instanceof ApiFehler ? ursache.message : 'Unbekannter Fehler.');
    } finally {
      setLaeuft(false);
    }
  };

  const zuKurz = einrichtung && passwort.length > 0 && passwort.length < MIN_PASSWORTLAENGE;

  return (
    <div
      className="flex min-h-screen items-center justify-center px-4 py-10"
      style={{
        background: 'linear-gradient(165deg, var(--sidebar) 0%, #1b3d28 42%, var(--canvas) 42.1%)',
      }}
    >
      <div className="w-full max-w-md">
        <div className="mb-6 flex items-center gap-3">
          <span className="marke h-11 w-11" style={{ height: 44, width: 44, borderRadius: 12 }}>
            {einrichtung
              ? <ShieldCheck className="h-6 w-6" />
              : <Tag className="h-6 w-6" />}
          </span>
          <div>
            <h1 className="text-xl font-semibold tracking-tight text-white">Anzeigen-Studio</h1>
            <p className="text-sm" style={{ color: 'var(--sidebar-text)' }}>
              {einrichtung ? 'Erstes Konto anlegen' : 'Anmelden'}
            </p>
          </div>
        </div>

        <form onSubmit={absenden} className="karte p-6">
          {einrichtung && (
            <p className="hinweis hinweis-warn mb-5">
              Dieses Konto schützt die Oberfläche. Die Zugangsdaten für Kleinanzeigen
              werden später je Profil hinterlegt – das sind zwei verschiedene Dinge.
            </p>
          )}

          <label className="block">
            <span className="beschriftung">Benutzername</span>
            <input
              type="text"
              value={name}
              onChange={e => setName(e.target.value)}
              autoComplete="username"
              required
              className="feld mt-1"
            />
          </label>

          <label className="mt-4 block">
            <span className="beschriftung">Passwort</span>
            <input
              type="password"
              value={passwort}
              onChange={e => setPasswort(e.target.value)}
              autoComplete={einrichtung ? 'new-password' : 'current-password'}
              required
              className="feld mt-1"
            />
            {einrichtung && (
              <span className={`mt-1 block text-xs ${zuKurz ? 'text-red-700' : 'text-leise'}`}>
                Mindestens {MIN_PASSWORTLAENGE} Zeichen. Länge zählt mehr als Sonderzeichen.
              </span>
            )}
          </label>

          {einrichtung && (
            <label className="mt-4 block">
              <span className="beschriftung">Passwort wiederholen</span>
              <input
                type="password"
                value={wiederholung}
                onChange={e => setWiederholung(e.target.value)}
                autoComplete="new-password"
                required
                className="feld mt-1"
              />
            </label>
          )}

          {fehler && (
            <p role="alert" className="hinweis hinweis-fehler mt-4">
              {fehler}
            </p>
          )}

          <button
            type="submit"
            disabled={laeuft || zuKurz}
            className="btn-primaer mt-6 w-full"
          >
            {laeuft ? 'Bitte warten …' : einrichtung ? 'Konto anlegen' : 'Anmelden'}
          </button>
        </form>
      </div>
    </div>
  );
}
