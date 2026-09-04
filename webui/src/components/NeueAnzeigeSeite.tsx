// SPDX-FileCopyrightText: © Anzeigen-Studio contributors
// SPDX-License-Identifier: AGPL-3.0-or-later
//
// Fotos rein, Anzeigenentwurf raus (AP-4.4, AP-4.6).
//
// Der Ablauf ist bewusst dreigeteilt und jeder Teil hat seinen eigenen
// Zustand: Bilder wählen → erkennen lassen → Rückfragen beantworten und
// anlegen. Nur der mittlere Schritt kostet Geld, und nur er ruft den Anbieter.
// Das Beantworten der Rückfragen läuft ohne zweiten Aufruf.
//
// Was der Fortschrittsanzeige zugrunde liegt, ist echt gemessen und nicht
// geschätzt: Das Hochladen meldet der Browser prozentgenau, die Wartezeit
// danach wird mitgezählt. Zwischenschritte zu erfinden, die niemand misst,
// wäre genau die Sorte grüner Haken, an der dieses Projekt schon einmal
// hängengeblieben ist.

import { useCallback, useEffect, useRef, useState } from 'react';
import {
  AlertTriangle, Check, ImagePlus, Loader2, Sparkles, Trash2,
} from 'lucide-react';
import { api, ApiFehler } from '../services/api';
import { useProfil } from '../context/useProfil';
import type { KiEntwurf, KiKosten, KiStatus } from '../types';
import { ProfilWarteschlange } from './ProfilWarteschlange';

/** Woran der Vorgang gerade ist. Jede Stufe entspricht etwas Messbarem. */
type Stufe =
  | { art: 'ruhe' }
  | { art: 'hochladen'; anteil: number }
  | { art: 'warten'; sekunden: number }
  | { art: 'anlegen' };

const MAX_BILDER = 4;

/** Was der Bot beim Hochladen spaeter wieder lesen kann. HEIC gehoert nicht dazu. */
const ERLAUBTE_TYPEN = ['image/jpeg', 'image/png', 'image/gif'];

