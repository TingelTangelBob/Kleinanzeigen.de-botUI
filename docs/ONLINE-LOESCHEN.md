# SPDX-FileCopyrightText: © Anzeigen-Studio contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
#

# Anzeige auf kleinanzeigen.de löschen

Der normale Button „Löschen“ entfernt die lokale Anzeige. Im anschließenden
Dialog kann bei einer eigenen Anzeige mit vorhandener Nummer zusätzlich die
Checkbox „Zusätzlich auf kleinanzeigen.de löschen“ gewählt werden. Dann wird
ein gezielter `delete`-Lauf für genau diese Anzeigennummer eingereiht und die
lokale Datei erst nach einem erfolgreichen Lauf entfernt. Ohne Checkbox bleibt
die Plattform unberührt und die lokale Datei wird sofort entfernt.

Während der Plattform-Lauf wartet, bleibt die lokale Kopie absichtlich liegen.
Damit kann der Bot die Anzeige sicher lesen; bei einem Fehler bleibt sie für
die anschließende Prüfung erhalten. Nach einem erfolgreichen Lauf meldet das
Jobprotokoll, dass auch die lokale Kopie entfernt wurde, wenn die Checkbox
gewählt war. Ein Neustart des Backends verliert diese Zusage nicht, weil der
Nachschritt am Job gespeichert wird. Beim normalen Löschen ohne Checkbox bleibt
die Plattform unberührt und die lokale Datei wird sofort entfernt. Ein
Plattform-Delete ohne optionale lokale Folgeaktion (API-Weg) lässt die lokale
Datei dagegen als `active: false` erhalten.

Vor dem Absenden weist die Oberfläche auf den lokalen und – falls gewählt –
den Plattform-Schritt hin. Der Lauf löscht ausschließlich diese Nummer; eine
Suche nach ähnlichen Titeln ist an dieser Stelle nicht möglich. Bei
ungespeicherten Eingaben bleibt die Checkbox gesperrt, bis der gespeicherte
Stand eindeutig ist.

## Öffentliche Gegenprobe

### Was tatsächlich trägt: die Anbieterliste

Die belastbare Gegenprobe ist die öffentliche Anzeigenliste des Anbieters. Steht
die Nummer nicht mehr darin, ist die Anzeige weg:

```text
https://www.kleinanzeigen.de/s-bestandsliste.html?userId=<Anbieternummer>
```

Das Skript kann das seit dem 2026-09-04 selbst:

```bash
python3 scripts/pruefe_kleinanzeigen_loeschung.py --anbieter 55557058 --nummer 3503227963
```

Die Anbieternummer steht auf jeder eigenen Anzeigenseite im Link „Alle Anzeigen
dieses Anbieters". Auch das ist nur ein `GET` ohne Anmeldung.

Rückgabecodes in dieser Betriebsart:

- `0`: Die Nummer steht nicht mehr in der Liste — **gelöscht**.
- `1`: Die Nummer steht noch in der Liste — der Löschlauf hat nicht gewirkt.
- `2`: Kein Urteil möglich: Captcha, geändertes Markup, gar keine Nummer
  gefunden, oder die Liste hat mehrere Seiten und die Anzeige könnte auf einer
  weiteren stehen.

### Warum die Detailseite nicht reicht (Befund 2026-09-04)

`scripts/pruefe_kleinanzeigen_loeschung.py` ruft die Detailseite der Anzeige auf.
**Diese Prüfung trägt bei kleinanzeigen.de nicht:** Die Detailseite einer
gelöschten Anzeige wird weiterhin mit `HTTP 200` und vollständigem Inhalt
ausgeliefert — Titel, Beschreibung und Anzeigen-ID inklusive. Belegt an zwei
Anzeigen, die nachweislich gelöscht sind (3503227963 direkt nach dem Löschlauf,
3461223245 seit Tagen); beide melden `1` – „noch erreichbar".

Der Fehler geht in die ungefährliche Richtung: Das Skript behauptet **nie**
fälschlich „gelöscht", es schlägt falschen Alarm.

**Das Skript zieht daraus seit dem 2026-09-04 die Konsequenz:** Eine erreichbare
Detailseite gilt nicht mehr als „noch online", sondern als `2` – unbekannt, mit
Verweis auf die Anbieterliste. Der frühere `1` an dieser Stelle war ein
Fehlalarm nach jedem erfolgreichen Löschlauf.

```bash
python3 scripts/pruefe_kleinanzeigen_loeschung.py --url 'https://www.kleinanzeigen.de/s-anzeige/titel/3310837392'
```

Rückgabecodes in dieser Betriebsart:

- `0`: HTTP 404/410 oder ein ausdrücklicher Löschhinweis auf der Seite.
  Aussagekräftig.
- `2`: Alles andere – **auch eine vollständig geladene Anzeigenseite**.

Bei Rückgabecode `2` darf der Status nicht als gelöscht verbucht werden. Dann
die Anbieterliste prüfen oder im Browser nachsehen.

### Was das Studio selbst zeigt

Bei einem Plattform-Delete ohne optionale lokale Folgeaktion steht die Anzeige
lokal nach einem erfolgreichen Löschlauf auf `active: false` und trägt in der
Liste das Kennzeichen „Gelöscht". Beim kombinierten Vorgang ist die lokale Datei
danach entfernt. In beiden Fällen protokolliert der Lauf die Zeile `-> ERFOLG:
Anzeige [...] (ID: ...) gelöscht`; sie ist der direkteste Beleg und steht im
Protokoll des Laufs.
