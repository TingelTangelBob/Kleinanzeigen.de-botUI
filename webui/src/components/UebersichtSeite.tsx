// SPDX-FileCopyrightText: © Anzeigen-Studio contributors
// SPDX-License-Identifier: AGPL-3.0-or-later
//
// Übersicht: der erste Blick nach dem Anmelden (AP-2.3).
//
// Zeigt drei Dinge, und zwar in dieser Reihenfolge: Was ist mit dem Konto, was
// hat der Bot zuletzt getan, und was steht an. Alles andere gehört auf die
// Fachseiten. Eine Übersicht, die alles zeigt, zeigt nichts.

import { useCallback, useEffect, useState } from 'react';
import { AlertTriangle, ArrowRight, KeyRound } from 'lucide-react';
import { api, ApiFehler } from '../services/api';
import { useProfil } from '../context/useProfil';
import type { BestandsAnzeige, Job, ZugangStatus } from '../types';
import { AnzeigenZeile } from './AnzeigenZeile';
import type { Seite } from './Layout';

const ZUSTAND_TEXT: Record<string, string> = {
  wartet: 'wartet', laeuft: 'läuft', braucht_eingabe: 'braucht dich',
  fertig: 'fertig', pruefen: 'prüfen', gescheitert: 'gescheitert',
  abgebrochen: 'abgebrochen',
};

function zeitText(iso: string | null): string {
  if (!iso) return '';
  const zeitpunkt = new Date(iso);
  if (Number.isNaN(zeitpunkt.getTime())) return '';
  return zeitpunkt.toLocaleString('de-DE', {
    day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit',
  });
}

function Kachel({ zahl, label, betont }: { zahl: number; label: string; betont?: boolean }) {
  return (
    <div className={`rounded border p-3 ${betont && zahl > 0
      ? 'border-amber-300 bg-amber-50' : 'border-gray-200 bg-white'}`}
    >
      <div className="text-2xl font-semibold text-gray-900">{zahl}</div>
      <div className="text-xs text-gray-600">{label}</div>
    </div>
  );
}

