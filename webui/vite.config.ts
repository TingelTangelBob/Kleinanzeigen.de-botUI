// SPDX-License-Identifier: AGPL-3.0-or-later
//
// Uebernommen aus SoloOffice (AGPL-3.0-or-later), 2026-08-22.
// Ergaenzt um den Proxy auf das Backend, damit Oberflaeche und /api im
// Entwicklungsbetrieb unter demselben Ursprung liegen - wie spaeter in
// Produktion hinter dem Reverse Proxy.

import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  optimizeDeps: {
    exclude: ['lucide-react'],
  },
  server: {
    host: true, // im Container erreichbar, nicht nur auf localhost
    port: 5173,
    proxy: {
      '/api': {
        target: process.env.VITE_API_TARGET ?? 'http://backend:8000',
        changeOrigin: true,
      },
    },
  },
});
