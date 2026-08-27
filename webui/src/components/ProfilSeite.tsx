// SPDX-FileCopyrightText: © Anzeigen-Studio contributors
// SPDX-License-Identifier: AGPL-3.0-or-later
//
// Profile anlegen und Zugangsdaten hinterlegen (AP-2.1/2.10, AP-4.1).

import { useCallback, useEffect, useState, type FormEvent } from 'react';
import { KeyRound, Plus, Sparkles, Trash2, Users } from 'lucide-react';
import { api, ApiFehler } from '../services/api';
import type { KiStatus, Profil, ZugangStatus } from '../types';

export function ProfilSeite() {
  const [profile, setProfile] = useState<Profil[]>([]);
  const [zugaenge, setZugaenge] = useState<Record<string, ZugangStatus | null>>({});
  const [fehler, setFehler] = useState<string | null>(null);
  const [laedt, setLaedt] = useState(true);
  const [formOffen, setFormOffen] = useState(false);

  const laden = useCallback(async () => {
    setLaedt(true);
    try {
      const liste = await api.profile.liste();
      setProfile(liste);
      const paare = await Promise.all(
        liste.map(async p => [p.slug, await api.profile.zugang(p.slug)] as const),
      );
      setZugaenge(Object.fromEntries(paare));
      setFehler(null);
    } catch (ursache) {
      setFehler(ursache instanceof ApiFehler ? ursache.message : 'Unbekannter Fehler.');
    } finally {
      setLaedt(false);
    }
  }, []);

  useEffect(() => { void laden(); }, [laden]);

  return (
    <div className="mx-auto max-w-3xl">
      <div className="mb-6 flex flex-wrap items-center justify-between gap-3">
        <h1 className="flex items-center gap-2 text-2xl font-bold text-gray-900">
          <Users className="h-6 w-6 text-primary-custom" />
          Profile
        </h1>
        <button
          type="button"
          onClick={() => setFormOffen(o => !o)}
          className="flex items-center gap-2 rounded bg-primary-custom px-4 py-2 text-sm font-medium"
        >
          <Plus className="h-4 w-4" />
          Profil anlegen
        </button>
      </div>

      <p className="mb-6 rounded border border-amber-200 bg-amber-50 p-3 text-sm text-amber-900">
        Ein Profil steht für ein Kleinanzeigen-Konto. Die Zugangsdaten werden verschlüsselt
        gespeichert und nur beim Start eines Laufs an den Bot gereicht – sie stehen nie im
        Klartext auf der Platte.
      </p>

      {fehler && (
        <p role="alert" className="mb-4 rounded border border-red-200 bg-red-50 p-3 text-sm text-red-800">
          {fehler}
        </p>
      )}

      {formOffen && <NeuesProfil aufFertig={() => { setFormOffen(false); void laden(); }} />}

      {laedt && <p className="text-sm text-gray-500">Wird geladen …</p>}

      {!laedt && profile.length === 0 && !formOffen && (
        <p className="rounded border border-gray-200 bg-white p-6 text-center text-sm text-gray-600">
          Noch kein Profil angelegt.
        </p>
      )}

      <div className="space-y-4">
        {profile.map(profil => (
          <ProfilKarte
            key={profil.slug}
            profil={profil}
            zugang={zugaenge[profil.slug] ?? null}
            aufAenderung={laden}
          />
        ))}
      </div>

      <KiZugang />
    </div>
  );
}

/**
 * Der Schlüssel zum KI-Anbieter (AP-4.1).
 *
 * Steht unter den Profilen und nicht in einem davon: Er gehört dem Betreiber
 * dieser Installation, nicht einem Kleinanzeigen-Konto. Zwei Profile teilen
 * sich denselben Schlüssel.
 */