export function NeueAnzeigeSeite() {
  const { aktiv } = useProfil();
  const profil = aktiv?.slug ?? '';

  const [kiStatus, setKiStatus] = useState<KiStatus | null>(null);
  const [dateien, setDateien] = useState<File[]>([]);
  const [vorschauen, setVorschauen] = useState<string[]>([]);
  const [stufe, setStufe] = useState<Stufe>({ art: 'ruhe' });
  const [entwurf, setEntwurf] = useState<KiEntwurf | null>(null);
  const [kosten, setKosten] = useState<KiKosten | null>(null);
  const [antworten, setAntworten] = useState<Record<string, string>>({});
  const [kategorie, setKategorie] = useState<string | null>(null);
  const [versandpakete, setVersandpakete] = useState<string[]>([]);
  // Der Preis, den der Mensch bestaetigt hat. Bleibt null, bis jemand
  // etwas anklickt oder eintippt - die Schaetzung fuellt ihn nicht.
  const [preis, setPreis] = useState<number | null>(null);
  const [fehler, setFehler] = useState<string | null>(null);
  const [angelegt, setAngelegt] = useState<string | null>(null);

  useEffect(() => {
    void api.ki.status().then(setKiStatus).catch(() => setKiStatus(null));
  }, []);

  // Vorschaubilder sind Objekt-URLs. Ohne Freigabe hält der Browser die Bilder
  // im Speicher, solange die Seite offen ist - bei Handyfotos schnell spürbar.
  useEffect(() => {
    const urls = dateien.map(datei => URL.createObjectURL(datei));
    setVorschauen(urls);
    return () => urls.forEach(url => URL.revokeObjectURL(url));
  }, [dateien]);

  const dateienWaehlen = (liste: FileList | null) => {
    if (!liste || liste.length === 0) return;

    // SOFORT auslesen, nicht erst im Aktualisierer von setDateien. Eine
    // FileList haengt am <input>; wer danach `input.value = ''` setzt - und das
    // muss man, damit dieselbe Datei erneut gewaehlt werden kann - leert damit
    // auch die FileList. React ruft den Aktualisierer spaeter auf, und dann ist
    // sie leer. Genau daran ist die erste Fassung gescheitert: Datei waehlen
    // ging, danach passierte nichts.
    const gewaehlt = Array.from(liste);

    const unbrauchbar = gewaehlt.filter(datei => !ERLAUBTE_TYPEN.includes(datei.type));
    if (unbrauchbar.length > 0) {
      const heic = unbrauchbar.some(d => /hei[cf]/i.test(d.type) || /\.hei[cf]$/i.test(d.name));
      setFehler(heic
        ? 'HEIC-Fotos vom iPhone kann das Studio noch nicht lesen. In den iPhone-Einstellungen '
          + 'unter Kamera → Formate „Maximale Kompatibilität“ wählen, oder das Foto als JPEG exportieren.'
        : `Nicht lesbar: ${unbrauchbar.map(d => d.name).join(', ')}. Erlaubt sind JPEG, PNG und GIF.`);
    } else {
      setFehler(null);
    }

    const brauchbar = gewaehlt.filter(datei => ERLAUBTE_TYPEN.includes(datei.type));
    if (brauchbar.length === 0) return;
    setDateien(vorher => [...vorher, ...brauchbar].slice(0, MAX_BILDER));
  };

  const zuruecksetzen = () => {
    setEntwurf(null);
    setKosten(null);
    setAntworten({});
    setKategorie(null);
    setVersandpakete([]);
    // Sonst haftet der Preis des vorigen Entwurfs am naechsten - und zwar
    // unsichtbar, weil die Schaetzung daneben eine andere Zahl zeigt.
    setPreis(null);
    setAngelegt(null);
  };

  const erkennen = async () => {
    if (dateien.length === 0 || !profil) return;
    setFehler(null);
    zuruecksetzen();
    setStufe({ art: 'hochladen', anteil: 0 });

    // Ab dem Moment, in dem der Upload durch ist, läuft die Uhr. Sie ist die
    // einzige ehrliche Auskunft über eine Wartezeit, die wir nicht aufteilen
    // können: Der Anbieter meldet keinen Zwischenstand.
    let uhr: number | undefined;
    try {
      const antwort = await api.ki.entwurf(profil, dateien, anteil => {
        setStufe({ art: 'hochladen', anteil });
        if (anteil >= 1 && uhr === undefined) {
          const start = Date.now();
          setStufe({ art: 'warten', sekunden: 0 });
          uhr = window.setInterval(() => {
            setStufe({ art: 'warten', sekunden: Math.round((Date.now() - start) / 1000) });
          }, 1000);
        }
      });
      setEntwurf(antwort.entwurf);
      setKosten(antwort.kosten);
    } catch (ursache) {
      setFehler(ursache instanceof ApiFehler ? ursache.message : 'Unbekannter Fehler.');
    } finally {
      if (uhr !== undefined) window.clearInterval(uhr);
      setStufe({ art: 'ruhe' });
    }
  };

  const anlegen = async () => {
    if (!entwurf || !profil) return;
    setFehler(null);
    setStufe({ art: 'anlegen' });
    try {
      const ergebnis = await api.ki.anlegen(profil, entwurf, antworten, dateien, {
        kategorie, versandpakete, preis,
      });
      setAngelegt(ergebnis.titel);
    } catch (ursache) {
      setFehler(ursache instanceof ApiFehler ? ursache.message : 'Unbekannter Fehler.');
    } finally {
      setStufe({ art: 'ruhe' });
    }
  };

  const offeneFragen = entwurf?.fragen.filter(f => !antworten[f.id]) ?? [];

  return (
    // Dieselbe breitere Kante wie im Editor (AP-2.24): die Chip-Reihen der
    // Vorschläge und der Bildstreifen bekommen mehr Platz und brechen später
    // um. Fließtext bleibt über `.lesebreite` gedeckelt.
    <div className="seite-breit">
      <div className="seite-kopf mb-5">
        <div>
          <h1 className="sr-only">Neue Anzeige</h1>
          <p className="seite-beschrieb">
        Fotos hochladen, erkennen lassen, Rückfragen beantworten. Die Anzeige wird
        anschließend <strong>lokal angelegt</strong> – veröffentlicht wird sie nicht.
          </p>
        </div>
      </div>

      {kiStatus && !kiStatus.hinterlegt && <SchluesselFehlt />}

      {/* Vor dem Formular, nicht darunter (AP-2.21): Die Auskunft, dass noch
          ein Lauf aussteht, ist erst danach wertlos. */}
      {profil && <ProfilWarteschlange profil={profil} />}

      <DatenschutzHinweis bildkante={kiStatus?.bildkante ?? 768} />

      <BildAuswahl
        dateien={dateien}
        vorschauen={vorschauen}
        gesperrt={stufe.art !== 'ruhe'}
        aufWaehlen={dateienWaehlen}
        aufEntfernen={index => {
          setDateien(vorher => vorher.filter((_, i) => i !== index));
          zuruecksetzen();
        }}
      />

      {fehler && (
        <p role="alert" className="hinweis hinweis-fehler lesebreite mb-4">
          {fehler}
        </p>
      )}

      {stufe.art !== 'ruhe' ? (
        <Fortschritt stufe={stufe} />
      ) : (
        <div className="mb-6">
          <button
            type="button"
            onClick={() => void erkennen()}
            disabled={dateien.length === 0 || !profil || !kiStatus?.hinterlegt}
            className="btn-primaer w-full sm:w-auto"
          >
            <Sparkles className="h-4 w-4" />
            {entwurf ? 'Noch einmal erkennen lassen' : 'Erkennen lassen'}
          </button>
          {/* Ein grauer Knopf ohne Begruendung laesst den Nutzer raten. */}
          {(dateien.length === 0 || !profil || !kiStatus?.hinterlegt) && (
            <p className="lesebreite mt-2 text-center text-xs text-leise sm:text-left">
              {kiStatus === null
                ? 'Der Zustand des KI-Zugangs ließ sich nicht laden – ist das Backend erreichbar?'
                : !kiStatus.hinterlegt
                  ? 'Es fehlt der OpenAI-Schlüssel.'
                  : !profil
                    ? 'Zuerst ein Profil anlegen und auswählen.'
                    : 'Wähle mindestens ein Foto.'}
            </p>
          )}
        </div>
      )}

      {entwurf && !angelegt && (
        <Ergebnis
          entwurf={entwurf}
          kosten={kosten}
          antworten={antworten}
          aufAntwort={(id, wert) => setAntworten(vorher => ({ ...vorher, [id]: wert }))}
          aufZuruecknehmen={id => setAntworten(vorher => {
            const neu = { ...vorher };
            delete neu[id];
            return neu;
          })}
          offen={offeneFragen.length}
          gesperrt={stufe.art !== 'ruhe'}
          aufAnlegen={() => void anlegen()}
          kategorie={kategorie}
          versandpakete={versandpakete}
          preis={preis}
          setKategorie={setKategorie}
          setVersandpakete={setVersandpakete}
          setPreis={setPreis}
        />
      )}

      {angelegt && (
        <div className="hinweis lesebreite">
          <p className="flex items-center gap-2 font-medium">
            <Check className="h-5 w-5" />
            „{angelegt}“ liegt jetzt im Bestand.
          </p>
          <p className="mt-2 text-sm">
            Sie ist <strong>nicht</strong> veröffentlicht. Unter „Anzeigen“ lässt sie sich
            bearbeiten – Kategorie und Versand fehlen noch – und von dort aus hochladen.
          </p>
          <a href="#bestand" className="mt-3 inline-block text-sm font-medium underline">
            Zum Bestand
          </a>
        </div>
      )}
    </div>
  );
}

