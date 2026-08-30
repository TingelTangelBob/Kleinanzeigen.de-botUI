// SPDX-FileCopyrightText: © Anzeigen-Studio contributors
// SPDX-License-Identifier: AGPL-3.0-or-later
//
// Anzeigeneditor (AP-2.5).
//
// Die Grenzen kommen aus dem Upstream-Schema (`schemas/ad.schema.json`) und
// stehen hier als Konstanten: Titel 10 bis 65 Zeichen, die Aufzählungen für
// Art, Preistyp und Versandart. Sie doppelt zu führen wäre falsch - deshalb
// prüft am Ende immer das Modell des Bots, nicht dieses Formular. Was hier
// steht, ist Bedienhilfe, nicht Wahrheit.
//
// Zwei Dinge muss dieser Editor sagen, sonst führt er in die Irre (AP-3.4):
// dass ein späterer Download die Änderung überschreibt, und was dem
// Veröffentlichen im Weg steht.

import { useCallback, useEffect, useState } from 'react';
import { AlertTriangle, ArrowLeft, ArrowUpFromLine, BookmarkPlus, Check, Copy, Info, Save } from 'lucide-react';
import { api, ApiFehler } from '../services/api';
import type { AnzeigeInhalt } from '../types';
import { BilderVerwaltung } from './BilderVerwaltung';
import { HochladenDialog } from './HochladenDialog';
import { KategorieWahl } from './KategorieWahl';
import { VersandpaketWahl } from './VersandpaketWahl';

const TITEL_MIN = 10;
const TITEL_MAX = 65;

const ARTEN = [
  { wert: 'OFFER', label: 'Angebot' },
  { wert: 'WANTED', label: 'Gesuch' },
];

const PREISTYPEN = [
  { wert: 'FIXED', label: 'Festpreis' },
  { wert: 'NEGOTIABLE', label: 'Verhandlungsbasis' },
  { wert: 'GIVE_AWAY', label: 'Zu verschenken' },
  { wert: 'NOT_APPLICABLE', label: 'Kein Preis' },
];

const VERSANDARTEN = [
  { wert: 'SHIPPING', label: 'Versand möglich' },
  { wert: 'PICKUP', label: 'Nur Abholung' },
  { wert: 'NOT_APPLICABLE', label: 'Nicht zutreffend' },
];

type Felder = Record<string, unknown>;

function text(wert: unknown): string {
  if (wert === null || wert === undefined) return '';
  return String(wert);
}

function zahlOderNull(roh: string): number | null {
  if (roh.trim() === '') return null;
  const wert = Number(roh.replace(',', '.'));
  return Number.isFinite(wert) ? wert : null;
}

interface Props {
  profil: string;
  datei: string;
  aufZurueck: (geaendert: boolean) => void;
  /** Wird nach dem Duplizieren mit der Datei der Kopie gerufen (AP-3.3). */
  aufKopie?: (datei: string) => void;
}

