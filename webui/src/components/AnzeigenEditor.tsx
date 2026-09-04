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

import { useCallback, useEffect, useMemo, useState } from 'react';
import {
  ArrowLeft, ArrowUpFromLine, BookmarkPlus, Check, ChevronDown, Copy, Save, Trash2,
} from 'lucide-react';
import { api, ApiFehler } from '../services/api';
import type { AnzeigeInhalt } from '../types';
import { titelFuerAnzeige } from '../titel';
import type { Meldung } from '../context/meldungenKontext';
import { useMeldungenQuelle } from '../context/useMeldungen';
import { BilderVerwaltung } from './BilderVerwaltung';
import { HochladenDialog } from './HochladenDialog';
import { KategorieWahl } from './KategorieWahl';
import { LoeschDialog } from './LoeschDialog';
import { VersandpaketWahl } from './VersandpaketWahl';

const TITEL_MIN = 10;
const TITEL_MAX = 65;
// Aus dem Upstream-Modell (`MAX_DESCRIPTION_LENGTH`, ad_model.py). Wie beim
// Titel ist das hier Bedienhilfe - geprüft wird am Ende das Modell des Bots.
const BESCHREIBUNG_MAX = 4000;

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
  /** Die Anzeige wurde lokal gelöscht - diese Maske hat kein Ziel mehr (AP-2.20). */
  aufGeloescht?: () => void;
  /**
   * Ob die Anzeige auf kleinanzeigen.de nicht mehr aktiv ist, lokal aber noch
   * liegt - dann steht im Kopf ein „Gelöscht"-Badge (Mockup v4, AP-3.10). Nur
   * ein Vorabwert, damit das Badge nicht erst nach dem Laden erscheint; die
   * verbindliche Klassifikation kommt mit `kopf.geloescht` aus dem Backend.
   */
  geloescht?: boolean;
}

