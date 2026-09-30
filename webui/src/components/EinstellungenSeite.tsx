// SPDX-FileCopyrightText: © Anzeigen-Studio contributors
// SPDX-License-Identifier: AGPL-3.0-or-later
//
// Einstellungen der Bot-Konfiguration (AP-2.9).
//
// Das Formular kommt vom Backend, erzeugt aus schemas/config.schema.json.
// Neue Upstream-Felder erscheinen erst, wenn sie einer Gruppe zugeordnet sind.
// Die vier Sperrfelder aus AP-1.11 und Login-Klartext sind serverseitig
// nicht setzbar – und hier auch nicht angeboten.
//
// UI-Anpassung 2026-09-07: Reiter „Anzeigen" - die Gruppe „Standardwerte für
// Anzeigen" (u. a. der Standard-Abstand zur Neueinstellung) liegt jetzt dort
// statt unter „Bot". Gleiche Lade-/Speicherwege, nur andere Einsortierung.
//
// AP-2.46/2.52: Abgleich gehört in denselben Speichern-Entwurf wie die
// Bot-Felder; Feldhilfen und lange Kartenerklärungen liegen in InfoTips.
//
// AP-2.47: Seitenintros über den Reitern entfernt. Reiterleiste wie Meine
// Anzeigen (nicht vollbreit, Suche rechts, filtert Gruppen/Felder).
// UI-Anpassung 2026-09-13: Die drei kurzen Bot-Karten stehen auf breiten
// Bildschirmen in einem responsiven Raster; die umfangreiche Sicherung bleibt
// als eigene Karte darunter.

import { useCallback, useEffect, useMemo, useState, type FormEvent, type ReactNode } from 'react';
import {
  AlertTriangle, ArrowRight, CalendarClock, Check, ChevronsDownUp, ChevronsUpDown, KeyRound, Monitor, Moon,
  RotateCcw, Save, Search, Sparkles, Sun, Users,
} from 'lucide-react';
import type { LucideIcon } from 'lucide-react';
import { api, ApiFehler } from '../services/api';
import { useProfil } from '../context/useProfil';
import { KI_STATUS_EVENT } from '../context/profilKontext';
import { useThema, type ThemaWahl } from '../hooks/useThema';
import type { EinstellungsAbschnitt } from '../routing';
import type {
  AbgleichStand, EinstellungsFeld, EinstellungsGruppe, KiStatus, Profil, VerlaengernStand, ZugangStatus,
} from '../types';
import { BrowsersichtSeite } from './BrowsersichtSeite';
import { InfoTip } from './InfoTip';
import { ProfilSeite } from './ProfilSeite';
import { SicherungAbschnitt } from './SicherungAbschnitt';

const MIN_PASSWORTLAENGE = 12;
const ABGLEICH_PFAD = 'abgleich.eingeschaltet';
const VERLAENGERN_PFAD = 'verlaengern.eingeschaltet';

// Gruppen, die zum Reiter „Anzeigen" gehören statt zu „Bot": Studio-Vorgaben
// für Anzeigen (u. a. der Standard-Abstand zur Neueinstellung). Sie werden
// unverändert über denselben Lade- und Speicherweg geführt - nur anders
// einsortiert, damit „Bot" die reinen Bot-Schrauben behält.
const ANZEIGEN_GRUPPEN_IDS = new Set(['ad_defaults']);

// Die Voreinstellungen sollen im Alltag genügen. Technische Stellschrauben
// bleiben über „Weitere Einstellungen“ und die Suche erreichbar, stehen aber
// nicht mehr zwischen den wenigen Entscheidungen, die die meisten Menschen
// tatsächlich treffen müssen.
const WICHTIGE_FELDER = new Set([
  'ad_defaults.active',
  'ad_defaults.type',
  'ad_defaults.price_type',
  'ad_defaults.shipping_type',
  'ad_defaults.sell_directly',
  'ad_defaults.republication_interval',
  'download.preserve_local_settings',
]);

function holen(werte: Record<string, unknown>, pfad: string): unknown {
  let knoten: unknown = werte;
  for (const teil of pfad.split('.')) {
    if (knoten === null || typeof knoten !== 'object' || Array.isArray(knoten)) return undefined;
    knoten = (knoten as Record<string, unknown>)[teil];
  }
  return knoten;
}

function setzen(werte: Record<string, unknown>, pfad: string, wert: unknown): Record<string, unknown> {
  const teile = pfad.split('.');
  const kopie: Record<string, unknown> = { ...werte };
  let knoten: Record<string, unknown> = kopie;
  for (let i = 0; i < teile.length - 1; i += 1) {
    const teil = teile[i];
    const bisher = knoten[teil];
    const naechster = (bisher !== null && typeof bisher === 'object' && !Array.isArray(bisher))
      ? { ...(bisher as Record<string, unknown>) }
      : {};
    knoten[teil] = naechster;
    knoten = naechster;
  }
  const letzt = teile[teile.length - 1];
  if (wert === undefined) delete knoten[letzt];
  else knoten[letzt] = wert;
  return kopie;
}

function anzeigeWert(feld: EinstellungsFeld, roh: unknown): unknown {
  if (roh === undefined) return feld.vorgabe ?? (feld.typ === 'boolean' ? false : '');
  return roh;
}

function Feld({
  feld, wert, onChange,
}: {
  feld: EinstellungsFeld;
  wert: unknown;
  onChange: (wert: unknown) => void;
}) {
  const id = `feld-${feld.pfad.replace(/\./g, '-')}`;
  const aktuell = anzeigeWert(feld, wert);

  if (feld.typ === 'boolean') {
    return (
      <label htmlFor={id} className="lesebreite flex items-start gap-3">
        <input
          id={id}
          type="checkbox"
          checked={aktuell === true}
          onChange={e => onChange(e.target.checked)}
          className="mt-1 h-4 w-4"
        />
        <span>
          <span className="block text-sm font-medium text-stark">
            {feld.titel}
            {feld.beschreibung && (
              <InfoTip text={feld.beschreibung} label={`Erklärung zu ${feld.titel}`} className="ml-1" />
            )}
          </span>
        </span>
      </label>
    );
  }

  const eingabeKlasse = 'feld mt-1';

  let steuer: ReactNode;
  if (feld.typ === 'enum' && feld.enum) {
    steuer = (
      <select
        id={id}
        value={aktuell === null || aktuell === undefined ? '' : String(aktuell)}
        onChange={e => onChange(e.target.value === '' && feld.null_erlaubt ? null : e.target.value)}
        className={eingabeKlasse}
      >
        {feld.null_erlaubt && <option value="">—</option>}
        {feld.enum.map(eintrag => (
          <option key={eintrag} value={eintrag}>
            {feld.enum_labels?.[eintrag] ?? eintrag}
          </option>
        ))}
      </select>
    );
  } else if (feld.typ === 'integer' || feld.typ === 'number') {
    steuer = (
      <input
        id={id}
        type="number"
        step={feld.typ === 'integer' ? 1 : 'any'}
        value={aktuell === null || aktuell === undefined ? '' : String(aktuell)}
        onChange={e => {
          const roh = e.target.value;
          if (roh === '') {
            onChange(feld.null_erlaubt ? null : '');
            return;
          }
          const zahl = feld.typ === 'integer' ? Number.parseInt(roh, 10) : Number(roh);
          onChange(Number.isFinite(zahl) ? zahl : roh);
        }}
        className={eingabeKlasse}
      />
    );
  } else if (feld.typ === 'string[]') {
    const text = Array.isArray(aktuell)
      ? (aktuell as unknown[]).map(String).join('\n')
      : (aktuell === null || aktuell === undefined ? '' : String(aktuell));
    steuer = (
      <textarea
        id={id}
        rows={3}
        value={text}
        onChange={e => onChange(e.target.value.split('\n').map(z => z.trim()).filter(Boolean))}
        className={`${eingabeKlasse} font-mono`}
      />
    );
  } else if (feld.langtext) {
    steuer = (
      <textarea
        id={id}
        rows={3}
        value={aktuell === null || aktuell === undefined ? '' : String(aktuell)}
        onChange={e => onChange(e.target.value)}
        className={eingabeKlasse}
      />
    );
  } else {
    steuer = (
      <input
        id={id}
        type="text"
        value={aktuell === null || aktuell === undefined ? '' : String(aktuell)}
        onChange={e => onChange(e.target.value)}
        className={eingabeKlasse}
      />
    );
  }

  return (
    // `.lesebreite` am Label begrenzt das Eingabefeld. Die ausführliche
    // Feldhilfe steckt im InfoTip am Titel, damit die Karten überfliegbar bleiben.
    <label htmlFor={id} className="lesebreite block">
      <span className="beschriftung">
        {feld.titel}
        {feld.beschreibung && (
          <InfoTip text={feld.beschreibung} label={`Erklärung zu ${feld.titel}`} className="ml-1" />
        )}
      </span>
      {steuer}
    </label>
  );
}

