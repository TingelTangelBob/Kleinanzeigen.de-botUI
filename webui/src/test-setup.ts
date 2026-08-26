// SPDX-FileCopyrightText: © Anzeigen-Studio contributors
// SPDX-License-Identifier: AGPL-3.0-or-later
//
// Aufräumen zwischen den Tests.
//
// Testing Library hängt sein Auto-Cleanup nur ein, wenn Vitest mit `globals`
// läuft. Das tut es hier nicht - die Testdateien importieren `describe` und
// `it` ausdrücklich, damit keine zusätzliche Typ-Einbindung nötig ist. Ohne
// diese Datei bliebe das DOM zwischen den Tests stehen, und Abfragen fänden
// Treffer aus dem vorigen Test.

import { afterEach } from 'vitest';
import { cleanup } from '@testing-library/react';

afterEach(cleanup);
