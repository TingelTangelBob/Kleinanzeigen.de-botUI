# SPDX-FileCopyrightText: © Anzeigen-Studio contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# Backend-Abbild des Anzeigen-Studio-Forks. Neue Datei, nicht im Upstream.
#
# Enthaelt Backend, Bot und Chromium unter Xvfb.
#
# Frueher war ein getrennter Browser-Dienst vorgesehen. Revidiert am
# 2026-08-23: Die Trennung sollte verhindern, dass ein Browserabsturz die
# Schnittstelle mitreisst - genau das leistet aber bereits der Unterprozess aus
# AP-1.5. Der zweite Container haette einen Fernsteuerungspfad, ein
# zusaetzliches Netz und einen Umweg um binary_location gekostet, ohne etwas
# hinzuzufuegen.

FROM python:3.12-slim-bookworm

# Zeitzone ist nicht kosmetisch: republication_interval und das
# Acht-Tage-Verlaengerungsfenster des Bots sind datumsbasiert.
ENV TZ=Europe/Berlin \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    DISPLAY_NUM=99 \
    DISPLAY=:99

RUN apt-get update \
 && apt-get install -y --no-install-recommends \
      ca-certificates tzdata \
      chromium \
      xvfb x11-utils \
      x11vnc novnc websockify \
      fonts-liberation fonts-dejavu-core \
      procps \
 && rm -rf /var/lib/apt/lists/*

# Nicht als root. Feste UID/GID, damit die Rechte im Volume vorhersehbar sind.
# Chromium verweigert den Dienst als root - der Bot hat dafuer sogar eigene
# Fehlertexte.
RUN groupadd --gid 10001 studio \
 && useradd --uid 10001 --gid studio --create-home --shell /bin/sh studio

WORKDIR /app

# Backend-Abhaengigkeiten aus einer eigenen Datei - nicht aus pyproject.toml.
# Begruendung in requirements.txt: pdm.lock wird upstream automatisiert neu
# erzeugt, und generierte Dateien sind der teuerste Konflikttyp.
COPY docker/anzeigen-studio/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt && rm /tmp/requirements.txt

# Laufzeitabhaengigkeiten des Bots.
#
# requests steht bewusst hier: der Upstream importiert es in update_checker.py
# zur Laufzeit, deklariert aber nur types-requests. Ohne diese Zeile bricht der
# Import ab. Ein Pull Request dazu ist vorbereitet (AP-0.10); sobald er drin
# ist, kann die Zeile weg.
RUN pip install --no-cache-dir \
      certifi colorama "jaraco.text" "nodriver==0.50.3" "platformdirs>=2.1.0" \
      "pydantic>=2.11.0" "ruamel.yaml" psutil wcmatch "sanitize-filename>=1.2.0" \
      requests rich typer

COPY --chown=studio:studio src/ /app/src/
COPY --chown=studio:studio schemas/ /app/schemas/
COPY --chown=studio:studio docker/anzeigen-studio/entrypoint.sh /usr/local/bin/entrypoint.sh
RUN chmod +x /usr/local/bin/entrypoint.sh

# Das Datenverzeichnis muss dem Dienstbenutzer gehoeren, BEVOR das benannte
# Volume das erste Mal eingehaengt wird - Docker uebernimmt beim Anlegen die
# Eigentumsrechte des Pfads aus dem Abbild. Ohne diesen Schritt gehoert /data
# root, und der Start scheitert mit "unable to open database file".
RUN mkdir -p /data && chown studio:studio /data
VOLUME ["/data"]

ENV PYTHONPATH=/app/src \
    ANZEIGEN_STUDIO_DATA_DIR=/data \
    ANZEIGEN_STUDIO_CHROMIUM=/usr/bin/chromium

USER studio
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/api/health',timeout=3).status==200 else 1)"

ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
CMD ["uvicorn", "anzeigen_studio.main:app", "--host", "0.0.0.0", "--port", "8000"]