/**
 * Vergleichsformen für die Suche (AP-2.19). Wer sucht, tippt schnell und oft
 * ohne Umlaut - und dann auf zwei verschiedene Arten.
 *
 * Deshalb trägt der Heuhaufen beide Schreibweisen nebeneinander: „Zeitgrenzen"
 * bleibt, „Veröffentlichung" steht als `veroffentlichung` **und** als
 * `veroeffentlichung` drin. Die Nadel wird nur von ihren Diakritika befreit.
 * So findet dieselbe Gruppe, wer „Veröffentlichung", „veroffentlichung" oder
 * „veroeffentlichung" eintippt.
 */
function heuhaufen(text: string): string {
  const klein = text.toLowerCase();
  const entfaltet = klein
    .replace(/ä/g, 'ae').replace(/ö/g, 'oe').replace(/ü/g, 'ue').replace(/ß/g, 'ss');
  return `${nadel(klein)} ${entfaltet}`;
}

function nadel(text: string): string {
  return text.toLowerCase()
    .normalize('NFD').replace(/[̀-ͯ]/g, '')
    .replace(/ß/g, 'ss');
}

function feldPasst(feld: EinstellungsFeld, gesucht: string): boolean {
  return heuhaufen(`${feld.titel} ${feld.beschreibung}`).includes(gesucht);
}

function Gruppe({
  gruppe, felder, werte, onChange, offen, aufOffen, geaendert, ohneKlapp,
}: {
  gruppe: EinstellungsGruppe;
  /** Die anzuzeigenden Felder - bei aktiver Suche weniger als `gruppe.felder`. */
  felder: EinstellungsFeld[];
  werte: Record<string, unknown>;
  onChange: (pfad: string, wert: unknown) => void;
  offen: boolean;
  aufOffen: (offen: boolean) => void;
  /** Wie viele Felder dieser Gruppe seit dem Laden geändert wurden. */
  geaendert: number;
  /** Bei aktiver Suche: fest aufgeklappt, ohne Klappknopf. */
  ohneKlapp?: boolean;
}) {
  const diagnoseAn = gruppe.id === 'diagnostics' && gruppe.felder.some(feld => {
    const wert = holen(werte, feld.pfad);
    const aktuell = wert === undefined ? feld.vorgabe : wert;
    return aktuell === true;
  });

  const rumpf = (
    <div className="space-y-4 px-4 py-4" style={{ borderTop: '1px solid var(--karte-rand)' }}>
      {gruppe.beschreibung && (
        <p className="lesebreite text-sm text-leise">{gruppe.beschreibung}</p>
      )}
      {gruppe.warnung && diagnoseAn && (
        <p role="alert" className="hinweis hinweis-warn lesebreite">
          <AlertTriangle className="mb-1 inline h-4 w-4" /> {gruppe.warnung}
        </p>
      )}
      <div className={gruppe.id === 'ad_defaults' ? 'grid gap-4 sm:grid-cols-2' : 'space-y-4'}>
        {felder.map(feld => (
          <Feld
            key={feld.pfad}
            feld={feld}
            wert={holen(werte, feld.pfad)}
            onChange={wert => onChange(feld.pfad, wert)}
          />
        ))}
      </div>
    </div>
  );

  // Die Zeile über dem Rumpf. Die Zahl sagt, wie viel zugeklappt darunter
  // liegt; „n geändert" verhindert, dass jemand ungesehen speichert, was er
  // vor dem Zuklappen getippt hat.
  const kopf = (
    <>
      <span className="flex-1 truncate">{gruppe.titel}</span>
      {geaendert > 0 && (
        <span className="merkmal merkmal-gelb flex-shrink-0">{geaendert} geändert</span>
      )}
      <span className="flex-shrink-0 text-xs font-normal text-leise">
        {felder.length}
      </span>
    </>
  );

  if (ohneKlapp) {
    return (
      <section className="karte">
        <h3 className="flex items-center gap-2 px-4 py-3 text-sm font-medium text-stark">
          {kopf}
        </h3>
        {rumpf}
      </section>
    );
  }

  return (
    <details
      open={offen}
      onToggle={e => aufOffen((e.currentTarget as HTMLDetailsElement).open)}
      className="karte"
    >
      <summary className="flex cursor-pointer items-center gap-2 px-4 py-3 text-sm font-medium text-stark">
        {kopf}
      </summary>
      {rumpf}
    </details>
  );
}