export function AnzeigenEditor({
  profil, datei, aufZurueck, aufKopie, aufGeloescht, geloescht = false,
}: Props) {
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
  // Welcher Befehl daraus wurde (AP-3.8). Das Backend entscheidet das an der
  // Anzeigennummer; die Meldung soll denselben Vorgang nennen, nicht raten.
  const [eingereihterBefehl, setEingereihterBefehl] = useState<string | null>(null);
  const [fragtLoeschen, setFragtLoeschen] = useState(false);
  const [loescht, setLoescht] = useState(false);
  // Seltener gebrauchte Felder liegen eingeklappt (Mockup v4): mehr Formular
  // passt so above the fold.
  const [weitereOffen, setWeitereOffen] = useState(false);

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

  /**
   * Löscht diese Anzeige von der Platte (AP-2.20) - derselbe Endpunkt wie das
   * Sammellöschen in der Liste, damit die Zusage „nur lokal" nur an einer
   * Stelle hängt. Danach hat diese Maske kein Ziel mehr und muss zu.
   */
  const loeschen = async () => {
    setLoescht(true);
    setFehler(null);
    try {
      await api.bestand.loeschen(profil, [datei]);
      setFragtLoeschen(false);
      if (aufGeloescht) aufGeloescht();
      else aufZurueck(true);
    } catch (ursache) {
      setFehler(ursache instanceof ApiFehler ? ursache.message : 'Unbekannter Fehler.');
      setFragtLoeschen(false);
    } finally {
      setLoescht(false);
    }
  };

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
      setEingereihterBefehl(ergebnis.befehl);
      setFragtHochladen(false);
    } catch (ursache) {
      setFehler(ursache instanceof ApiFehler ? ursache.message : 'Unbekannter Fehler.');
      setFragtHochladen(false);
    } finally {
      setLaedtHoch(false);
    }
  };

  // Tipps und Hinweise wandern in die Glocke (AP-2.30) statt als hohe Banner
  // über dem Formular zu stehen. Kritische Fehler (`role=alert`) bleiben unten
  // im Formular. Die Kennung `editor-speichern-lokal` ist dieselbe wie beim
  // früheren Banner - wer ihn schon weggeklickt hatte, sieht ihn nicht wieder.
  const meldungen = useMemo<Meldung[]>(() => {
    if (!inhalt) return [];
    const liste: Meldung[] = [{
      id: 'editor-speichern-lokal',
      ton: 'hinweis',
      titel: 'Speichern bleibt auf diesem Rechner',
      text: inhalt.kopf.id !== null
        ? 'Speichern ändert nichts auf kleinanzeigen.de - dafür ist „Aktualisieren". '
          + 'Und ein späteres Herunterladen überschreibt, was hier geändert wurde.'
        : 'Speichern ändert nichts auf kleinanzeigen.de. Diese Anzeige war nie online - '
          + '„Veröffentlichen" stellt sie neu ein, erst danach hat sie eine Nummer.',
    }];
    for (const h of hinweise) {
      liste.push({
        id: `editor-nicht-veroeffentlichbar:${h}`,
        ton: 'warnung',
        titel: 'Gespeichert, aber so nicht veröffentlichbar',
        text: h,
      });
    }
    return liste;
  }, [inhalt, hinweise]);
  useMeldungenQuelle('editor', meldungen);

  if (fehler && !inhalt) {
    return (
      <div className="seite-breit">
        <button type="button" onClick={() => aufZurueck(false)} className="btn-leise mb-4 -ml-2">
          <ArrowLeft className="h-4 w-4" aria-hidden /> Zurück zur Liste
        </button>
        <p className="hinweis hinweis-fehler">{fehler}</p>
      </div>
    );
  }

  if (!inhalt) return <p className="text-sm text-leise">Wird geladen …</p>;

  const titel = titelFuerAnzeige(text(felder.title));
  const geloeschtAnzeige = inhalt.kopf.geloescht || geloescht;
  const titelAnzeige = titelFuerAnzeige(titel || inhalt.kopf.titel || 'Ohne Titel');
  /*
   * Das „Gelöscht •"-Präfix wird auch im FELD nicht mitgeführt (AP-2.35).
   * Es steht in der heruntergeladenen Datei, ist aber kein Titel, sondern
   * eine Dekoration der Plattform - und es frisst 11 der 65 Zeichen. Wer hier
   * etwas tippt, arbeitet am echten Titel; gespeichert wird beim nächsten
   * Speichern der bereinigte Wert.
   */
  const titelZuKurz = titel.length > 0 && titel.length < TITEL_MIN;
  /*
   * Zu LANG kann der Titel nur werden, wenn er nicht hier getippt wurde:
   * `maxLength` am Feld bremst die Tastatur, aber nicht einen Wert, der schon
   * in der Datei stand. Genau so kommt er vor - heruntergeladene Titel kommen
   * von der Plattform, und ein von Hand geschriebenes YAML kennt keine Grenze.
   * Vorher stand dann „77 von 65 Zeichen" in Grau, der Knopf war offen, und
   * der Lauf lief bis in den 422 des Backends (AP-2.34).
   */
  const titelZuLang = titel.length > TITEL_MAX;
  /*
   * Ohne Kategorie weist das Backend mit 422 ab (AP-2.37) - kleinanzeigen.de
   * verlangt eine, und das Modell des Bots auch. Gefunden beim Live-Test: Die
   * Wegwerf-Anzeige hatte keine, der Knopf war offen, und die Meldung lautete
   * „category: Input should be a valid string". Jetzt steht die Bedingung
   * dort, wo man sie beheben kann - vor dem Klick, nicht danach.
   */
  const kategorieFehlt = text(felder.category).trim() === '';
  const titelUngueltig = titelZuKurz || titelZuLang;
  const nichtUebertragbar = titelUngueltig || kategorieFehlt;
  const bilder = (felder.images as string[] | null) ?? [];
  const sonderfelder = (felder.special_attributes as Record<string, unknown> | null) ?? {};
  const kontakt = (felder.contact as Record<string, unknown> | null) ?? {};

  return (
    <div className="seite-breit pb-44 sm:pb-32 lg:pb-24">
      {/* Eine Kopfzeile (Mockup v4): der Anzeigentitel und - für eine eigene
          Anzeige, die auf der Plattform nicht mehr aktiv ist (AP-3.10) - ein
          „Gelöscht"-Badge. Datenquelle ist `kopf.geloescht`; die Eigenschaft
          `geloescht` dient nur dazu, das Badge schon vor dem Laden zu zeigen.
          Kein „Zurück"-Link mehr; zurück führt die Seitenleiste. Die Glocke
          sitzt in der App-Kopfleiste (Layout) direkt darüber und trägt jetzt
          Tipps, Hinweise und Warnungen dieser Maske (AP-2.30). Alle Aktionen
          stehen in der Leiste unten (AP-2.24). */}
      <div className="editor-kopf">
        <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
          <h1 className="seite-titel break-words">
            {titelAnzeige}
          </h1>
          {geloeschtAnzeige && (
            <span
              className="merkmal merkmal-rot"
              title={'Auf kleinanzeigen.de nicht mehr aktiv. Gelöscht, pausiert oder '
                + 'in Prüfung – das unterscheidet der Download nicht. Die lokale Kopie bleibt.'}
            >
              Gelöscht
            </span>
          )}
        </div>
        {/*
          Nur die Anzeigennummer (AP-2.35). Vorher stand hier der ganze
          Dateipfad - und der enthält den Ordnernamen, der aus dem Titel
          gebildet wird: Die Zeile wiederholte damit die Überschrift darüber,
          über zwei Zeilen umgebrochen. Der Pfad ist Betriebswissen und hängt
          jetzt als `title` am Element; die Nummer ist das, womit man eine
          Anzeige auf kleinanzeigen.de wiederfindet.
        */}
        <p className="seite-beschrieb" title={datei}>
          {inhalt.kopf.id !== null
            ? `Anzeigennummer ${inhalt.kopf.id}`
            : 'Noch nicht veröffentlicht – keine Anzeigennummer'}
        </p>
      </div>

      {fragtLoeschen && inhalt && (
        <LoeschDialog
          anzeigen={[inhalt.kopf]}
          laeuft={loescht}
          aufAbbrechen={() => setFragtLoeschen(false)}
          aufLoeschen={() => void loeschen()}
        />
      )}

      {(fehler || eingereiht !== null) && (
        <div className="mb-4 space-y-2">
          {/* Kritischer Fehler bleibt im Formular stehen (role=alert). Tipps
              und „nicht veröffentlichbar"-Warnungen stehen in der Glocke. */}
          {fehler && (
            <p role="alert" className="hinweis hinweis-fehler lesebreite">
              {fehler}
            </p>
          )}

          {/* Der eingereihte Lauf steht in der Glocke (AP-2.25); hier bleibt
              nur die kurze Bestätigung mit dem Weg dorthin. */}
          {eingereiht !== null && (
            <p className="lesebreite text-sm text-leise">
              {eingereihterBefehl === 'publish'
                ? `Lauf ${eingereiht} ist eingereiht – die Anzeige wird neu eingestellt.`
                : `Lauf ${eingereiht} ist eingereiht – die bestehende Anzeige wird bearbeitet.`}
              {' '}
              <a href="#warteschlange" className="font-medium underline">
                Zur Warteschlange
              </a>{' '}
              – dort mitlesen und abbrechen.
            </p>
          )}
        </div>
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

      {/* Fotos links, Felder rechts - wie eine Anzeige auf der Plattform auch
          gelesen wird. Die Fotospalte bleibt ab md stehen und scrollt für sich
          (Mockup v4). Unterhalb von md stapelt es sich, Fotos zuerst: Auf dem
          Handy ist das Bild das, woran man die Anzeige wiedererkennt. */}
      <div className="grid gap-6 md:grid-cols-[16rem_minmax(0,1fr)] xl:grid-cols-[19rem_minmax(0,1fr)]">
        <div className="editor-bilder min-w-0">
          <BilderVerwaltung
            profil={profil}
            datei={datei}
            bilder={bilder}
            aufAenderung={bilderAktualisiert}
          />
        </div>

        <div className="min-w-0 space-y-3">
          {/*
            Titel/Beschreibung und Art/Kategorie nebeneinander, 65 zu 35
            (AP-2.35). Der Text braucht die Breite - die Beschreibung ist das
            längste Feld der Maske -, die beiden Auswahlfelder daneben nicht.
            Übereinander gestapelt schob die Kategorie den Preis unter die
            Falz. Erst ab `lg`: Darunter wäre die schmale Spalte enger als das
            Kategoriefeld selbst.
          */}
          <div className="grid gap-3 lg:grid-cols-[65fr_35fr] lg:items-start">
          <div className="min-w-0 space-y-3">
          <section className="karte p-3">
            <h2 className="karte-kopf">Titel und Beschreibung</h2>

            <label className="block">
              <span className="beschriftung">Titel</span>
              <input
                type="text"
                value={titel}
                maxLength={TITEL_MAX}
                aria-invalid={titelUngueltig || undefined}
                onChange={e => setzen('title', e.target.value)}
                className="feld mt-1"
                style={titelUngueltig
                  ? { borderColor: 'var(--status-fehler)' }
                  : undefined}
              />
              <span className={`mt-1 block text-xs ${titelUngueltig ? 'text-red-700' : 'text-leise'}`}>
                {titel.length} von {TITEL_MAX} Zeichen
                {titelZuKurz ? `, mindestens ${TITEL_MIN}` : ''}
                {titelZuLang
                  ? ` – ${titel.length - TITEL_MAX} zu viel. Kürzen, sonst weist kleinanzeigen.de die Anzeige ab.`
                  : ''}
              </span>
            </label>

            <label className="mt-3 block">
              <span className="beschriftung">Beschreibung</span>
              <textarea
                rows={7}
                maxLength={BESCHREIBUNG_MAX}
                value={text(felder.description)}
                onChange={e => setzen('description', e.target.value)}
                className="feld mt-1"
              />
              <span className="mt-1 block text-right text-xs text-leise">
                {text(felder.description).length.toLocaleString('de-DE')} / {BESCHREIBUNG_MAX.toLocaleString('de-DE')}
              </span>
            </label>
          </section>

          <section className="karte p-3">
            <h2 className="karte-kopf">Preis und Versand</h2>

            {/* Breite nach Inhalt, nicht nach Spalte (AP-2.35): Ein Preis ist
                vier bis sechs Zeichen lang und stand vorher in einem Feld über
                die halbe Karte. `flex-wrap` statt Raster, damit die beiden
                Felder ihre eigene Breite behalten und auf schmalen Fenstern
                umbrechen, statt sich zu strecken. */}
            <div className="flex flex-wrap items-start gap-4">
              <label className="block">
                <span className="beschriftung">Preis (€)</span>
                <input
                  type="number"
                  step="1"
                  min="0"
                  inputMode="decimal"
                  value={text(felder.price)}
                  onChange={e => setzen('price', zahlOderNull(e.target.value))}
                  className="feld feld-zahl mt-1"
                />
              </label>

              <label className="block">
                <span className="beschriftung">Versand</span>
                <select
                  value={text(felder.shipping_type) || 'NOT_APPLICABLE'}
                  onChange={e => setzen('shipping_type', e.target.value)}
                  className="feld feld-auswahl mt-1"
                >
                  {VERSANDARTEN.map(v => <option key={v.wert} value={v.wert}>{v.label}</option>)}
                </select>
              </label>
            </div>
          </section>
          </div>

          <section className="karte p-3">
            <h2 className="karte-kopf">Art und Kategorie</h2>

            {/* In der schmalen Spalte untereinander: Zwei Auswahlfelder
                nebeneinander wären hier je gut 8rem breit - zu wenig für einen
                Kategoriepfad. */}
            <div className="space-y-3">
              <label className="block">
                <span className="beschriftung">Art</span>
                <select
                  value={text(felder.type) || 'OFFER'}
                  onChange={e => setzen('type', e.target.value)}
                  className="feld feld-auswahl mt-1"
                >
                  {ARTEN.map(a => <option key={a.wert} value={a.wert}>{a.label}</option>)}
                </select>
              </label>

              <div>
                <KategorieWahl
                  wert={text(felder.category)}
                  aufAenderung={wert => setzen('category', wert)}
                />
              </div>
            </div>

            {Object.keys(sonderfelder).length > 0 && (
              <div className="mt-3">
                <p className="beschriftung">Sonderfelder der Kategorie</p>
                <dl className="mt-1 grid gap-x-6 gap-y-1 text-sm sm:grid-cols-2">
                  {Object.entries(sonderfelder).map(([schluessel, wert]) => (
                    <div key={schluessel} className="flex min-w-0 gap-2">
                      <dt className="flex-shrink-0 text-leise">{schluessel}</dt>
                      <dd className="min-w-0 truncate text-stark">{text(wert)}</dd>
                    </div>
                  ))}
                </dl>
                <p className="mt-2 text-xs text-leise">
                  Noch nicht änderbar: Welche Werte eine Kategorie zulässt, weiß erst AP-2.7.
                </p>
              </div>
            )}
          </section>

          </div>


          {/* Weitere Optionen: Preistyp, Versandkosten und -pakete, Kontakt und
              Neueinstellung liegen eingeklappt (Mockup v4). Alle Felder bleiben
              erreichbar, nur eben nicht vor dem ersten Scrollen. */}
          <section className="karte">
            <button
              type="button"
              onClick={() => setWeitereOffen(o => !o)}
              aria-expanded={weitereOffen}
              className="flex w-full items-center justify-between gap-2 p-3 text-left"
            >
              <span className="karte-kopf mb-0">Weitere Optionen</span>
              <ChevronDown
                className={`h-4 w-4 flex-shrink-0 text-leise transition-transform ${weitereOffen ? 'rotate-180' : ''}`}
                aria-hidden
              />
            </button>

            {weitereOffen && (
              <div className="space-y-4 border-t px-3 pb-3 pt-3" style={{ borderColor: 'var(--karte-rand)' }}>
                <div className="grid gap-4 sm:grid-cols-2">
                  <label className="block">
                    <span className="beschriftung">Preistyp</span>
                    <select
                      value={text(felder.price_type) || 'FIXED'}
                      onChange={e => setzen('price_type', e.target.value)}
                      className="feld mt-1"
                    >
                      {PREISTYPEN.map(p => <option key={p.wert} value={p.wert}>{p.label}</option>)}
                    </select>
                  </label>

                  <label className="block">
                    <span className="beschriftung">Versandkosten (€)</span>
                    <input
                      type="number"
                      step="0.01"
                      min="0"
                      value={text(felder.shipping_costs)}
                      onChange={e => setzen('shipping_costs', zahlOderNull(e.target.value))}
                      className="feld mt-1"
                    />
                  </label>
                </div>

                <VersandpaketWahl
                  gewaehlt={(felder.shipping_options as string[] | null) ?? []}
                  versandkosten={typeof felder.shipping_costs === 'number' ? felder.shipping_costs : null}
                  direktKaufen={Boolean(felder.sell_directly)}
                  aufDirektKaufen={wert => setzen('sell_directly', wert)}
                  aufAenderung={pakete => setzen('shipping_options', pakete.length > 0 ? pakete : null)}
                />

                <div>
                  <p className="beschriftung mb-1">Kontakt</p>
                  <div className="grid gap-4 sm:grid-cols-3">
                    <label className="block">
                      <span className="text-xs text-leise">Name</span>
                      <input
                        type="text"
                        value={text(kontakt.name)}
                        onChange={e => kontaktSetzen('name', e.target.value)}
                        className="feld mt-1"
                      />
                    </label>
                    <label className="block">
                      <span className="text-xs text-leise">PLZ</span>
                      <input
                        type="text"
                        value={text(kontakt.zipcode)}
                        onChange={e => kontaktSetzen('zipcode', e.target.value)}
                        className="feld mt-1"
                      />
                    </label>
                    <label className="block">
                      <span className="text-xs text-leise">Ort</span>
                      <input
                        type="text"
                        value={text(kontakt.location)}
                        onChange={e => kontaktSetzen('location', e.target.value)}
                        className="feld mt-1"
                      />
                    </label>
                  </div>
                </div>

                <div>
                  <label className="flex items-center gap-2">
                    <input
                      type="checkbox"
                      checked={Boolean(felder.active)}
                      onChange={e => setzen('active', e.target.checked)}
                      className="h-4 w-4"
                    />
                    <span className="text-sm text-normal">Aktiv</span>
                  </label>

                  <label className="mt-3 block sm:max-w-xs">
                    <span className="beschriftung">Abstand zur Neueinstellung (Tage)</span>
                    <input
                      type="number"
                      step="1"
                      min="1"
                      value={text(felder.republication_interval)}
                      onChange={e => setzen('republication_interval', zahlOderNull(e.target.value))}
                      className="feld mt-1"
                    />
                  </label>
                </div>
              </div>
            )}
          </section>
        </div>
      </div>

      {/* Alle Aktionen der Maske stehen hier unten und bleiben stehen (AP-2.24).
          Bei einem Formular dieser Länge ist der obere Seitenkopf schnell
          weggescrollt - Duplizieren, Als Vorlage, Veröffentlichen und Löschen
          waren dann nur über den Weg zurück nach oben erreichbar.
          `lg:left-60` lässt die Seitenleiste frei - über die volle Breite legte
          sich die Leiste sonst über deren unterste Einträge. Innen dieselbe
          `.seite-breit`-Kante und dasselbe Seitenmaß wie im Inhalt, damit die
          Leiste mit der rechten Kante der Karten fluchtet. */}
      <div className="leiste-fix safe-unten fixed inset-x-0 bottom-0 z-20 px-6 py-3 sm:px-8 lg:left-60">
        <div className="seite-breit flex flex-wrap items-center gap-x-3 gap-y-2">
          <div className="flex min-w-0 flex-1 items-center gap-2 text-sm text-leise">
            {vorlageAngelegt && (
              <span className="flex items-center gap-1">
                <Check className="h-4 w-4" aria-hidden /> Als Vorlage gesichert
              </span>
            )}
            {gespeichert && !schmutzig && !vorlageAngelegt && (
              <span className="flex items-center gap-1">
                <Check className="h-4 w-4" aria-hidden /> Gespeichert
              </span>
            )}
            {schmutzig && <span>Ungespeicherte Änderungen</span>}
          </div>

          <div className="flex flex-wrap items-center justify-end gap-2">
            <button
              type="button"
              onClick={() => void duplizieren()}
              disabled={speichert || dupliziert || schmutzig}
              title={schmutzig
                ? 'Erst speichern - kopiert wird der gespeicherte Stand.'
                : 'Legt eine Kopie als neuen Entwurf an. Nur lokal.'}
              className="btn-ghost"
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
              className="btn-ghost"
            >
              <BookmarkPlus className="h-4 w-4" aria-hidden />
              {wirdVorlage ? 'Wird angelegt …' : 'Als Vorlage'}
            </button>

            {/* Rot: Es vernichtet Dateien und soll sich von den harmlosen
                Knöpfen daneben unterscheiden (AP-2.20). */}
            <button
              type="button"
              onClick={() => setFragtLoeschen(true)}
              disabled={speichert || loescht}
              title="Löscht die Anzeige von diesem Rechner. Auf kleinanzeigen.de ändert sich nichts."
              className="btn-ghost"
              style={{ color: 'var(--hinweis-fehler-text)', borderColor: 'var(--hinweis-fehler-rand)' }}
            >
              <Trash2 className="h-4 w-4" aria-hidden />
              Löschen
            </button>

            {/* Ohne Nummer nicht mehr gesperrt (AP-3.8): Eine neue Anzeige
                lässt sich veröffentlichen. Der Knopf heißt dann auch so - was er
                tut, unterscheidet sich, also darf er nicht gleich heißen. */}
            <button
              type="button"
              onClick={() => setFragtHochladen(true)}
              disabled={speichert || schmutzig || nichtUebertragbar}
              title={schmutzig
                ? 'Erst speichern - übertragen wird der gespeicherte Stand.'
                : kategorieFehlt
                  ? 'Ohne Kategorie weist kleinanzeigen.de die Anzeige ab. Rechts unter „Art und Kategorie" eine wählen.'
                  : titelZuLang
                  ? `Der Titel ist ${titel.length - TITEL_MAX} Zeichen zu lang - der Lauf würde abgewiesen.`
                  : titelZuKurz
                    ? `Der Titel braucht mindestens ${TITEL_MIN} Zeichen.`
                    : inhalt.kopf.id === null
                      ? 'Stellt die Anzeige neu auf kleinanzeigen.de ein.'
                      : 'Schreibt den gespeicherten Stand in die bestehende Anzeige.'
                }
              className="btn-ghost"
            >
              <ArrowUpFromLine className="h-4 w-4" aria-hidden />
              {inhalt.kopf.id === null ? 'Veröffentlichen' : 'Aktualisieren'}
            </button>

            <button
              type="button"
              onClick={() => void speichern()}
              disabled={speichert || !schmutzig}
              className="flex items-center gap-2 btn-primaer
                         disabled:cursor-not-allowed disabled:opacity-60"
            >
              <Save className="h-4 w-4" aria-hidden />
              {speichert ? 'Wird gespeichert …' : 'Speichern'}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
