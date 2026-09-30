// SPDX-FileCopyrightText: © Anzeigen-Studio contributors
// SPDX-License-Identifier: AGPL-3.0-or-later
//
// Stapel-Erkennung: viele Fotos, viele Entwürfe auf einmal.
// Neue Datei, Anzeigen-Studio, 2026-09-30.
//
// Die Fotos werden in Reihenfolge zu Anzeigen gruppiert. Jede Gruppe wird
// einzeln hochgeladen und serverseitig in die bestehende KI-Warteschlange
// (AP-4.8) eingereiht; dort laufen mehrere Analysen gleichzeitig. Einzeln
// hochladen statt in einer großen Anfrage, weil sonst schon zwanzig
// Handyfotos an der Größengrenze des Proxys scheitern - und weil so eine
// abgelehnte Gruppe die anderen nicht mitreißt.
//
// Geprüft und gespeichert wird weiterhin jeder Entwurf einzeln. Ein Stapel
// spart das Warten, nicht die menschliche Prüfung.

import { useEffect, useMemo, useRef, useState } from 'react';
import { ImagePlus, Layers, Loader2, Scissors, Sparkles, Trash2 } from 'lucide-react';
import { api, ApiFehler } from '../services/api';
import { anfaengeJe, fotosPruefen, gruppenAus } from '../kiFotos';
import type { KiStatus } from '../types';

interface Foto {
  id: number;
  datei: File;
  url: string;
}

type Ergebnis = { gruppe: number; ok: true } | { gruppe: number; ok: false; meldung: string };

let naechsteId = 1;