export function EinstellungenSeite({ abschnitt, aufZiel }: { abschnitt: EinstellungsAbschnitt; aufZiel: (ziel: string) => void }) {
  const { aktiv, profile, fehler: profileFehler, laedt: profileLaden } = useProfil();
  const [gruppen, setGruppen] = useState<EinstellungsGruppe[]>([]);
  const [werte, setWerte] = useState<Record<string, unknown>>({});
  const [zugang, setZugang] = useState<ZugangStatus | null>(null);
  const [kiStatus, setKiStatus] = useState<KiStatus | null>(null);
  const [fehler, setFehler] = useState<string | null>(null);
  const [laedt, setLaedt] = useState(true);
  const [speichert, setSpeichert] = useState(false);
  const [gespeichert, setGespeichert] = useState(false);
  const [schmutzig, setSchmutzig] = useState(false);
  const [urspruenglicheWerte, setUrspruenglicheWerte] = useState<Record<string, unknown>>({});
  const [abgleichStand, setAbgleichStand] = useState<AbgleichStand | null>(null);
  const [urspruenglicherAbgleich, setUrspruenglicherAbgleich] = useState<boolean | null>(null);
  const [abgleichLaedt, setAbgleichLaedt] = useState(true);
  const [abgleichFehler, setAbgleichFehler] = useState<string | null>(null);
  const [verlaengernStand, setVerlaengernStand] = useState<VerlaengernStand | null>(null);
  const [urspruenglichesVerlaengern, setUrspruenglichesVerlaengern] = useState<boolean | null>(null);
  const [verlaengernLaedt, setVerlaengernLaedt] = useState(true);
  const [verlaengernFehler, setVerlaengernFehler] = useState<string | null>(null);
  // AP-2.19: Suche, Klappzustand je Gruppe und die Pfade, die seit dem Laden
  // angefasst wurden. Letztere nur, damit eine zugeklappte Gruppe zeigen kann,
  // dass in ihr etwas hängt - gespeichert wird unverändert alles.
  const [suche, setSuche] = useState('');
  // AP-2.47: unter sm klappt die Suche wie in Meine Anzeigen auf ein Lupen-Icon.
  const [sucheOffen, setSucheOffen] = useState(false);
  const [offeneGruppen, setOffeneGruppen] = useState<Record<string, boolean>>({});
  const [angefasst, setAngefasst] = useState<Set<string>>(new Set());

  const laden = useCallback(async () => {
    if (!aktiv) {
      setLaedt(false);
      setZugang(null);
      setAbgleichStand(null);
      setUrspruenglicherAbgleich(null);
      setVerlaengernStand(null);
      setUrspruenglichesVerlaengern(null);
      return;
    }
    setLaedt(true);
    setAbgleichLaedt(true);
    setVerlaengernLaedt(true);
    setFehler(null);
    setAbgleichFehler(null);
    setVerlaengernFehler(null);
    try {
      const [daten, zugangsdaten] = await Promise.all([
        api.einstellungen.lesen(aktiv.slug),
        api.profile.zugang(aktiv.slug),
      ]);
      setGruppen(daten.gruppen);
      setWerte(daten.werte);
      setUrspruenglicheWerte(daten.werte);
      setZugang(zugangsdaten);
      setSchmutzig(false);
      setGespeichert(false);
      setAngefasst(new Set());
      // Der Startzustand kommt weiter aus den Daten (`eingeklappt`), nicht aus
      // einer eigenen Vorliebe der Oberfläche.
      setOffeneGruppen(Object.fromEntries(daten.gruppen.map(g => [g.id, !g.eingeklappt])));

      try {
        const abgleich = await api.abgleich.stand(aktiv.slug);
        setAbgleichStand(abgleich);
        setUrspruenglicherAbgleich(abgleich.eingeschaltet);
      } catch (ursache) {
        setAbgleichFehler(ursache instanceof ApiFehler ? ursache.message : 'Stand nicht abrufbar.');
      }
      try {
        const verl = await api.verlaengern.stand(aktiv.slug);
        setVerlaengernStand(verl);
        setUrspruenglichesVerlaengern(verl.eingeschaltet);
      } catch (ursache) {
        setVerlaengernFehler(ursache instanceof ApiFehler ? ursache.message : 'Stand nicht abrufbar.');
      }
    } catch (ursache) {
      setFehler(ursache instanceof ApiFehler ? ursache.message : 'Unbekannter Fehler.');
    } finally {
      setLaedt(false);
      setAbgleichLaedt(false);
      setVerlaengernLaedt(false);
    }
  }, [aktiv]);

  useEffect(() => { void laden(); }, [laden]);

  // Der KI-Zugang ist installationsweit und wird deshalb auch ohne aktives
  // Profil angezeigt. Die Abfrage bleibt getrennt von den Profil-Einstellungen,
  // damit eine Störung hier nicht das Speichern der Bot-Felder blockiert.
  useEffect(() => {
    let verworfen = false;
    const ladenKi = async () => {
      try {
        const status = await api.ki.status();
        if (!verworfen) setKiStatus(status);
      } catch {
        if (!verworfen) setKiStatus(null);
      }
    };
    void ladenKi();
    const aktualisiert = () => void ladenKi();
    window.addEventListener(KI_STATUS_EVENT, aktualisiert);
    return () => {
      verworfen = true;
      window.removeEventListener(KI_STATUS_EVENT, aktualisiert);
    };
  }, []);

  const aendern = (pfad: string, wert: unknown) => {
    setWerte(vorher => setzen(vorher, pfad, wert));
    setAngefasst(vorher => new Set(vorher).add(pfad));
    setSchmutzig(true);
    setGespeichert(false);
  };

  const abgleichAendern = (eingeschaltet: boolean) => {
    setAbgleichStand(vorher => vorher ? { ...vorher, eingeschaltet } : vorher);
    setAngefasst(vorher => new Set(vorher).add(ABGLEICH_PFAD));
    setSchmutzig(true);
    setGespeichert(false);
  };

  const verlaengernAendern = (eingeschaltet: boolean) => {
    setVerlaengernStand(vorher => vorher ? { ...vorher, eingeschaltet } : vorher);
    setAngefasst(vorher => new Set(vorher).add(VERLAENGERN_PFAD));
    setSchmutzig(true);
    setGespeichert(false);
  };

  const speichern = async () => {
    if (!aktiv) return;
    setFehler(null);
    setSpeichert(true);
    try {
      const studioSchalter = new Set([ABGLEICH_PFAD, VERLAENGERN_PFAD]);
      const einstellungenGeaendert = [...angefasst].some(pfad => !studioSchalter.has(pfad));
      const abgleichGeaendert = angefasst.has(ABGLEICH_PFAD)
        && abgleichStand !== null
        && urspruenglicherAbgleich !== null
        && abgleichStand.eingeschaltet !== urspruenglicherAbgleich;
      const verlaengernGeaendert = angefasst.has(VERLAENGERN_PFAD)
        && verlaengernStand !== null
        && urspruenglichesVerlaengern !== null
        && verlaengernStand.eingeschaltet !== urspruenglichesVerlaengern;

      if (einstellungenGeaendert) {
        let payload: Record<string, unknown> = {};
        for (const gruppe of gruppen) {
          for (const feld of gruppe.felder) {
            const wert = holen(werte, feld.pfad);
            if (wert !== undefined) payload = setzen(payload, feld.pfad, wert);
          }
        }
        const antwort = await api.einstellungen.speichern(aktiv.slug, payload);
        setWerte(antwort.werte);
        setUrspruenglicheWerte(antwort.werte);
      }
      if (abgleichGeaendert && abgleichStand) {
        const antwort = await api.abgleich.schalten(aktiv.slug, abgleichStand.eingeschaltet);
        setAbgleichStand(antwort);
        setUrspruenglicherAbgleich(antwort.eingeschaltet);
      }
      if (verlaengernGeaendert && verlaengernStand) {
        const antwort = await api.verlaengern.schalten(aktiv.slug, verlaengernStand.eingeschaltet);
        setVerlaengernStand(antwort);
        setUrspruenglichesVerlaengern(antwort.eingeschaltet);
      }
      setSchmutzig(false);
      setAngefasst(new Set());
      setGespeichert(true);
    } catch (ursache) {
      setFehler(ursache instanceof ApiFehler ? ursache.message : 'Unbekannter Fehler.');
    } finally {
      setSpeichert(false);
    }
  };

  const zuruecksetzen = () => {
    setWerte(urspruenglicheWerte);
    setAbgleichStand(vorher => vorher && urspruenglicherAbgleich !== null
      ? { ...vorher, eingeschaltet: urspruenglicherAbgleich }
      : vorher);
    setVerlaengernStand(vorher => vorher && urspruenglichesVerlaengern !== null
      ? { ...vorher, eingeschaltet: urspruenglichesVerlaengern }
      : vorher);
    setAngefasst(new Set());
    setSchmutzig(false);
    setGespeichert(false);
    setFehler(null);
  };

  /**
   * Was die Suche übrig lässt (AP-2.19).
   *
   * Trifft der Suchtext den Gruppentitel oder ihre Beschreibung, bleibt die
   * ganze Gruppe stehen - wer „Diagnose" tippt, will alles darin sehen und
   * nicht nur die Felder, in denen das Wort zufällig noch einmal vorkommt.
   * Sonst bleiben die Felder, die selbst passen.
   *
   * Wichtig: Das ist reine Anzeige. `speichern()` läuft weiter über `gruppen`,
   * nicht über diese Auswahl - eine Suche darf nicht bestimmen, was auf der
   * Platte landet.
   */
  const gesucht = nadel(suche.trim());
  const sucheAktiv = gesucht.length > 0;

  // Der Reiter „Anzeigen" zeigt die Anzeigen-Gruppen, „Bot" den Rest.
  const reiterGruppen = useMemo(() => {
    const fuerAnzeigen = abschnitt === 'anzeigen';
    return gruppen.filter(g => ANZEIGEN_GRUPPEN_IDS.has(g.id) === fuerAnzeigen);
  }, [gruppen, abschnitt]);

  const aufgeteilteGruppen = useMemo(() => reiterGruppen.map(gruppe => ({
    gruppe,
    wichtigeFelder: gruppe.felder.filter(feld => WICHTIGE_FELDER.has(feld.pfad)),
    weitereFelder: gruppe.felder.filter(feld => !WICHTIGE_FELDER.has(feld.pfad)),
  })), [reiterGruppen]);

  const wichtigeGruppen = useMemo(
    () => aufgeteilteGruppen
      .filter(t => t.wichtigeFelder.length > 0)
      .map(t => ({
        gruppe: t.gruppe,
        // Die zwei häufigsten Schalter stehen zusammen. Auf schmalen
        // Bildschirmen fällt das Raster auf eine Spalte zurück.
        felder: t.gruppe.id === 'ad_defaults'
          ? [...t.wichtigeFelder].sort((a, b) => {
            const reihenfolge = ['ad_defaults.active', 'ad_defaults.sell_directly'];
            const platzA = reihenfolge.indexOf(a.pfad);
            const platzB = reihenfolge.indexOf(b.pfad);
            return (platzA < 0 ? reihenfolge.length : platzA)
              - (platzB < 0 ? reihenfolge.length : platzB);
          })
          : t.wichtigeFelder,
      })),
    [aufgeteilteGruppen],
  );

  const weitereGruppen = useMemo(
    () => aufgeteilteGruppen
      .filter(t => t.weitereFelder.length > 0)
      .map(t => ({ gruppe: t.gruppe, felder: t.weitereFelder })),
    [aufgeteilteGruppen],
  );

  const gesuchteGruppen = useMemo(() => {
    return reiterGruppen
      .map(g => {
        const gruppeTrifft = heuhaufen(`${g.titel} ${g.beschreibung}`).includes(gesucht);
        return {
          gruppe: g,
          felder: gruppeTrifft ? g.felder : g.felder.filter(f => feldPasst(f, gesucht)),
        };
      })
      .filter(t => t.felder.length > 0);
  }, [reiterGruppen, gesucht]);

  const sichtbareGruppen = sucheAktiv ? gesuchteGruppen : wichtigeGruppen;

  const felderGesamt = useMemo(
    () => reiterGruppen.reduce((summe, g) => summe + g.felder.length, 0),
    [reiterGruppen],
  );
  const wichtigeFelderGesamt = wichtigeGruppen.reduce((summe, t) => summe + t.felder.length, 0);
  const weitereFelderGesamt = weitereGruppen.reduce((summe, t) => summe + t.felder.length, 0);
  const felderSichtbar = sichtbareGruppen.reduce((summe, t) => summe + t.felder.length, 0);
  const alleOffen = sichtbareGruppen.length > 0
    && sichtbareGruppen.every(t => offeneGruppen[t.gruppe.id]);

  const alleKlappen = (offen: boolean) => {
    setOffeneGruppen(Object.fromEntries(gruppen.map(g => [g.id, offen])));
  };

  const diagnoseHinweis = useMemo(() => {
    const gruppe = gruppen.find(g => g.id === 'diagnostics');
    if (!gruppe?.warnung) return false;
    return gruppe.felder.some(feld => {
      const wert = holen(werte, feld.pfad);
      const aktuell = wert === undefined ? feld.vorgabe : wert;
      return aktuell === true;
    });
  }, [gruppen, werte]);

  const geaendertInSicht = (felder: EinstellungsFeld[]) =>
    felder.filter(feld => angefasst.has(feld.pfad)).length;

  if (profileLaden) {
    return <p className="text-sm text-leise">Wird geladen …</p>;
  }

  // „Läufe" ist hier weder Reiter noch Unterseite mehr (AP-2.28/2.31): Der
  // Einstieg ist der Menüpunkt „Warteschlange". Die alte Route
  // `einstellungen/laeufe` wird in `routing.ts` auf `warteschlange` umgelenkt,
  // damit Glocke, Dashboard und Editor nicht ins Leere führen.
  const tabs: { id: EinstellungsAbschnitt; label: string; hash: string }[] = [
    { id: 'uebersicht', label: 'Ersteinrichtung', hash: 'einstellungen' },
    { id: 'anzeigen', label: 'Anzeigen', hash: 'einstellungen/anzeigen' },
    { id: 'bot', label: 'Bot', hash: 'einstellungen/bot' },
    { id: 'profile', label: 'Profile', hash: 'einstellungen/profile' },
    { id: 'browser', label: 'Browser', hash: 'einstellungen/browser' },
    { id: 'passwort', label: 'Passwort', hash: 'einstellungen/passwort' },
    { id: 'darstellung', label: 'Darstellung', hash: 'einstellungen/darstellung' },
  ];

  // AP-2.47: Reiter links, Suche rechts – dieselbe Zeile wie in Meine Anzeigen.
  // Suche nur auf Bot/Anzeigen (dort gibt es Gruppen/Felder zum Filtern).
  const sucheSichtbar = abschnitt === 'bot' || abschnitt === 'anzeigen';

  const unternav = (
    <div className="mb-4 flex flex-wrap items-center gap-2">
      {sucheSichtbar && (
        <button
          type="button"
          onClick={() => setSucheOffen(o => !o)}
          aria-label="Suche ein- oder ausblenden"
          aria-expanded={sucheOffen}
          className="btn-icon order-first flex-shrink-0 sm:hidden"
        >
          <Search className="h-4 w-4" aria-hidden />
        </button>
      )}

      {sucheSichtbar && (
        <label
          className={`relative flex-shrink-0 sm:order-last sm:ml-auto sm:block sm:w-64 ${
            sucheOffen ? 'order-last block w-full' : 'hidden sm:block'
          }`}
        >
          <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-leise" aria-hidden />
          <span className="sr-only">Einstellungen durchsuchen</span>
          <input
            type="search"
            value={suche}
            onChange={e => setSuche(e.target.value)}
            placeholder="Einstellung oder Beschreibung suchen"
            className="feld py-2 pl-9 pr-3"
          />
        </label>
      )}

      <nav
        className="reiter-leiste order-first min-w-0 flex-1 overflow-x-auto sm:order-none sm:flex-none"
        aria-label="Einstellungsbereiche"
      >
        {tabs.map(tab => (
          <button
            key={tab.id}
            type="button"
            onClick={() => aufZiel(tab.hash)}
            aria-current={abschnitt === tab.id ? 'page' : undefined}
            className={`reiter ${abschnitt === tab.id ? 'reiter-aktiv' : ''}`}
          >
            {tab.label}
          </button>
        ))}
      </nav>
    </div>
  );

  if (abschnitt === 'uebersicht') {
    return (
      <div className="seite">
        <h1 className="sr-only">Einstellungen</h1>
        {unternav}
        <ErsteinrichtungAbschnitt
          aktiv={aktiv}
          profile={profile}
          profileFehler={profileFehler}
          zugang={zugang}
          kiStatus={kiStatus}
          aufZiel={aufZiel}
        />
      </div>
    );
  }

  if (abschnitt === 'profile') {
    return (
      <div className="seite">
        <h1 className="sr-only">Einstellungen</h1>
        {unternav}
        <ProfilSeite ohneTitel />
      </div>
    );
  }

  if (abschnitt === 'browser') {
    return (
      <div className="seite">
        <h1 className="sr-only">Einstellungen</h1>
        {unternav}
        <BrowsersichtSeite ohneTitel />
        {aktiv && <BrowserprofilReset profil={aktiv.slug} />}
      </div>
    );
  }

  if (abschnitt === 'passwort') {
    return (
      <div className="seite">
        <h1 className="sr-only">Einstellungen</h1>
        {unternav}
        <Anwendungspasswort />
      </div>
    );
  }

  if (abschnitt === 'darstellung') {
    return (
      <div className="seite">
        <h1 className="sr-only">Einstellungen</h1>
        {unternav}
        <DarstellungAbschnitt />
      </div>
    );
  }

  if (!aktiv) {
    return (
      <div className="seite">
        <h1 className="sr-only">Einstellungen</h1>
        {unternav}
        <p className="leer">
          Erst ein Profil anlegen – die Bot-Einstellungen gelten je Konto.
        </p>
      </div>
    );
  }

  if (laedt) {
    return <p className="text-sm text-leise">Wird geladen …</p>;
  }

  // Reiter „Anzeigen": nur die Studio-Vorgaben für Anzeigen. Die Bot-Karten
  // darüber (Zugangsdaten, Abgleich, Sicherung, KI, Diagnose-Hinweis) gehören
  // zum Bot-Reiter. Die Suche in der Reiterzeile filtert Gruppen/Felder.
  const istAnzeigen = abschnitt === 'anzeigen';

  return (
    // `pb-24` hält den Platz für die feste Speichern-Leiste frei, sonst deckt
    // sie die letzte Gruppe zu (AP-2.19).
    <div className="seite pb-24">
      <h1 className="sr-only">
        Einstellungen
      </h1>

      {unternav}

      <p className="mb-4 max-w-2xl text-sm text-leise">
        Die wichtigsten Einstellungen reichen für die meisten Fälle. Weitere technische
        Optionen findest du bei Bedarf unter „Weitere Einstellungen“.
      </p>

      {fehler && (
        <p role="alert" className="hinweis hinweis-fehler lesebreite mb-4">
          {fehler}
        </p>
      )}
      {gespeichert && !fehler && (
        <p className="hinweis lesebreite mb-4 flex items-center gap-2">
          <Check className="h-4 w-4" /> Gespeichert. Wirksam mit dem nächsten Lauf.
        </p>
      )}

      {!istAnzeigen && diagnoseHinweis && (
        <p role="alert" className="hinweis hinweis-warn lesebreite mb-4">
          <AlertTriangle className="mb-1 inline h-4 w-4" /> Diagnose ist eingeschaltet.
          Die Artefakte enthalten Bildschirmfotos und das vollständige DOM einer angemeldeten
          Sitzung – Klarname, Adresse und Telefonnummer.
        </p>
      )}

      {!istAnzeigen && (
        <div className="mb-4 grid gap-3 md:grid-cols-2">
          <section className="karte p-4">
            <h2 className="flex items-center gap-2 font-medium text-stark">
              <KeyRound className="h-5 w-5 text-primary-custom" />
              Zugangsdaten
              <InfoTip
                label="Erklärung zu den Zugangsdaten"
                text="Der Plattformzugang wird je Profil verschlüsselt unter Profile verwaltet und nicht in der Bot-Konfiguration abgelegt."
              />
            </h2>
            <p className="mt-1 text-sm text-leise">Für dieses Profil.</p>
            <p className="lesebreite mt-2 text-sm text-normal">
              {zugang?.passwort_hinterlegt
                ? `Zugang hinterlegt (${zugang.benutzername}).`
                : 'Noch kein Zugang hinterlegt – Läufe können sich nicht anmelden.'}
            </p>
            <button
              type="button"
              onClick={() => aufZiel('einstellungen/profile')}
              className="btn-ghost mt-3"
            >
              Zu den Profil-Zugängen
            </button>
          </section>

          <TaeglicherAbgleich
            stand={abgleichStand}
            laedt={abgleichLaedt}
            fehler={abgleichFehler}
            deaktiviert={speichert}
            aufAenderung={abgleichAendern}
          />

          <AutomatischesVerlaengern
            stand={verlaengernStand}
            laedt={verlaengernLaedt}
            fehler={verlaengernFehler}
            deaktiviert={speichert}
            aufAenderung={verlaengernAendern}
          />
        </div>
      )}

      {!istAnzeigen && <SicherungAbschnitt profil={aktiv.slug} />}

      {/* Zählzeile + Alle auf/zu unter der Reiterzeile (AP-2.19/2.47). Die Suche
          sitzt seit AP-2.47 rechts neben den Reitern wie in Meine Anzeigen. */}
      <div className="mb-3 flex flex-wrap items-center gap-2">
        <p className="text-xs text-leise">
          {sucheAktiv
            ? `${felderSichtbar} von ${felderGesamt} Einstellungen`
            : `${wichtigeFelderGesamt} wichtige Einstellungen`}
        </p>
        {!sucheAktiv && sichtbareGruppen.length > 0 && (
          <button
            type="button"
            onClick={() => alleKlappen(!alleOffen)}
            className="btn-ghost ml-auto flex-shrink-0"
          >
            {alleOffen
              ? <><ChevronsDownUp className="h-4 w-4" aria-hidden /> Alle zuklappen</>
              : <><ChevronsUpDown className="h-4 w-4" aria-hidden /> Alle aufklappen</>}
          </button>
        )}
      </div>

      {sichtbareGruppen.length > 0 && (
        <div className={abschnitt === 'bot' ? 'grid gap-3 md:grid-cols-2' : 'space-y-3'}>
          {sichtbareGruppen.map(({ gruppe, felder }) => (
            <Gruppe
              key={gruppe.id}
              gruppe={gruppe}
              felder={felder}
              werte={werte}
              onChange={aendern}
              offen={offeneGruppen[gruppe.id] ?? !gruppe.eingeklappt}
              aufOffen={offen => setOffeneGruppen(vorher => ({ ...vorher, [gruppe.id]: offen }))}
              geaendert={geaendertInSicht(felder)}
              ohneKlapp={sucheAktiv || istAnzeigen}
            />
          ))}
        </div>
      )}

      {!sucheAktiv && weitereGruppen.length > 0 && (
        <details className="karte mt-4">
          <summary className="flex cursor-pointer items-center gap-2 px-4 py-3 text-sm font-medium text-stark">
            <span className="flex-1">Weitere Einstellungen</span>
            <span className="text-xs font-normal text-leise">
              {weitereFelderGesamt} technische Optionen
            </span>
          </summary>
          <div className="border-t p-3" style={{ borderColor: 'var(--karte-rand)' }}>
            <p className="px-1 text-sm text-leise">
              Diese Optionen musst du normalerweise nicht ändern. Die Voreinstellungen sind
              für die meisten Fälle passend.
            </p>
            <div className={abschnitt === 'bot' ? 'grid gap-3 md:grid-cols-2' : 'space-y-3'}>
              {weitereGruppen.map(({ gruppe, felder }) => (
                <Gruppe
                  key={gruppe.id}
                  gruppe={gruppe}
                  felder={felder}
                  werte={werte}
                  onChange={aendern}
                  offen={offeneGruppen[gruppe.id] ?? !gruppe.eingeklappt}
                  aufOffen={offen => setOffeneGruppen(vorher => ({ ...vorher, [gruppe.id]: offen }))}
                  geaendert={geaendertInSicht(felder)}
                />
              ))}
            </div>
          </div>
        </details>
      )}

      {sichtbareGruppen.length === 0 && (sucheAktiv || weitereGruppen.length === 0) && (
        <p className="leer">
          {sucheAktiv
            ? `Keine Einstellung passt zu „${suche.trim()}".`
            : 'Für diesen Bereich sind keine wichtigen Einstellungen verfügbar.'}
        </p>
      )}

      {/* Dieselbe feste Leiste wie im Anzeigeneditor (AP-2.15/2.19): innen auf
          `.seite`-Breite, damit Speichern mit der rechten Kante der Karten
          fluchtet, und `lg:left-60` lässt die Seitenleiste frei. Vorher standen
          zwei Speichern-Knöpfe im Fluss - oben und ganz unten -, und in der
          Mitte des Formulars war keiner von beiden zu sehen. */}
      <div className="leiste-fix safe-unten fixed inset-x-0 bottom-0 z-20 px-6 py-3 sm:px-8 lg:left-60">
        <div className="seite flex flex-wrap items-center justify-end gap-3">
          {gespeichert && !schmutzig && !fehler && (
            <span className="flex items-center gap-1 text-sm text-leise">
              <Check className="h-4 w-4" aria-hidden /> Gespeichert
            </span>
          )}
          {schmutzig && (
            <span className="mr-auto text-sm text-leise">
              {angefasst.size === 1 ? '1 Änderung' : `${angefasst.size} Änderungen`} ungespeichert
            </span>
          )}
          {schmutzig && (
            <button type="button" onClick={zuruecksetzen} className="btn-ghost">
              <RotateCcw className="h-4 w-4" aria-hidden />
              Zurücksetzen
            </button>
          )}
          <button
            type="button"
            onClick={() => void speichern()}
            disabled={speichert || !schmutzig}
            className="btn-primaer disabled:cursor-not-allowed disabled:opacity-60"
          >
            <Save className="h-4 w-4" aria-hidden />
            {speichert ? 'Speichert …' : 'Speichern'}
          </button>
        </div>
      </div>
    </div>
  );
}