function KiZugang() {
  const [status, setStatus] = useState<KiStatus | null>(null);
  const [eingabe, setEingabe] = useState('');
  const [laeuft, setLaeuft] = useState(false);
  const [fehler, setFehler] = useState<string | null>(null);

  const laden = useCallback(async () => {
    try {
      setStatus(await api.ki.status());
    } catch {
      setStatus(null);
    }
  }, []);

  useEffect(() => { void laden(); }, [laden]);

  const speichern = async (ereignis: FormEvent) => {
    ereignis.preventDefault();
    setFehler(null);
    setLaeuft(true);
    try {
      setStatus(await api.ki.schluesselSetzen(eingabe));
      // Sofort aus dem Speicher der Oberfläche entfernen. Er liegt danach
      // verschlüsselt im Backend; im Browser hat er nichts mehr zu suchen.
      setEingabe('');
    } catch (ursache) {
      setFehler(ursache instanceof ApiFehler ? ursache.message : 'Unbekannter Fehler.');
    } finally {
      setLaeuft(false);
    }
  };

  const entfernen = async () => {
    setFehler(null);
    try {
      setStatus(await api.ki.schluesselEntfernen());
    } catch (ursache) {
      setFehler(ursache instanceof ApiFehler ? ursache.message : 'Unbekannter Fehler.');
    }
  };

  return (
    <section className="mt-8 rounded border border-gray-200 bg-white p-4">
      <h2 className="flex items-center gap-2 font-medium text-gray-900">
        <Sparkles className="h-5 w-5 text-primary-custom" />
        KI-Zugang
      </h2>
      <p className="mt-1 text-sm text-gray-600">
        Gilt für die ganze Installation, nicht für ein einzelnes Profil. Ohne ihn bleibt
        „Neue Anzeige aus Fotos“ aus.
      </p>

      {status && (
        <p className="mt-3 text-sm text-gray-700">
          Modell: <span className="font-mono text-xs">{status.modell}</span>
          {status.hinterlegt ? (
            <>
              {' · Schlüssel hinterlegt'}
              {status.endet_auf && <> (endet auf <span className="font-mono text-xs">…{status.endet_auf}</span>)</>}
            </>
          ) : ' · kein Schlüssel hinterlegt'}
        </p>
      )}

      {fehler && (
        <p role="alert" className="mt-3 rounded border border-red-200 bg-red-50 p-2 text-sm text-red-800">
          {fehler}
        </p>
      )}

      <form onSubmit={ereignis => void speichern(ereignis)} className="mt-3 flex flex-col gap-2 sm:flex-row">
        <input
          type="password"
          value={eingabe}
          onChange={ereignis => setEingabe(ereignis.target.value)}
          placeholder={status?.hinterlegt ? 'Neuen Schlüssel eintragen' : 'OpenAI-Schlüssel einfügen'}
          aria-label="OpenAI-Schlüssel"
          autoComplete="off"
          className="min-w-0 flex-1 rounded border border-gray-300 px-3 py-2 font-mono text-sm"
        />
        <button
          type="submit"
          disabled={laeuft || !eingabe.trim()}
          className="rounded bg-primary-custom px-4 py-2 text-sm font-medium text-white disabled:opacity-40"
        >
          {laeuft ? 'Wird gespeichert …' : 'Speichern'}
        </button>
        {status?.hinterlegt && (
          <button
            type="button"
            onClick={() => void entfernen()}
            className="rounded border border-gray-300 px-4 py-2 text-sm text-gray-700"
          >
            Entfernen
          </button>
        )}
      </form>
      <p className="mt-2 text-xs text-gray-500">
        Wird verschlüsselt gespeichert, genau wie die Kleinanzeigen-Zugangsdaten, und nie
        im Protokoll ausgegeben.
      </p>
    </section>
  );
}

