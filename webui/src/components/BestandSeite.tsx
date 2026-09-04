// SPDX-FileCopyrightText: © Anzeigen-Studio contributors
// SPDX-License-Identifier: AGPL-3.0-or-later
//
// Der lokale Anzeigenbestand: Liste, Suche, Filter (AP-2.4, AP-3.2).
//
// Gefiltert und gesucht wird in der Oberfläche, nicht im Backend. Bei einem
// privaten Bestand - Dutzende Anzeigen, nicht Zehntausende - ist das die
// einfachere Lösung und fühlt sich besser an, weil jeder Tastendruck sofort
// wirkt. Sobald ein Bestand das nicht mehr hergibt, wandert es serverseitig.

import { useCallback, useEffect, useMemo, useState } from 'react';
import {
  AlertTriangle, ArrowLeftRight, Download, RefreshCw, Search, Trash2, Upload, X,
} from 'lucide-react';
import { api, ApiFehler } from '../services/api';
import { useProfil } from '../context/useProfil';
import type { AnzeigenHerkunft } from '../routing';
import type { BestandsAnzeige } from '../types';
import { AnzeigenEditor } from './AnzeigenEditor';
import { AnzeigenZeile } from './AnzeigenZeile';
import { LoeschDialog } from './LoeschDialog';
import { NachladenDialog } from './NachladenDialog';
import { VorlagenListe } from './VorlagenListe';

type Filter = 'aktiv' | 'faellig' | 'geaendert' | 'auffaellig' | 'geloescht' | 'alle';

/*
 * Reihenfolge und Vorgabe (AP-2.36).
 *
 * „Alle" stand vorn und war die Vorgabe - und zeigte damit als Erstes auch
 * jede gelöschte Anzeige. Nach einem Konto-Download mit vielen abgelaufenen
 * Anzeigen ist das eine Liste, in der das Aktuelle untergeht.
 *
 * Jetzt ist „Aktiv" die Vorgabe, und „Alle" heißt wieder wörtlich alle - es
 * steht am Ende, wo man es sucht, wenn man wirklich alles sehen will. Damit
 * bleibt „Alle" ehrlich, statt still etwas wegzulassen.
 */
const FILTER: { id: Filter; label: string }[] = [
  { id: 'aktiv', label: 'Aktiv' },
  { id: 'faellig', label: 'Fällig' },
  { id: 'geaendert', label: 'Lokal geändert' },
  { id: 'auffaellig', label: 'Mit Hinweis' },
  { id: 'geloescht', label: 'Gelöscht' },
  { id: 'alle', label: 'Alle' },
];

const STANDARD_FILTER: Filter = 'aktiv';

function passtZumFilter(anzeige: BestandsAnzeige, filter: Filter): boolean {
  switch (filter) {
    // „Aktiv" heißt: steht auf der Plattform noch. `geloescht` deckt die
    // eigenen ab (AP-3.10), `aktiv` zusätzlich alles, was das YAML-Feld
    // `active: false` trägt - etwa pausierte fremde Anzeigen.
    case 'aktiv': return anzeige.aktiv && !anzeige.geloescht;
    case 'faellig': return anzeige.faellig;
    case 'geaendert': return anzeige.lokal_geaendert;
    case 'auffaellig': return anzeige.hinweise.length > 0 || anzeige.unlesbar !== null;
    case 'geloescht': return anzeige.geloescht || !anzeige.aktiv;
    default: return true;
  }
}

function passtZurSuche(anzeige: BestandsAnzeige, suche: string): boolean {
  if (!suche) return true;
  const begriff = suche.trim().toLowerCase();
  if (!begriff) return true;
  return [anzeige.titel, anzeige.kategorie ?? '', String(anzeige.id ?? '')]
    .some(feld => feld.toLowerCase().includes(begriff));
}