/**
 * Täglicher Abgleich der eigenen Anzeigen (AP-3.12).
 *
 * Der einzige Schalter in dieser Oberfläche, der einen wiederkehrenden Lauf
 * gegen das echte Konto erlaubt. Deshalb steht hier ausdrücklich, was er tut,
 * bevor er umgelegt wird – und deshalb ist die Vorgabe „aus".
 *
 * Er liegt neben den Zugangsdaten und nicht in den Bot-Gruppen darunter: Die
 * kommen aus dem Upstream-Schema und werden in `nutzer.yaml` gespeichert;
 * dieser Schalter gehört dem Studio und liegt in der Datenbank.
 */
function TaeglicherAbgleich({
  stand, laedt, fehler, deaktiviert, aufAenderung,
}: {
  stand: AbgleichStand | null;
  laedt: boolean;
  fehler: string | null;
  deaktiviert: boolean;
  aufAenderung: (eingeschaltet: boolean) => void;
}) {
  const zeit = (iso: string | null) => {
    if (!iso) return null;
    const wann = new Date(iso);
    return Number.isNaN(wann.getTime()) ? null : wann.toLocaleString('de-DE');
  };
  const zuletzt = zeit(stand?.letzter_lauf_am ?? null);

  return (
    <section className="karte p-4">
      <h2 className="flex items-center gap-2 font-medium text-stark">
        <CalendarClock className="h-5 w-5 text-primary-custom" />
        Täglicher Abgleich
        <InfoTip
          label="Erklärung zum täglichen Abgleich"
          text="Einmal am Tag prüft ein Browserlauf die eigenen Anzeigen und meldet echte Änderungen in der Glocke. Der Lauf nutzt die Warteschlange und braucht einen hinterlegten Plattformzugang."
        />
      </h2>
      <p className="mt-1 text-sm text-leise">Eigene Anzeigen automatisch täglich prüfen.</p>

      {laedt ? (
        <p className="mt-3 text-sm text-leise">Wird geladen …</p>
      ) : (
        <>
          <label htmlFor="abgleich-an" className="lesebreite mt-3 flex items-start gap-3">
            <input
              id="abgleich-an"
              type="checkbox"
              checked={stand?.eingeschaltet === true}
              disabled={deaktiviert || stand === null}
              onChange={e => aufAenderung(e.target.checked)}
              className="mt-1 h-4 w-4"
            />
            <span>
              <span className="block text-sm font-medium text-stark">
                Täglich abgleichen
              </span>
            </span>
          </label>

          {stand?.eingeschaltet && !stand.zugang_vorhanden && (
            <p role="alert" className="hinweis hinweis-warn lesebreite mt-3">
              <AlertTriangle className="mb-1 inline h-4 w-4" aria-hidden /> Kein Passwort
              hinterlegt – der Abgleich bleibt aus.
            </p>
          )}

          <dl className="mt-3 space-y-1 text-sm">
            <div className="flex flex-wrap gap-x-2">
              <dt className="text-leise">Zuletzt gestartet:</dt>
              <dd className="text-normal">{zuletzt ?? 'noch nie'}</dd>
            </div>
            <div className="flex flex-wrap gap-x-2">
              <dt className="text-leise">Ergebnis:</dt>
              <dd className="text-normal">
                {stand?.laeuft
                  ? 'Der Lauf von heute läuft noch.'
                  : stand?.letztes_ergebnis ?? '—'}
              </dd>
            </div>
            {stand?.eingeschaltet && stand.heute_gelaufen && !stand.laeuft && (
              <div className="text-xs text-leise">Heute bereits erledigt.</div>
            )}
          </dl>
        </>
      )}

      {fehler && (
        <p role="alert" className="hinweis hinweis-fehler lesebreite mt-3">{fehler}</p>
      )}
    </section>
  );
}