function NeuesProfil({ aufFertig }: { aufFertig: () => void }) {
  const [slug, setSlug] = useState('');
  const [anzeigename, setAnzeigename] = useState('');
  const [fehler, setFehler] = useState<string | null>(null);
  const [laeuft, setLaeuft] = useState(false);

  const absenden = async (e: FormEvent) => {
    e.preventDefault();
    setLaeuft(true);
    setFehler(null);
    try {
      await api.profile.anlegen(slug, anzeigename);
      aufFertig();
    } catch (ursache) {
      setFehler(ursache instanceof ApiFehler ? ursache.message : 'Unbekannter Fehler.');
    } finally {
      setLaeuft(false);
    }
  };

  return (
    <form onSubmit={absenden} className="mb-6 rounded border border-gray-200 bg-white p-4">
      <div className="grid gap-4 sm:grid-cols-2">
        <label className="block">
          <span className="text-sm font-medium text-gray-700">Kürzel</span>
          <input
            value={slug}
            onChange={e => setSlug(e.target.value)}
            placeholder="haushalt"
            required
            className="mt-1 w-full rounded border border-gray-300 px-3 py-2
                       focus:border-primary-custom focus:outline-none focus:ring-1 focus:ring-primary-custom"
          />
          <span className="mt-1 block text-xs text-gray-500">
            Kleinbuchstaben, Ziffern, Bindestriche. Wird zum Verzeichnisnamen und ist
            danach unveränderlich.
          </span>
        </label>
        <label className="block">
          <span className="text-sm font-medium text-gray-700">Anzeigename</span>
          <input
            value={anzeigename}
            onChange={e => setAnzeigename(e.target.value)}
            placeholder="Haushaltsauflösung"
            required
            className="mt-1 w-full rounded border border-gray-300 px-3 py-2
                       focus:border-primary-custom focus:outline-none focus:ring-1 focus:ring-primary-custom"
          />
        </label>
      </div>
      {fehler && <p role="alert" className="mt-3 text-sm text-red-700">{fehler}</p>}
      <button
        type="submit"
        disabled={laeuft}
        className="mt-4 rounded bg-primary-custom px-4 py-2 text-sm font-medium disabled:opacity-50"
      >
        {laeuft ? 'Wird angelegt …' : 'Anlegen'}
      </button>
    </form>
  );
}

function ProfilKarte({
  profil, zugang, aufAenderung,
}: { profil: Profil; zugang: ZugangStatus | null; aufAenderung: () => void }) {
  const [offen, setOffen] = useState(false);

  return (
    <div className="rounded border border-gray-200 bg-white p-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <h2 className="truncate font-medium text-gray-900">{profil.anzeigename}</h2>
          <p className="text-sm text-gray-500">Kürzel: {profil.slug}</p>
          <p className="mt-1 text-sm">
            {zugang?.passwort_hinterlegt ? (
              <span className="text-green-800">
                Zugang hinterlegt: {zugang.benutzername}
              </span>
            ) : (
              <span className="text-amber-800">Noch kein Kleinanzeigen-Zugang hinterlegt</span>
            )}
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <button
            type="button"
            onClick={() => setOffen(o => !o)}
            className="flex items-center gap-2 rounded border border-gray-300 px-3 py-2 text-sm text-gray-700 hover:bg-gray-50"
          >
            <KeyRound className="h-4 w-4" />
            Zugang
          </button>
          <ProfilLoeschen slug={profil.slug} aufAenderung={aufAenderung} />
        </div>
      </div>

      {offen && (
        <ZugangForm
          slug={profil.slug}
          vorhanden={zugang}
          aufFertig={() => { setOffen(false); aufAenderung(); }}
        />
      )}
    </div>
  );
}