function SchluesselFehlt() {
  return (
    <div className="hinweis hinweis-warn lesebreite mb-4 flex items-start gap-3">
      <AlertTriangle className="mt-0.5 h-5 w-5 flex-shrink-0" aria-hidden />
      <p>
        Es ist noch kein OpenAI-Schlüssel hinterlegt. Ohne ihn kann nichts erkannt werden –
        einzutragen unter <a href="#profile" className="font-medium underline">Profile</a>.
      </p>
    </div>
  );
}

/** AP-4.7: Vor dem ersten Versand muss klar sein, dass Bilder das Haus verlassen. */
function DatenschutzHinweis({ bildkante }: { bildkante: number }) {
  const [offen, setOffen] = useState(false);
  return (
    <div className="karte lesebreite mb-4 p-3 text-sm">
      <button
        type="button"
        onClick={() => setOffen(!offen)}
        aria-expanded={offen}
        // `py-1` bringt die Zeile auf 24px Trefferhöhe (AP-2.34) - vorher 20px
        // und damit unter dem Mindestmaß aus WCAG 2.5.8.
        className="flex w-full items-start gap-2 py-1 text-left text-normal"
      >
        <AlertTriangle className="mt-0.5 h-4 w-4 flex-shrink-0 text-leise" aria-hidden />
        <span>
          Die Fotos werden an OpenAI geschickt.{' '}
          <span className="underline">{offen ? 'Weniger' : 'Was genau passiert?'}</span>
        </span>
      </button>
      {offen && (
        <ul className="mt-2 list-disc space-y-1 pl-9 text-normal">
          <li>Vor dem Versand wird jedes Bild auf höchstens {bildkante} px verkleinert.</li>
          <li>
            Alle Metadaten werden entfernt – auch die GPS-Koordinaten, die Handyfotos
            mitbringen und die bei einer Aufnahme zu Hause die Wohnadresse sind.
          </li>
          <li>Höchstens {MAX_BILDER} Bilder gehen mit; weitere werden nicht gesendet.</li>
          <li>
            Wenn im aktiven Profil <strong>veröffentlichte</strong> Anzeigen liegen, gehen
            höchstens fünf ihrer Beschreibungstexte als Stilvorlage mit – ohne E-Mail-Adressen
            und Telefonnummern. Eigene Entwürfe, die nie online waren, bleiben außen vor:
            Sonst ahmt das Modell sich selbst nach. Ohne veröffentlichte Anzeigen gilt eine
            feste Stilvorgabe, und es gehen nur die Fotos raus.
          </li>
          <li>Prüfe trotzdem, was im Hintergrund zu sehen ist. Das kann keine Software für dich.</li>
        </ul>
      )}
    </div>
  );
}

