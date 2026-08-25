// SPDX-FileCopyrightText: © Anzeigen-Studio contributors
// SPDX-License-Identifier: AGPL-3.0-or-later
//
// Einstieg und Routing.
//
// Hash-Routing ohne Router, wie in SoloOffice: Bei einer Handvoll Seiten ist
// eine Bibliothek dafür mehr Abhängigkeit als Nutzen.

import { useEffect, useState } from 'react';
import { AuthProvider } from './context/AuthContext';
import { ProfilProvider } from './context/ProfilContext';
import { useAuth } from './context/useAuth';
import { AuthSeite } from './components/AuthSeite';
import { BestandSeite } from './components/BestandSeite';
import { JobSeite } from './components/JobSeite';
import { Layout, type Seite } from './components/Layout';
import { ProfilSeite } from './components/ProfilSeite';
import { UebersichtSeite } from './components/UebersichtSeite';

const SEITEN: Seite[] = ['uebersicht', 'bestand', 'profile', 'jobs', 'browsersicht'];

function seiteAusHash(): Seite {
  const roh = window.location.hash.replace(/^#/, '') as Seite;
  return SEITEN.includes(roh) ? roh : 'uebersicht';
}

function Inhalt() {
  const { status, laedt } = useAuth();
  const [seite, setSeite] = useState<Seite>(seiteAusHash);

  useEffect(() => {
    const aufHash = () => setSeite(seiteAusHash());
    window.addEventListener('hashchange', aufHash);
    return () => window.removeEventListener('hashchange', aufHash);
  }, []);

  if (laedt) {
    return (
      <div className="flex min-h-screen items-center justify-center text-gray-500">
        Wird geladen …
      </div>
    );
  }

  // Kein Status heißt: Backend nicht erreichbar. Das ist etwas anderes als
  // "nicht angemeldet" und braucht eine eigene Meldung.
  if (status === null) {
    return (
      <div className="flex min-h-screen items-center justify-center px-4">
        <p className="max-w-md rounded border border-red-200 bg-red-50 p-4 text-center text-sm text-red-800">
          Das Backend ist nicht erreichbar. Läuft der Dienst?
        </p>
      </div>
    );
  }

  if (!status.eingerichtet) return <AuthSeite einrichtung />;
  if (!status.angemeldet) return <AuthSeite einrichtung={false} />;

  // Ein Seitenwechsel aus dem Inhalt heraus muss auch den Hash setzen, sonst
  // zeigt die Adresszeile auf die vorige Seite.
  const wechseln = (ziel: Seite) => {
    window.location.hash = ziel;
    setSeite(ziel);
  };

  return (
    <Layout seite={seite} aufSeitenwechsel={setSeite}>
      {seite === 'uebersicht' && <UebersichtSeite aufSeite={wechseln} />}
      {seite === 'bestand' && <BestandSeite />}
      {seite === 'profile' && <ProfilSeite />}
      {seite === 'jobs' && <JobSeite />}
      {seite === 'browsersicht' && <Browsersicht />}
    </Layout>
  );
}

function Browsersicht() {
  return (
    <div className="mx-auto max-w-5xl">
      <h1 className="mb-2 text-2xl font-bold text-gray-900">Browsersicht</h1>
      <p className="mb-4 text-sm text-gray-600">
        Der Browser, in dem der Bot arbeitet. Hier lässt sich ein Captcha oder eine
        Bestätigung von Hand lösen, wenn ein Lauf darauf wartet.
      </p>
      {/* Eigenes Fenster statt eingebettet: Ein Captcha in einem kleinen
          Rahmen ist mühsam, und noVNC braucht die volle Tastatur. */}
      <a
        href="/browsersicht/vnc.html?autoconnect=1&resize=scale"
        target="_blank"
        rel="noreferrer"
        className="inline-block rounded bg-primary-custom px-4 py-2 text-sm font-medium"
      >
        In neuem Fenster öffnen
      </a>
      <div className="mt-6 overflow-hidden rounded border border-gray-200 bg-black">
        <iframe
          title="Browsersicht"
          src="/browsersicht/vnc.html?autoconnect=1&resize=scale"
          className="h-[60vh] w-full"
        />
      </div>
    </div>
  );
}

export default function App() {
  return (
    <AuthProvider>
      <ProfilProvider>
        <Inhalt />
      </ProfilProvider>
    </AuthProvider>
  );
}