/**
 * Automatisches kostenloses Verlängern (AP-3.15).
 *
 * Eigener Schalter neben dem täglichen Abgleich. Vorgabe aus. Nur Free-
 * „Verlängern" (+60 Tage) – kein Hochschieben, kein Paid-Boost.
 */
function AutomatischesVerlaengern({
  stand, laedt, fehler, deaktiviert, aufAenderung,
}: {
  stand: VerlaengernStand | null;
  laedt: boolean;
  fehler: string | null;
  deaktiviert: boolean;
  aufAenderung: (eingeschaltet: boolean) => void;
}) {
  const zeit = (iso: string | null) => {
    if (!iso) return null;
    const wann = new Date(iso);
    return Number.isNaN(wann.getTime()) ? null : wann.toLocaleString('de-DE');
  };
  const zuletzt = zeit(stand?.letzter_lauf_am ?? null);

  return (
    <section className="karte p-4">
      <h2 className="flex items-center gap-2 font-medium text-stark">
        <CalendarClock className="h-5 w-5 text-primary-custom" />
        Automatisch verlängern
        <InfoTip
          label="Erklärung zum automatischen Verlängern"
          text="Einmal am Tag reiht das Studio einen kostenlosen Verlängern-Lauf ein (+60 Tage Laufzeit). Nur Anzeigen im Acht-Tage-Fenster. Kein Hochschieben und kein Paid-Boost – der Dankes-Dialog wird nur geschlossen. Braucht heruntergeladene Anzeigen und einen hinterlegten Plattformzugang."
        />
      </h2>
      <p className="mt-1 text-sm text-leise">
        Kostenlos +60 Tage. Kein Hochschieben, kein Paid-Boost.
      </p>

      {laedt ? (
        <p className="mt-3 text-sm text-leise">Wird geladen …</p>
      ) : (
        <>
          <label htmlFor="verlaengern-an" className="lesebreite mt-3 flex items-start gap-3">
            <input
              id="verlaengern-an"
              type="checkbox"
              checked={stand?.eingeschaltet === true}
              disabled={deaktiviert || stand === null}
              onChange={e => aufAenderung(e.target.checked)}
              className="mt-1 h-4 w-4"
            />
            <span className="block text-sm font-medium text-stark">
              Automatisch kostenlos verlängern
            </span>
          </label>
          <p className="lesebreite mt-1 pl-7 text-xs text-leise">
            Vorgabe aus. Nur Free-Verlängern im Acht-Tage-Fenster.
          </p>

          {stand?.eingeschaltet && !stand.zugang_vorhanden && (
            <p role="alert" className="hinweis hinweis-warn lesebreite mt-3">
              <AlertTriangle className="mb-1 inline h-4 w-4" aria-hidden /> Kein Passwort
              hinterlegt – das Verlängern bleibt aus.
            </p>
          )}

          <dl className="mt-3 space-y-1 text-sm">
            <div className="flex flex-wrap gap-x-2">
              <dt className="text-leise">Zuletzt gestartet:</dt>
              <dd className="text-normal">{zuletzt ?? 'noch nie'}</dd>
            </div>
            <div className="flex flex-wrap gap-x-2">
              <dt className="text-leise">Ergebnis:</dt>
              <dd className="text-normal">
                {stand?.laeuft
                  ? 'Der Lauf von heute läuft noch.'
                  : stand?.letztes_ergebnis ?? '—'}
              </dd>
            </div>
            {stand?.eingeschaltet && stand.heute_gelaufen && !stand.laeuft && (
              <div className="text-xs text-leise">Heute bereits erledigt.</div>
            )}
          </dl>
        </>
      )}

      {fehler && (
        <p role="alert" className="hinweis hinweis-fehler lesebreite mt-3">{fehler}</p>
      )}
    </section>
  );
}