function BildAuswahl({
  dateien, vorschauen, gesperrt, aufWaehlen, aufEntfernen,
}: {
  dateien: File[];
  vorschauen: string[];
  gesperrt: boolean;
  aufWaehlen: (liste: FileList | null) => void;
  aufEntfernen: (index: number) => void;
}) {
  const eingabe = useRef<HTMLInputElement>(null);
  const [ueberZone, setUeberZone] = useState(false);

  // Reinziehen. Ohne `preventDefault` auf dragover nimmt der Browser die Datei
  // selbst an und zeigt sie im Tab an - die Seite ist dann weg, samt allem,
  // was schon eingetragen war.
  const aufDragOver = (ereignis: React.DragEvent) => {
    if (gesperrt) return;
    ereignis.preventDefault();
    setUeberZone(true);
  };

  const aufDrop = (ereignis: React.DragEvent) => {
    ereignis.preventDefault();
    setUeberZone(false);
    if (gesperrt) return;
    aufWaehlen(ereignis.dataTransfer.files);
  };

  return (
    <div
      className={`mb-4 ${ueberZone ? 'dropzone-aktiv' : ''}`}
      onDragOver={aufDragOver}
      onDragEnter={aufDragOver}
      onDragLeave={() => setUeberZone(false)}
      onDrop={aufDrop}
    >
      {dateien.length === 0 ? (
        <button
          type="button"
          onClick={() => eingabe.current?.click()}
          disabled={gesperrt}
          className={`dropzone ${ueberZone ? 'dropzone-aktiv' : ''}`}
        >
          <ImagePlus className="h-8 w-8" />
          <span className="text-base font-medium text-stark">Fotos hierher ziehen</span>
          <span className="text-sm text-leise">oder klicken, um Dateien zu wählen. JPEG, PNG oder GIF.</span>
        </button>
      ) : (
        <div className={`karte p-3 ${ueberZone ? 'dropzone-aktiv' : ''}`}>
          <div className="flex gap-3 overflow-x-auto pb-1">
            {vorschauen.map((url, index) => (
              <div key={url} className="relative h-24 w-24 flex-shrink-0 overflow-hidden rounded-xl" style={{ border: '1px solid var(--karte-rand)' }}>
                <img src={url} alt={`Foto ${index + 1}`} className="h-full w-full object-cover" />
                {!gesperrt && (
                  <button
                    type="button"
                    onClick={() => aufEntfernen(index)}
                    aria-label={`Foto ${index + 1} entfernen`}
                    className="absolute right-1 top-1 rounded-full bg-white/90 p-1 text-stark shadow"
                  >
                    <Trash2 className="h-4 w-4" />
                  </button>
                )}
              </div>
            ))}
            {dateien.length < MAX_BILDER && !gesperrt && (
              <button
                type="button"
                onClick={() => eingabe.current?.click()}
                className="flex h-24 w-24 flex-shrink-0 flex-col items-center justify-center gap-1 rounded-xl text-leise"
                style={{ border: '2px dashed var(--karte-rand)' }}
              >
                <ImagePlus className="h-5 w-5" />
                <span className="text-[11px]">Foto</span>
              </button>
            )}
          </div>
        </div>
      )}
      <input
        ref={eingabe}
        type="file"
        accept="image/jpeg,image/png,image/gif"
        multiple
        className="hidden"
        onChange={ereignis => {
          aufWaehlen(ereignis.target.files);
          // Zurücksetzen, damit dieselbe Datei erneut gewählt werden kann.
          ereignis.target.value = '';
        }}
      />
      <p className="lesebreite mt-2 text-xs text-leise">
        {dateien.length} von {MAX_BILDER} Fotos. Mehrere Ansichten helfen – Vorderseite,
        Rückseite, Typenschild. JPEG, PNG oder GIF.
      </p>
    </div>
  );
}

