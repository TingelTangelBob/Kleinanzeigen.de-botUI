// SPDX-FileCopyrightText: © Anzeigen-Studio contributors
// SPDX-License-Identifier: AGPL-3.0-or-later
//
// Einstieg und Routing.
//
// Hash-Routing ohne Router, wie in SoloOffice: Bei einer Handvoll Seiten ist
// eine Bibliothek dafür mehr Abhängigkeit als Nutzen.

import { useEffect, useState } from 'react';
import { AuthProvider } from './context/AuthContext';
import { MeldungenProvider } from './context/MeldungenContext';
import { ProfilProvider } from './context/ProfilContext';
import { useAuth } from './context/useAuth';
import { AuthSeite } from './components/AuthSeite';
import { BestandSeite } from './components/BestandSeite';
import { EinstellungenSeite } from './components/EinstellungenSeite';
import { Layout } from './components/Layout';
import { NeueAnzeigeSeite } from './components/NeueAnzeigeSeite';
import { UebersichtSeite } from './components/UebersichtSeite';
import { WarteschlangeSeite } from './components/WarteschlangeSeite';
import { routeAusHash, type Route } from './routing';

function Inhalt() {
  const { status, laedt } = useAuth();
  const [route, setRoute] = useState<Route>(routeAusHash);

  useEffect(() => {
    const aufHash = () => setRoute(routeAusHash());
    window.addEventListener('hashchange', aufHash);
    return () => window.removeEventListener('hashchange', aufHash);
  }, []);

  if (laedt) {
    return (
      <div className="flex min-h-screen items-center justify-center text-leise">
        Wird geladen …
      </div>
    );
  }

  // Kein Status heißt: Backend nicht erreichbar. Das ist etwas anderes als
  // "nicht angemeldet" und braucht eine eigene Meldung.
  if (status === null) {
    return (
      <div className="flex min-h-screen items-center justify-center px-4">
        <p className="hinweis hinweis-fehler max-w-md text-center">
          Das Backend ist nicht erreichbar. Läuft der Dienst?
        </p>
      </div>
    );
  }

  if (!status.eingerichtet) return <AuthSeite einrichtung />;
  if (!status.angemeldet) return <AuthSeite einrichtung={false} />;

  // Ein Seitenwechsel aus dem Inhalt heraus muss auch den Hash setzen, sonst
  // zeigt die Adresszeile auf die vorige Seite.
  const wechseln = (ziel: string) => {
    window.location.hash = ziel;
    setRoute(routeAusHash(`#${ziel}`));
  };

  return (
    <Layout route={route} aufZiel={wechseln}>
      {route.seite === 'uebersicht' && <UebersichtSeite aufZiel={wechseln} />}
      {route.seite === 'anzeigen' && (
        <BestandSeite herkunft={route.anzeigen} aufZiel={wechseln} />
      )}
      {route.seite === 'neu' && <NeueAnzeigeSeite />}
      {route.seite === 'warteschlange' && <WarteschlangeSeite />}
      {route.seite === 'einstellungen' && (
        <EinstellungenSeite abschnitt={route.einstellung} aufZiel={wechseln} />
      )}
    </Layout>
  );
}

export default function App() {
  return (
    <AuthProvider>
      <ProfilProvider>
        <MeldungenProvider>
          <Inhalt />
        </MeldungenProvider>
      </ProfilProvider>
    </AuthProvider>
  );
}
