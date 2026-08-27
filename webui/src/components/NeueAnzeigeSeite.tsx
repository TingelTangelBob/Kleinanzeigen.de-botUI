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
    setAngelegt(null);
  };

  const erkennen = async () => {
    if (dateien.length === 0) return;
    setFehler(null);
    zuruecksetzen();
    setStufe({ art: 'hochladen', anteil: 0 });

    // Ab dem Moment, in dem der Upload durch ist, läuft die Uhr. Sie ist die
    // einzige ehrliche Auskunft über eine Wartezeit, die wir nicht aufteilen
    // können: Der Anbieter meldet keinen Zwischenstand.
    let uhr: number | undefined;
    try {
      const antwort = await api.ki.entwurf(dateien, anteil => {
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
      const ergebnis = await api.ki.anlegen(profil, entwurf, antworten, dateien);
      setAngelegt(ergebnis.titel);
    } catch (ursache) {
      setFehler(ursache instanceof ApiFehler ? ursache.message : 'Unbekannter Fehler.');
    } finally {
      setStufe({ art: 'ruhe' });
    }
  };

  const offeneFragen = entwurf?.fragen.filter(f => !antworten[f.id]) ?? [];

  return (
    <div className="mx-auto max-w-3xl">
      <h1 className="mb-1 text-xl font-semibold text-gray-900">Neue Anzeige aus Fotos</h1>
      <p className="mb-5 text-sm text-gray-600">
        Fotos hochladen, erkennen lassen, Rückfragen beantworten. Die Anzeige wird
        anschließend <strong>lokal angelegt</strong> – veröffentlicht wird sie nicht.
      </p>

      {kiStatus && !kiStatus.hinterlegt && <SchluesselFehlt />}

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
        <p role="alert" className="mb-4 rounded border border-red-200 bg-red-50 p-3 text-sm text-red-800">
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
            disabled={dateien.length === 0 || !kiStatus?.hinterlegt}
            className="flex w-full items-center justify-center gap-2 rounded bg-primary-custom px-4 py-3 text-sm font-medium text-white disabled:cursor-not-allowed disabled:opacity-40"
          >
            <Sparkles className="h-4 w-4" />
            {entwurf ? 'Noch einmal erkennen lassen' : 'Erkennen lassen'}
          </button>
          {/* Ein grauer Knopf ohne Begruendung laesst den Nutzer raten. */}
          {(dateien.length === 0 || !kiStatus?.hinterlegt) && (
            <p className="mt-2 text-center text-xs text-gray-500">
              {kiStatus === null
                ? 'Der Zustand des KI-Zugangs ließ sich nicht laden – ist das Backend erreichbar?'
                : !kiStatus.hinterlegt
                  ? 'Es fehlt der OpenAI-Schlüssel.'
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
        />
      )}

      {angelegt && (
        <div className="rounded border border-green-200 bg-green-50 p-4">
          <p className="flex items-center gap-2 font-medium text-green-900">
            <Check className="h-5 w-5" />
            „{angelegt}“ liegt jetzt im Bestand.
          </p>
          <p className="mt-2 text-sm text-green-800">
            Sie ist <strong>nicht</strong> veröffentlicht. Unter „Anzeigen“ lässt sie sich
            bearbeiten – Kategorie und Versand fehlen noch – und von dort aus hochladen.
          </p>
          <a href="#bestand" className="mt-3 inline-block text-sm font-medium text-green-900 underline">
            Zum Bestand
          </a>
        </div>
      )}
    </div>
  );
}

function SchluesselFehlt() {
  return (
    <div className="mb-4 flex items-start gap-3 rounded border border-amber-200 bg-amber-50 p-3">
      <AlertTriangle className="mt-0.5 h-5 w-5 flex-shrink-0 text-amber-700" aria-hidden />
      <p className="text-sm text-amber-900">
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
    <div className="mb-4 rounded border border-gray-200 bg-gray-50 p-3 text-sm">
      <button
        type="button"
        onClick={() => setOffen(!offen)}
        className="flex w-full items-start gap-2 text-left text-gray-800"
      >
        <AlertTriangle className="mt-0.5 h-4 w-4 flex-shrink-0 text-gray-500" aria-hidden />
        <span>
          Die Fotos werden an OpenAI geschickt.{' '}
          <span className="underline">{offen ? 'Weniger' : 'Was genau passiert?'}</span>
        </span>
      </button>
      {offen && (
        <ul className="mt-2 list-disc space-y-1 pl-9 text-gray-700">
          <li>Vor dem Versand wird jedes Bild auf höchstens {bildkante} px verkleinert.</li>
          <li>
            Alle Metadaten werden entfernt – auch die GPS-Koordinaten, die Handyfotos
            mitbringen und die bei einer Aufnahme zu Hause die Wohnadresse sind.
          </li>
          <li>Höchstens {MAX_BILDER} Bilder gehen mit; weitere werden nicht gesendet.</li>
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
      className={`mb-4 rounded-lg border-2 border-dashed p-3 transition-colors ${
        ueberZone ? 'border-primary-custom bg-blue-50/50' : 'border-transparent'
      }`}
      onDragOver={aufDragOver}
      onDragEnter={aufDragOver}
      onDragLeave={() => setUeberZone(false)}
      onDrop={aufDrop}
    >
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        {vorschauen.map((url, index) => (
          <div key={url} className="group relative aspect-square overflow-hidden rounded border border-gray-200">
            <img src={url} alt={`Foto ${index + 1}`} className="h-full w-full object-cover" />
            {!gesperrt && (
              <button
                type="button"
                onClick={() => aufEntfernen(index)}
                aria-label={`Foto ${index + 1} entfernen`}
                className="absolute right-1 top-1 rounded bg-white/90 p-1 text-gray-700 shadow"
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
            className="flex aspect-square flex-col items-center justify-center gap-1 rounded border-2 border-dashed border-gray-300 text-gray-500 hover:border-primary-custom hover:text-primary-custom"
          >
            <ImagePlus className="h-6 w-6" />
            <span className="text-xs">Foto wählen</span>
            <span className="text-[10px] text-gray-400">oder hierher ziehen</span>
          </button>
        )}
      </div>
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
      <p className="mt-2 text-xs text-gray-500">
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
    <div className="mb-6 rounded border border-gray-200 bg-white p-4" role="status" aria-live="polite">
      <p className="flex items-center gap-2 text-sm font-medium text-gray-900">
        <Loader2 className="h-4 w-4 animate-spin text-primary-custom" aria-hidden />
        {text}
      </p>
      {stufe.art === 'hochladen' && (
        <div className="mt-3 h-1.5 overflow-hidden rounded bg-gray-200">
          <div
            className="h-full bg-primary-custom transition-[width] duration-200"
            style={{ width: `${Math.round(stufe.anteil * 100)}%` }}
          />
        </div>
      )}
      {stufe.art === 'warten' && (
        <p className="mt-2 text-xs text-gray-600">
          Das dauert meist 10 bis 30 Sekunden. Der Anbieter meldet keinen Zwischenstand –
          deshalb steht hier eine Uhr und kein Balken.
        </p>
      )}
    </div>
  );
}

function Ergebnis({
  entwurf, kosten, antworten, aufAntwort, aufZuruecknehmen, offen, gesperrt, aufAnlegen,
}: {
  entwurf: KiEntwurf;
  kosten: KiKosten | null;
  antworten: Record<string, string>;
  aufAntwort: (id: string, wert: string) => void;
  aufZuruecknehmen: (id: string) => void;
  offen: number;
  gesperrt: boolean;
  aufAnlegen: () => void;
}) {
  return (
    <div className="space-y-4">
      {entwurf.sicherheit === 'niedrig' && (
        <div className="flex items-start gap-3 rounded border border-amber-200 bg-amber-50 p-3">
          <AlertTriangle className="mt-0.5 h-5 w-5 flex-shrink-0 text-amber-700" aria-hidden />
          <p className="text-sm text-amber-900">
            Das Modell ist sich unsicher, was auf den Fotos zu sehen ist. Sieh dir den
            Vorschlag genau an oder lade deutlichere Fotos hoch.
          </p>
        </div>
      )}

      <div className="rounded border border-gray-200 bg-white p-4">
        <h2 className="mb-3 font-medium text-gray-900">Vorschlag</h2>
        <dl className="space-y-3 text-sm">
          <Zeile bezeichnung="Titel">{entwurf.titel}</Zeile>
          <Zeile bezeichnung="Beschreibung">
            <span className="whitespace-pre-wrap">{entwurf.beschreibung}</span>
          </Zeile>
          <Zeile bezeichnung="Zustand">{entwurf.zustand_text ?? 'nicht erkennbar'}</Zeile>
          <Zeile bezeichnung="Preis">
            {entwurf.preis_euro !== null ? `${entwurf.preis_euro.toFixed(2).replace('.', ',')} €` : 'kein Vorschlag'}
            {entwurf.preis_begruendung && (
              <span className="mt-0.5 block text-xs text-gray-500">{entwurf.preis_begruendung}</span>
            )}
          </Zeile>
          <Zeile bezeichnung="Kategorie">
            {entwurf.kategorie ?? 'kein Vorschlag'}
            <span className="mt-0.5 block text-xs text-gray-500">
              Nur ein Hinweis – die Kategorie wird im Editor gesetzt, nicht hier.
            </span>
          </Zeile>
        </dl>
      </div>

      {entwurf.fragen.length > 0 && (
        <div className="rounded border border-gray-200 bg-white p-4">
          <h2 className="mb-1 font-medium text-gray-900">Rückfragen</h2>
          <p className="mb-3 text-xs text-gray-600">
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

      {kosten && (
        <p className="text-xs text-gray-500">
          {kosten.modell} · {kosten.bilder_gesendet} Bilder ({Math.round(kosten.bytes_gesendet / 1024)} KB)
          {' · '}{kosten.token_eingabe + kosten.token_ausgabe} Token
          {' · rund '}{(kosten.usd * 100).toFixed(2).replace('.', ',')} US-Cent
        </p>
      )}

      <button
        type="button"
        onClick={aufAnlegen}
        disabled={gesperrt}
        className="flex w-full items-center justify-center gap-2 rounded bg-primary-custom px-4 py-3 text-sm font-medium text-white disabled:opacity-40"
      >
        <Check className="h-4 w-4" />
        {offen > 0 ? `Anzeige anlegen (${offen} Rückfrage${offen === 1 ? '' : 'n'} offen)` : 'Anzeige anlegen'}
      </button>
      <p className="text-center text-xs text-gray-500">
        Legt die Anzeige nur lokal an. Nichts geht dabei online.
      </p>
    </div>
  );
}

function Zeile({ bezeichnung, children }: { bezeichnung: string; children: React.ReactNode }) {
  return (
    <div>
      <dt className="text-xs uppercase tracking-wide text-gray-500">{bezeichnung}</dt>
      <dd className="text-gray-900">{children}</dd>
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

  const uebernehmen = useCallback(() => {
    if (freitext.trim()) aufAntwort(freitext.trim());
  }, [freitext, aufAntwort]);

  return (
    <fieldset className="rounded border border-gray-200 p-3">
      <legend className="px-1 text-sm font-medium text-gray-900">{frage.frage}</legend>

      {beantwortet ? (
        <p className="flex items-start justify-between gap-3 text-sm">
          <span className="flex items-start gap-2 text-gray-800">
            <Check className="mt-0.5 h-4 w-4 flex-shrink-0 text-green-600" aria-hidden />
            {antwort}
          </span>
          <button type="button" onClick={aufZuruecknehmen} className="flex-shrink-0 text-xs text-gray-500 underline">
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
                className="rounded border border-gray-300 px-3 py-1.5 text-sm text-gray-800 hover:border-primary-custom hover:bg-gray-50"
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
                className="min-w-0 flex-1 rounded border border-gray-300 px-3 py-1.5 text-sm"
              />
              <button
                type="button"
                onClick={uebernehmen}
                disabled={!freitext.trim()}
                className="rounded border border-gray-300 px-3 py-1.5 text-sm text-gray-800 disabled:opacity-40"
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