export function StapelErkennung({
  profil,
  kiStatus,
  hinweis,
  aufEingereiht,
}: {
  profil: string;
  kiStatus: KiStatus | null;
  /** Der Datenschutzhinweis der Seite - derselbe Text wie bei der Einzelerkennung. */
  hinweis?: React.ReactNode;
  /** Wird nach jeder angenommenen Gruppe gerufen, damit die Warteschlange nachlädt. */
  aufEingereiht: () => void;
}) {
  const maxBilder = Math.max(1, kiStatus?.max_bilder ?? 4);
  const maxOffen = Math.max(1, kiStatus?.max_offen ?? 50);
  const kiBereit = kiStatus?.hinterlegt === true;

  const [fotos, setFotos] = useState<Foto[]>([]);
  const [anfaenge, setAnfaenge] = useState<Set<number>>(new Set([0]));
  const [je, setJe] = useState(1);
  const [fehler, setFehler] = useState<string | null>(null);
  const [fortschritt, setFortschritt] = useState<{ fertig: number; gesamt: number } | null>(null);
  const [ergebnisse, setErgebnisse] = useState<Ergebnis[]>([]);
  const eingabe = useRef<HTMLInputElement>(null);
  const fotosRef = useRef<Foto[]>([]);
  useEffect(() => { fotosRef.current = fotos; }, [fotos]);

  // Objekt-URLs erst beim Verlassen der Seite freigeben; einzelne werden beim
  // Entfernen sofort freigegeben.
  useEffect(() => () => fotosRef.current.forEach(foto => URL.revokeObjectURL(foto.url)), []);

  const gruppen = useMemo(() => gruppenAus(fotos.length, anfaenge), [fotos.length, anfaenge]);
  const zuGross = gruppen.filter(gruppe => gruppe.length > maxBilder).length;
  const zuViele = gruppen.length > maxOffen;
  const laeuft = fortschritt !== null;
  const modellName = kiStatus?.modelle?.find(m => m.kennung === kiStatus.modell)?.name ?? kiStatus?.modell;

  const neuGruppieren = (anzahl: number, groesse: number) => setAnfaenge(anfaengeJe(anzahl, groesse));

  const hinzufuegen = (liste: FileList | null) => {
    if (!liste || liste.length === 0) return;
    // Sofort auslesen - dieselbe Falle wie in der Einzelerkennung: Das Leeren
    // des Eingabefelds leert auch die FileList.
    const { brauchbar, fehler: pruefFehler } = fotosPruefen(Array.from(liste));
    setFehler(pruefFehler);
    if (brauchbar.length === 0) return;
    const neu = brauchbar.map(datei => ({ id: naechsteId++, datei, url: URL.createObjectURL(datei) }));
    const alle = [...fotos, ...neu];
    setFotos(alle);
    neuGruppieren(alle.length, je);
    setErgebnisse([]);
  };

  const entfernen = (index: number) => {
    URL.revokeObjectURL(fotos[index].url);
    const rest = fotos.filter((_, i) => i !== index);
    setFotos(rest);
    neuGruppieren(rest.length, je);
  };

  /** Trennt vor diesem Foto eine neue Anzeige ab oder fügt es der vorigen hinzu. */
  const trennungUmschalten = (index: number) => {
    if (index === 0) return;
    setAnfaenge(vorher => {
      const neu = new Set(vorher);
      if (neu.has(index)) neu.delete(index);
      else neu.add(index);
      return neu;
    });
  };

  const alleEntfernen = () => {
    fotos.forEach(foto => URL.revokeObjectURL(foto.url));
    setFotos([]);
    setAnfaenge(new Set([0]));
    setErgebnisse([]);
    setFehler(null);
  };

  const einreihen = async () => {
    if (gruppen.length === 0 || zuGross > 0 || zuViele || !kiBereit) return;
    setFehler(null);
    setErgebnisse([]);
    setFortschritt({ fertig: 0, gesamt: gruppen.length });

    const ergebnis: Ergebnis[] = [];
    for (const [nummer, gruppe] of gruppen.entries()) {
      try {
        await api.ki.erkennungStarten(profil, gruppe.map(index => fotos[index].datei));
        ergebnis.push({ gruppe: nummer, ok: true });
        aufEingereiht();
      } catch (ursache) {
        ergebnis.push({
          gruppe: nummer,
          ok: false,
          meldung: ursache instanceof ApiFehler ? ursache.message : 'Nicht angenommen.',
        });
        // Bei einer Obergrenze oder fehlendem Zugang scheitert jede weitere
        // Gruppe genauso. Weiterzumachen hieße nur, dieselbe Meldung zu
        // sammeln und Fotos unnötig hochzuladen.
        if (ursache instanceof ApiFehler && [401, 403, 409, 429].includes(ursache.status)) break;
      }
      setFortschritt({ fertig: nummer + 1, gesamt: gruppen.length });
    }

    // Angenommene Gruppen verlassen die Auswahl; was nicht angenommen wurde,
    // bleibt stehen und kann nach einer Korrektur erneut eingereiht werden.
    const angenommen = new Set(
      ergebnis.filter(e => e.ok).flatMap(e => gruppen[e.gruppe]),
    );
    const rest = fotos.filter((_, index) => !angenommen.has(index));
    fotos.filter((_, index) => angenommen.has(index)).forEach(foto => URL.revokeObjectURL(foto.url));
    setFotos(rest);
    neuGruppieren(rest.length, je);
    setErgebnisse(ergebnis);
    setFortschritt(null);
  };

  const angenommen = ergebnisse.filter(e => e.ok).length;
  const abgelehnt = ergebnisse.filter((e): e is Extract<Ergebnis, { ok: false }> => !e.ok);

  return (
    <div>
      <div className="mb-3 flex flex-wrap items-center gap-x-3 gap-y-2 text-sm">
        <label htmlFor="stapel-je" className="text-normal">Fotos je Anzeige</label>
        <select
          id="stapel-je"
          value={je}
          disabled={laeuft}
          onChange={ereignis => {
            const wert = Number(ereignis.target.value);
            setJe(wert);
            neuGruppieren(fotos.length, wert);
          }}
          className="feld w-auto py-1.5"
        >
          {Array.from({ length: maxBilder }, (_, i) => i + 1).map(wert => (
            <option key={wert} value={wert}>{wert}</option>
          ))}
        </select>
        <span className="text-xs text-leise">
          Mit <Scissors className="inline h-3 w-3" aria-hidden /> zwischen zwei Fotos trennen oder zusammenfügen.
        </span>
      </div>

      {fotos.length === 0 ? (
        <button
          type="button"
          onClick={() => eingabe.current?.click()}
          disabled={laeuft}
          className="dropzone mb-4"
          onDragOver={ereignis => ereignis.preventDefault()}
          onDrop={ereignis => { ereignis.preventDefault(); hinzufuegen(ereignis.dataTransfer.files); }}
        >
          <Layers className="h-8 w-8" />
          <span className="text-base font-medium text-stark">Viele Fotos auf einmal hierher ziehen</span>
          <span className="text-sm text-leise">
            In Reihenfolge fotografieren: erst alle Fotos der ersten Sache, dann der nächsten.
          </span>
        </button>
      ) : (
        <div
          className="karte mb-4 p-3"
          onDragOver={ereignis => ereignis.preventDefault()}
          onDrop={ereignis => { ereignis.preventDefault(); if (!laeuft) hinzufuegen(ereignis.dataTransfer.files); }}
        >
          <ol className="flex flex-wrap items-stretch gap-y-3" aria-label="Fotos im Stapel">
            {fotos.map((foto, index) => {
              const gruppe = gruppen.findIndex(g => g.includes(index));
              const beginnt = index === 0 || anfaenge.has(index);
              const groesse = gruppen[gruppe]?.length ?? 0;
              return (
                <li key={foto.id} className="flex items-stretch">
                  {index > 0 && (
                    <button
                      type="button"
                      onClick={() => trennungUmschalten(index)}
                      disabled={laeuft}
                      aria-pressed={beginnt}
                      aria-label={beginnt
                        ? `Foto ${index + 1} mit der vorigen Anzeige zusammenfügen`
                        : `Vor Foto ${index + 1} eine neue Anzeige beginnen`}
                      title={beginnt ? 'Zusammenfügen' : 'Hier trennen'}
                      className={`mx-0.5 flex w-6 items-center justify-center rounded ${beginnt ? 'text-primary-custom' : 'text-leise opacity-40 hover:opacity-100'}`}
                    >
                      {beginnt
                        ? <span className="h-full w-0.5 rounded bg-current" aria-hidden />
                        : <Scissors className="h-3.5 w-3.5" aria-hidden />}
                    </button>
                  )}
                  <div className="flex flex-col">
                    <span className={`mb-1 h-4 text-[11px] ${groesse > maxBilder ? 'font-medium text-[color:var(--merkmal-rot-text)]' : 'text-leise'}`}>
                      {beginnt ? `Anzeige ${gruppe + 1}${groesse > maxBilder ? ` · zu viele Fotos` : ''}` : ''}
                    </span>
                    <div className="relative h-20 w-20 overflow-hidden rounded-xl" style={{ border: '1px solid var(--karte-rand)' }}>
                      <img src={foto.url} alt={`Foto ${index + 1}, Anzeige ${gruppe + 1}`} className="h-full w-full object-cover" />
                      {!laeuft && (
                        <button
                          type="button"
                          onClick={() => entfernen(index)}
                          aria-label={`Foto ${index + 1} entfernen`}
                          className="absolute right-1 top-1 rounded-full bg-white/90 p-1 text-stark shadow"
                        >
                          <Trash2 className="h-3.5 w-3.5" />
                        </button>
                      )}
                    </div>
                  </div>
                </li>
              );
            })}
            {!laeuft && (
              <li className="ml-2 flex flex-col">
                <span className="mb-1 h-4" />
                <button
                  type="button"
                  onClick={() => eingabe.current?.click()}
                  className="flex h-20 w-20 flex-col items-center justify-center gap-1 rounded-xl text-leise"
                  style={{ border: '2px dashed var(--karte-rand)' }}
                >
                  <ImagePlus className="h-5 w-5" />
                  <span className="text-[11px]">Fotos</span>
                </button>
              </li>
            )}
          </ol>
        </div>
      )}

      <input
        ref={eingabe}
        type="file"
        accept="image/jpeg,image/png,image/gif"
        multiple
        className="hidden"
        aria-label="Fotos für den Stapel wählen"
        onChange={ereignis => {
          hinzufuegen(ereignis.target.files);
          ereignis.target.value = '';
        }}
      />

      {fehler && <p role="alert" className="hinweis hinweis-fehler lesebreite mb-4">{fehler}</p>}
      {zuGross > 0 && (
        <p role="alert" className="hinweis hinweis-fehler lesebreite mb-4">
          {zuGross === 1 ? 'Eine Anzeige hat' : `${zuGross} Anzeigen haben`} mehr als {maxBilder} Fotos.
          Bitte dort trennen.
        </p>
      )}
      {zuViele && (
        <p role="alert" className="hinweis hinweis-fehler lesebreite mb-4">
          Höchstens {maxOffen} Anzeigen je Stapel. Bitte den Rest danach einreihen.
        </p>
      )}

      {fortschritt ? (
        <p className="flex items-center gap-2 text-sm text-normal" role="status">
          <Loader2 className="h-4 w-4 animate-spin text-primary-custom" aria-hidden />
          Fotos werden übergeben: {fortschritt.fertig} von {fortschritt.gesamt} Anzeigen
        </p>
      ) : (
        <div className="flex flex-col gap-3 sm:flex-row sm:items-stretch">
          <button
            type="button"
            onClick={() => void einreihen()}
            disabled={gruppen.length === 0 || zuGross > 0 || zuViele || !kiBereit || !profil}
            className="btn-primaer min-h-12 w-full sm:w-auto"
          >
            <Sparkles className="h-4 w-4" />
            {gruppen.length <= 1
              ? 'Erkennen lassen'
              : `${gruppen.length} Entwürfe erkennen lassen`}
          </button>
          {kiBereit && hinweis}
          {fotos.length > 0 && (
            <button type="button" onClick={alleEntfernen} className="btn-leise">
              Auswahl leeren
            </button>
          )}
        </div>
      )}

      {kiBereit && gruppen.length > 1 && !laeuft && (
        <p className="mt-2 text-xs text-leise">
          {fotos.length} Fotos, {gruppen.length} Anzeigen
          {modellName ? ` · Modell ${modellName}` : ''}
          {kiStatus?.parallel ? ` · ${kiStatus.parallel} Analysen gleichzeitig` : ''}
          {kiStatus ? ` · diesen Monat ${usd(kiStatus.verbrauch_usd)} von ${usd(kiStatus.budget_usd)} verbraucht` : ''}
        </p>
      )}

      {ergebnisse.length > 0 && (
        <div className="mt-4 lesebreite text-sm" role="status">
          {angenommen > 0 && (
            <p className="text-normal">
              {angenommen === 1 ? 'Eine Anzeige wird' : `${angenommen} Anzeigen werden`} jetzt analysiert.
              Die Entwürfe erscheinen oben unter „KI-Entwürfe prüfen“.
            </p>
          )}
          {abgelehnt.length > 0 && (
            <p className="hinweis hinweis-fehler mt-2">
              {abgelehnt.length === 1 ? 'Eine Anzeige wurde' : `${abgelehnt.length} Anzeigen wurden`} nicht
              angenommen: {abgelehnt[0].meldung} Alle nicht übergebenen Fotos bleiben in der Auswahl.
            </p>
          )}
        </div>
      )}
    </div>
  );
}

function usd(betrag: number): string {
  return `${betrag.toLocaleString('de-DE', { minimumFractionDigits: 2, maximumFractionDigits: 2 })} $`;
}
