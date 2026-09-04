#!/usr/bin/env bash
# SPDX-FileCopyrightText: © Anzeigen-Studio contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# Aktualisiert den ausdrücklich freigegebenen LAN-Testserver (AP-0.1).
#
# Der Arbeitsstand wird als Archiv übertragen. .env-Dateien und Daten bleiben
# auf dem Server. Erst wenn die Übertragung und der Docker-Bau erfolgreich
# waren, wird der LAN-Stack umgeschaltet.
#
# ZWEI EIGENSCHAFTEN, DIE MAN KENNEN MUSS:
#
# 1. KEIN --delete. Das Archiv legt sich ÜBER den Bestand, es räumt nicht auf.
#    Eine Datei, die hier gelöscht wurde, bleibt auf dem Server liegen und wird
#    weiter mitgebaut - eine entfernte Komponente kann dort also noch laufen.
#    Das ist Absicht (.env und Daten sollen überleben), aber es heißt: Wer eine
#    Datei löscht, muss sie auf dem Server von Hand nachlöschen, oder das
#    Zielverzeichnis einmal frisch aus Git klonen.
#
# 2. TAR-OVERLAY, KEIN `git pull`. Das Zielverzeichnis ist ein Git-Checkout;
#    nach dieser Auslieferung meldet `git status` dort Änderungen, die niemand
#    committet hat, und der laufende Stand ist aus dem Checkout nicht mehr
#    ablesbar. Deshalb schreibt das Skript eine Datei BUILD_STAND mit Commit,
#    Zweig und Anzahl ungespeicherter Dateien - sie ist die einzige verlässliche
#    Auskunft darüber, was dort tatsächlich läuft.

set -Eeuo pipefail

readonly SKRIPT_ORDNER="$(CDPATH= cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
readonly REPO_ORDNER="$(CDPATH= cd -- "${SKRIPT_ORDNER}/.." && pwd)"

readonly TESTSERVER_BENUTZER="${ANZEIGEN_STUDIO_TESTSERVER_BENUTZER:-root}"
readonly TESTSERVER_HOST="${ANZEIGEN_STUDIO_TESTSERVER_HOST:-192.168.178.127}"
readonly TESTSERVER_ORDNER="${ANZEIGEN_STUDIO_TESTSERVER_ORDNER:-/opt/studio-wip}"
readonly SSH_SCHLUESSEL="${ANZEIGEN_STUDIO_SSH_SCHLUESSEL:-${HOME}/.ssh/id_kabot_test}"
readonly STACK="docker compose -f docker-compose.yml -f docker/anzeigen-studio/docker-compose.lan.yml"

PRUEFE_BACKEND=0

usage() {
  cat <<'EOF'
Verwendung: scripts/aktualisiere_testserver.sh [--pruefen]

Überträgt den aktuellen Arbeitsstand auf den Anzeigen-Studio-LAN-Testserver,
baut Backend und Weboberfläche, startet den LAN-Stack neu und prüft die
Startseite. Die .env-Dateien und das Daten-Volume werden nicht übertragen.

Das Archiv legt sich über den Bestand, ohne aufzuräumen: Lokal gelöschte
Dateien bleiben auf dem Server und werden weiter mitgebaut. Was dort läuft,
steht nach der Auslieferung in der Datei BUILD_STAND - `git status` im
Zielverzeichnis ist nach einem Overlay ohne Aussagekraft.

Optionen:
  --pruefen       zusätzlich Ruff, Mypy, SPDX und alle tests_studio ausführen
  --hilfe         diese Hilfe anzeigen

Ziele lassen sich für einen anderen Testserver überschreiben:
  ANZEIGEN_STUDIO_TESTSERVER_HOST
  ANZEIGEN_STUDIO_TESTSERVER_ORDNER
  ANZEIGEN_STUDIO_SSH_SCHLUESSEL
  ANZEIGEN_STUDIO_TESTSERVER_BENUTZER
EOF
}

for argument in "$@"; do
  case "$argument" in
    --pruefen) PRUEFE_BACKEND=1 ;;
    --hilfe|-h) usage; exit 0 ;;
    *) echo "Unbekannte Option: ${argument}" >&2; usage >&2; exit 2 ;;
  esac
done

# Der Pfad wird in mehreren Remote-Shell-Befehlen verwendet. Keine
# Shell-Sonderzeichen zulassen, damit ein versehentlich gesetzter Wert nicht
# die Remote-Kommandos verändert.
if [[ ! "${TESTSERVER_ORDNER}" =~ ^/[A-Za-z0-9._/-]+$ ]]; then
  echo "Fehler: ANZEIGEN_STUDIO_TESTSERVER_ORDNER enthält ungültige Zeichen." >&2
  exit 2
fi

if [[ ! -f "${REPO_ORDNER}/docker-compose.yml" || ! -f "${REPO_ORDNER}/docker/anzeigen-studio/docker-compose.lan.yml" ]]; then
  echo "Fehler: Das Skript wurde nicht aus dem Anzeigen-Studio-Repository gestartet." >&2
  exit 1
fi
if [[ ! -r "${SSH_SCHLUESSEL}" ]]; then
  echo "Fehler: SSH-Schlüssel nicht lesbar: ${SSH_SCHLUESSEL}" >&2
  exit 1
