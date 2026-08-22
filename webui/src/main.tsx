// SPDX-License-Identifier: AGPL-3.0-or-later

import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import App from './App.tsx';
import './index.css';

const container = document.getElementById('root');
if (!container) throw new Error('Wurzelelement #root nicht gefunden');

createRoot(container).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