export function BestandSeite({
  herkunft, aufZiel,
}: {
  herkunft: AnzeigenHerkunft;
  aufZiel: (ziel: string) => void;
}) {
  const { aktiv, laedt: profileLaden } = useProfil();
  const [anzeigen, setAnzeigen] = useState<BestandsAnzeige[]>([]);
  const [laedt, setLaedt] = useState(false);
  const [fehler, setFehler] = useState<string | null>(null);
  const [suche, setSuche] = useState('');
  const [filter, setFilter] = useState<Filter>(STANDARD_FILTER);
  const [bearbeitet, setBearbeitet] = useState<string | null>(null);
  const [holtNach, setHoltNach] = useState(false);
  const [warnung, setWarnung] = useState<BestandsAnzeige[] | null>(null);
  const [startetDownload, setStartetDownload] = useState(false);
  const [downloadHinweis, setDownloadHinweis] = useState<number | null>(null);
  const [zuletztHerkunft, setZuletztHerkunft] = useState<AnzeigenHerkunft>(herkunft);
  // AP-2.20: Mehrfachauswahl über die Dateipfade - dieselbe Kennung, mit der
  // auch das Backend arbeitet.
  const [auswahl, setAuswahl] = useState<Set<string>>(new Set());
  const [loeschDialog, setLoeschDialog] = useState<BestandsAnzeige[] | null>(null);
  const [sammelLaeuft, setSammelLaeuft] = useState<string | null>(null);
  const [sammelHinweis, setSammelHinweis] = useState<string | null>(null);

  // App.tsx rendert für #anzeigen/eigene und #anzeigen/fremde dieselbe
  // Komponente; nur `herkunft` wechselt. React unmountet dabei nicht, also
  // bliebe eine offene Bearbeiten-Maske stehen, während die Seitenleiste
  // bereits die andere Herkunft markiert (AP-2.13).
  //
  // Zurückgesetzt wird während des Renderns statt in einem Effekt: ein Effekt
  // liefe erst nach dem Anzeigen, die alte Maske wäre also einen Frame lang
  // unter der neuen Navigation zu sehen. Das ist das von React dokumentierte
  // Muster, Zustand an geänderte Eigenschaften anzupassen.
  if (zuletztHerkunft !== herkunft) {
    setZuletztHerkunft(herkunft);
    setBearbeitet(null);
    setHoltNach(false);
    setWarnung(null);
    setDownloadHinweis(null);
    setFehler(null);
    setSuche('');
    setFilter(STANDARD_FILTER);
    setAuswahl(new Set());
    setLoeschDialog(null);
    setSammelHinweis(null);
  }

  const laden = useCallback(async () => {
    if (!aktiv) {
      setAnzeigen([]);
      return;
    }
    setLaedt(true);
    setFehler(null);
    try {
      setAnzeigen(await api.bestand.liste(aktiv.slug));
    } catch (ursache) {
      setFehler(ursache instanceof ApiFehler ? ursache.message : 'Unbekannter Fehler.');
    } finally {
      setLaedt(false);
    }
  }, [aktiv]);

  useEffect(() => {
    void laden();
  }, [laden]);

  const sichtbar = useMemo(
    () => anzeigen.filter(a => a.herkunft === herkunft),
    [anzeigen, herkunft],
  );

  const gefiltert = useMemo(
    () => sichtbar.filter(a => passtZumFilter(a, filter) && passtZurSuche(a, suche)),
    [sichtbar, filter, suche],
  );

  const zaehler = useMemo(() => ({
    aktiv: sichtbar.filter(a => a.aktiv && !a.geloescht).length,
    faellig: sichtbar.filter(a => a.faellig).length,
    geaendert: sichtbar.filter(a => a.lokal_geaendert).length,
    auffaellig: sichtbar.filter(a => a.hinweise.length > 0 || a.unlesbar).length,
    geloescht: sichtbar.filter(a => a.geloescht || !a.aktiv).length,
    alle: sichtbar.length,
  }), [sichtbar]);

  const kontoHolen = async (trotzdem = false) => {
    if (!aktiv) return;
    setFehler(null);
    setStartetDownload(true);
    try {
      if (!trotzdem) {
        try {
          const betroffen = await api.bestand.lokaleAenderungen(aktiv.slug);
          const eigene = betroffen.filter(a => a.herkunft === 'eigene');
          if (eigene.length > 0) {
            setWarnung(eigene);
            return;
          }
        } catch {
          // Die Prüfung ist eine Vorsichtsmaßnahme, keine Voraussetzung.
        }
      }
      const job = await api.jobs.starten(aktiv.slug, 'download');
      setDownloadHinweis(job.id);
    } catch (ursache) {
      setFehler(ursache instanceof ApiFehler ? ursache.message : 'Unbekannter Fehler.');
    } finally {
      setStartetDownload(false);
    }
  };

  const umsortieren = async (anzeige: BestandsAnzeige) => {
    if (!aktiv) return;
    const ziel = anzeige.herkunft === 'eigene' ? 'fremde' : 'eigene';
    try {
      await api.bestand.herkunftSetzen(aktiv.slug, anzeige.datei, ziel);
      await laden();
    } catch (ursache) {
      setFehler(ursache instanceof ApiFehler ? ursache.message : 'Unbekannter Fehler.');
    }
  };

  // --- Mehrfachauswahl (AP-2.20) -----------------------------------------

  const gewaehlte = useMemo(
    () => gefiltert.filter(a => auswahl.has(a.datei)),
    [gefiltert, auswahl],
  );
  const alleGewaehlt = gefiltert.length > 0 && gewaehlte.length === gefiltert.length;

  const umschalten = (datei: string) => {
    setAuswahl(vorher => {
      const neu = new Set(vorher);
      if (neu.has(datei)) neu.delete(datei);
      else neu.add(datei);
      return neu;
    });
  };

  const alleUmschalten = () => {
    setAuswahl(alleGewaehlt ? new Set() : new Set(gefiltert.map(a => a.datei)));
  };

  /**
   * Eine Sammelaktion über die Auswahl.
   *
   * Die Auswahl wird erst geleert, wenn der Durchlauf fertig ist - bricht er
   * ab, bleibt sie stehen, damit man sieht, worum es ging, und es erneut
   * versuchen kann.
   */
  const sammeln = async (
    art: string, tun: (dateien: string[]) => Promise<string>,
  ) => {
    if (!aktiv || gewaehlte.length === 0) return;
    setFehler(null);
    setSammelHinweis(null);
    setSammelLaeuft(art);
    try {
      const meldung = await tun(gewaehlte.map(a => a.datei));
      setAuswahl(new Set());
      setSammelHinweis(meldung);
    } catch (ursache) {
      setFehler(ursache instanceof ApiFehler ? ursache.message : 'Unbekannter Fehler.');
    } finally {
      setSammelLaeuft(null);
      await laden();
    }
  };

  const sammelHerkunft = () => sammeln('herkunft', async dateien => {
    const ziel = herkunft === 'eigene' ? 'fremde' : 'eigene';
    // Nacheinander, nicht parallel: Der Endpunkt verschiebt Ordner. Zwei
    // gleichzeitige Umzüge in dasselbe Ziel wären ein Wettlauf um denselben
    // Ordnernamen.
    for (const datei of dateien) {
      await api.bestand.herkunftSetzen(aktiv!.slug, datei, ziel);
    }
    return `${dateien.length} ${dateien.length === 1 ? 'Anzeige' : 'Anzeigen'} verschoben.`;
  });

  const sammelHochladen = () => sammeln('hochladen', async dateien => {
    const jobs: number[] = [];
    for (const datei of dateien) {
      const antwort = await api.bestand.hochladen(aktiv!.slug, datei);
      jobs.push(antwort.job_id);
    }
    return `${jobs.length} ${jobs.length === 1 ? 'Lauf' : 'Läufe'} eingereiht.`;
  });

  const loeschenAusfuehren = (dateien: string[]) => sammeln('loeschen', async () => {
    const antwort = await api.bestand.loeschen(aktiv!.slug, dateien);
    const anzahl = antwort.geloescht.length;
    const bilder = antwort.geloescht.reduce((summe, g) => summe + g.bilder, 0);
    setLoeschDialog(null);
    return `${anzahl} ${anzahl === 1 ? 'Anzeige' : 'Anzeigen'} und ${bilder} `
      + `${bilder === 1 ? 'Bild' : 'Bilder'} von diesem Rechner gelöscht.`;
  });

  if (bearbeitet && aktiv) {
    return (
      <AnzeigenEditor
        profil={aktiv.slug}
        datei={bearbeitet}
        // Vorabwert fürs „Gelöscht"-Badge (AP-3.10); der Editor bestätigt es
        // aus den frisch geladenen Kopfdaten.
        geloescht={anzeigen.find(a => a.datei === bearbeitet)?.geloescht ?? false}
        aufZurueck={geaendert => {
          setBearbeitet(null);
          if (geaendert) void laden();
        }}
        aufKopie={kopie => {
          void laden();
          setBearbeitet(kopie);
        }}
        // Die Datei ist weg - die Maske darauf wäre eine Maske auf nichts
        // (AP-2.20).
        aufGeloescht={() => {
          setBearbeitet(null);
          setAuswahl(new Set());
          setSammelHinweis('Anzeige von diesem Rechner gelöscht.');
          void laden();
        }}
      />
    );
  }

  if (profileLaden) return <p className="text-sm text-leise">Wird geladen …</p>;

  if (!aktiv) {
    return (
      <p className="hinweis hinweis-warn">
        Zuerst ein Profil anlegen.
      </p>
    );
  }

  const eigene = herkunft === 'eigene';

  return (
    <div className="seite">
      <div className="seite-kopf">
        <div>
          <h1 className="sr-only">{eigene ? 'Meine Anzeigen' : 'Von anderen'}</h1>
          <p className="seite-beschrieb">
            {eigene
              ? 'Anzeigen aus deinem Kleinanzeigen-Konto.'
              : 'Anzeigen, die du per Link geholt hast – nicht aus deinem Konto.'}
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          {eigene ? (
            <button
              type="button"
              onClick={() => void kontoHolen()}
              disabled={startetDownload}
              className="btn-primaer"
            >
              <Download className="h-4 w-4" aria-hidden />
              {startetDownload ? 'Wird eingereiht …' : 'Vom Konto holen'}
            </button>
          ) : (
            <button
              type="button"
              onClick={() => setHoltNach(true)}
              className="btn-primaer"
            >
              <Download className="h-4 w-4" aria-hidden />
              Anzeigen per Link holen
            </button>
          )}
          <button
            type="button"
            onClick={() => void laden()}
            className="btn-ghost"
          >
            <RefreshCw className={`h-4 w-4 ${laedt ? 'animate-spin' : ''}`} aria-hidden />
            Neu einlesen
          </button>
        </div>
      </div>

      {holtNach && (
        <NachladenDialog profil={aktiv.slug} aufSchliessen={() => { setHoltNach(false); void laden(); }} />
      )}

      {loeschDialog && (
        <LoeschDialog
          anzeigen={loeschDialog}
          laeuft={sammelLaeuft === 'loeschen'}
          aufAbbrechen={() => setLoeschDialog(null)}
          aufLoeschen={() => void loeschenAusfuehren(loeschDialog.map(a => a.datei))}
        />
      )}

      {warnung && (
        <UeberschreibWarnung
          anzeigen={warnung}
          aufAbbrechen={() => setWarnung(null)}
          aufWeiter={() => {
            setWarnung(null);
            void kontoHolen(true);
          }}
        />
      )}

      {/* Kein Vollbreite-Banner mehr (AP-2.25): Der eingereihte Lauf steht in
          der Glocke oben. Hier bleibt die kurze Zeile mit dem Weg dorthin. */}
      {downloadHinweis !== null && (
        <p className="mb-4 text-sm text-leise">
          Lauf {downloadHinweis} ist eingereiht.{' '}
          <button
            type="button"
            onClick={() => aufZiel('warteschlange')}
            className="font-medium underline"
          >
            Zur Warteschlange
          </button>
        </p>
      )}

      {fehler && (
        <p className="hinweis hinweis-fehler mb-4">{fehler}</p>
      )}

      {!eigene && (
        <p className="hinweis hinweis-warn mb-4 flex items-start gap-2">
          <AlertTriangle className="mt-0.5 h-4 w-4 flex-shrink-0" aria-hidden />
          <span>
            Nur was auf kleinanzeigen.de noch als Seite erreichbar ist, lässt sich holen.
            Endgültig gelöschte Anzeigen sind weg – kein Werkzeug holt sie zurück.
          </span>
        </p>
      )}

      {eigene && (
        <VorlagenListe
          profil={aktiv.slug}
          aufAngewendet={datei => {
            void laden();
            setBearbeitet(datei);
          }}
        />
      )}

      <div className="mb-4 space-y-3">
        <label className="relative block">
          <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-leise" aria-hidden />
          <span className="sr-only">Anzeigen durchsuchen</span>
          <input
            type="search"
            value={suche}
            onChange={e => setSuche(e.target.value)}
            placeholder="Titel, Kategorie oder Anzeigennummer"
            className="feld py-2 pl-9 pr-3"
          />
        </label>

        <div className="reiter-leiste">
          {FILTER.map(f => {
            // Jeder Reiter trägt seine Zahl (AP-2.36). Vorher hatten drei von
            // fünf eine - gerade „Gelöscht" ist die Zahl aber die Auskunft, ob
            // sich ein Blick überhaupt lohnt.
            const anzahl = zaehler[f.id] ?? null;
            return (
              <button
                key={f.id}
                type="button"
                onClick={() => setFilter(f.id)}
                aria-pressed={filter === f.id}
                className={`reiter ${filter === f.id ? 'reiter-aktiv' : ''}`}
              >
                {f.label}{anzahl !== null && anzahl > 0 ? ` (${anzahl})` : ''}
              </button>
            );
          })}
        </div>
      </div>

      {sichtbar.length === 0 && !laedt ? (
        <div className="leer">
          <p>
            {eigene ? 'Noch keine eigenen Anzeigen auf der Platte.' : 'Noch keine Anzeigen von anderen.'}
          </p>
          <p className="mt-1 text-leise">
            {eigene
              ? '„Vom Konto holen“ lädt den Bestand deines Kleinanzeigen-Kontos.'
              : '„Anzeigen per Link holen“ nimmt beliebige Kleinanzeigen-Adressen entgegen.'}
          </p>
        </div>
      ) : (
        <>
          {/* Zählzeile und Alles-Wählen in einer Zeile (AP-2.20). Das Kästchen
              wählt, was gerade sichtbar ist - nicht den ganzen Bestand. Alles
              andere wäre eine Auswahl, die man nicht sieht. */}
          <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
            <label className="flex items-center gap-2 text-xs text-leise">
              <input
                type="checkbox"
                checked={alleGewaehlt}
                onChange={alleUmschalten}
                className="h-4 w-4"
                aria-label={alleGewaehlt ? 'Auswahl aufheben' : 'Alle sichtbaren auswählen'}
              />
              {gefiltert.length} von {sichtbar.length} Anzeigen
            </label>
            {sammelHinweis && (
              <span className="text-xs text-leise">{sammelHinweis}</span>
            )}
          </div>

          {gewaehlte.length > 0 && (
            <SammelLeiste
              anzahl={gewaehlte.length}
              eigene={eigene}
              laeuft={sammelLaeuft}
              aufHerkunft={() => void sammelHerkunft()}
              aufHochladen={() => void sammelHochladen()}
              aufLoeschen={() => setLoeschDialog(gewaehlte)}
              aufAufheben={() => setAuswahl(new Set())}
            />
          )}
          {/* Der Rahmen entsteht nur mit Inhalt (AP-2.18). Ohne diese Bedingung
              stand bei „kein Treffer" ein 2 px hoher, leerer Kasten mit Rand und
              Schatten über dem gestrichelten Leerzustand - ein Strich, den
              niemand erklären kann. */}
          {gefiltert.length > 0 && (
          <ul className="liste">
            {gefiltert.map(a => (
              <li key={a.datei} className="sm:flex sm:items-stretch">
                <div className="flex items-center pl-4 pt-4 sm:pt-0">
                  <input
                    type="checkbox"
                    checked={auswahl.has(a.datei)}
                    onChange={() => umschalten(a.datei)}
                    className="h-4 w-4"
                    aria-label={`„${a.titel}" auswählen`}
                  />
                </div>
                <div className="min-w-0 flex-1">
                  <AnzeigenZeile
                    anzeige={a}
                    profil={aktiv.slug}
                    aufKlick={a.unlesbar ? undefined : () => setBearbeitet(a.datei)}
                  />
                </div>
                <div className="flex items-center px-3 pb-3 sm:pb-0">
                  <button
                    type="button"
                    onClick={() => void umsortieren(a)}
                    className="btn-ghost w-full text-xs sm:w-auto"
                    title={eigene ? 'Nach „Von anderen“ verschieben' : 'Zu meinen Anzeigen'}
                  >
                    <ArrowLeftRight className="h-3.5 w-3.5" aria-hidden />
                    {eigene ? 'Zu „Von anderen“' : 'Zu meinen'}
                  </button>
                </div>
              </li>
            ))}
          </ul>
          )}
          {gefiltert.length === 0 && (
            <p className="leer mt-3">Kein Treffer für diese Auswahl.</p>
          )}
        </>
      )}
    </div>
  );
}