fi

readonly ZIEL="${TESTSERVER_BENUTZER}@${TESTSERVER_HOST}"
readonly SSH_OPTIONEN=(
  -i "${SSH_SCHLUESSEL}"
  -o BatchMode=yes
  -o ConnectTimeout=10
)

echo "Übertrage Arbeitsstand nach ${ZIEL}:${TESTSERVER_ORDNER} …"
COPYFILE_DISABLE=1 tar \
  --exclude='./.git' \
  --exclude='./.env' \
  --exclude='./.env.*' \
  --exclude='./node_modules' \
  --exclude='./dist' \
  --exclude='./venv' \
  --exclude='./.venv' \
  --exclude='./data' \
  --exclude='./.temp' \
  --exclude='./__pycache__' \
  -C "${REPO_ORDNER}" -cf - . \
  | ssh "${SSH_OPTIONEN[@]}" "${ZIEL}" "mkdir -p '${TESTSERVER_ORDNER}' && tar -xf - -C '${TESTSERVER_ORDNER}'"

# Woher der ausgelieferte Stand kommt. Ohne diese Datei ist auf dem Server
# nicht mehr feststellbar, was läuft: Das Overlay hinterlässt einen
# Git-Checkout voller nicht committeter Änderungen. Gleiches Verfahren wie
# BUILD_COMMIT in SoloOffice.
echo "Schreibe BUILD_STAND …"
commit="$(git -C "${REPO_ORDNER}" rev-parse --short HEAD 2>/dev/null || echo 'unbekannt')"
zweig="$(git -C "${REPO_ORDNER}" rev-parse --abbrev-ref HEAD 2>/dev/null || echo 'unbekannt')"
betreff="$(git -C "${REPO_ORDNER}" log -1 --pretty=%s 2>/dev/null || echo '-')"
# `|| true`: Ausserhalb eines Repos liefert git nichts, und `set -e` soll die
# Auslieferung deswegen nicht abbrechen - die Datei sagt dann eben "unbekannt".
schmutzig="$(git -C "${REPO_ORDNER}" status --porcelain 2>/dev/null | wc -l | tr -d ' ' || true)"
printf '%s\n' \
  "Anzeigen-Studio - Stand dieses Verzeichnisses" \
  "" \
  "Ausgeliefert: $(date -Iseconds)" \
  "Verfahren:    tar-Overlay von einem Arbeitsplatz (kein git pull, kein --delete)" \
  "Commit:       ${commit} (${zweig}) ${betreff}" \
  "Ungespeichert: ${schmutzig:-0} Datei(en) waren zum Zeitpunkt der Auslieferung nicht committet" \
  "" \
  "Achtung: 'git status' in diesem Verzeichnis beschreibt NICHT den laufenden" \
  "Stand. Das Overlay schreibt Dateien am Git-Baum vorbei. Diese Datei ist die" \
  "verlaessliche Auskunft; sie wird bei jeder Auslieferung neu geschrieben." \
  | ssh "${SSH_OPTIONEN[@]}" "${ZIEL}" "cat > '${TESTSERVER_ORDNER}/BUILD_STAND'"

echo "Baue Backend und Weboberfläche …"
ssh "${SSH_OPTIONEN[@]}" "${ZIEL}" \
  "cd '${TESTSERVER_ORDNER}' && ${STACK} build backend webui"

if [[ "${PRUEFE_BACKEND}" -eq 1 ]]; then
  echo "Prüfe Backend im Docker-Testcontainer …"
  ssh "${SSH_OPTIONEN[@]}" "${ZIEL}" \
    "docker run --rm -u 0 --entrypoint bash -v '${TESTSERVER_ORDNER}:/work' -w /work anzeigen-studio-backend:latest -lc \"pip install --quiet ruff==0.16.4 mypy==2.3.1 pytest pytest-asyncio httpx && ruff check src/anzeigen_studio tests_studio scripts/check_spdx.py scripts/pruefe_kleinanzeigen_loeschung.py && mypy --config-file docker/anzeigen-studio/mypy.ini && python scripts/check_spdx.py && python -m pytest tests_studio -o addopts= -q\""
fi

if [[ "${PRUEFE_BACKEND}" -eq 1 ]]; then
  echo "Prüfung bestanden - starte LAN-Teststack …"
else
  echo "Starte LAN-Teststack (OHNE Prüfung - dafür --pruefen angeben) …"
fi
ssh "${SSH_OPTIONEN[@]}" "${ZIEL}" \
  "cd '${TESTSERVER_ORDNER}' && ${STACK} up -d --no-build && ${STACK} ps"

echo "Prüfe HTTP-Startseite …"
ssh "${SSH_OPTIONEN[@]}" "${ZIEL}" \
  "for versuch in \$(seq 1 30); do curl --fail --silent --show-error http://127.0.0.1:8080/ >/dev/null && exit 0; sleep 2; done; echo 'HTTP-Prüfung des LAN-Stacks fehlgeschlagen.' >&2; exit 1"

echo "Testserver aktualisiert: http://${TESTSERVER_HOST}:8080"
