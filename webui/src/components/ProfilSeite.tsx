// SPDX-FileCopyrightText: © Anzeigen-Studio contributors
// SPDX-License-Identifier: AGPL-3.0-or-later
//
// Profile anlegen und Zugangsdaten hinterlegen (AP-2.1/2.10, AP-4.1).

import { useCallback, useEffect, useState, type FormEvent } from 'react';
import { KeyRound, Plus, Sparkles, Trash2, Users } from 'lucide-react';
import { api, ApiFehler } from '../services/api';
import type { KiStatus, Profil, ZugangStatus } from '../types';

export function ProfilSeite({ ohneTitel = false }: { ohneTitel?: boolean } = {}) {
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
    <div className="seite">
      <div className="mb-6 flex flex-wrap items-center justify-between gap-3">
        {!ohneTitel && (
          <h1 className="seite-titel flex items-center gap-2">
            <Users className="h-5 w-5 text-primary-custom" />
            Profile
          </h1>
        )}
        {ohneTitel && <p className="seite-beschrieb m-0">Kleinanzeigen-Konten dieser Installation.</p>}
        <button
          type="button"
          onClick={() => setFormOffen(o => !o)}
          className="btn-primaer"
        >
          <Plus className="h-4 w-4" />
          Profil anlegen
        </button>
      </div>

      <p className="mb-6 hinweis hinweis-warn">
        Ein Profil steht für ein Kleinanzeigen-Konto. Die Zugangsdaten werden verschlüsselt
        gespeichert und nur beim Start eines Laufs an den Bot gereicht – sie stehen nie im
        Klartext auf der Platte.
      </p>

      {fehler && (
        <p role="alert" className="mb-4 hinweis hinweis-fehler">
          {fehler}
        </p>
      )}

      {formOffen && <NeuesProfil aufFertig={() => { setFormOffen(false); void laden(); }} />}

      {laedt && <p className="text-sm text-leise">Wird geladen …</p>}

      {!laedt && profile.length === 0 && !formOffen && (
        <p className="leer">
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
    <section className="mt-8 karte p-4">
      <h2 className="flex items-center gap-2 font-medium text-stark">
        <Sparkles className="h-5 w-5 text-primary-custom" />
        KI-Zugang
      </h2>
      <p className="mt-1 text-sm text-leise">
        Gilt für die ganze Installation, nicht für ein einzelnes Profil. Ohne ihn bleibt
        „Neue Anzeige aus Fotos“ aus.
      </p>

      {status && (
        <p className="mt-3 text-sm text-normal">
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
        <p role="alert" className="mt-3 hinweis hinweis-fehler">
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
          className="feld min-w-0 flex-1 font-mono"
        />
        <button
          type="submit"
          disabled={laeuft || !eingabe.trim()}
          className="btn-primaer"
        >
          {laeuft ? 'Wird gespeichert …' : 'Speichern'}
        </button>
        {status?.hinterlegt && (
          <button
            type="button"
            onClick={() => void entfernen()}
            className="btn-ghost"
          >
            Entfernen
          </button>
        )}
      </form>
      <p className="mt-2 text-xs text-leise">
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
    <form onSubmit={absenden} className="mb-6 karte p-4">
      <div className="grid gap-4 sm:grid-cols-2">
        <label className="block">
          <span className="text-sm font-medium text-normal">Kürzel</span>
          <input
            value={slug}
            onChange={e => setSlug(e.target.value)}
            placeholder="haushalt"
            required
            className="feld mt-1"
          />
          <span className="mt-1 block text-xs text-leise">
            Kleinbuchstaben, Ziffern, Bindestriche. Wird zum Verzeichnisnamen und ist
            danach unveränderlich.
          </span>
        </label>
        <label className="block">
          <span className="text-sm font-medium text-normal">Anzeigename</span>
          <input
            value={anzeigename}
            onChange={e => setAnzeigename(e.target.value)}
            placeholder="Haushaltsauflösung"
            required
            className="feld mt-1"
          />
        </label>
      </div>
      {fehler && <p role="alert" className="mt-3 text-sm text-red-700">{fehler}</p>}
      <button
        type="submit"
        disabled={laeuft}
        className="mt-4 btn-primaer"
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
    <div className="karte p-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <h2 className="truncate font-medium text-stark">{profil.anzeigename}</h2>
          <p className="text-sm text-leise">Kürzel: {profil.slug}</p>
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
            className="btn-ghost"
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
    <form onSubmit={absenden} className="mt-4 pt-4" style={{ borderTop: '1px solid var(--karte-rand)' }}>
      <div className="grid gap-4 sm:grid-cols-2">
        <label className="block">
          <span className="text-sm font-medium text-normal">Kleinanzeigen-Benutzername</span>
          <input
            type="email"
            value={benutzername}
            onChange={e => setBenutzername(e.target.value)}
            autoComplete="off"
            required
            className="feld mt-1"
          />
        </label>
        <label className="block">
          <span className="text-sm font-medium text-normal">Passwort</span>
          <input
            type="password"
            value={passwort}
            onChange={e => setPasswort(e.target.value)}
            autoComplete="new-password"
            placeholder={vorhanden?.passwort_hinterlegt ? 'unverändert lassen' : ''}
            required={!vorhanden?.passwort_hinterlegt}
            className="feld mt-1"
          />
          {vorhanden?.passwort_hinterlegt && (
            <span className="mt-1 block text-xs text-leise">
              Leer lassen, um das gespeicherte Passwort zu behalten.
            </span>
          )}
        </label>
      </div>
      {fehler && <p role="alert" className="mt-3 text-sm text-red-700">{fehler}</p>}
      <button
        type="submit"
        disabled={laeuft}
        className="mt-4 btn-primaer"
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
        className="btn-ghost"
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
    <div className="hinweis hinweis-fehler w-full">
      <p className="mb-3 text-sm text-red-900">
        Profil <strong>{slug}</strong> löschen?
      </p>
      <div className="flex flex-wrap gap-2">
        <button
          type="button"
          disabled={laeuft}
          onClick={() => void loeschen(false)}
          className="btn-ghost"
        >
          Nur Profil, Anzeigen behalten
        </button>
        <button
          type="button"
          disabled={laeuft}
          onClick={() => void loeschen(true)}
          className="btn-primaer"
        >
          Profil und alle Anzeigen löschen
        </button>
        <button
          type="button"
          disabled={laeuft}
          onClick={() => setFrage(false)}
          className="rounded px-3 py-2 text-sm text-normal"
        >
          Abbrechen
        </button>
      </div>
    </div>
  );
}