function ErsteinrichtungAbschnitt({
  aktiv, profile, profileFehler, zugang, kiStatus, aufZiel,
}: {
  aktiv: Profil | null;
  profile: Profil[];
  profileFehler: string | null;
  zugang: ZugangStatus | null;
  kiStatus: KiStatus | null;
  aufZiel: (ziel: string) => void;
}) {
  const profilFertig = profileFehler === null && profile.length > 0;
  const plattformFertig = Boolean(aktiv && zugang?.passwort_hinterlegt);
  const kiFertig = kiStatus?.hinterlegt === true;
  const bekannteSchritte = [profilFertig, plattformFertig, kiFertig].filter(Boolean).length;
  const kiGehostet = kiStatus?.modus === 'gehostet';

  return (
    <div className="pb-8">
      <div className="mb-6 max-w-2xl">
        <h1 className="seite-titel">Ersteinrichtung</h1>
        <p className="mt-2 text-base text-normal">
          Richte die drei Dinge ein, die du für einen Lauf und für neue Anzeigen brauchst.
          Danach kannst du die technischen Einstellungen einfach ausblenden lassen.
        </p>
        <p className="mt-2 text-sm text-leise">
          {bekannteSchritte} von 3 wichtigen Schritten erledigt.
        </p>
      </div>

      <div className="space-y-3">
        <EinrichtungKarte
          nummer={1}
          icon={Users}
          titel={profilFertig ? 'Profil ist angelegt' : 'Profil anlegen'}
          text={profileFehler
            ? 'Die Profile konnten gerade nicht geprüft werden.'
            : profilFertig
              ? `Aktives Profil: ${aktiv?.anzeigename ?? profile[0]?.anzeigename ?? 'ausgewählt'}.`
              : 'Ein Profil steht für ein Kleinanzeigen-Konto.'}
          fertig={profilFertig}
          fehler={profileFehler}
          aufZiel={() => aufZiel('einstellungen/profile')}
          aktion={profilFertig ? 'Profile verwalten' : 'Profil anlegen'}
        />

        <EinrichtungKarte
          nummer={2}
          icon={KeyRound}
          titel={plattformFertig ? 'Kleinanzeigen-Zugang ist hinterlegt' : 'Kleinanzeigen-Zugang hinterlegen'}
          text={plattformFertig
            ? `Benutzername: ${zugang?.benutzername || 'hinterlegt'}.`
            : aktiv
              ? 'Ohne diesen Zugang können keine Läufe starten.'
              : 'Lege zuerst ein Profil an und hinterlege dort den Zugang.'}
          fertig={plattformFertig}
          aufZiel={() => aufZiel('einstellungen/profile')}
          aktion={plattformFertig ? 'Zugang verwalten' : 'Zugang hinterlegen'}
          deaktiviert={!aktiv}
        />

        <EinrichtungKarte
          nummer={3}
          icon={Sparkles}
          titel={kiFertig ? 'KI-Zugang ist bereit' : 'KI-Zugang einrichten'}
          text={kiStatus === null
            ? 'Der Status konnte gerade nicht geladen werden.'
            : kiFertig
              ? `${kiGehostet ? 'Vom Betreiber bereitgestellt' : 'Eigener Zugang hinterlegt'} · bis zu ${kiStatus.max_bilder ?? 4} Fotos je Entwurf.`
              : kiGehostet
                ? 'Der KI-Zugang wird vom Betreiber bereitgestellt.'
                : 'Für die Erkennung aus Fotos kannst du hier deinen eigenen Zugang hinterlegen.'}
          fertig={kiFertig}
          aufZiel={() => aufZiel('einstellungen/profile')}
          aktion={kiGehostet ? undefined : 'KI-Zugang öffnen'}
          deaktiviert={kiStatus === null || kiGehostet}
        />
      </div>

      {profilFertig && plattformFertig && kiFertig && (
        <p className="hinweis mt-4 flex items-center gap-2">
          <Check className="h-4 w-4" aria-hidden /> Die Ersteinrichtung ist abgeschlossen.
        </p>
      )}

      <button type="button" onClick={() => aufZiel('einstellungen/darstellung')} className="btn-ghost mt-6">
        <Monitor className="h-4 w-4" aria-hidden /> Darstellung öffnen
      </button>
    </div>
  );
}

