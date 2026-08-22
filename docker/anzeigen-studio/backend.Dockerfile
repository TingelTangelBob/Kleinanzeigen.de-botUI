# SPDX-License-Identifier: AGPL-3.0-or-later
#
# Backend-Image des Anzeigen-Studio-Forks. Neue Datei, nicht im Upstream.
#
# Enthaelt bewusst KEIN Chromium: der Browser laeuft im eigenen Dienst
# (docker/anzeigen-studio/browser.Dockerfile, AP-1.1), damit ein Browserabsturz
# nicht die Schnittstelle mitreisst und beide getrennt skaliert werden koennen.

FROM python:3.12-slim-bookworm

# Zeitzone ist nicht kosmetisch: Wiederveroeffentlichungsintervall und das
# Acht-Tage-Verlaengerungsfenster des Bots sind datumsbasiert.
ENV TZ=Europe/Berlin \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

RUN apt-get update \
 && apt-get install -y --no-install-recommends tzdata ca-certificates \
 && rm -rf /var/lib/apt/lists/*

# Nicht als root. Feste UID/GID, damit die Rechte im Volume vorhersehbar sind.
RUN groupadd --gid 10001 studio \
 && useradd --uid 10001 --gid studio --create-home --shell /usr/sbin/nologin studio

WORKDIR /app

# TODO(AP-1.2): Abhaengigkeiten ueber pdm aus pyproject.toml installieren,
# sobald die Backend-Pakete tatsaechlich Code enthalten. Bis dahin genuegt der
# minimale Satz, um das Geruest zu starten und die Kette zu pruefen.
RUN pip install --no-cache-dir "fastapi>=0.115" "uvicorn[standard]>=0.32"

COPY --chown=studio:studio src/ /app/src/
COPY --chown=studio:studio schemas/ /app/schemas/

ENV PYTHONPATH=/app/src \
    ANZEIGEN_STUDIO_DATA_DIR=/data

USER studio
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/api/health',timeout=3).status==200 else 1)"

CMD ["uvicorn", "anzeigen_studio.main:app", "--host", "0.0.0.0", "--port", "8000"]
