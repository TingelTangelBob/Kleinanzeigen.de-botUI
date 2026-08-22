// SPDX-License-Identifier: AGPL-3.0-or-later
//
// Geruest aus AP-0.6. Zweck ist ausschliesslich, die Werkzeugkette nachzuweisen:
// Vite baut, TypeScript prueft, Tailwind greift, das Backend antwortet.
//
// Die eigentliche App-Schale kommt in AP-2.1 aus SoloOffice. Bewusst steht hier
// keine nachgebaute Seitenleiste - das waere Wegwerfarbeit und wuerde Fortschritt
// vortaeuschen, den es nicht gibt.

import { useEffect, useState } from 'react';

interface Health {
  status: string;
  version: string;
  missing_config: string[];
}

export default function App() {
  const [health, setHealth] = useState<Health | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetch('/api/health')
      .then(response => {
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        return response.json() as Promise<Health>;
      })
      .then(setHealth)
      .catch((cause: unknown) =>
        setError(cause instanceof Error ? cause.message : 'Unbekannter Fehler'),
      );
  }, []);

  return (
    <main className="mx-auto max-w-xl p-8">
      <h1 className="text-xl font-semibold text-gray-900">Anzeigen-Studio</h1>
      <p className="mt-2 text-sm text-gray-600">
        Geruest. Die Oberflaeche entsteht in Phase 2.
      </p>

      <section className="mt-6 rounded border border-gray-200 p-4">
        <h2 className="text-sm font-medium text-gray-900">Backend</h2>
        {error && <p className="mt-1 text-sm text-red-700">Nicht erreichbar: {error}</p>}
        {!error && !health && <p className="mt-1 text-sm text-gray-500">Wird geprueft …</p>}
        {health && (
          <>
            <p className="mt-1 text-sm text-gray-700">
              Erreichbar, Version {health.version}
            </p>
            {health.missing_config.length > 0 && (
              <p className="mt-1 text-sm text-amber-700">
                Fehlende Konfiguration: {health.missing_config.join(', ')}
              </p>
            )}
          </>
        )}
      </section>
    </main>
  );
}
