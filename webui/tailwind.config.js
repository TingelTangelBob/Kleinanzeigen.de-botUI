/** @type {import('tailwindcss').Config} */
// Uebernommen aus SoloOffice (AGPL-3.0-or-later), 2026-08-22.
export default {
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  theme: {
    extend: {
      screens: {
        // Tablet ist eine eigene Stufe, kein vergroessertes Mobile-Layout.
        tablet: '768px',
      },
    },
  },
  plugins: [],
};