function Fortschritt({ stufe }: { stufe: Stufe }) {
  const text =
    stufe.art === 'hochladen' ? `Fotos werden hochgeladen … ${Math.round(stufe.anteil * 100)} %`
      : stufe.art === 'warten' ? `Das Modell sieht sich die Fotos an … ${stufe.sekunden} s`
        : 'Anzeige wird angelegt …';

  return (
    <div className="karte lesebreite mb-6 p-4" role="status" aria-live="polite">
      <p className="flex items-center gap-2 text-sm font-medium text-stark">
        <Loader2 className="h-4 w-4 animate-spin text-primary-custom" aria-hidden />
        {text}
      </p>
      {stufe.art === 'hochladen' && (
        <div className="mt-3 h-1.5 overflow-hidden rounded" style={{ background: 'var(--karte-rand)' }}>
          <div
            className="h-full bg-primary-custom transition-[width] duration-200"
            style={{ width: `${Math.round(stufe.anteil * 100)}%` }}
          />
        </div>
      )}
      {stufe.art === 'warten' && (
        <p className="mt-2 text-xs text-leise">
          Das dauert meist 10 bis 30 Sekunden. Der Anbieter meldet keinen Zwischenstand –
          deshalb steht hier eine Uhr und kein Balken.
        </p>
      )}
    </div>
  );
}

