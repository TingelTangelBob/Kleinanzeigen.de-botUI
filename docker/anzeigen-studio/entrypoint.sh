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

# Xvfb mitnehmen, wenn das Backend endet.
trap 'kill "${XVFB_PID}" 2>/dev/null || true' EXIT INT TERM

exec "$@"
