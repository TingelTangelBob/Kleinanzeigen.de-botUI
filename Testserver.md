# LAN-Testserver

Stand: 2026-09-13

> **Verbindliche Projektregel:** `192.168.178.127` ist die Testumgebung für
> Anzeigen-Studio. Der Stack läuft unter `/opt/studio-wip` in Docker. Bei
> Änderungen gehören Build, Backend-Prüfungen und Browserabnahme auf diesen
> Testserver; ein fehlendes Docker auf dem lokalen Arbeitsplatz ist kein Grund,
> die Prüfung auszulassen.

Diese Datei beschreibt ausschließlich den freigegebenen Anzeigen-Studio-Teststand. Der Server
liegt im eigenen LAN beziehungsweise VPN und ist kein Produktivserver. Zugangsdaten, `.env`-
Dateien und Nutzdaten werden nicht in dieser Datei dokumentiert.

## Verbindliche Zuordnung

| Bereich | Anzeigen-Studio | Konfliktregel |
|---|---|---|
| Testserver | `192.168.178.127` (`TestDocker`) | Nur LAN/VPN; nicht als öffentlicher Server behandeln |
| SSH | TCP `22`, Nutzer `root`, Schlüssel `~/.ssh/id_kabot_test` | Schlüssel nie kopieren oder in Logs ausgeben |
| Checkout | `/opt/studio-wip` | Nur dieser Checkout gehört zum Anzeigen-Studio-Stack |
| Compose-Dateien | `docker-compose.yml` + `docker/anzeigen-studio/docker-compose.lan.yml` | Immer beide Dateien verwenden |
| Weboberfläche | `http://192.168.178.127:8080` | TCP `8080` ist für Anzeigen-Studio reserviert |
| WebUI-Port im Container | TCP `80` | Nur über die Veröffentlichung auf Host-Port `8080` verwenden |
| Backend | TCP `8000` im Compose-Netz | Nicht zusätzlich auf dem Host veröffentlichen |
| Browsersicht/noVNC | TCP `6080` im Compose-Netz | Nicht zusätzlich auf dem Host veröffentlichen; Zugriff über `/browsersicht/` |
| Daten | Docker-Volume `studio-data` | Nicht löschen oder durch ein Projektarchiv ersetzen |
| SoloOffice-Teststand | `/opt/solooffice-tor-s`, `http://192.168.178.127:8090` | Host-Port `8090` bleibt für SoloOffice reserviert |

Damit sind auf diesem Host die beiden bekannten Projektports fest vergeben:

| Host-Port | Projekt | Stack-Pfad |
|---:|---|---|
| `8080` | Anzeigen-Studio | `/opt/studio-wip` |
| `8090` | SoloOffice | `/opt/solooffice-tor-s` |

Andere Projekte dürfen keinen dieser Ports verwenden. Vor einem neuen Stack müssen sie mit
`docker ps` und `docker compose ... ps` prüfen, welche Ports bereits belegt sind, einen eigenen
Checkout und einen ausdrücklich vereinbarten freien Host-Port verwenden und ihre Zuordnung in
der gemeinsamen Serververwaltung dokumentieren. Zwei Agenten dürfen nicht gleichzeitig denselben
Checkout oder denselben Compose-Stack bauen, umschalten oder stoppen.

## Verbindlicher Ablauf für Agenten

Projektspezifische Deploy-Skripte müssen ausgabearm gestaltet sein: Vollständige
Build- und Testausgaben werden in eine Logdatei geschrieben. Im Chat erscheint
nur eine möglichst kurze Zusammenfassung mit Status, Ziel, URL und Health-
Ergebnis; bei Fehlern zusätzlich der Logpfad. Detailausgaben werden nur bei
Bedarf gelesen.

Vor jedem Upload oder Deploy wird zuerst ein kurzer Erreichbarkeitstest ausgeführt. Der Test darf
keine Zugangsdaten ausgeben:

```bash
ping -c 1 -W 2000 192.168.178.127
ssh -o BatchMode=yes -o ConnectTimeout=5 -i ~/.ssh/id_kabot_test \
  root@192.168.178.127 'true'
```

