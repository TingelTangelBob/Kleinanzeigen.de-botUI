// SPDX-FileCopyrightText: © Anzeigen-Studio contributors
// SPDX-License-Identifier: AGPL-3.0-or-later
//
// Einstellungen der Bot-Konfiguration (AP-2.9).
//
// Das Formular kommt vom Backend, erzeugt aus schemas/config.schema.json.
// Neue Upstream-Felder erscheinen erst, wenn sie einer Gruppe zugeordnet sind.
// Die vier Sperrfelder aus AP-1.11 und Login-Klartext sind serverseitig
// nicht setzbar – und hier auch nicht angeboten.

import { useCallback, useEffect, useMemo, useState, type FormEvent, type ReactNode } from 'react';
import {
  AlertTriangle, Check, ChevronsDownUp, ChevronsUpDown, KeyRound, Monitor, Moon, RotateCcw, Save,
  Search, Sparkles, Sun,
} from 'lucide-react';
import type { LucideIcon } from 'lucide-react';
import { api, ApiFehler } from '../services/api';
import { useProfil } from '../context/useProfil';
import { useThema, type ThemaWahl } from '../hooks/useThema';
import type { EinstellungsAbschnitt } from '../routing';
import type { EinstellungsFeld, EinstellungsGruppe, ZugangStatus } from '../types';
import { BrowsersichtSeite } from './BrowsersichtSeite';
import { ProfilSeite } from './ProfilSeite';