export function AnzeigenEditor({ profil, datei, aufZurueck, aufKopie }: Props) {
  const [inhalt, setInhalt] = useState<AnzeigeInhalt | null>(null);
  const [felder, setFelder] = useState<Felder>({});
  const [fehler, setFehler] = useState<string | null>(null);
  const [hinweise, setHinweise] = useState<string[]>([]);
  const [gespeichert, setGespeichert] = useState(false);
  const [speichert, setSpeichert] = useState(false);
  const [schmutzig, setSchmutzig] = useState(false);
  const [fragtHochladen, setFragtHochladen] = useState(false);
  const [dupliziert, setDupliziert] = useState(false);
  const [wirdVorlage, setWirdVorlage] = useState(false);
  const [vorlageAngelegt, setVorlageAngelegt] = useState(false);
  const [laedtHoch, setLaedtHoch] = useState(false);
  const [eingereiht, setEingereiht] = useState<number | null>(null);

  const laden = useCallback(async () => {
    setFehler(null);
    try {
      const geladen = await api.bestand.anzeige(profil, datei);
      setInhalt(geladen);
      setFelder({ ...geladen.felder });
    } catch (ursache) {
      setFehler(ursache instanceof ApiFehler ? ursache.message : 'Unbekannter Fehler.');
    }
  }, [profil, datei]);

  useEffect(() => {
    void laden();
  }, [laden]);

  const setzen = (feld: string, wert: unknown) => {
    setFelder(vorher => ({ ...vorher, [feld]: wert }));
    setSchmutzig(true);
    setGespeichert(false);
  };

  // Bilder wirken sofort (AP-2.6). Deshalb wandert die neue Liste in beide
  // Staende: in den bearbeiteten und in den Vergleichsstand. Sonst haelte der
  // Editor sie fuer eine ungespeicherte Aenderung und boete an, sie noch
  // einmal zu schreiben.
  const bilderAktualisiert = (neuBilder: string[]) => {
    setFelder(vorher => ({ ...vorher, images: neuBilder }));
    setInhalt(vorher => (vorher
      ? { ...vorher, felder: { ...vorher.felder, images: neuBilder } }
      : vorher));
  };

  const kontaktSetzen = (feld: string, wert: string) => {
    const kontakt = { ...(felder.contact as Record<string, unknown> ?? {}) };
    kontakt[feld] = wert === '' ? null : wert;
    setzen('contact', kontakt);
  };

  const speichern = async () => {
    if (!inhalt) return;
    setSpeichert(true);
    setFehler(null);
    try {
      // Nur wirklich Geändertes schicken. Alles zu senden schriebe auch
      // unberührte Felder neu - aus 3.0 würde 3, aus einer Liste eine andere
      // Schreibweise. Die Datei gehört auch der Kommandozeile; sie soll sich
      // nur dort ändern, wo jemand etwas geändert hat.
      const geaendert = Object.fromEntries(
        Object.entries(felder).filter(([k, v]) =>
          inhalt.aenderbar.includes(k)
          && JSON.stringify(v) !== JSON.stringify(inhalt.felder[k])),
      );
      if (Object.keys(geaendert).length === 0) {
        setSchmutzig(false);
        setGespeichert(true);
        return;
      }
      const ergebnis = await api.bestand.speichern(profil, datei, geaendert);
      // Der gespeicherte Stand ist ab jetzt der Vergleichsstand.
      setInhalt({ ...inhalt, kopf: ergebnis.kopf, felder: { ...felder } });
      setHinweise(ergebnis.hinweise);
      setGespeichert(true);
      setSchmutzig(false);
    } catch (ursache) {
      setFehler(ursache instanceof ApiFehler ? ursache.message : 'Unbekannter Fehler.');
    } finally {
      setSpeichert(false);
    }
  };

  // Duplizieren kopiert den GESPEICHERTEN Stand, nicht den im Formular. Das
  // ist der Grund fuer die Sperre bei ungespeicherten Aenderungen: Eine Kopie,
  // die anders aussieht als das, was auf dem Bildschirm steht, waere eine
  // Ueberraschung.
  const duplizieren = async () => {
    if (!profil) return;
    setDupliziert(true);
    try {
      const kopie = await api.bestand.duplizieren(profil, datei);
      // Direkt in die Kopie wechseln: Wer dupliziert, will sie bearbeiten -
      // Titel und Preis stimmen ja noch nicht.
      if (aufKopie) {
        aufKopie(kopie.datei);
      } else {
        aufZurueck(true);
      }
    } catch (ursache) {
      setFehler(ursache instanceof ApiFehler ? ursache.message : 'Unbekannter Fehler.');
    } finally {
      setDupliziert(false);
    }
  };

  // Wie beim Duplizieren wird der GESPEICHERTE Stand genommen, nicht der im
  // Formular - deshalb dieselbe Sperre bei ungespeicherten Aenderungen.
  //
  // Anders als beim Duplizieren wird hier NICHT gewechselt: Eine Vorlage ist
  // nichts, was man anschliessend bearbeitet, sondern etwas, das man spaeter
  // anwendet. Die Anzeige bleibt offen, ein Hinweis bestaetigt den Vorgang.
  const alsVorlage = async () => {
    if (!profil) return;
    setWirdVorlage(true);
    try {
      await api.bestand.alsVorlage(profil, datei);
      setVorlageAngelegt(true);
    } catch (ursache) {
      setFehler(ursache instanceof ApiFehler ? ursache.message : 'Unbekannter Fehler.');
    } finally {
      setWirdVorlage(false);
    }
  };

  // Hochladen ist der erste Vorgang, der etwas auf der Plattform veraendert -
  // deshalb erst die Rueckfrage, dann der Lauf.
  const hochladen = async () => {
    setLaedtHoch(true);
    setFehler(null);
    try {
      const ergebnis = await api.bestand.hochladen(profil, datei);
      setEingereiht(ergebnis.job_id);
      setFragtHochladen(false);
    } catch (ursache) {
      setFehler(ursache instanceof ApiFehler ? ursache.message : 'Unbekannter Fehler.');
      setFragtHochladen(false);
    } finally {
      setLaedtHoch(false);
    }
  };

  if (fehler && !inhalt) {
    return (
      <div className="mx-auto max-w-3xl">
        <button type="button" onClick={() => aufZurueck(false)} className="mb-4 flex items-center gap-1 text-sm text-gray-700">
          <ArrowLeft className="h-4 w-4" aria-hidden /> Zurück zur Liste
        </button>
        <p className="rounded border border-red-200 bg-red-50 p-3 text-sm text-red-800">{fehler}</p>
      </div>
    );
  }

  if (!inhalt) return <p className="text-sm text-gray-500">Wird geladen …</p>;

  const titel = text(felder.title);
  const titelZuKurz = titel.length > 0 && titel.length < TITEL_MIN;
  const bilder = (felder.images as string[] | null) ?? [];
  const sonderfelder = (felder.special_attributes as Record<string, unknown> | null) ?? {};
  const kontakt = (felder.contact as Record<string, unknown> | null) ?? {};

  return (
    <div className="mx-auto max-w-3xl pb-24">
      <button
        type="button"
        onClick={() => aufZurueck(schmutzig || gespeichert)}
        className="mb-4 flex items-center gap-1 text-sm text-gray-700 hover:text-gray-900"
      >
        <ArrowLeft className="h-4 w-4" aria-hidden /> Zurück zur Liste
      </button>

      <h1 className="mb-1 text-2xl font-bold text-gray-900">Anzeige bearbeiten</h1>
      <p className="mb-6 text-sm text-gray-600">
        {inhalt.kopf.id !== null ? `Nr. ${inhalt.kopf.id} · ` : ''}{datei}
      </p>

      {/* Diese Aussage muss stimmen und auffallen. Ein Nutzer hat eine
          Preisänderung gespeichert und sie auf kleinanzeigen.de gesucht - der
          alte Hinweis sprach nur vom Herunterladen und ließ offen, dass
          Speichern nichts veröffentlicht. */}
      <div className="mb-6 flex items-start gap-2 rounded border border-amber-200 bg-amber-50 p-3 text-sm text-amber-900">
        <Info className="mt-0.5 h-4 w-4 flex-shrink-0" aria-hidden />
        <div>
          <p className="font-medium">Speichern ändert nichts auf kleinanzeigen.de.</p>
          <p className="mt-1">
            Die Änderung liegt danach nur hier auf dem Rechner. Das Hochladen einer
            geänderten Anzeige ist noch nicht gebaut – bis dahin geht es nur direkt
            auf der Website. Und Achtung: Ein späteres Herunterladen übernimmt den
            Stand der Plattform und überschreibt, was du hier geändert hast.
          </p>
        </div>
      </div>

      {fehler && (
        <p role="alert" className="mb-4 rounded border border-red-200 bg-red-50 p-3 text-sm text-red-800">
          {fehler}
        </p>
      )}

      {eingereiht !== null && (
        <p className="mb-4 rounded border border-green-200 bg-green-100 p-3 text-sm text-green-800">
          Lauf {eingereiht} ist eingereiht. Unter „Läufe" lässt er sich mitlesen –
          und abbrechen, solange er nicht fertig ist.
        </p>
      )}

      {fragtHochladen && inhalt && (
        <HochladenDialog
          anzeige={inhalt.kopf}
          profil={profil}
          laeuft={laedtHoch}
          aufAbbrechen={() => setFragtHochladen(false)}
          aufBestaetigen={() => void hochladen()}
        />
      )}

      {hinweise.length > 0 && (
        <div className="mb-4 rounded border border-amber-200 bg-amber-50 p-3 text-sm text-amber-900">
          <p className="mb-1 flex items-center gap-2 font-medium">
            <AlertTriangle className="h-4 w-4" aria-hidden />
            Gespeichert, aber so nicht veröffentlichbar
          </p>
          <ul className="list-inside list-disc">
            {hinweise.map(h => <li key={h}>{h}</li>)}
          </ul>
        </div>
      )}

      <div className="space-y-4 rounded border border-gray-200 bg-white p-4">
        <label className="block">
          <span className="text-sm font-medium text-gray-700">Titel</span>
          <input
            type="text"
            value={titel}
            maxLength={TITEL_MAX}
            onChange={e => setzen('title', e.target.value)}
            className="mt-1 w-full rounded border border-gray-300 px-3 py-2
                       focus:border-primary-custom focus:outline-none focus:ring-1 focus:ring-primary-custom"
          />
          <span className={`mt-1 block text-xs ${titelZuKurz ? 'text-red-700' : 'text-gray-500'}`}>
            {titel.length} von {TITEL_MAX} Zeichen{titelZuKurz ? `, mindestens ${TITEL_MIN}` : ''}
          </span>
        </label>

        <label className="block">
          <span className="text-sm font-medium text-gray-700">Beschreibung</span>
          <textarea
            rows={10}
            value={text(felder.description)}
            onChange={e => setzen('description', e.target.value)}
            className="mt-1 w-full rounded border border-gray-300 px-3 py-2
                       focus:border-primary-custom focus:outline-none focus:ring-1 focus:ring-primary-custom"
          />
        </label>

        <div className="grid gap-4 sm:grid-cols-2">
          <label className="block">
            <span className="text-sm font-medium text-gray-700">Art</span>
            <select
              value={text(felder.type) || 'OFFER'}
              onChange={e => setzen('type', e.target.value)}
              className="mt-1 w-full rounded border border-gray-300 px-3 py-2"
            >
              {ARTEN.map(a => <option key={a.wert} value={a.wert}>{a.label}</option>)}
            </select>
          </label>

          <div className="sm:col-span-2">
            <KategorieWahl
              wert={text(felder.category)}
              aufAenderung={wert => setzen('category', wert)}
            />
          </div>

          <label className="block">
            <span className="text-sm font-medium text-gray-700">Preis (€)</span>
            <input
              type="number"
              step="1"
              min="0"
              value={text(felder.price)}
              onChange={e => setzen('price', zahlOderNull(e.target.value))}
              className="mt-1 w-full rounded border border-gray-300 px-3 py-2"
            />
          </label>

          <label className="block">
            <span className="text-sm font-medium text-gray-700">Preistyp</span>
            <select
              value={text(felder.price_type) || 'FIXED'}
              onChange={e => setzen('price_type', e.target.value)}
              className="mt-1 w-full rounded border border-gray-300 px-3 py-2"
            >
              {PREISTYPEN.map(p => <option key={p.wert} value={p.wert}>{p.label}</option>)}
            </select>
          </label>

          <label className="block">
            <span className="text-sm font-medium text-gray-700">Versand</span>
            <select
              value={text(felder.shipping_type) || 'NOT_APPLICABLE'}
              onChange={e => setzen('shipping_type', e.target.value)}
              className="mt-1 w-full rounded border border-gray-300 px-3 py-2"
            >
              {VERSANDARTEN.map(v => <option key={v.wert} value={v.wert}>{v.label}</option>)}
            </select>
          </label>

          <label className="block">
            <span className="text-sm font-medium text-gray-700">Versandkosten (€)</span>
            <input
              type="number"
              step="0.01"
              min="0"
              value={text(felder.shipping_costs)}
              onChange={e => setzen('shipping_costs', zahlOderNull(e.target.value))}
              className="mt-1 w-full rounded border border-gray-300 px-3 py-2"
            />
          </label>

          <label className="block">
            <span className="text-sm font-medium text-gray-700">Abstand zur Neueinstellung (Tage)</span>
            <input
              type="number"
              step="1"
              min="1"
              value={text(felder.republication_interval)}
              onChange={e => setzen('republication_interval', zahlOderNull(e.target.value))}
              className="mt-1 w-full rounded border border-gray-300 px-3 py-2"
            />
          </label>
        </div>

        <VersandpaketWahl
          gewaehlt={(felder.shipping_options as string[] | null) ?? []}
          versandkosten={typeof felder.shipping_costs === 'number' ? felder.shipping_costs : null}
          direktKaufen={Boolean(felder.sell_directly)}
          aufAenderung={pakete => setzen('shipping_options', pakete.length > 0 ? pakete : null)}
        />

        <div className="flex flex-wrap gap-6">
          <label className="flex items-center gap-2">
            <input
              type="checkbox"
              checked={Boolean(felder.active)}
              onChange={e => setzen('active', e.target.checked)}
              className="h-4 w-4"
            />
            <span className="text-sm text-gray-700">Aktiv</span>
          </label>

          <label className="flex items-center gap-2">
            <input
              type="checkbox"
              checked={Boolean(felder.sell_directly)}
              onChange={e => setzen('sell_directly', e.target.checked)}
              className="h-4 w-4"
            />
            <span className="text-sm text-gray-700">Direkt kaufen</span>
          </label>
        </div>

        <fieldset className="grid gap-4 rounded border border-gray-200 p-3 sm:grid-cols-3">
          <legend className="px-1 text-sm font-medium text-gray-700">Kontakt</legend>
          <label className="block">
            <span className="text-xs text-gray-600">Name</span>
            <input
              type="text"
              value={text(kontakt.name)}
              onChange={e => kontaktSetzen('name', e.target.value)}
              className="mt-1 w-full rounded border border-gray-300 px-3 py-2"
            />
          </label>
          <label className="block">
            <span className="text-xs text-gray-600">PLZ</span>
            <input
              type="text"
              value={text(kontakt.zipcode)}
              onChange={e => kontaktSetzen('zipcode', e.target.value)}
              className="mt-1 w-full rounded border border-gray-300 px-3 py-2"
            />
          </label>
          <label className="block">
            <span className="text-xs text-gray-600">Ort</span>
            <input
              type="text"
              value={text(kontakt.location)}
              onChange={e => kontaktSetzen('location', e.target.value)}
              className="mt-1 w-full rounded border border-gray-300 px-3 py-2"
            />
          </label>
        </fieldset>

        {Object.keys(sonderfelder).length > 0 && (
          <fieldset className="rounded border border-gray-200 p-3">
            <legend className="px-1 text-sm font-medium text-gray-700">
              Sonderfelder der Kategorie
            </legend>
            <dl className="grid gap-x-4 gap-y-1 text-sm sm:grid-cols-2">
              {Object.entries(sonderfelder).map(([schluessel, wert]) => (
                <div key={schluessel} className="flex justify-between gap-2">
                  <dt className="truncate text-gray-600">{schluessel}</dt>
                  <dd className="truncate text-gray-900">{text(wert)}</dd>
                </div>
              ))}
            </dl>
            <p className="mt-2 text-xs text-gray-500">
              Noch nicht änderbar: Welche Werte eine Kategorie zulässt, weiß erst AP-2.7.
            </p>
          </fieldset>
        )}

        <BilderVerwaltung
          profil={profil}
          datei={datei}
          bilder={bilder}
          aufAenderung={bilderAktualisiert}
        />
      </div>

      {/* Der Knopf bleibt am unteren Rand stehen. Bei einem Formular dieser
          Länge sonst zu weit weg von dem, was man gerade getippt hat. */}
      <div className="safe-unten fixed inset-x-0 bottom-0 border-t border-gray-200 bg-white px-4 py-3">
        <div className="mx-auto flex max-w-3xl items-center justify-end gap-3">
          {vorlageAngelegt && (
            <span className="flex items-center gap-1 text-sm text-gray-600">
              <Check className="h-4 w-4" aria-hidden /> Als Vorlage gesichert
            </span>
          )}
          {gespeichert && !schmutzig && !vorlageAngelegt && (
            <span className="flex items-center gap-1 text-sm text-gray-600">
              <Check className="h-4 w-4" aria-hidden /> Gespeichert
            </span>
          )}
          <button
            type="button"
            onClick={() => void duplizieren()}
            disabled={speichert || dupliziert || schmutzig}
            title={schmutzig
              ? 'Erst speichern - kopiert wird der gespeicherte Stand.'
              : 'Legt eine Kopie als neuen Entwurf an. Nur lokal.'}
            className="flex items-center gap-2 rounded border border-gray-300 px-4 py-2 text-sm
                       text-gray-700 hover:bg-gray-50 disabled:cursor-not-allowed disabled:opacity-60"
          >
            <Copy className="h-4 w-4" aria-hidden />
            {dupliziert ? 'Wird kopiert …' : 'Duplizieren'}
          </button>

          <button
            type="button"
            onClick={() => void alsVorlage()}
            disabled={speichert || wirdVorlage || schmutzig}
            title={schmutzig
              ? 'Erst speichern - übernommen wird der gespeicherte Stand.'
              : 'Legt eine Vorlage an. Sie geht nie online und lässt sich beliebig oft anwenden.'}
            className="flex items-center gap-2 rounded border border-gray-300 px-4 py-2 text-sm
                       text-gray-700 hover:bg-gray-50 disabled:cursor-not-allowed disabled:opacity-60"
          >
            <BookmarkPlus className="h-4 w-4" aria-hidden />
            {wirdVorlage ? 'Wird angelegt …' : 'Als Vorlage'}
          </button>

          <button
            type="button"
            onClick={() => setFragtHochladen(true)}
            disabled={speichert || schmutzig || inhalt.kopf.id === null}
            title={schmutzig
              ? 'Erst speichern - hochgeladen wird der gespeicherte Stand.'
              : undefined}
            className="flex items-center gap-2 rounded border border-gray-300 px-4 py-2 text-sm
                       text-gray-700 hover:bg-gray-50 disabled:cursor-not-allowed disabled:opacity-60"
          >
            <ArrowUpFromLine className="h-4 w-4" aria-hidden />
            Hochladen
          </button>

          <button
            type="button"
            onClick={() => void speichern()}
            disabled={speichert || !schmutzig}
            className="flex items-center gap-2 rounded bg-primary-custom px-4 py-2 text-sm font-medium
                       disabled:cursor-not-allowed disabled:opacity-60"
          >
            <Save className="h-4 w-4" aria-hidden />
            {speichert ? 'Wird gespeichert …' : 'Speichern'}
          </button>
        </div>
      </div>
    </div>
  );
}
