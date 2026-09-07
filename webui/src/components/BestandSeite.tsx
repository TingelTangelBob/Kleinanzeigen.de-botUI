// SPDX-FileCopyrightText: © Anzeigen-Studio contributors
// SPDX-License-Identifier: AGPL-3.0-or-later
//
// Der lokale Anzeigenbestand: Liste, Suche, Filter (AP-2.4, AP-3.2).
//
// UI-Anpassung 2026-09-07: Kopf verdichtet (Kebab unter md, Zahnrad zu den
// Anzeigen-Einstellungen), Suche schmal neben der Reiter-Leiste, Reiter „Fällig"
// und „Mit Hinweis" entfernt, Sammelaktionen in die Auswahlzeile geholt,
// eingereihte Läufe in die Glocke.
//
// Gefiltert und gesucht wird in der Oberfläche, nicht im Backend. Bei einem
// privaten Bestand - Dutzende Anzeigen, nicht Zehntausende - ist das die
// einfachere Lösung und fühlt sich besser an, weil jeder Tastendruck sofort
// wirkt. Sobald ein Bestand das nicht mehr hergibt, wandert es serverseitig.

import { useCallback, useEffect, useMemo, useState } from 'react';
import {
  AlertTriangle, ArrowLeftRight, Download, RefreshCw, Search, Settings,
  Trash2, Upload, X,
} from 'lucide-react';
import { api, ApiFehler } from '../services/api';
import { useProfil } from '../context/useProfil';
import { useMeldungenQuelle } from '../context/useMeldungen';
import type { Meldung } from '../context/meldungenKontext';
import { useKopfAktionen } from '../context/kopfAktionenKontext';
import { useIstMobil } from '../hooks/useMedienabfrage';
import { hashFuer, hashFuerAnzeige, type AnzeigenListe } from '../routing';
import type { BestandsAnzeige } from '../types';
import { AnzeigenEditor } from './AnzeigenEditor';
import { AnzeigenZeile } from './AnzeigenZeile';
import { HochladenDialog } from './HochladenDialog';
import { LoeschDialog } from './LoeschDialog';
import { NachladenDialog } from './NachladenDialog';
import { Hinweis } from './Hinweis';
import { VorlagenListe } from './VorlagenListe';

type Filter = 'aktiv' | 'geaendert' | 'geloescht' | 'alle';

/*
 * Reihenfolge und Vorgabe (AP-2.36).
 *
 * „Alle" stand vorn und war die Vorgabe - und zeigte damit als Erstes auch
 * jede gelöschte Anzeige. Nach einem Konto-Download mit vielen abgelaufenen
 * Anzeigen ist das eine Liste, in der das Aktuelle untergeht.
 *
 * Jetzt ist „Aktiv" die Vorgabe, und „Alle" heißt wieder wörtlich alle - es
 * steht am Ende, wo man es sucht, wenn man wirklich alles sehen will.
 *
 * UI-Anpassung 2026-09-07: „Fällig" und „Mit Hinweis" sind keine Reiter mehr.
 * „Fällig" (Neueinstellungs-Intervall abgelaufen) und die Problem-Hinweise
 * (Versand ohne Paket, ohne Bild, unlesbare Datei …) bleiben als Badge an der
 * Zeile; ein eigener Reiter dafür war mehr Bedienlast als Nutzen.
 */