function Ergebnis({
  entwurf, kosten, antworten, aufAntwort, aufZuruecknehmen, offen, gesperrt, aufAnlegen,
  kategorie, versandpakete, preis, setKategorie, setVersandpakete, setPreis,
}: {
  entwurf: KiEntwurf;
  kosten: KiKosten | null;
  antworten: Record<string, string>;
  kategorie: string | null;
  versandpakete: string[];
  preis: number | null;
  setKategorie: (wert: string | null) => void;
  setVersandpakete: (werte: string[]) => void;
  setPreis: (wert: number | null) => void;
  aufAntwort: (id: string, wert: string) => void;
  aufZuruecknehmen: (id: string) => void;
  offen: number;
  gesperrt: boolean;
  aufAnlegen: () => void;
}) {
  return (
    <div className="space-y-4">
      {entwurf.sicherheit === 'niedrig' && (
        <div className="hinweis hinweis-warn lesebreite flex items-start gap-3">
          <AlertTriangle className="mt-0.5 h-5 w-5 flex-shrink-0" aria-hidden />
          <p>
            Das Modell ist sich unsicher, was auf den Fotos zu sehen ist. Sieh dir den
            Vorschlag genau an oder lade deutlichere Fotos hoch.
          </p>
        </div>
      )}

      <div className="karte lesebreite p-4">
        <h2 className="mb-3 font-medium text-stark">Vorschlag</h2>
        <dl className="space-y-3 text-sm">
          <Zeile bezeichnung="Titel">{entwurf.titel}</Zeile>
          <Zeile bezeichnung="Beschreibung">
            <span className="whitespace-pre-wrap">{entwurf.beschreibung}</span>
          </Zeile>
          <Zeile bezeichnung="Zustand">{entwurf.zustand_text ?? 'nicht erkennbar'}</Zeile>
          <Zeile bezeichnung="Preis">
            {entwurf.preis_von_euro !== null && entwurf.preis_bis_euro !== null
              ? `grobe Einordnung: ${euro(entwurf.preis_von_euro)} bis ${euro(entwurf.preis_bis_euro)}`
              : 'keine Einschätzung'}
            {entwurf.preis_begruendung && (
              <span className="lesebreite mt-0.5 block text-xs text-leise">{entwurf.preis_begruendung}</span>
            )}
            <span className="lesebreite mt-0.5 block text-xs text-leise">
              Geschätzt, nicht recherchiert – das Modell kennt keine aktuellen Marktpreise.
              Der Preis wird unten gesetzt, nicht hier.
            </span>
          </Zeile>
          <Zeile bezeichnung="Kategorie">
            {entwurf.kategorie ?? 'kein Vorschlag'}
            <span className="lesebreite mt-0.5 block text-xs text-leise">
              Nur ein Hinweis – die Kategorie wird im Editor gesetzt, nicht hier.
            </span>
          </Zeile>
        </dl>
      </div>

      {entwurf.fragen.length > 0 && (
        <div className="karte p-4">
          <h2 className="mb-1 font-medium text-stark">Rückfragen</h2>
          <p className="lesebreite mb-3 text-xs text-leise">
            Das kann man auf Fotos nicht sehen. Antworten kostet nichts – sie werden
            eingesetzt, ohne noch einmal zu fragen.
          </p>
          <div className="space-y-4">
            {entwurf.fragen.map(frage => (
              <Rueckfrage
                key={frage.id}
                frage={frage}
                antwort={antworten[frage.id]}
                aufAntwort={wert => aufAntwort(frage.id, wert)}
                aufZuruecknehmen={() => aufZuruecknehmen(frage.id)}
              />
            ))}
          </div>
        </div>
      )}

      <Vorschlaege
        entwurf={entwurf}
        kategorie={kategorie}
        versandpakete={versandpakete}
        preis={preis}
        aufKategorie={setKategorie}
        aufVersand={setVersandpakete}
        aufPreis={setPreis}
      />

      {kosten && (
        <div className="lesebreite space-y-1 text-xs text-leise">
          <p>
            {kosten.modell} · {kosten.bilder_gesendet} Bilder ({Math.round(kosten.bytes_gesendet / 1024)} KB)
            {' · '}{kosten.token_eingabe + kosten.token_ausgabe} Token
            {' · rund '}{(kosten.usd * 100).toFixed(2).replace('.', ',')} US-Cent
          </p>
          <p>
            Ton nach{' '}
            {kosten.stil_eigene_texte > 0
              ? `${kosten.stil_eigene_texte} eigenen Anzeige${kosten.stil_eigene_texte === 1 ? '' : 'n'}`
              : 'Standardvorgabe – noch keine eigene Anzeige veröffentlicht'}
            {' · diesen Monat '}
            {kosten.verbrauch_usd.toFixed(2).replace('.', ',')} von{' '}
            {kosten.budget_usd.toFixed(2).replace('.', ',')} US-Dollar
          </p>
        </div>
      )}

      <button
        type="button"
        onClick={aufAnlegen}
        disabled={gesperrt}
        className="btn-primaer w-full sm:w-auto"
      >
        <Check className="h-4 w-4" />
        {offen > 0 ? `Anzeige anlegen (${offen} Rückfrage${offen === 1 ? '' : 'n'} offen)` : 'Anzeige anlegen'}
      </button>
      <p className="lesebreite text-center text-xs text-leise sm:text-left">
        Legt die Anzeige nur lokal an. Nichts geht dabei online.
      </p>
    </div>
  );
}

/** Euro-Betrag in deutscher Schreibweise. An genug Stellen gebraucht, um ihn
 * einmal zu haben statt viermal `.toFixed(2).replace('.', ',')`. */
