// SPDX-FileCopyrightText: © Anzeigen-Studio contributors
// SPDX-License-Identifier: AGPL-3.0-or-later
//
// Übersicht: der erste Blick nach dem Anmelden (AP-2.3).
//
// Zeigt drei Dinge, und zwar in dieser Reihenfolge: Was ist mit dem Konto, was
// hat der Bot zuletzt getan, und was steht an. Alles andere gehört auf die
// Fachseiten. Eine Übersicht, die alles zeigt, zeigt nichts.

import { useCallback, useEffect, useState } from 'react';
import { ArrowRight, KeyRound } from 'lucide-react';
import { api, ApiFehler } from '../services/api';
import { anzeigeBezug, befehlIcon, befehlText } from '../jobText';
import { useProfil } from '../context/useProfil';
import type { BestandsAnzeige, Job, ZugangStatus } from '../types';
import { AnzeigenZeile } from './AnzeigenZeile';
import { InfoTip } from './InfoTip';

const ZUSTAND_TEXT: Record<string, string> = {
  wartet: 'wartet', laeuft: 'läuft', braucht_eingabe: 'braucht dich',
  fertig: 'fertig', pruefen: 'prüfen', gescheitert: 'gescheitert',
  abgebrochen: 'abgebrochen',
};

/** Zustände, bei denen jemand hinsehen muss - die tragen zusätzlich Text. */
const AUFFAELLIG = new Set(['braucht_eingabe', 'gescheitert', 'pruefen']);

const ZUSTAND_MERKMAL: Record<string, string> = {
  braucht_eingabe: 'merkmal merkmal-gelb',
  gescheitert: 'merkmal merkmal-rot',
  pruefen: 'merkmal merkmal-gelb',
};

const ZUSTAND_PUNKT: Record<string, string> = {
  wartet: 'status-punkt-grau',
  laeuft: 'status-punkt-gruen',
  braucht_eingabe: 'status-punkt-gelb',
  fertig: 'status-punkt-gruen',
  pruefen: 'status-punkt-gelb',
  gescheitert: 'status-punkt-rot',
  abgebrochen: 'status-punkt-grau',
};

function zeitText(iso: string | null): string {
  if (!iso) return '';
  const zeitpunkt = new Date(iso);
  if (Number.isNaN(zeitpunkt.getTime())) return '';
  return zeitpunkt.toLocaleString('de-DE', {
    day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit',
  });
}

function Kachel({
  zahl, label, betont, onClick,
}: {
  zahl: number;
  label: string;
  betont?: boolean;
  onClick?: () => void;
}) {
  const klasse = `kachel ${betont && zahl > 0 ? 'kachel-betont' : ''}`;
  const inner = (
    <>
      <div className="kachel-zahl">{zahl}</div>
      <div className="kachel-label">{label}</div>
    </>
  );
  if (!onClick) return <div className={klasse}>{inner}</div>;
  return (
    <button type="button" onClick={onClick} className={klasse}>
      {inner}
    </button>
  );
}