function ZugangForm({
  slug, vorhanden, aufFertig,
}: { slug: string; vorhanden: ZugangStatus | null; aufFertig: () => void }) {
  const [benutzername, setBenutzername] = useState(vorhanden?.benutzername ?? '');
  const [passwort, setPasswort] = useState('');
  const [fehler, setFehler] = useState<string | null>(null);
  const [laeuft, setLaeuft] = useState(false);

  const absenden = async (e: FormEvent) => {
    e.preventDefault();
    setLaeuft(true);
    setFehler(null);
    try {
      // Leeres Feld heißt: vorhandenes Passwort behalten. So lässt sich der
      // Benutzername korrigieren, ohne das Passwort erneut einzugeben.
      await api.profile.zugangSetzen(slug, benutzername, passwort === '' ? null : passwort);
      aufFertig();
    } catch (ursache) {
      setFehler(ursache instanceof ApiFehler ? ursache.message : 'Unbekannter Fehler.');
    } finally {
      setLaeuft(false);
    }
  };

  return (
    <form onSubmit={absenden} className="mt-4 border-t border-gray-200 pt-4">
      <div className="grid gap-4 sm:grid-cols-2">
        <label className="block">
          <span className="text-sm font-medium text-gray-700">Kleinanzeigen-Benutzername</span>
          <input
            type="email"
            value={benutzername}
            onChange={e => setBenutzername(e.target.value)}
            autoComplete="off"
            required
            className="mt-1 w-full rounded border border-gray-300 px-3 py-2
                       focus:border-primary-custom focus:outline-none focus:ring-1 focus:ring-primary-custom"
          />
        </label>
        <label className="block">
          <span className="text-sm font-medium text-gray-700">Passwort</span>
          <input
            type="password"
            value={passwort}
            onChange={e => setPasswort(e.target.value)}
            autoComplete="new-password"
            placeholder={vorhanden?.passwort_hinterlegt ? 'unverändert lassen' : ''}
            required={!vorhanden?.passwort_hinterlegt}
            className="mt-1 w-full rounded border border-gray-300 px-3 py-2
                       focus:border-primary-custom focus:outline-none focus:ring-1 focus:ring-primary-custom"
          />
          {vorhanden?.passwort_hinterlegt && (
            <span className="mt-1 block text-xs text-gray-500">
              Leer lassen, um das gespeicherte Passwort zu behalten.
            </span>
          )}
        </label>
      </div>
      {fehler && <p role="alert" className="mt-3 text-sm text-red-700">{fehler}</p>}
      <button
        type="submit"
        disabled={laeuft}
        className="mt-4 rounded bg-primary-custom px-4 py-2 text-sm font-medium disabled:opacity-50"
      >
        {laeuft ? 'Wird gespeichert …' : 'Speichern'}
      </button>
    </form>
  );
}

function ProfilLoeschen({ slug, aufAenderung }: { slug: string; aufAenderung: () => void }) {
  const [frage, setFrage] = useState(false);
  const [laeuft, setLaeuft] = useState(false);

  const loeschen = async (mitDaten: boolean) => {
    setLaeuft(true);
    try {
      await api.profile.loeschen(slug, mitDaten);
      aufAenderung();
    } finally {
      setLaeuft(false);
      setFrage(false);
    }
  };

  if (!frage) {
    return (
      <button
        type="button"
        onClick={() => setFrage(true)}
        className="flex items-center gap-2 rounded border border-gray-300 px-3 py-2 text-sm text-red-700 hover:bg-red-50"
      >
        <Trash2 className="h-4 w-4" />
        Löschen
      </button>
    );
  }

  // Bewusst zweistufig und mit ausdrücklicher Unterscheidung: Der
  // Anzeigenbestand ist das Wertvollste am Profil. Datenverlust darf kein
  // Nebeneffekt eines Klicks sein.
  return (
    <div className="w-full rounded border border-red-200 bg-red-50 p-3">
      <p className="mb-3 text-sm text-red-900">
        Profil <strong>{slug}</strong> löschen?
      </p>
      <div className="flex flex-wrap gap-2">
        <button
          type="button"
          disabled={laeuft}
          onClick={() => void loeschen(false)}
          className="rounded border border-gray-300 bg-white px-3 py-2 text-sm text-gray-800 disabled:opacity-50"
        >
          Nur Profil, Anzeigen behalten
        </button>
        <button
          type="button"
          disabled={laeuft}
          onClick={() => void loeschen(true)}
          className="rounded bg-red-700 px-3 py-2 text-sm font-medium text-white disabled:opacity-50"
        >
          Profil und alle Anzeigen löschen
        </button>
        <button
          type="button"
          disabled={laeuft}
          onClick={() => setFrage(false)}
          className="rounded px-3 py-2 text-sm text-gray-700"
        >
          Abbrechen
        </button>
      </div>
    </div>
  );
}