function euro(betrag: number): string {
  return `${betrag.toFixed(2).replace('.', ',')} €`;
}


function Zeile({ bezeichnung, children }: { bezeichnung: string; children: React.ReactNode }) {
  return (
    <div>
      <dt className="text-xs uppercase tracking-wide text-leise">{bezeichnung}</dt>
      <dd className="text-stark">{children}</dd>
    </div>
  );
}

function Rueckfrage({
  frage, antwort, aufAntwort, aufZuruecknehmen,
}: {
  frage: KiEntwurf['fragen'][number];
  antwort: string | undefined;
  aufAntwort: (wert: string) => void;
  aufZuruecknehmen: () => void;
}) {
  const [freitext, setFreitext] = useState('');
  const beantwortet = antwort !== undefined;
  const antwortAnzeige = frage.optionen.find(option => option.wert === antwort)?.text ?? antwort;

  const uebernehmen = useCallback(() => {
    if (freitext.trim()) aufAntwort(freitext.trim());
  }, [freitext, aufAntwort]);

  return (
    <fieldset className="karte p-3">
      <legend className="px-1 text-sm font-medium text-stark">{frage.frage}</legend>

      {beantwortet ? (
        <p className="flex items-start justify-between gap-3 text-sm">
          <span className="flex items-start gap-2 text-normal">
            <Check className="mt-0.5 h-4 w-4 flex-shrink-0 text-green-600" aria-hidden />
            {antwortAnzeige}
          </span>
          <button type="button" onClick={aufZuruecknehmen} className="flex-shrink-0 text-xs text-leise underline">
            ändern
          </button>
        </p>
      ) : (
        <>
          <div className="flex flex-wrap gap-2">
            {frage.optionen.map(option => (
              <button
                key={option.wert}
                type="button"
                onClick={() => aufAntwort(option.wert)}
                className="btn-ghost"
              >
                {option.text}
              </button>
            ))}
          </div>
          {frage.freitext_erlaubt && (
            <div className="mt-2 flex gap-2">
              <input
                type="text"
                value={freitext}
                onChange={ereignis => setFreitext(ereignis.target.value)}
                onKeyDown={ereignis => { if (ereignis.key === 'Enter') { ereignis.preventDefault(); uebernehmen(); } }}
                placeholder="oder selbst eintragen"
                aria-label={`Eigene Antwort auf: ${frage.frage}`}
                className="feld min-w-0 flex-1"
              />
              <button
                type="button"
                onClick={uebernehmen}
                disabled={!freitext.trim()}
                className="btn-ghost"
              >
                Übernehmen
              </button>
            </div>
          )}
        </>
      )}
    </fieldset>
  );
}


/**
 * Kategorie- und Versandvorschlag (AP-4.5).
 *
 * Angeklickt statt gesetzt: Beide Felder können einen Lauf zum Stehen bringen -
 * ein falscher Kategoriepfad im Kategoriedialog, ein unpassender Versandweg im
 * Versanddialog. Was hier steht, ist gegen den echten Katalog abgeglichen und
 * existiert damit; ob es *stimmt*, weiß nur der Mensch vor dem Bildschirm.
 */
