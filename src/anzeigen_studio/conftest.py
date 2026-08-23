# SPDX-FileCopyrightText: © Anzeigen-Studio contributors
# SPDX-ArtifactOfProjectHomePage: https://github.com/TingelTangelBob/Kleinanzeigen.de-botUI/
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# Haelt die pytest-Sammlung des Upstreams aus diesem Verzeichnis heraus.
#
# Der Upstream sammelt mit `testpaths = ["src", "tests"]` und
# `--doctest-modules`, importiert dabei also JEDES Modul unter src/. Unsere
# Module brauchen fastapi, cryptography und ruamel.yaml - die in der
# Upstream-CI nicht installiert sind. Ergebnis waren 13 Importfehler und eine
# dauerhaft rote Upstream-CI.
#
# Diese Datei loest das, ohne eine einzige Zeile am Upstream zu aendern: Sie
# liegt in unserem eigenen Verzeichnis. Die Tests des Forks liegen in
# tests_studio/ und laufen ueber die eigene CI mit installierten Paketen.

collect_ignore_glob = ["*"]