const FILTER: { id: Filter; label: string }[] = [
  { id: 'aktiv', label: 'Aktiv' },
  { id: 'geaendert', label: 'Lokal geändert' },
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
    case 'geaendert': return anzeige.lokal_geaendert;
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
  herkunft, anzeigeDatei = null, anzeigeBearbeiten = false, aufZiel,
}: {
  herkunft: AnzeigenListe;
  /** Die offene Anzeige kommt aus dem Hash, nicht aus flüchtigem React-Zustand. */
  anzeigeDatei?: string | null;
  /** Der Hash merkt sich zusätzlich, ob die Detailansicht editierbar ist. */
  anzeigeBearbeiten?: boolean;
  aufZiel: (ziel: string) => void;
}) {
  const { aktiv, laedt: profileLaden } = useProfil();
  const [anzeigen, setAnzeigen] = useState<BestandsAnzeige[]>([]);
  const [laedt, setLaedt] = useState(false);
  const [fehler, setFehler] = useState<string | null>(null);
  const [suche, setSuche] = useState('');
  const [filter, setFilter] = useState<Filter>(herkunft === 'archiv' ? 'alle' : STANDARD_FILTER);
  const [holtNach, setHoltNach] = useState(false);
  const [warnung, setWarnung] = useState<BestandsAnzeige[] | null>(null);
  const [startetDownload, setStartetDownload] = useState(false);
  const [downloadHinweis, setDownloadHinweis] = useState<number | null>(null);
  const [aktualisierung, setAktualisierung] = useState<BestandsAnzeige | null>(null);
  const [laedtAktualisierung, setLaedtAktualisierung] = useState(false);
  const [aktualisierungsHinweis, setAktualisierungsHinweis] = useState<number | null>(null);
  const [zuletztHerkunft, setZuletztHerkunft] = useState<AnzeigenListe>(herkunft);
  // AP-2.20: Mehrfachauswahl über die Dateipfade - dieselbe Kennung, mit der
  // auch das Backend arbeitet.
  const [auswahl, setAuswahl] = useState<Set<string>>(new Set());
  const [loeschDialog, setLoeschDialog] = useState<BestandsAnzeige[] | null>(null);
  const [sammelLaeuft, setSammelLaeuft] = useState<string | null>(null);
  const [sammelHinweis, setSammelHinweis] = useState<string | null>(null);
  // Auf schmalen Fenstern zusammengeklappte Suche.
  const [sucheOffen, setSucheOffen] = useState(false);

  // App.tsx rendert für #anzeigen/eigene|fremde|archiv dieselbe Komponente;
  // nur `herkunft` (Listen-Modus) wechselt. React unmountet dabei nicht, also
  // müssen Listenfilter und Dialoge beim Wechsel zurückgesetzt werden
  // (AP-2.13). Eine offene Anzeige kommt dagegen aus dem Hash und wird vom
  // Editor kontrolliert.
  //
  // Zurückgesetzt wird während des Renderns statt in einem Effekt: ein Effekt
  // liefe erst nach dem Anzeigen, die alte Maske wäre also einen Frame lang
  // unter der neuen Navigation zu sehen. Das ist das von React dokumentierte
  // Muster, Zustand an geänderte Eigenschaften anzupassen.
  if (zuletztHerkunft !== herkunft) {
    setZuletztHerkunft(herkunft);
    setHoltNach(false);
    setWarnung(null);
    setDownloadHinweis(null);
    setAktualisierung(null);
    setAktualisierungsHinweis(null);
    setFehler(null);
    setSuche('');
    // Archiv zeigt nur schon archivierte Einträge – „Aktiv" als Vorgabe wäre leer.
    setFilter(herkunft === 'archiv' ? 'alle' : STANDARD_FILTER);
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

  const sichtbar = useMemo(() => {
    // Archiv (AP-2.58): lokal nicht mehr aktive / gelöschte Anzeigen, unabhängig
    // von eigener/fremder Ordner-Herkunft – ohne Konto-Holen.
    if (herkunft === 'archiv') {
      return anzeigen.filter(a => a.geloescht || !a.aktiv);
    }
    return anzeigen.filter(a => a.herkunft === herkunft);
  }, [anzeigen, herkunft]);

  const gefiltert = useMemo(
    () => sichtbar.filter(a => passtZumFilter(a, filter) && passtZurSuche(a, suche)),
    [sichtbar, filter, suche],
  );

  const zaehler = useMemo(() => ({
    aktiv: sichtbar.filter(a => a.aktiv && !a.geloescht).length,
    geaendert: sichtbar.filter(a => a.lokal_geaendert).length,
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

  /** Öffnet die Rückfrage für eine bestehende Anzeige aus der Listenzeile. */
  const aktualisieren = (anzeige: BestandsAnzeige) => {
    if (anzeige.id === null || anzeige.unlesbar !== null) return;
    setFehler(null);
    setAktualisierung(anzeige);
  };

  const aktualisierungStarten = async () => {
    if (!aktiv || !aktualisierung) return;
    setLaedtAktualisierung(true);
    setFehler(null);
    try {
      const job = await api.bestand.hochladen(aktiv.slug, aktualisierung.datei);
      setAktualisierungsHinweis(job.job_id);
      setAktualisierung(null);
    } catch (ursache) {
      setFehler(ursache instanceof ApiFehler ? ursache.message : 'Unbekannter Fehler.');
    } finally {
      setLaedtAktualisierung(false);
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
      + `${bilder === 1 ? 'Bild' : 'Bilder'} von diesem Rechner gelöscht. `
      + 'Solange die Anzeige auf kleinanzeigen.de noch steht, holt sie „Vom Konto holen" zurück.';
  });

  // Eingereihte Läufe stehen in der Glocke, nicht als Zeile im Seitenfluss
  // (AP-2.25/2.30). Die Lösch-Bestätigung bleibt zusätzlich kurz an der
  // Auswahlzeile - dazu läuft `sammelHinweis` unten weiter.
  const meldungen = useMemo<Meldung[]>(() => {
    const liste: Meldung[] = [];
    if (downloadHinweis !== null) {
      liste.push({
        id: 'bestand-download',
        ton: 'hinweis',
        titel: `Lauf ${downloadHinweis} ist eingereiht`,
        text: 'Der Bestand deines Kleinanzeigen-Kontos wird geholt.',
      });
    }
    if (aktualisierungsHinweis !== null) {
      liste.push({
        id: 'bestand-aktualisierung',
        ton: 'hinweis',
        titel: `Lauf ${aktualisierungsHinweis} ist eingereiht`,
        text: 'Die Anzeige wird auf kleinanzeigen.de aktualisiert.',
      });
    }
    return liste;
  }, [downloadHinweis, aktualisierungsHinweis]);
  useMeldungenQuelle('bestand', meldungen);

  // Unter md wandern die Sammelaktionen in eine fixe Leiste unten (statt über
  // die Liste). Nur eine der beiden Varianten steht im Baum - sonst gäbe es
  // zwei `role="group"`.
  const istMobil = useIstMobil();

  const eigene = herkunft === 'eigene';
  const archiv = herkunft === 'archiv';

  // Die Aktionsknöpfe der Seite stehen in der App-Chrome, nicht in einem
  // eigenen Kopfbereich (2026-09-07). Ab md rechts in der Topleiste, darunter
  // als eigene Zeile unter der Leiste (useKopfAktionen entscheidet das Ziel).
  // In beiden Fällen alle Knöpfe sichtbar - kein Kebab mehr. Archiv: keine
  // Konto-/Link-Aktion (AP-2.58).
  const kopfAktionen = useKopfAktionen(
    <>
      {!archiv && (eigene ? (
        <button
          type="button"
          onClick={() => void kontoHolen()}
          disabled={startetDownload}
          className="btn-primaer"
          aria-label={startetDownload ? 'Wird eingereiht …' : 'Vom Konto holen'}
        >
          <Download className="h-4 w-4" aria-hidden />
          {startetDownload ? (
            'Wird eingereiht …'
          ) : (
            <>
              <span className="sm:hidden">Holen</span>
              <span className="hidden sm:inline">Vom Konto holen</span>
            </>
          )}
        </button>
      ) : (
        <button
          type="button"
          onClick={() => setHoltNach(true)}
          className="btn-primaer"
          aria-label="Anzeigen per Link holen"
        >
          <Download className="h-4 w-4" aria-hidden />
          <span className="sm:hidden">Per Link</span>
          <span className="hidden sm:inline">Anzeigen per Link holen</span>
        </button>
      ))}

      <button
        type="button"
        onClick={() => void laden()}
        className="btn-ghost"
      >
        <RefreshCw className={`h-4 w-4 ${laedt ? 'animate-spin' : ''}`} aria-hidden />
        <span className="sm:hidden">Neu</span>
        <span className="hidden sm:inline">Neu einlesen</span>
      </button>
      <button
        type="button"
        onClick={() => aufZiel('einstellungen/anzeigen')}
        aria-label="Anzeigen-Einstellungen"
        title="Anzeigen-Einstellungen"
        className="btn-icon"
      >
        <Settings className="h-4 w-4" aria-hidden />
      </button>
    </>,
  );

  if (profileLaden) return <p className="text-sm text-leise">Wird geladen …</p>;

  if (!aktiv) {
    return (
      <p className="hinweis hinweis-warn">
        Zuerst ein Profil anlegen.
      </p>
    );
  }

  if (anzeigeDatei) {
    const offene = anzeigen.find(a => a.datei === anzeigeDatei);
    const dateiHerkunft = offene?.herkunft ?? (herkunft === 'fremde' ? 'fremde' : 'eigene');
    return (
      <AnzeigenEditor
        profil={aktiv.slug}
        datei={anzeigeDatei}
        bearbeitbar={anzeigeBearbeiten}
        onlineLoeschbar={dateiHerkunft === 'eigene'}
        aufBearbeiten={() => aufZiel(hashFuerAnzeige(herkunft, anzeigeDatei, true))}
        aufAnsehen={() => aufZiel(hashFuerAnzeige(herkunft, anzeigeDatei))}
        // Vorabwert fürs „Gelöscht"-Badge (AP-3.10); der Editor bestätigt es
        // aus den frisch geladenen Kopfdaten.
        geloescht={offene?.geloescht ?? false}
        aufZurueck={geaendert => {
          aufZiel(hashFuer('anzeigen', herkunft));
          if (geaendert) void laden();
        }}
        aufKopie={kopie => {
          void laden();
          aufZiel(hashFuerAnzeige(herkunft, kopie, true));
        }}
        // Die Datei ist weg - die Maske darauf wäre eine Maske auf nichts
        // (AP-2.20).
        aufGeloescht={(hinweis) => {
          aufZiel(hashFuer('anzeigen', herkunft));
          setAuswahl(new Set());
          setSammelHinweis(hinweis ?? 'Anzeige von diesem Rechner gelöscht.');
          void laden();
        }}
      />
    );
  }

  return (
    <div className={`seite ${istMobil && gewaehlte.length > 0 ? 'pb-24' : ''}`}>
      <h1 className="sr-only">{archiv ? 'Archiv' : eigene ? 'Meine Anzeigen' : 'Von anderen'}</h1>
      {kopfAktionen}
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

      {aktualisierung && (
        <HochladenDialog
          anzeige={aktualisierung}
          profil={aktiv.slug}
          laeuft={laedtAktualisierung}
          aufAbbrechen={() => setAktualisierung(null)}
          aufBestaetigen={() => void aktualisierungStarten()}
        />
      )}

      {/* „Lauf N ist eingereiht" steht in der Glocke (siehe `meldungen` /
          useMeldungenQuelle) - kein Vollbreite-Hinweis mehr im Seitenfluss. */}

      {fehler && (
        <p className="hinweis hinweis-fehler mb-4">{fehler}</p>
      )}

      {/* Wegklickbar mit localStorage (AP-2.59) – Hinweis-Komponente wie auf der Jobseite. */}
      {!eigene && !archiv && (
        <Hinweis
          id="bestand-fremde-geloescht"
          ton="warn"
          icon={AlertTriangle}
          className="mb-4"
        >
          Nur was auf kleinanzeigen.de noch als Seite erreichbar ist, lässt sich holen.
          Endgültig gelöschte Anzeigen sind weg – kein Werkzeug holt sie zurück.
        </Hinweis>
      )}

      {eigene && !archiv && (
        <VorlagenListe
          profil={aktiv.slug}
          aufAngewendet={datei => {
            void laden();
            aufZiel(hashFuerAnzeige('eigene', datei, true));
          }}
        />
      )}

      {/* Reiter links, Suche rechts. Ab sm steht die Suche schmal rechtsbündig
          neben der Reiter-Leiste; unter sm sitzt rechts nur ein Lupen-Icon, die
          Reiter scrollen horizontal, und die Suche öffnet als eigene Zeile
          (2026-09-07, mobil aufgeräumt 2026-09-09). */}
      <div className="mb-4 flex flex-wrap items-center gap-2">
        <button
          type="button"
          onClick={() => setSucheOffen(o => !o)}
          aria-label="Suche ein- oder ausblenden"
          aria-expanded={sucheOffen}
          className="btn-icon order-last flex-shrink-0 sm:hidden"
        >
          <Search className="h-4 w-4" aria-hidden />
        </button>

        <label
          className={`relative flex-shrink-0 sm:order-last sm:ml-auto sm:block sm:w-64 ${
            sucheOffen ? 'order-last block w-full' : 'hidden'
          }`}
        >
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

        {!archiv && (
          <div className="reiter-leiste order-first min-w-0 flex-1 flex-nowrap overflow-x-auto sm:order-none sm:flex-none">
            {FILTER.map(f => {
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
        )}
        {archiv && (
          <p className="order-first min-w-0 flex-1 text-sm text-leise sm:order-none sm:flex-none">
            Lokal archiviert ({sichtbar.length})
          </p>
        )}
      </div>

      {sichtbar.length === 0 && !laedt ? (
        <div className="leer">
          <p>
            {archiv
              ? 'Noch keine archivierten Anzeigen.'
              : eigene
                ? 'Noch keine eigenen Anzeigen auf der Platte.'
                : 'Noch keine Anzeigen von anderen.'}
          </p>
          <p className="mt-1 text-leise">
            {archiv
              ? 'Hier erscheinen Anzeigen, die lokal als gelöscht oder inaktiv gelten – ohne Bindung an ein Konto-Holen.'
              : eigene
                ? '„Vom Konto holen“ lädt den Bestand deines Kleinanzeigen-Kontos.'
                : '„Anzeigen per Link holen“ nimmt beliebige Kleinanzeigen-Adressen entgegen.'}
          </p>
        </div>
      ) : (
        <>
          {/* Zählzeile mit Alles-Wählen. Das Kästchen sitzt auf demselben
              Links-Einzug wie die Zeilen-Kästchen. Ab md stehen die
              Sammelaktionen rechts daneben; darunter fahren sie als fixe
              Leiste am unteren Rand ein (2026-09-09), damit die Liste nicht
              nach unten springt. */}
          <div className="bestand-auswahlzeile mb-2 flex flex-wrap items-center gap-x-3 gap-y-2">
            <label className="flex items-center gap-2 pl-4 text-xs text-leise">
              <input
                type="checkbox"
                checked={alleGewaehlt}
                onChange={alleUmschalten}
                className="h-4 w-4"
                aria-label={alleGewaehlt ? 'Auswahl aufheben' : 'Alle sichtbaren auswählen'}
              />
              {gewaehlte.length > 0
                ? `${gewaehlte.length} ausgewählt`
                : `${gefiltert.length} von ${sichtbar.length} Anzeigen`}
            </label>

            {gewaehlte.length > 0
              ? (!istMobil && (
                <SammelAktionen
                  className="ml-auto"
                  archiv={archiv}
                  eigene={eigene}
                  sammelLaeuft={sammelLaeuft}
                  aufHerkunft={() => void sammelHerkunft()}
                  aufHochladen={() => void sammelHochladen()}
                  aufLoeschen={() => setLoeschDialog(gewaehlte)}
                  aufAufheben={() => setAuswahl(new Set())}
                />
              ))
              : (sammelHinweis && (
                <span className="ml-auto text-xs text-leise">{sammelHinweis}</span>
              ))}
          </div>

          {/* Unter md: die Sammelaktionen als fixe Leiste unten - dieselbe
              Sprache wie die Speichern-Leiste im Editor. */}
          {istMobil && gewaehlte.length > 0 && (
            <div className="leiste-fix safe-unten fixed inset-x-0 bottom-0 z-30 flex flex-wrap items-center gap-x-3 gap-y-2 px-4 py-3 md:hidden">
              <span className="text-sm font-medium text-stark">{gewaehlte.length} ausgewählt</span>
              <SammelAktionen
                className="ml-auto"
                archiv={archiv}
                eigene={eigene}
                sammelLaeuft={sammelLaeuft}
                aufHerkunft={() => void sammelHerkunft()}
                aufHochladen={() => void sammelHochladen()}
                aufLoeschen={() => setLoeschDialog(gewaehlte)}
                aufAufheben={() => setAuswahl(new Set())}
              />
            </div>
          )}
          {/* Der Rahmen entsteht nur mit Inhalt (AP-2.18). Ohne diese Bedingung
              stand bei „kein Treffer" ein 2 px hoher, leerer Kasten mit Rand und
              Schatten über dem gestrichelten Leerzustand - ein Strich, den
              niemand erklären kann. */}
          {gefiltert.length > 0 && (
          <ul className="liste">
            {gefiltert.map(a => (
              <li key={a.datei} className="flex items-stretch">
                <div className="flex flex-shrink-0 items-center pl-4">
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
                    aufKlick={a.unlesbar ? undefined : () => aufZiel(hashFuerAnzeige(herkunft, a.datei))}
                    aufOeffnen={() => aufZiel(hashFuerAnzeige(herkunft, a.datei))}
                    aufAktualisieren={
                      !archiv && eigene && a.id !== null && !a.unlesbar
                        ? () => aktualisieren(a)
                        : undefined
                    }
                    aufUmsortieren={archiv ? undefined : () => void umsortieren(a)}
                  />
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

/**
 * Die Sammelaktionen über die Auswahl. Ab md inline in der Zählzeile, unter md
 * in der fixen Leiste unten - dieselben Knöpfe, damit sie nicht zweifach im
 * Baum stehen (ein `role="group"`).
 */
function SammelAktionen({
  archiv, eigene, sammelLaeuft, aufHerkunft, aufHochladen, aufLoeschen, aufAufheben,
  className = '',
}: {
  archiv: boolean;
  eigene: boolean;
  sammelLaeuft: string | null;
  aufHerkunft: () => void;
  aufHochladen: () => void;
  aufLoeschen: () => void;
  aufAufheben: () => void;
  className?: string;
}) {
  const gesperrt = sammelLaeuft !== null;
  return (
    <div
      role="group"
      aria-label="Sammelaktionen"
      className={`flex flex-wrap items-center gap-2 ${className}`}
    >
      {!archiv && (
        <button type="button" onClick={aufHerkunft} disabled={gesperrt} className="btn-ghost text-xs">
          <ArrowLeftRight className="h-3.5 w-3.5" aria-hidden />
          {sammelLaeuft === 'herkunft'
            ? 'Wird verschoben …'
            : eigene ? 'Zu „Von anderen"' : 'Zu meinen Anzeigen'}
        </button>
      )}
      {!archiv && (
        <button type="button" onClick={aufHochladen} disabled={gesperrt} className="btn-ghost text-xs">
          <Upload className="h-3.5 w-3.5" aria-hidden />
          {sammelLaeuft === 'hochladen' ? 'Wird eingereiht …' : 'Hochladen'}
        </button>
      )}
      {/* Rot: Es vernichtet Dateien und soll sich von den harmlosen Knöpfen
          daneben abheben (AP-2.20). */}
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
      <button type="button" onClick={aufAufheben} disabled={gesperrt} className="btn-leise text-xs">
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