function Vorschlaege({
  entwurf, kategorie, versandpakete, preis, aufKategorie, aufVersand, aufPreis,
}: {
  entwurf: KiEntwurf;
  kategorie: string | null;
  versandpakete: string[];
  preis: number | null;
  aufKategorie: (wert: string | null) => void;
  aufVersand: (werte: string[]) => void;
  aufPreis: (wert: number | null) => void;
}) {
  const hatKategorien = entwurf.kategorie_vorschlaege.length > 0;
  const hatVersand = entwurf.versand_vorschlaege.length > 0;
  const spanne = entwurf.preis_von_euro !== null && entwurf.preis_bis_euro !== null
    ? { von: entwurf.preis_von_euro, bis: entwurf.preis_bis_euro }
    : null;

  const paketUmschalten = (wert: string) => {
    aufVersand(versandpakete.includes(wert)
      ? versandpakete.filter(p => p !== wert)
      : [...versandpakete, wert]);
  };

  // Schnellwerte: die beiden Grenzen der Schätzung und die eigenen früheren
  // Preise. Doppelte fallen weg - zwei Knöpfe mit derselben Zahl sind keine
  // Auswahl, sondern ein Versehen.
  const schnellwerte = [...new Set([
    ...(spanne ? [spanne.von, spanne.bis] : []),
    ...entwurf.eigene_preise.map(p => p.preis),
  ])].sort((a, b) => a - b);

  return (
    <div className="karte p-4">
      <h2 className="mb-1 font-medium text-stark">Vorschläge zum Übernehmen</h2>
      <p className="lesebreite mb-3 text-xs text-leise">
        Nichts davon wird automatisch gesetzt. Was du hier nicht anklickst, bleibt leer
        und lässt sich später im Editor nachtragen.
      </p>

      <fieldset className="mb-4">
        <legend className="mb-1 text-sm font-medium text-stark">Preis</legend>
        <p className="lesebreite mb-2 text-xs text-leise">
          {spanne
            ? `Grobe Einordnung: ${euro(spanne.von)} bis ${euro(spanne.bis)}.`
            : 'Das Modell konnte den Preis nicht einschätzen.'}
          {' '}Geschätzt aus den Fotos, ohne Marktdaten – prüf ihn, bevor du ihn nimmst.
          Leer lassen ist in Ordnung; dann trägst du ihn später im Editor nach.
        </p>
        {entwurf.eigene_preise.length > 0 && (
          <p className="lesebreite mb-2 text-xs text-leise">
            Deine früheren Anzeigen:{' '}
            {entwurf.eigene_preise.map(p => `${p.titel} (${euro(p.preis)})`).join(', ')}
          </p>
        )}
        <div className="flex flex-wrap items-center gap-2">
          {schnellwerte.map(wert => (
            <button
              key={wert}
              type="button"
              onClick={() => aufPreis(preis === wert ? null : wert)}
              aria-pressed={preis === wert}
              className={`reiter ${preis === wert ? 'reiter-aktiv' : ''}`}
            >
              {euro(wert)}
            </button>
          ))}
          <label className="flex items-center gap-2 text-sm text-normal">
            <span className="sr-only">Preis in Euro</span>
            <input
              type="number"
              min="0"
              step="0.01"
              inputMode="decimal"
              placeholder="eigener Preis"
              value={preis ?? ''}
              onChange={e => {
                const zahl = Number.parseFloat(e.target.value);
                aufPreis(Number.isFinite(zahl) && zahl > 0 ? zahl : null);
              }}
              className="feld w-32"
            />
            <span className="text-leise">€</span>
          </label>
        </div>
      </fieldset>

      {hatKategorien && (
        <fieldset className="mb-4">
          <legend className="mb-2 text-sm font-medium text-stark">Kategorie</legend>
          <div className="flex flex-wrap gap-2">
            {entwurf.kategorie_vorschlaege.map(k => (
              <button
                key={k.wert}
                type="button"
                onClick={() => aufKategorie(kategorie === k.wert ? null : k.wert)}
                aria-pressed={kategorie === k.wert}
                className={`reiter ${kategorie === k.wert ? 'reiter-aktiv' : ''}`}
              >
                {k.name}
              </button>
            ))}
          </div>
        </fieldset>
      )}

      {hatVersand && (
        <fieldset>
          <legend className="mb-1 text-sm font-medium text-stark">
            Versand ({entwurf.versand_vorschlaege[0].groesse})
          </legend>
          <p className="lesebreite mb-2 text-xs text-leise">
            Geschätzt nach den Fotos. Miss im Zweifel nach – ein zu kleines Paket fällt
            erst beim Versenden auf.
          </p>
          <div className="flex flex-wrap gap-2">
            {entwurf.versand_vorschlaege.map(v => (
              <button
                key={v.wert}
                type="button"
                onClick={() => paketUmschalten(v.wert)}
                aria-pressed={versandpakete.includes(v.wert)}
                className={`reiter ${versandpakete.includes(v.wert) ? 'reiter-aktiv' : ''}`}
              >
                {v.wert.replace(/_/g, ' ')}
                {v.preis !== null && (
                  <span className="ml-2 text-xs text-leise">{euro(v.preis)}</span>
                )}
              </button>
            ))}
          </div>
        </fieldset>
      )}
    </div>
  );
}