export function UebersichtSeite({ aufSeite }: { aufSeite: (seite: Seite) => void }) {
  const { aktiv, laedt: profileLaden, fehler: profilFehler, neuLaden: profileNeuLaden } = useProfil();
  const [anzeigen, setAnzeigen] = useState<BestandsAnzeige[]>([]);
  const [jobs, setJobs] = useState<Job[]>([]);
  const [zugang, setZugang] = useState<ZugangStatus | null>(null);
  const [fehler, setFehler] = useState<string | null>(null);

  const laden = useCallback(async () => {
    if (!aktiv) return;
    setFehler(null);
    try {
      const [bestand, laeufe, zugangsdaten] = await Promise.all([
        api.bestand.liste(aktiv.slug),
        api.jobs.liste(aktiv.slug),
        api.profile.zugang(aktiv.slug),
      ]);
      setAnzeigen(bestand);
      setJobs(laeufe.slice(0, 5));
      setZugang(zugangsdaten);
    } catch (ursache) {
      setFehler(ursache instanceof ApiFehler ? ursache.message : 'Unbekannter Fehler.');
    }
  }, [aktiv]);

  useEffect(() => {
    void laden();
  }, [laden]);

  if (profileLaden) return <p className="text-sm text-gray-500">Wird geladen …</p>;

  // Eine Störung darf nicht als „noch kein Profil" erscheinen. Das sah aus wie
  // ein gültiger Zustand und verschwieg, dass ein Abruf fehlgeschlagen war.
  if (profilFehler) {
    return (
      <div className="mx-auto max-w-4xl">
        <h1 className="mb-4 text-2xl font-bold text-gray-900">Übersicht</h1>
        <p className="rounded border border-red-200 bg-red-50 p-4 text-sm text-red-800">
          Die Profile ließen sich nicht laden: {profilFehler}
        </p>
        <button
          type="button"
          onClick={() => void profileNeuLaden()}
          className="mt-3 rounded border border-gray-300 px-4 py-2 text-sm text-gray-700 hover:bg-gray-50"
        >
          Erneut versuchen
        </button>
      </div>
    );
  }

  if (!aktiv) {
    return (
      <div className="mx-auto max-w-4xl">
        <h1 className="mb-4 text-2xl font-bold text-gray-900">Übersicht</h1>
        <p className="rounded border border-amber-200 bg-amber-50 p-4 text-sm text-amber-900">
          Noch kein Profil angelegt. Ein Profil steht für ein Kleinanzeigen-Konto.
        </p>
        <button
          type="button"
          onClick={() => aufSeite('profile')}
          className="mt-3 rounded bg-primary-custom px-4 py-2 text-sm font-medium"
        >
          Profil anlegen
        </button>
      </div>
    );
  }

  const faellige = anzeigen.filter(a => a.faellig);
  const geaendert = anzeigen.filter(a => a.lokal_geaendert).length;
  const auffaellig = anzeigen.filter(a => a.hinweise.length > 0 || a.unlesbar).length;

  return (
    <div className="mx-auto max-w-4xl">
      <h1 className="mb-1 text-2xl font-bold text-gray-900">Übersicht</h1>
      <p className="mb-6 text-sm text-gray-600">{aktiv.anzeigename}</p>

      {fehler && (
        <p className="mb-4 rounded border border-red-200 bg-red-50 p-3 text-sm text-red-800">{fehler}</p>
      )}

      {!zugang?.passwort_hinterlegt && (
        <div className="mb-6 flex items-start gap-3 rounded border border-amber-200 bg-amber-50 p-4">
          <KeyRound className="mt-0.5 h-5 w-5 flex-shrink-0 text-amber-700" aria-hidden />
          <div className="min-w-0 flex-1">
            <p className="text-sm text-amber-900">
              Für dieses Profil sind keine Zugangsdaten hinterlegt. Ohne sie kann kein Lauf starten.
            </p>
            <button
              type="button"
              onClick={() => aufSeite('profile')}
              className="mt-2 text-sm font-medium text-amber-900 underline"
            >
              Zugangsdaten hinterlegen
            </button>
          </div>
        </div>
      )}

      <div className="mb-6 grid grid-cols-2 gap-3 sm:grid-cols-4">
        <Kachel zahl={anzeigen.length} label="Anzeigen" />
        <Kachel zahl={faellige.length} label="Fällig" betont />
        <Kachel zahl={geaendert} label="Lokal geändert" betont />
        <Kachel zahl={auffaellig} label="Mit Hinweis" betont />
      </div>

      <section className="mb-6">
        <div className="mb-2 flex items-center justify-between">
          <h2 className="font-semibold text-gray-900">Letzte Läufe</h2>
          <button
            type="button"
            onClick={() => aufSeite('jobs')}
            className="flex items-center gap-1 text-sm text-primary-custom"
          >
            Alle Läufe <ArrowRight className="h-4 w-4" aria-hidden />
          </button>
        </div>
        {jobs.length === 0 ? (
          <p className="rounded border border-gray-200 bg-white p-4 text-sm text-gray-600">
            Noch kein Lauf. Unter „Läufe" lässt sich einer starten.
          </p>
        ) : (
          <ul className="divide-y divide-gray-200 overflow-hidden rounded border border-gray-200 bg-white">
            {jobs.map(job => (
              <li key={job.id} className="flex items-center justify-between gap-3 px-3 py-2 text-sm">
                <span className="truncate text-gray-900">{job.befehl}</span>
                <span className="flex flex-shrink-0 items-center gap-3">
                  <span className="text-xs text-gray-500">{zeitText(job.eingereicht_am)}</span>
                  <span className="text-xs text-gray-700">{ZUSTAND_TEXT[job.zustand] ?? job.zustand}</span>
                </span>
              </li>
            ))}
          </ul>
        )}
      </section>

      <section>
        <div className="mb-2 flex items-center justify-between">
          <h2 className="font-semibold text-gray-900">Steht an</h2>
          <button
            type="button"
            onClick={() => aufSeite('bestand')}
            className="flex items-center gap-1 text-sm text-primary-custom"
          >
            Alle Anzeigen <ArrowRight className="h-4 w-4" aria-hidden />
          </button>
        </div>
        {faellige.length === 0 ? (
          <p className="rounded border border-gray-200 bg-white p-4 text-sm text-gray-600">
            Keine Anzeige ist zur Neueinstellung fällig.
          </p>
        ) : (
          <>
            {/* Bewusst ohne Zeitangabe der Plattform: Wann eine Anzeige dort
                abläuft, steht nicht in der heruntergeladenen Datei. Was hier
                zählt, ist der selbst eingestellte Abstand. */}
            <p className="mb-2 flex items-start gap-2 text-xs text-gray-600">
              <AlertTriangle className="mt-0.5 h-3.5 w-3.5 flex-shrink-0" aria-hidden />
              Fällig heißt: Der eingestellte Abstand zur letzten Veröffentlichung ist erreicht.
              Das Ablaufdatum der Plattform steht nicht in den heruntergeladenen Dateien.
            </p>
            <ul className="divide-y divide-gray-200 overflow-hidden rounded border border-gray-200 bg-white">
              {faellige.slice(0, 5).map(a => (
                <li key={a.datei}>
                  <AnzeigenZeile anzeige={a} profil={aktiv.slug} />
                </li>
              ))}
            </ul>
            {faellige.length > 5 && (
              <p className="mt-2 text-sm text-gray-600">und {faellige.length - 5} weitere</p>
            )}
          </>
        )}
      </section>
    </div>
  );
}