/** Erscheint, sobald etwas ausgewählt ist, und verschwindet mit der Auswahl. */
function SammelLeiste({
  anzahl, eigene, laeuft, aufHerkunft, aufHochladen, aufLoeschen, aufAufheben,
}: {
  anzahl: number;
  eigene: boolean;
  laeuft: string | null;
  aufHerkunft: () => void;
  aufHochladen: () => void;
  aufLoeschen: () => void;
  aufAufheben: () => void;
}) {
  const gesperrt = laeuft !== null;
  return (
    <div
      role="group"
      aria-label="Sammelaktionen"
      className="karte mb-3 flex flex-wrap items-center gap-2 p-3"
    >
      <span className="mr-1 text-sm font-medium text-stark">
        {anzahl} ausgewählt
      </span>

      <button type="button" onClick={aufHerkunft} disabled={gesperrt} className="btn-ghost text-xs">
        <ArrowLeftRight className="h-3.5 w-3.5" aria-hidden />
        {laeuft === 'herkunft'
          ? 'Wird verschoben …'
          : eigene ? 'Zu „Von anderen"' : 'Zu meinen Anzeigen'}
      </button>

      <button type="button" onClick={aufHochladen} disabled={gesperrt} className="btn-ghost text-xs">
        <Upload className="h-3.5 w-3.5" aria-hidden />
        {laeuft === 'hochladen' ? 'Wird eingereiht …' : 'Hochladen'}
      </button>

      {/* Rot, weil es Dateien vernichtet - und nur hier, damit es sich vom
          Verschieben und Hochladen daneben unterscheidet. */}
      <button
        type="button"
        onClick={aufLoeschen}
        disabled={gesperrt}
        className="btn-ghost text-xs"
        style={{ color: 'var(--hinweis-fehler-text)', borderColor: 'var(--hinweis-fehler-rand)' }}
      >
        <Trash2 className="h-3.5 w-3.5" aria-hidden />
        Lokal löschen
      </button>

      <button type="button" onClick={aufAufheben} disabled={gesperrt} className="btn-leise ml-auto text-xs">
        <X className="h-3.5 w-3.5" aria-hidden />
        Auswahl aufheben
      </button>
    </div>
  );
}

