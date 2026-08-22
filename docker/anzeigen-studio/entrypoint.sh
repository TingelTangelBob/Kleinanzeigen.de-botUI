#!/bin/sh
# SPDX-FileCopyrightText: © Anzeigen-Studio contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# Startet den X-Server und danach das Backend.
#
# Xvfb ist Pflicht, nicht Wahl: Der Bot setzt headless hartkodiert auf False
# (web_scraping_mixin.py:221). Ohne Anzeige startet Chromium nicht.
#
# Angenehmer Nebeneffekt: Weil ohnehin ein X-Server laeuft, ist der Weg zur
# Uebernahme durch den Menschen (AP-1.8, VNC/noVNC auf denselben Bildschirm)
# kurz.

set -eu

DISPLAY_NUM="${DISPLAY_NUM:-99}"
SCREEN="${XVFB_SCREEN:-1280x1024x24}"
export DISPLAY=":${DISPLAY_NUM}"

# Ein alter Sperrhinweis ueberlebt einen unsauberen Abbruch und verhindert
# sonst jeden weiteren Start.
rm -f "/tmp/.X${DISPLAY_NUM}-lock"

echo "Starte Xvfb auf ${DISPLAY} (${SCREEN})"
Xvfb "${DISPLAY}" -screen 0 "${SCREEN}" -nolisten tcp -dpi 96 &
XVFB_PID=$!

# Auf den X-Server warten, statt blind weiterzulaufen: Chromium scheitert
# sonst mit einer irrefuehrenden Meldung.
i=0
until xdpyinfo -display "${DISPLAY}" >/dev/null 2>&1; do
    i=$((i + 1))
    if [ "$i" -gt 50 ]; then
        echo "Xvfb ist nach 10 Sekunden nicht erreichbar - Abbruch." >&2
        exit 1
    fi
    sleep 0.2
done
echo "Xvfb bereit."

# --- Browsersicht fuer die Uebernahme durch den Menschen (AP-1.8) ----------
#
# x11vnc spiegelt denselben Bildschirm, auf dem Chromium laeuft; websockify
# stellt noVNC davor, damit die Oberflaeche ihn im Browser einbetten kann.
#
# SICHERHEIT, genau:
#   * x11vnc bindet an 127.0.0.1 - nur websockify im selben Container kommt dran.
#   * websockify bindet an alle Schnittstellen des Containers, damit nginx aus
#     dem webui-Container es erreichen kann. Der Port ist NICHT nach aussen
#     veroeffentlicht; im Docker-Netz liegen nur backend und webui.
#   * nginx laesst nur durch, wer eine gueltige Sitzung hat (auth_request gegen
#     /api/auth/pruefen). Ein offener VNC-Zugang waere eine Fernsteuerung des
#     Rechners - deshalb kein Port nach aussen und kein Zugang ohne Anmeldung.
VNC_PORT="${VNC_PORT:-5900}"
NOVNC_PORT="${NOVNC_PORT:-6080}"

echo "Starte x11vnc auf 127.0.0.1:${VNC_PORT}"
x11vnc -display "${DISPLAY}" -localhost -rfbport "${VNC_PORT}" \
       -shared -forever -nopw -quiet -noxdamage >/dev/null 2>&1 &
VNC_PID=$!

echo "Starte noVNC auf :${NOVNC_PORT} (nur im Docker-Netz erreichbar)"
websockify --web=/usr/share/novnc "0.0.0.0:${NOVNC_PORT}" \
           "127.0.0.1:${VNC_PORT}" >/dev/null 2>&1 &
NOVNC_PID=$!

# Alle Hilfsdienste mitnehmen, wenn das Backend endet.
trap 'kill "${XVFB_PID}" "${VNC_PID}" "${NOVNC_PID}" 2>/dev/null || true' EXIT INT TERM

exec "$@"