function EinrichtungKarte({
  nummer, icon: Icon, titel, text, fertig, fehler, aufZiel, aktion, deaktiviert = false,
}: {
  nummer: number;
  icon: LucideIcon;
  titel: string;
  text: string;
  fertig: boolean;
  fehler?: string | null;
  aufZiel: () => void;
  aktion?: string;
  deaktiviert?: boolean;
}) {
  return (
    <section className={`karte einrichtung-karte p-4 ${fertig ? 'einrichtung-karte-fertig' : ''}`}>
      <div className="flex items-start gap-3">
        <span className="neue-anzeige-schritt" aria-hidden>{fertig ? <Check className="h-4 w-4" /> : nummer}</span>
        <div className="min-w-0 flex-1">
          <h2 className="flex items-center gap-2 font-medium text-stark">
            <Icon className="h-5 w-5 text-primary-custom" aria-hidden />
            {titel}
          </h2>
          <p className="mt-1 text-sm text-normal">{text}</p>
          {fehler && <p role="alert" className="mt-2 text-xs text-red-700">{fehler}</p>}
        </div>
        {aktion && (
          <button type="button" onClick={aufZiel} disabled={deaktiviert} className="btn-ghost flex-shrink-0">
            {aktion}<ArrowRight className="h-4 w-4" aria-hidden />
          </button>
        )}
      </div>
    </section>
  );
}

/**
 * Theme-Wahl (AP-2.27). Der eigentliche Ort für Hell / Dunkel / System; der
 * Schalter im Sidebar-Fuß hängt an derselben `useThema`-Wahrheit. „System"
 * folgt dem Betriebssystem und wechselt ohne Neuladen mit.
 */
