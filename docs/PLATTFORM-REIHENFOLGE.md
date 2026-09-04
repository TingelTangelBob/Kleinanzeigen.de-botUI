# SPDX-FileCopyrightText: © Anzeigen-Studio contributors
# SPDX-License-Identifier: AGPL-3.0-or-later

# Plattform-Reihenfolge und günstiger Abgleich

Die Reihenfolge eigener Anzeigen kommt aus der authentifizierten,
schreibgeschützten Schnittstelle des Bots:

```text
/m-meine-anzeigen-verwalten.json?sort=DEFAULT&pageNum=N
```

Der neue Bot-Befehl `sync-order` fragt diese JSON-Seiten ab und schreibt neben
`config.yaml` vorübergehend `.anzeigen-studio-plattform-reihenfolge.json`.
Darin stehen nur numerische Anzeigen-IDs, ihre Reihenfolge und der
Prüfzeitpunkt. Nach einem erfolgreichen Lauf übernimmt das Backend die Daten
in SQLite und löscht den Sidecar. Bei einer unvollständigen Antwort bleibt der
letzte gültige Stand erhalten.

Die Oberfläche sortiert eigene Anzeigen nach diesem Rang. Entwürfe, fremde
Anzeigen und Anzeigen, die noch nicht in der letzten Plattformantwort standen,
folgen danach in der bisherigen lokalen Fallback-Reihenfolge.

## Taktung

Wenn der Abgleich unter Einstellungen ausdrücklich eingeschaltet ist, läuft
die kleine Reihenfolgeprüfung höchstens einmal pro Stunde. Ein täglicher
Vollabgleich bleibt zusätzlich bestehen. Nach einem erfolgreichen
`publish`, `update`, `delete` oder `extend` wird ebenfalls ein
`sync-order`-Folgelauf in dieselbe Warteschlange gestellt. Profilsperre,
Zeitfenster und Abbruch gelten unverändert.

Die Abfrage erkennt zuverlässig Änderungen an Reihenfolge, Anzahl und
Plattformstatus der eigenen Einträge. Sie beweist aber nicht, dass sich der
Text einer Anzeige geändert hat, wenn Kleinanzeigen sie dabei nicht neu
einreiht. Dafür bleibt ein vollständiger Download der Anzeige erforderlich.