function UeberschreibWarnung({
  anzeigen, aufAbbrechen, aufWeiter,
}: { anzeigen: BestandsAnzeige[]; aufAbbrechen: () => void; aufWeiter: () => void }) {
  return (
    <div className="fixed inset-0 z-50 flex items-end justify-center bg-black/40 p-4 sm:items-center">
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="warnung-titel"
        className="dialog"
      >
        <div className="mb-3 flex items-start gap-3">
          <AlertTriangle className="mt-0.5 h-5 w-5 flex-shrink-0 text-amber-600" aria-hidden />
          <div className="min-w-0">
            <h2 id="warnung-titel" className="font-semibold text-stark">
              Lokale Änderungen gehen verloren
            </h2>
            <p className="mt-1 text-sm text-normal">
              Beim Herunterladen wird der Stand der Plattform übernommen.
              {' '}
              {anzeigen.length === 1
                ? 'Eine Anzeige wurde hier geändert und wird überschrieben:'
                : `${anzeigen.length} Anzeigen wurden hier geändert und werden überschrieben:`}
            </p>
          </div>
        </div>
        <ul className="mb-4 max-h-48 overflow-y-auto rounded-xl p-2 text-sm" style={{ background: 'var(--canvas)', border: '1px solid var(--karte-rand)' }}>
          {anzeigen.map(a => (
            <li key={a.datei} className="truncate py-0.5 text-stark">{a.titel}</li>
          ))}
        </ul>
        <div className="flex flex-col-reverse gap-2 sm:flex-row sm:justify-end">
          <button type="button" onClick={aufAbbrechen} className="btn-ghost">Abbrechen</button>
          <button type="button" onClick={aufWeiter} className="btn-primaer">
            Trotzdem herunterladen
          </button>
        </div>
      </div>
    </div>
  );
}
