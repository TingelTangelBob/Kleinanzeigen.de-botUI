// SPDX-FileCopyrightText: © Anzeigen-Studio contributors
// SPDX-License-Identifier: AGPL-3.0-or-later
//
// Anmeldung und Ersteinrichtung.
//
// Muster übernommen aus SoloOffice (AGPL-3.0-or-later); Texte und Ablauf an
// dieses Projekt angepasst.

import { useState, type FormEvent } from 'react';
import { KeyRound, ShieldCheck } from 'lucide-react';
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
    <div className="flex min-h-screen items-center justify-center bg-gray-50 px-4 py-10">
      <div className="w-full max-w-md">
        <div className="mb-6 flex items-center gap-3">
          <span className="flex h-11 w-11 items-center justify-center rounded-lg bg-primary-custom">
            {einrichtung
              ? <ShieldCheck className="h-6 w-6 text-white" />
              : <KeyRound className="h-6 w-6 text-white" />}
          </span>
          <div>
            <h1 className="text-xl font-semibold text-gray-900">Anzeigen-Studio</h1>
            <p className="text-sm text-gray-600">
              {einrichtung ? 'Erstes Konto anlegen' : 'Anmelden'}
            </p>
          </div>
        </div>

        <form onSubmit={absenden} className="rounded-lg border border-gray-200 bg-white p-6 shadow-sm">
          {einrichtung && (
            <p className="mb-5 rounded border border-amber-200 bg-amber-50 p-3 text-sm text-amber-900">
              Dieses Konto schützt die Oberfläche. Die Zugangsdaten für Kleinanzeigen
              werden später je Profil hinterlegt – das sind zwei verschiedene Dinge.
            </p>
          )}

          <label className="block">
            <span className="text-sm font-medium text-gray-700">Benutzername</span>
            <input
              type="text"
              value={name}
              onChange={e => setName(e.target.value)}
              autoComplete="username"
              required
              className="mt-1 w-full rounded border border-gray-300 px-3 py-2 text-gray-900
                         focus:border-primary-custom focus:outline-none focus:ring-1 focus:ring-primary-custom"
            />
          </label>

          <label className="mt-4 block">
            <span className="text-sm font-medium text-gray-700">Passwort</span>
            <input
              type="password"
              value={passwort}
              onChange={e => setPasswort(e.target.value)}
              autoComplete={einrichtung ? 'new-password' : 'current-password'}
              required
              className="mt-1 w-full rounded border border-gray-300 px-3 py-2 text-gray-900
                         focus:border-primary-custom focus:outline-none focus:ring-1 focus:ring-primary-custom"
            />
            {einrichtung && (
              <span className={`mt-1 block text-xs ${zuKurz ? 'text-red-700' : 'text-gray-500'}`}>
                Mindestens {MIN_PASSWORTLAENGE} Zeichen. Länge zählt mehr als Sonderzeichen.
              </span>
            )}
          </label>

          {einrichtung && (
            <label className="mt-4 block">
              <span className="text-sm font-medium text-gray-700">Passwort wiederholen</span>
              <input
                type="password"
                value={wiederholung}
                onChange={e => setWiederholung(e.target.value)}
                autoComplete="new-password"
                required
                className="mt-1 w-full rounded border border-gray-300 px-3 py-2 text-gray-900
                           focus:border-primary-custom focus:outline-none focus:ring-1 focus:ring-primary-custom"
              />
            </label>
          )}

          {fehler && (
            <p role="alert" className="mt-4 rounded border border-red-200 bg-red-50 p-3 text-sm text-red-800">
              {fehler}
            </p>
          )}

          <button
            type="submit"
            disabled={laeuft || zuKurz}
            className="mt-6 w-full rounded bg-primary-custom px-4 py-2 font-medium text-white
                       transition-opacity hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-50"
          >
            {laeuft ? 'Bitte warten …' : einrichtung ? 'Konto anlegen' : 'Anmelden'}
          </button>
        </form>
      </div>
    </div>
  );
}