Nur wenn dieser Test erfolgreich ist, darf der Agent das projektspezifische Deploy-Skript starten.
Bei einem Fehler gilt:

1. Höchstens einmal kurz Ursache und Route prüfen (`route -n get 192.168.178.127` beziehungsweise
   die entsprechende Systemprüfung).
2. Nicht wiederholt automatisch verbinden, keinen anderen Server und keinen anderen Port raten.
3. Den Deploy als **nicht ausgeführt** melden; ein fehlgeschlagener Verbindungsversuch ist kein
   Nachweis für einen ausgelieferten Stand.
4. Falls das Projekt noch kein Skript besitzt, ein begrenztes Skript im Projekt anlegen. Es muss
   Host, Zielpfad, Compose-Dateien, Port, Ausschlüsse für `.env`/Daten und die Abschlussprüfung
   ausdrücklich enthalten.
5. Dem Nutzer den Befehl anbieten, dieses Skript selbst in seinem interaktiven Terminal
   auszuführen. Der Nutzer-Terminal kann eine andere LAN-/VPN-Berechtigung haben als die
   Agent-Umgebung.

Beispiel für die Übergabe an den Nutzer:

```text
Der Agent kann den Testserver aus seiner Umgebung nicht erreichen. Bitte führe im Projektstamm
selbst aus: ./scripts/aktualisiere_testserver.sh --pruefen
Danach bitte die Ausgabe und insbesondere den Health-Status zurückmelden.
```

Ein Agent darf nach diesem Muster ein Skript für das konkrete Projekt vorbereiten, aber nicht
behaupten, dass der Stand live ist, solange Upload, Bau, Stack-Start und HTTP-Prüfung nicht
erfolgreich nachgewiesen sind.

## Zugriff und Prüfung

```bash
ssh -i ~/.ssh/id_kabot_test root@192.168.178.127
docker ps --format 'table {{.Names}}\t{{.Ports}}\t{{.Status}}'
cd /opt/studio-wip
docker compose -f docker-compose.yml -f docker/anzeigen-studio/docker-compose.lan.yml ps
```

Die erreichbaren Prüfziele des Anzeigen-Studio-Stacks sind:

```text
Weboberfläche: http://192.168.178.127:8080/
Health:         http://192.168.178.127:8080/api/health
Browsersicht:   http://192.168.178.127:8080/browsersicht/  (Anmeldung erforderlich)
```

## Auslieferung

Vom Projektstamm aus wird der aktuelle Arbeitsstand mit dem vorhandenen Skript übertragen:

```bash
./scripts/aktualisiere_testserver.sh --pruefen
```

Das Skript überträgt per Tar-Overlay nach `/opt/studio-wip`, baut Backend und WebUI, führt die
angeforderten Prüfungen aus und startet danach genau den LAN-Stack mit den beiden oben genannten
Compose-Dateien. `.env`, `.git`, Docker-Volume, `node_modules`, `dist` und temporäre Dateien
bleiben auf dem Server. Der tatsächlich ausgelieferte Stand steht danach in:

```bash
ssh -i ~/.ssh/id_kabot_test root@192.168.178.127 'cat /opt/studio-wip/BUILD_STAND'
```

Das Overlay verwendet bewusst keinen `--delete`-Schritt. Lokal gelöschte Dateien können deshalb
auf dem Server liegen bleiben und weiter in den Bau einfließen. Bei einer Löschung muss der
Serverstand gezielt bereinigt werden; `.env` und das Daten-Volume dürfen dabei nicht entfernt
werden.

Nach jedem Bau sind mindestens diese Prüfungen auszuführen:

```bash
ssh -i ~/.ssh/id_kabot_test root@192.168.178.127 \
  'cd /opt/studio-wip && docker compose -f docker-compose.yml -f docker/anzeigen-studio/docker-compose.lan.yml ps'
curl --fail http://192.168.178.127:8080/api/health
```

Ein echter Kleinanzeigen- oder eBay-Lauf darf nur nach ausdrücklicher Freigabe des
Projektinhabers gestartet werden. Captchas und Zwei-Faktor-Abfragen werden nicht automatisiert
umgangen.