const MIN_PASSWORTLAENGE = 12;

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
          <span className="block text-sm font-medium text-stark">{feld.titel}</span>
          {feld.beschreibung && (
            <span className="lesebreite mt-0.5 block text-xs text-leise">{feld.beschreibung}</span>
          )}
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
    // Zwei Deckel, mit Absicht (AP-2.16): `.lesebreite` am Label begrenzt das
    // Eingabefeld, `.lesebreite` an der Beschreibung noch einmal den Text. Der
    // Deckel rechnet in `ch` und damit in der Schriftgröße des Elements, an dem
    // er hängt - eine 12px-Beschreibung im 16px-Label bekäme sonst 87 Zeichen
    // je Zeile statt 70.
    <label htmlFor={id} className="lesebreite block">
      <span className="beschriftung">{feld.titel}</span>
      {feld.beschreibung && (
        <span className="lesebreite mt-0.5 block text-xs text-leise">{feld.beschreibung}</span>
      )}
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
      {felder.map(feld => (
        <Feld
          key={feld.pfad}
          feld={feld}
          wert={holen(werte, feld.pfad)}
          onChange={wert => onChange(feld.pfad, wert)}
        />
      ))}
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
  const { aktiv, laedt: profileLaden } = useProfil();
  const [gruppen, setGruppen] = useState<EinstellungsGruppe[]>([]);
  const [werte, setWerte] = useState<Record<string, unknown>>({});
  const [zugang, setZugang] = useState<ZugangStatus | null>(null);
  const [fehler, setFehler] = useState<string | null>(null);
  const [laedt, setLaedt] = useState(true);
  const [speichert, setSpeichert] = useState(false);
  const [gespeichert, setGespeichert] = useState(false);
  const [schmutzig, setSchmutzig] = useState(false);
  // AP-2.19: Suche, Klappzustand je Gruppe und die Pfade, die seit dem Laden
  // angefasst wurden. Letztere nur, damit eine zugeklappte Gruppe zeigen kann,
  // dass in ihr etwas hängt - gespeichert wird unverändert alles.
  const [suche, setSuche] = useState('');
  const [offeneGruppen, setOffeneGruppen] = useState<Record<string, boolean>>({});
  const [angefasst, setAngefasst] = useState<Set<string>>(new Set());

  const laden = useCallback(async () => {
    if (!aktiv) {
      setLaedt(false);
      return;
    }
    setLaedt(true);
    setFehler(null);
    try {
      const [daten, zugangsdaten] = await Promise.all([
        api.einstellungen.lesen(aktiv.slug),
        api.profile.zugang(aktiv.slug),
      ]);
      setGruppen(daten.gruppen);
      setWerte(daten.werte);
      setZugang(zugangsdaten);
      setSchmutzig(false);
      setGespeichert(false);
      setAngefasst(new Set());
      // Der Startzustand kommt weiter aus den Daten (`eingeklappt`), nicht aus
      // einer eigenen Vorliebe der Oberfläche.
      setOffeneGruppen(Object.fromEntries(daten.gruppen.map(g => [g.id, !g.eingeklappt])));
    } catch (ursache) {
      setFehler(ursache instanceof ApiFehler ? ursache.message : 'Unbekannter Fehler.');
    } finally {
      setLaedt(false);
    }
  }, [aktiv]);

  useEffect(() => { void laden(); }, [laden]);

  const aendern = (pfad: string, wert: unknown) => {
    setWerte(vorher => setzen(vorher, pfad, wert));
    setAngefasst(vorher => new Set(vorher).add(pfad));
    setSchmutzig(true);
    setGespeichert(false);
  };

  const speichern = async () => {
    if (!aktiv) return;
    setFehler(null);
    setSpeichert(true);
    try {
      let payload: Record<string, unknown> = {};
      for (const gruppe of gruppen) {
        for (const feld of gruppe.felder) {
          const wert = holen(werte, feld.pfad);
          if (wert !== undefined) payload = setzen(payload, feld.pfad, wert);
        }
      }
      const antwort = await api.einstellungen.speichern(aktiv.slug, payload);
      setWerte(antwort.werte);
      setSchmutzig(false);
      setAngefasst(new Set());
      setGespeichert(true);
    } catch (ursache) {
      setFehler(ursache instanceof ApiFehler ? ursache.message : 'Unbekannter Fehler.');
    } finally {
      setSpeichert(false);
    }
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

  const sichtbareGruppen = useMemo(() => {
    if (!sucheAktiv) return gruppen.map(g => ({ gruppe: g, felder: g.felder }));
    return gruppen
      .map(g => {
        const gruppeTrifft = heuhaufen(`${g.titel} ${g.beschreibung}`).includes(gesucht);
        return {
          gruppe: g,
          felder: gruppeTrifft ? g.felder : g.felder.filter(f => feldPasst(f, gesucht)),
        };
      })
      .filter(t => t.felder.length > 0);
  }, [gruppen, gesucht, sucheAktiv]);

  const felderGesamt = useMemo(
    () => gruppen.reduce((summe, g) => summe + g.felder.length, 0),
    [gruppen],
  );
  const felderSichtbar = sichtbareGruppen.reduce((summe, t) => summe + t.felder.length, 0);
  const alleOffen = sichtbareGruppen.length > 0
    && sichtbareGruppen.every(t => offeneGruppen[t.gruppe.id]);

  const alleKlappen = (offen: boolean) => {
    setOffeneGruppen(Object.fromEntries(gruppen.map(g => [g.id, offen])));
  };

  /** Wie viele angefasste Felder in einer Gruppe liegen - für die Kopfzeile. */
  const geaendertIn = (gruppe: EinstellungsGruppe) =>
    gruppe.felder.filter(f => angefasst.has(f.pfad)).length;

  const diagnoseHinweis = useMemo(() => {
    const gruppe = gruppen.find(g => g.id === 'diagnostics');
    if (!gruppe?.warnung) return false;
    return gruppe.felder.some(feld => {
      const wert = holen(werte, feld.pfad);
      const aktuell = wert === undefined ? feld.vorgabe : wert;
      return aktuell === true;
    });
  }, [gruppen, werte]);

  if (profileLaden) {
    return <p className="text-sm text-leise">Wird geladen …</p>;
  }

  // „Läufe" ist hier weder Reiter noch Unterseite mehr (AP-2.28/2.31): Der
  // Einstieg ist der Menüpunkt „Warteschlange". Die alte Route
  // `einstellungen/laeufe` wird in `routing.ts` auf `warteschlange` umgelenkt,
  // damit Glocke, Dashboard und Editor nicht ins Leere führen.
  const tabs: { id: EinstellungsAbschnitt; label: string; hash: string }[] = [
    { id: 'bot', label: 'Bot', hash: 'einstellungen' },
    { id: 'profile', label: 'Profile', hash: 'einstellungen/profile' },
    { id: 'browser', label: 'Browser', hash: 'einstellungen/browser' },
    { id: 'passwort', label: 'Passwort', hash: 'einstellungen/passwort' },
    { id: 'darstellung', label: 'Darstellung', hash: 'einstellungen/darstellung' },
  ];

  const unternav = (
    <nav className="reiter-leiste mb-8 overflow-x-auto" aria-label="Einstellungsbereiche">
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
  );

  if (abschnitt === 'profile') {
    return (
      <div className="seite">
        <h1 className="sr-only">Einstellungen</h1>
        <p className="seite-beschrieb mb-6">Kleinanzeigen-Konten und KI-Zugang.</p>
        {unternav}
        <ProfilSeite ohneTitel />
      </div>
    );
  }

  if (abschnitt === 'browser') {
    return (
      <div className="seite">
        <h1 className="sr-only">Einstellungen</h1>
        <p className="seite-beschrieb mb-6">Eingebetteter Browser und Profilreset.</p>
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
        <p className="seite-beschrieb mb-6">Passwort dieser Oberfläche, nicht das Kleinanzeigen-Konto.</p>
        {unternav}
        <Anwendungspasswort />
      </div>
    );
  }

  if (abschnitt === 'darstellung') {
    return (
      <div className="seite">
        <h1 className="sr-only">Einstellungen</h1>
        <p className="seite-beschrieb mb-6">Thema dieser Oberfläche – gilt je Browser, nicht je Konto.</p>
        {unternav}
        <DarstellungAbschnitt />
      </div>
    );
  }

  if (!aktiv) {
    return (
      <div className="seite">
        <h1 className="sr-only">Einstellungen</h1>
        <p className="seite-beschrieb mb-6">Bot-Konfiguration gilt je Konto.</p>
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

  return (
    // `pb-24` hält den Platz für die feste Speichern-Leiste frei, sonst deckt
    // sie die letzte Gruppe zu (AP-2.19).
    <div className="seite pb-24">
      <h1 className="sr-only">
        Einstellungen
      </h1>

      <p className="seite-beschrieb mb-6">
        Gilt für <span className="font-medium text-stark">{aktiv.anzeigename}</span>.
        Gespeichert wird in diesem Profil; der nächste Lauf übernimmt die Werte.
      </p>
      {unternav}

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

      {diagnoseHinweis && (
        <p role="alert" className="hinweis hinweis-warn lesebreite mb-4">
          <AlertTriangle className="mb-1 inline h-4 w-4" /> Diagnose ist eingeschaltet.
          Die Artefakte enthalten Bildschirmfotos und das vollständige DOM einer angemeldeten
          Sitzung – Klarname, Adresse und Telefonnummer.
        </p>
      )}

      <section className="karte mb-4 p-4">
        <h2 className="flex items-center gap-2 font-medium text-stark">
          <KeyRound className="h-5 w-5 text-primary-custom" />
          Zugangsdaten kleinanzeigen.de
        </h2>
        <p className="lesebreite mt-1 text-sm text-leise">
          Die Anmeldung an der Plattform steht nicht in der Bot-Konfiguration –
          nur als Platzhalter. Hinterlegt wird sie unter Profile, verschlüsselt.
        </p>
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

      {/* Suchzeile über den Gruppen (AP-2.19). Der Bot-Reiter führt gut vier
          Dutzend Felder in zehn Gruppen; wer eine Zeitgrenze sucht, soll nicht
          scrollen, sondern tippen. */}
      <div className="mb-3 flex flex-wrap items-center gap-2">
        {/* `basis-full` unter sm: neben dem Klappknopf blieb dem Suchfeld auf
            375 px so wenig übrig, dass der Platzhalter nach „Einstellung suc"
            abriss. */}
        <label className="relative block min-w-0 flex-1 basis-full sm:basis-auto">
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
        {!sucheAktiv && (
          <button
            type="button"
            onClick={() => alleKlappen(!alleOffen)}
            className="btn-ghost flex-shrink-0"
          >
            {alleOffen
              ? <><ChevronsDownUp className="h-4 w-4" aria-hidden /> Alle zuklappen</>
              : <><ChevronsUpDown className="h-4 w-4" aria-hidden /> Alle aufklappen</>}
          </button>
        )}
      </div>

      <p className="mb-2 text-xs text-leise">
        {sucheAktiv
          ? `${felderSichtbar} von ${felderGesamt} Einstellungen`
          : `${felderGesamt} Einstellungen in ${gruppen.length} Gruppen`}
      </p>

      {sichtbareGruppen.length === 0 ? (
        <p className="leer">Keine Einstellung passt zu „{suche.trim()}".</p>
      ) : (
        <div className="space-y-3">
          {sichtbareGruppen.map(({ gruppe, felder }) => (
            <Gruppe
              key={gruppe.id}
              gruppe={gruppe}
              felder={felder}
              werte={werte}
              onChange={aendern}
              offen={offeneGruppen[gruppe.id] ?? !gruppe.eingeklappt}
              aufOffen={offen => setOffeneGruppen(vorher => ({ ...vorher, [gruppe.id]: offen }))}
              geaendert={geaendertIn(gruppe)}
              ohneKlapp={sucheAktiv}
            />
          ))}
        </div>
      )}

      <KiHinweis aufZiel={aufZiel} />

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
            <span className="text-sm text-leise">
              {angefasst.size === 1 ? '1 Änderung' : `${angefasst.size} Änderungen`} ungespeichert
            </span>
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

function KiHinweis({ aufZiel }: { aufZiel: (ziel: string) => void }) {
  return (
    <section className="karte mt-6 p-4">
      <h2 className="flex items-center gap-2 font-medium text-stark">
        <Sparkles className="h-5 w-5 text-primary-custom" />
        LLM-Schlüssel
      </h2>
      <p className="lesebreite mt-1 text-sm text-leise">
        Der Schlüssel zum KI-Anbieter gilt für die ganze Installation, nicht für ein
        Profil, und wird nicht in der Bot-Konfiguration gespeichert. Verwalten unter Profile.
      </p>
      <button
        type="button"
        onClick={() => aufZiel('einstellungen/profile')}
        className="btn-ghost mt-3"
      >
        Zum KI-Zugang
      </button>
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
    { wert: 'hell', titel: 'Hell', text: 'Immer helles Erscheinungsbild.', icon: Sun },
    { wert: 'dunkel', titel: 'Dunkel', text: 'Immer dunkles Erscheinungsbild.', icon: Moon },
    {
      wert: 'system',
      titel: 'System',
      text: 'Folgt dem Betriebssystem und wechselt automatisch mit.',
      icon: Monitor,
    },
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
