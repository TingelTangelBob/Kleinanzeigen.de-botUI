# SPDX-License-Identifier: AGPL-3.0-or-later
#
# Frontend-Image des Anzeigen-Studio-Forks. Neue Datei, nicht im Upstream.
# Zweistufig: bauen mit Node, ausliefern mit nginx.

FROM node:22-alpine AS build
WORKDIR /build

# Erst die Manifeste, dann der Quelltext - so bleibt die Abhaengigkeitsschicht
# im Cache, solange sich package.json nicht aendert.
COPY webui/package.json webui/package-lock.json* ./
RUN npm ci || npm install

COPY webui/ ./
# Lint, Typpruefung und Tests laufen im Build mit. Der Frontend-Container
# liefert die gebaute Fassung aus; damit ist der Docker-Build die Stelle, an
# der alles drei tatsaechlich geprueft wird (siehe CONTEXT.md). Ein Bau, der
# durchlaeuft, ist damit zugleich der Nachweis, dass die Tests gruen sind.
RUN npm run lint && npm run typecheck && npm run test && npm run build

FROM nginx:alpine
COPY --from=build /build/dist /usr/share/nginx/html
COPY docker/anzeigen-studio/nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