function DarstellungAbschnitt() {
  const { wahl, setWahl, effektiv } = useThema();

  const optionen: { wert: ThemaWahl; titel: string; text: string; icon: LucideIcon }[] = [
    {
      wert: 'system',
      titel: 'System',
      text: 'Folgt dem Betriebssystem und wechselt automatisch mit.',
      icon: Monitor,
    },
    { wert: 'hell', titel: 'Hell', text: 'Immer helles Erscheinungsbild.', icon: Sun },
    { wert: 'dunkel', titel: 'Dunkel', text: 'Immer dunkles Erscheinungsbild.', icon: Moon },
  ];

  return (
    <section className="karte mt-6 p-4">
      <h2 className="flex items-center gap-2 font-medium text-stark">
        <Monitor className="h-5 w-5 text-primary-custom" />
        Thema
      </h2>
      <p className="lesebreite mt-1 text-sm text-leise">
        Gilt nur für diese Oberfläche in diesem Browser, nicht für ein Konto oder einen Lauf.
      </p>
      <fieldset className="mt-4 space-y-2 border-0 p-0">
        <legend className="sr-only">Thema wählen</legend>
        {optionen.map(({ wert, titel, text, icon: Icon }) => (
          <label
            key={wert}
            className="lesebreite flex cursor-pointer items-start gap-3 rounded-lg border p-3"
            style={{
              borderColor: wahl === wert ? 'var(--primary-color)' : 'var(--karte-rand)',
              background: wahl === wert ? 'var(--primary-light)' : 'transparent',
            }}
          >
            <input
              type="radio"
              name="thema"
              value={wert}
              checked={wahl === wert}
              onChange={() => setWahl(wert)}
              className="mt-1 h-4 w-4"
            />
            <span className="min-w-0">
              <span className="flex flex-wrap items-center gap-2 text-sm font-medium text-stark">
                <Icon className="h-4 w-4 flex-shrink-0" aria-hidden />
                {titel}
                {wert === 'system' && (
                  <span className="merkmal merkmal-grau">
                    aktuell {effektiv === 'dunkel' ? 'dunkel' : 'hell'}
                  </span>
                )}
              </span>
              <span className="mt-0.5 block text-xs text-leise">{text}</span>
            </span>
          </label>
        ))}
      </fieldset>
    </section>
  );
}

function Anwendungspasswort() {
  const [alt, setAlt] = useState('');
  const [neu, setNeu] = useState('');
  const [wiederholung, setWiederholung] = useState('');
  const [fehler, setFehler] = useState<string | null>(null);
  const [ok, setOk] = useState(false);
  const [laeuft, setLaeuft] = useState(false);

  const absenden = async (ereignis: FormEvent) => {
    ereignis.preventDefault();
    setFehler(null);
    setOk(false);
    if (neu !== wiederholung) {
      setFehler('Die beiden neuen Passwörter stimmen nicht überein.');
      return;
    }
    if (neu.length < MIN_PASSWORTLAENGE) {
      setFehler(`Das neue Passwort muss mindestens ${MIN_PASSWORTLAENGE} Zeichen lang sein.`);
      return;
    }
    setLaeuft(true);
    try {
      await api.auth.passwortAendern(alt, neu);
      setAlt('');
      setNeu('');
      setWiederholung('');
      setOk(true);
    } catch (ursache) {
      setFehler(ursache instanceof ApiFehler ? ursache.message : 'Unbekannter Fehler.');
    } finally {
      setLaeuft(false);
    }
  };

  return (
    <section className="karte mt-6 p-4">
      <h2 className="font-medium text-stark">Anwendungspasswort ändern</h2>
      <p className="lesebreite mt-1 text-sm text-leise">
        Das Passwort dieser Oberfläche, nicht das Kleinanzeigen-Konto.
        Danach enden alle Sitzungen, auch diese.
      </p>
      {fehler && (
        <p role="alert" className="hinweis hinweis-fehler lesebreite mt-3">
          {fehler}
        </p>
      )}
      {ok && (
        <p className="hinweis lesebreite mt-3">
          Passwort geändert.
        </p>
      )}
      <form onSubmit={ereignis => void absenden(ereignis)} className="lesebreite mt-3 space-y-3">
        <label className="block">
          <span className="beschriftung">Bisheriges Passwort</span>
          <input
            type="password"
            value={alt}
            onChange={e => setAlt(e.target.value)}
            autoComplete="current-password"
            required
            className="feld mt-1"
          />
        </label>
        <label className="block">
          <span className="beschriftung">Neues Passwort</span>
          <input
            type="password"
            value={neu}
            onChange={e => setNeu(e.target.value)}
            autoComplete="new-password"
            minLength={MIN_PASSWORTLAENGE}
            required
            className="feld mt-1"
          />
        </label>
        <label className="block">
          <span className="beschriftung">Neues Passwort wiederholen</span>
          <input
            type="password"
            value={wiederholung}
            onChange={e => setWiederholung(e.target.value)}
            autoComplete="new-password"
            required
            className="feld mt-1"
          />
        </label>
        <button
          type="submit"
          disabled={laeuft}
          className="btn-primaer"
        >
          {laeuft ? 'Speichert …' : 'Passwort ändern'}
        </button>
      </form>
    </section>
  );
}

function BrowserprofilReset({ profil }: { profil: string }) {
  const [fragt, setFragt] = useState(false);
  const [laeuft, setLaeuft] = useState(false);
  const [fehler, setFehler] = useState<string | null>(null);
  const [ok, setOk] = useState(false);

  const ausfuehren = async () => {
    setFehler(null);
    setLaeuft(true);
    try {
      await api.einstellungen.browserprofilZuruecksetzen(profil);
      setOk(true);
      setFragt(false);
    } catch (ursache) {
      setFehler(ursache instanceof ApiFehler ? ursache.message : 'Unbekannter Fehler.');
    } finally {
      setLaeuft(false);
    }
  };

  return (
    <section className="karte mt-6 p-4">
      <h2 className="flex items-center gap-2 font-medium text-stark">
        <RotateCcw className="h-5 w-5 text-primary-custom" />
        Browserprofil zurücksetzen
      </h2>
      <p className="lesebreite mt-1 text-sm text-leise">
        Löscht nur den Chromium-Ordner dieses Profils (Anmeldung im Browser, Cookies).
        Anzeigen und die Datenbank bleiben. Der nächste Lauf legt den Ordner neu an –
        dann ist eine erneute Anmeldung auf kleinanzeigen.de nötig.
      </p>
      {fehler && (
        <p role="alert" className="hinweis hinweis-fehler lesebreite mt-3">
          {fehler}
        </p>
      )}
      {ok && (
        <p className="hinweis lesebreite mt-3">
          Browserprofil gelöscht.
        </p>
      )}
      {!fragt ? (
        <button
          type="button"
          onClick={() => { setFragt(true); setOk(false); }}
          className="btn-ghost mt-3" style={{ color: 'var(--hinweis-fehler-text)', borderColor: 'var(--hinweis-fehler-rand)' }}
        >
          Browserprofil zurücksetzen
        </button>
      ) : (
        <div className="hinweis hinweis-warn lesebreite mt-3">
          <p>
            Die gespeicherte Browseranmeldung geht verloren. Anzeigen bleiben.
            Wirklich zurücksetzen?
          </p>
          <div className="mt-3 flex gap-2">
            <button
              type="button"
              onClick={() => void ausfuehren()}
              disabled={laeuft}
              className="btn-primaer" style={{ background: 'var(--status-fehler)', color: '#fff' }}
            >
              {laeuft ? 'Löscht …' : 'Ja, zurücksetzen'}
            </button>
            <button
              type="button"
              onClick={() => setFragt(false)}
              className="btn-ghost"
            >
              Abbrechen
            </button>
          </div>
        </div>
      )}
    </section>
  );
}