export function UebersichtSeite({ aufZiel }: { aufZiel: (ziel: string) => void }) {
  const { aktiv, laedt: profileLaden, fehler: profilFehler, neuLaden: profileNeuLaden } = useProfil();
  const [anzeigen, setAnzeigen] = useState<BestandsAnzeige[]>([]);
  const [jobs, setJobs] = useState<Job[]>([]);
  const [zugang, setZugang] = useState<ZugangStatus | null>(null);
  const [fehler, setFehler] = useState<string | null>(null);

  const laden = useCallback(async () => {
    if (!aktiv) return;
    setFehler(null);
    try {
      const [bestand, laeufe, zugangsdaten] = await Promise.all([
        api.bestand.liste(aktiv.slug),
        api.jobs.liste(aktiv.slug),
        api.profile.zugang(aktiv.slug),
      ]);
      setAnzeigen(bestand);
      setJobs(laeufe.slice(0, 5));
      setZugang(zugangsdaten);
    } catch (ursache) {
      setFehler(ursache instanceof ApiFehler ? ursache.message : 'Unbekannter Fehler.');
    }
  }, [aktiv]);

  useEffect(() => {
    void laden();
  }, [laden]);

  if (profileLaden) return <p className="text-sm text-leise">Wird geladen …</p>;

  // Eine Störung darf nicht als „noch kein Profil" erscheinen. Das sah aus wie
  // ein gültiger Zustand und verschwieg, dass ein Abruf fehlgeschlagen war.
  if (profilFehler) {
    return (
      <div className="seite">
        <div className="seite-kopf">
          <div>
            <h1 className="sr-only">Übersicht</h1>
          </div>
        </div>
        <p className="hinweis hinweis-fehler lesebreite">
          Die Profile ließen sich nicht laden: {profilFehler}
        </p>
        <button
          type="button"
          onClick={() => void profileNeuLaden()}
          className="btn-ghost mt-3"
        >
          Erneut versuchen
        </button>
      </div>
    );
  }

  if (!aktiv) {
    return (
      <div className="seite">
        <div className="seite-kopf">
          <div>
            <h1 className="sr-only">Übersicht</h1>
          </div>
        </div>
        <p className="hinweis hinweis-warn lesebreite">
          Noch kein Profil angelegt. Ein Profil steht für ein Kleinanzeigen-Konto.
        </p>
        <button
          type="button"
          onClick={() => aufZiel('einstellungen/profile')}
          className="btn-primaer mt-3"
        >
          Profil anlegen
        </button>
      </div>
    );
  }

  /*
   * Nur die EIGENEN Anzeigen (AP-2.34). Vorher zählten die Kacheln über den
   * ganzen Bestand, also auch über „Von anderen" – die Kachel meldete 6 und
   * führte per Klick auf eine Liste mit 5. Fremde Anzeigen sind eine getrennte
   * Sammlung mit eigenem Menüpunkt; auf dem Dashboard des eigenen Kontos haben
   * sie in keiner der vier Zahlen etwas zu suchen.
   */
  const eigene = anzeigen.filter(a => a.herkunft === 'eigene');
  const faellige = eigene.filter(a => a.faellig);
  const geaendert = eigene.filter(a => a.lokal_geaendert).length;
  const auffaellig = eigene.filter(a => a.hinweise.length > 0 || a.unlesbar).length;

  return (
    <div className="seite">
      <div className="seite-kopf">
        <div>
          <h1 className="sr-only">Übersicht</h1>
          <p className="seite-beschrieb">{aktiv.anzeigename}</p>
        </div>
      </div>

      {fehler && (
        <p className="hinweis hinweis-fehler lesebreite mb-4">{fehler}</p>
      )}

      {!zugang?.passwort_hinterlegt && (
        <div className="hinweis hinweis-warn lesebreite mb-6 flex items-start gap-3">
          <KeyRound className="mt-0.5 h-5 w-5 flex-shrink-0" aria-hidden />
          <div className="min-w-0 flex-1">
            <p>
              Für dieses Profil sind keine Zugangsdaten hinterlegt. Ohne sie kann kein Lauf starten.
            </p>
            <button
              type="button"
              onClick={() => aufZiel('einstellungen/profile')}
              className="mt-2 text-sm font-medium underline"
            >
              Zugangsdaten hinterlegen
            </button>
          </div>
        </div>
      )}

      {/* Das Raster behält die volle Seitenbreite – es baut die Seite mit auf
          und hält die Kante zu den Listen darunter (AP-2.16). Gedeckelt wird
          nur, was gelesen wird. Der Inhalt einer Kachel bleibt links und
          kompakt: Zahl und Beschriftung werden nicht auseinandergezogen, um
          die Breite zu füllen. */}
      <div className="mb-8 grid grid-cols-2 gap-3 sm:grid-cols-4">
        {/* Nur „Fällig" ist betont (AP-2.18). Vorher trugen drei von vier
            Kacheln die Betonung – wenn die Mehrheit hervorgehoben ist, hebt
            nichts mehr hervor. „Fällig" ist die einzige Zahl, die zu einer
            Handlung auffordert; „Lokal geändert" und „Mit Hinweis" sind
            Zustandsangaben und stehen jetzt so ruhig da wie „Anzeigen". */}
        <Kachel zahl={eigene.length} label="Anzeigen" onClick={() => aufZiel('anzeigen/eigene')} />
        <Kachel zahl={faellige.length} label="Fällig" betont onClick={() => aufZiel('anzeigen/eigene')} />
        <Kachel zahl={geaendert} label="Lokal geändert" />
        <Kachel zahl={auffaellig} label="Mit Hinweis" />
      </div>

      <section className="mb-8">
        <div className="mb-3 flex items-center justify-between">
          <h2 className="text-base font-semibold tracking-tight text-stark">Letzte Läufe</h2>
          <button
            type="button"
            onClick={() => aufZiel('warteschlange')}
            className="btn-leise"
          >
            Zur Warteschlange <ArrowRight className="h-4 w-4" aria-hidden />
          </button>
        </div>
        {jobs.length === 0 ? (
          <p className="leer">
            Noch kein Lauf. In der Warteschlange lässt sich einer starten.
          </p>
        ) : (
          <ul className="liste">
            {jobs.map(job => {
              const zustandText = ZUSTAND_TEXT[job.zustand] ?? job.zustand;
              const bezug = anzeigeBezug(job, anzeigen);
              // Symbol trägt den Vorgang (AP-2.32), die Primärzeile den
              // Anzeigentitel; fehlt der Bezug, tritt der Befehlsname ein.
              const Icon = befehlIcon(job.befehl);
              const titel = bezug ?? befehlText(job.befehl);
              return (
                <li key={job.id}>
                  {/* Klick führt auf die Warteschlange (AP-2.31). Dort steht
                      das Protokoll und lässt sich der Lauf aufklappen. */}
                  <button
                    type="button"
                    onClick={() => aufZiel('warteschlange')}
                    className="zeile items-center !py-2.5 text-sm"
                    title={`${befehlText(job.befehl)}${bezug ? ` · ${bezug}` : ''} · ${zustandText}`}
                  >
                    <span className="flex min-w-0 flex-1 items-center gap-2.5">
                      <Icon className="h-4 w-4 flex-shrink-0 text-leise" aria-hidden />
                      <span
                        className={`status-punkt ${ZUSTAND_PUNKT[job.zustand] ?? 'status-punkt-grau'}`}
                        role="img"
                        aria-label={zustandText}
                      />
                      <span className="truncate text-stark">{titel}</span>
                      {/* Farbe allein trägt den Status nicht (AP-2.34): Rot
                          und Grün sind für Rot-Grün-Blinde derselbe Punkt, und
                          „fertig" gegen „gescheitert" ist genau der
                          Unterschied, der zählt. Screenreader lesen ohnehin das
                          `aria-label` am Punkt; hier geht es um die Augen.
                          Beschriftet werden nur die Zustände, die Aufmerksamkeit
                          brauchen – ein Dashboard, das auch „fertig"
                          ausbuchstabiert, ist wieder eine Wand. */}
                      {AUFFAELLIG.has(job.zustand) && (
                        <span className={`${ZUSTAND_MERKMAL[job.zustand]} hidden flex-shrink-0 sm:inline-flex`}>
                          {zustandText}
                        </span>
                      )}
                    </span>
                    <span className="flex-shrink-0 text-xs text-leise">{zeitText(job.eingereicht_am)}</span>
                  </button>
                </li>
              );
            })}
          </ul>
        )}
      </section>

      <section>
        <div className="mb-3 flex items-center justify-between">
          <h2 className="flex items-center gap-1 text-base font-semibold tracking-tight text-stark">
            Steht an
            {/* Früher ein Dauerabsatz über der Liste (AP-2.25): Wann eine
                Anzeige auf der Plattform abläuft, steht nicht in der
                heruntergeladenen Datei – gezählt wird der selbst eingestellte
                Abstand. Das ist Hintergrund, kein Alarm, also als Kurzhilfe. */}
            <InfoTip
              label="Was „fällig“ bedeutet"
              text="Fällig heißt: Der eingestellte Abstand zur letzten Veröffentlichung ist erreicht. Das Ablaufdatum der Plattform steht nicht in den heruntergeladenen Dateien."
            />
          </h2>
          <button
            type="button"
            onClick={() => aufZiel('anzeigen/eigene')}
            className="btn-leise"
          >
            Alle Anzeigen <ArrowRight className="h-4 w-4" aria-hidden />
          </button>
        </div>
        {faellige.length === 0 ? (
          <p className="leer">
            Keine Anzeige ist zur Neueinstellung fällig.
          </p>
        ) : (
          <>
            <ul className="liste">
              {faellige.slice(0, 5).map(a => (
                <li key={a.datei}>
                  <AnzeigenZeile anzeige={a} profil={aktiv.slug} />
                </li>
              ))}
            </ul>
            {faellige.length > 5 && (
              <p className="mt-2 text-sm text-leise">und {faellige.length - 5} weitere</p>
            )}
          </>
        )}
      </section>
    </div>
  );
}
