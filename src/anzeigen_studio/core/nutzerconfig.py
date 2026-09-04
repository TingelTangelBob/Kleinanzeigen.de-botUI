# SPDX-FileCopyrightText: © Anzeigen-Studio contributors
# SPDX-ArtifactOfProjectHomePage: https://github.com/TingelTangelBob/Kleinanzeigen.de-botUI/
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# Nutzereditierbare Bot-Konfiguration (AP-2.9).
#
# Getrennt von config.yaml: Die Warteschlange schreibt config.yaml vor jedem
# Lauf neu (botbridge.konfiguration.schreiben) und legt die feste Basis UEBER
# diese Werte. Hier liegt nur, was die Oberflaeche gesetzt hat.
#
# Zwei Filter greifen, bevor etwas gespeichert wird:
# 1. Felder aus AP-1.11 (browser.binary_location/extensions/arguments, ad_files)
#    und Login-Klartext werden ABGEWIESEN, nicht still verworfen.
# 2. Alles, was nicht im Upstream-Schema steht oder keiner bekannten Gruppe
#    angehoert, wird abgewiesen - neue Upstream-Felder rutschen nicht durch.

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any, Final

from ruamel.yaml import YAML

from anzeigen_studio.botbridge.konfiguration import GESPERRTE_FELDER, gesperrte_entfernen
from anzeigen_studio.core.errors import FachlicherFehler

#: Dateiname im Profilverzeichnis. Bewusst nicht config.yaml - die gehoert dem Bot.
DATEINAME: Final = "nutzer.yaml"

#: Felder, die weder in der Oberflaeche erscheinen noch per API setzbar sind.
#: Die vier aus AP-1.11 plus Login-Klartext plus Pfadfelder, die das Studio
#: selbst verwaltet. Ein automatisch aus dem Schema gebautes Formular wuerde
#: sie sonst von selbst anbieten.
VERBOTENE_PFADE: Final[frozenset[str]] = frozenset({
    "ad_files",
    "browser.binary_location",
    "browser.extensions",
    "browser.arguments",
    "browser.user_data_dir",
    "browser.profile_name",
    "login",
    "login.username",
    "login.password",
    "ad_defaults.description",
    "diagnostics.output_dir",
    "categories",
    # In der Basis fest verdrahtet - speichern wuerde eine Wirkung vortaeuschen.
    "browser.use_private_window",
    "update_check.enabled",
})

#: Reihenfolge und Darstellung der Formulargruppen. Nur diese Wurzeln werden
#: gespeichert - ein neues Top-Level-Feld im Schema erscheint erst, wenn es
#: hier eine Gruppe bekommt.
GRUPPEN: Final[tuple[dict[str, Any], ...]] = (
    {
        "id": "ad_defaults",
        "wurzel": "ad_defaults",
        "titel": "Standardwerte für Anzeigen",
        "beschreibung": "Gelten für neue Anzeigen, soweit die Anzeigendatei nichts anderes setzt.",
        "eingeklappt": False,
    },
    {
        "id": "publishing",
        "wurzel": "publishing",
        "titel": "Veröffentlichung",
        "beschreibung": "Was der Bot beim Einstellen und erneuten Veröffentlichen tut.",
        "eingeklappt": False,
    },
    {
        "id": "deleting",
        "wurzel": "deleting",
        "titel": "Nach dem Löschen",
        "beschreibung": "Was mit der lokalen Anzeigendatei passiert, nachdem sie auf der Plattform gelöscht wurde.",
        "eingeklappt": True,
    },
    {
        "id": "download",
        "wurzel": "download",
        "titel": "Download",
        "beschreibung": "Wie heruntergeladene Anzeigen auf der Platte landen.",
        "eingeklappt": False,
    },
    {
        "id": "browser",
        "wurzel": "browser",
        "titel": "Browser",
        "beschreibung": (
            "Chromium-Pfad, Erweiterungen und freie Schalter setzt das Studio selbst – "
            "sie sind ein Codeausführungspfad und hier nicht veränderbar. "
            "Privates Fenster bleibt aus, damit die Anmeldung im Profilordner überlebt."
        ),
        "eingeklappt": False,
    },
    {
        "id": "timeouts",
        "wurzel": "timeouts",
        "titel": "Zeitgrenzen",
        "beschreibung": "Wartezeiten des Bots in Sekunden. Die Vorgabe reicht in der Regel.",
        "eingeklappt": True,
    },
    {
        "id": "humanization",
        "wurzel": "humanization",
        "titel": "Humanisierung",
        "beschreibung": "Tippverzögerung, Pausen zwischen Aktionen und Fenstergröße.",
        "eingeklappt": True,
    },
    {
        "id": "diagnostics",
        "wurzel": "diagnostics",
        "titel": "Diagnose",
        "beschreibung": (
            "Standardmäßig aus. Eingeschaltet enthalten die Artefakte Bildschirmfotos "
            "und das vollständige DOM einer angemeldeten Sitzung – mit Klarname, "
            "Adresse und Telefonnummer."
        ),
        "eingeklappt": True,
        "warnung": (
            "Diagnoseartefakte enthalten Bildschirmfotos und das vollständige DOM "
            "einer angemeldeten Sitzung: Klarname, Adresse, Telefonnummer und "
            "sitzungsbezogene Token. Nur einschalten, wenn du einen Fehler suchst, "
            "und die Dateien danach löschen."
        ),
    },
    {
        "id": "captcha",
        "wurzel": "captcha",
        "titel": "Captcha",
        "beschreibung": "Wie der Bot reagiert, wenn die Plattform ein Captcha zeigt.",
        "eingeklappt": False,
    },
    {
        "id": "update_check",
        "wurzel": "update_check",
        "titel": "Update-Prüfung",
        "beschreibung": (
            "Die Prüfung des Bots auf neue Fassungen ist serverseitig aus: "
            "Aktualisierungen laufen über das Container-Abbild, nicht zur Laufzeit. "
            "Kanal und Abstand werden deshalb nicht wirksam."
        ),
        "eingeklappt": True,
    },
)

BEZEICHNUNGEN: Final[dict[str, str]] = {
    "ad_defaults.active": "Aktiv",
    "ad_defaults.type": "Art",
    "ad_defaults.description_prefix": "Text vor der Beschreibung",
    "ad_defaults.description_suffix": "Text nach der Beschreibung",
    "ad_defaults.price_type": "Preistyp",
    "ad_defaults.shipping_type": "Versandart",
    "ad_defaults.sell_directly": "Direkt kaufen",
    "ad_defaults.republication_interval": "Tage bis zur Neueinstellung",
    "ad_defaults.auto_price_reduction.enabled": "Preis automatisch senken",
    "ad_defaults.auto_price_reduction.strategy": "Strategie",
    "ad_defaults.auto_price_reduction.amount": "Betrag oder Prozent",
    "ad_defaults.auto_price_reduction.min_price": "Mindestpreis",
    "ad_defaults.auto_price_reduction.delay_reposts": "Neueinstellungen abwarten",
    "ad_defaults.auto_price_reduction.delay_days": "Tage abwarten",
    "ad_defaults.auto_price_reduction.on_update": "Auch beim Aktualisieren",
    "ad_defaults.contact.name": "Kontaktname",
    "ad_defaults.contact.street": "Straße",
    "ad_defaults.contact.zipcode": "Postleitzahl",
    "ad_defaults.contact.location": "Ort",
    "ad_defaults.contact.phone": "Telefon",
    "publishing.delete_old_ads": "Alte Anzeige löschen",
    "publishing.delete_old_ads_by_title": "Alte Anzeige am Titel erkennen",
    "publishing.local_path_renaming.mode": "Lokale Pfade umbenennen",
    "deleting.after_delete": "Lokale Datei nach dem Löschen",
    "download.dir": "Download-Ordner",
    "download.include_all_matching_shipping_options": "Alle passenden Versandoptionen",
    "download.excluded_shipping_options": "Ausgeschlossene Versandoptionen",
    "download.folder_name_max_length": "Maximale Ordnernamenslänge",
    "download.folder_name_template": "Ordnernamen-Vorlage",
    "download.ad_file_name_template": "Dateinamen-Vorlage",
    "download.rename_existing_folders": "Bestehende Ordner umbenennen",
    "download.preserve_local_settings": "Lokale Einstellungen behalten",
    "browser.suppress_unsupported_flag_warning": "Warnung zu unbekannten Schaltern unterdrücken",
    "timeouts.multiplier": "Faktor für alle Zeiten",
    "timeouts.default": "Standard (DOM)",
    "timeouts.page_load": "Seite laden",
    "timeouts.captcha_detection": "Captcha erkennen",
    "timeouts.sms_verification": "SMS-Bestätigung",
    "timeouts.email_verification": "E-Mail-Bestätigung",
    "timeouts.login_detection": "Anmeldung erkennen",
    "timeouts.publishing_result": "Veröffentlichungsergebnis",
    "timeouts.publishing_confirmation": "Veröffentlichungsbestätigung",
    "timeouts.image_upload": "Bild-Upload",
    "timeouts.pagination_initial": "Erste Seite der Liste",
    "timeouts.pagination_follow_up": "Weitere Seiten der Liste",
    "timeouts.quick_dom": "Kurze DOM-Prüfung",
    "timeouts.update_check": "Update-Prüfung",
    "timeouts.chrome_remote_probe": "Chrome-Sonde",
    "timeouts.chrome_remote_debugging": "Chrome-Fernsteuerung",
    "timeouts.chrome_binary_detection": "Chrome-Binärdatei erkennen",
    "timeouts.retry_enabled": "Wiederholen bei Fehlern",
    "timeouts.retry_max_attempts": "Höchstzahl Versuche",
    "timeouts.retry_backoff_factor": "Wartefaktor zwischen Versuchen",
    "humanization.enabled": "Zusätzliche Humanisierung",
    "humanization.typing_jitter": "Tippverzögerung",
    "humanization.typing_delay_min_ms": "Tippdelay mindestens (ms)",
    "humanization.typing_delay_max_ms": "Tippdelay höchstens (ms)",
    "humanization.action_delay_min_ms": "Aktionspause mindestens (ms)",
    "humanization.action_delay_max_ms": "Aktionspause höchstens (ms)",
    "humanization.randomize_viewport": "Fenstergröße würfeln",
    "humanization.viewport_sizes": "Erlaubte Fenstergrößen",
    "diagnostics.capture_on.login_detection": "Bei fehlender Anmeldungserkennung",
    "diagnostics.capture_on.publish": "Bei fehlgeschlagener Veröffentlichung",
    "diagnostics.capture_log_copy": "Komplettes Protokoll kopieren",
    "diagnostics.pause_on_login_detection_failure": "Nach fehlender Anmeldung anhalten",
    "diagnostics.timing_collection": "Zeitmessung sammeln",
    "captcha.auto_restart": "Nach Captcha automatisch neu starten",
    "captcha.restart_delay": "Wartezeit vor dem Neustart",
    "update_check.enabled": "Prüfung einschalten",
    "update_check.channel": "Kanal",
    "update_check.interval": "Abstand",
}

ENUM_LABELS: Final[dict[str, str]] = {
    "OFFER": "Angebot",
    "WANTED": "Gesuch",
    "FIXED": "Festpreis",
    "NEGOTIABLE": "Verhandlungsbasis",
    "GIVE_AWAY": "Zu verschenken",
    "NOT_APPLICABLE": "Nicht zutreffend",
    "PICKUP": "Nur Abholung",
    "SHIPPING": "Versand möglich",
    "PERCENTAGE": "Prozent",
    "BEFORE_PUBLISH": "Vor dem Einstellen",
    "AFTER_PUBLISH": "Nach dem Einstellen",
    "NEVER": "Nie",
    "NONE": "Unverändert lassen",
    "RESET": "Zurücksetzen",
    "DISABLE": "Deaktivieren",
    "OFF": "Aus",
    "TEMPLATE_MATCH": "An der Vorlage",
    "latest": "Stabil",
    "preview": "Vorschau",
}

# Felder, die als mehrzeiliger Text sinnvoller sind als als eine Zeile.
_LANGTEXT: Final[frozenset[str]] = frozenset({
    "ad_defaults.description_prefix",
    "ad_defaults.description_suffix",
})


def _schema_pfad() -> Path:
    """schemas/config.schema.json - im Abbild unter /app, lokal im Repostamm."""
    hier = Path(__file__).resolve()
    # core/nutzerconfig.py -> anzeigen_studio -> src -> Stamm
    stamm = hier.parents[3] / "schemas" / "config.schema.json"
    if stamm.is_file():
        return stamm
    fallback = Path("/app/schemas/config.schema.json")
    if fallback.is_file():
        return fallback
    raise FachlicherFehler("Das Konfigurationsschema fehlt.", status = 500)


@lru_cache(maxsize = 1)
def schema_laden() -> dict[str, Any]:
    with _schema_pfad().open(encoding = "utf-8") as datei:
        geladen: dict[str, Any] = json.load(datei)
    return geladen


def _aufloesen(schema: dict[str, Any], knoten: dict[str, Any]) -> dict[str, Any]:
    ref = knoten.get("$ref")
    if not isinstance(ref, str) or not ref.startswith("#/$defs/"):
        return knoten
    name = ref.rsplit("/", 1)[-1]
    defs = schema.get("$defs")
    if not isinstance(defs, dict) or name not in defs:
        return knoten
    ziel = defs[name]
    if not isinstance(ziel, dict):
        return knoten
    # Beschreibung und Titel der Referenzstelle gewinnen, der Rest kommt aus $defs.
    vermischt = dict(ziel)
    for schluessel in ("description", "title", "default"):
        if schluessel in knoten:
            vermischt[schluessel] = knoten[schluessel]
    return vermischt


def _null_erlaubt(knoten: dict[str, Any]) -> bool:
    if knoten.get("type") == "null":
        return True
    any_of = knoten.get("anyOf")
    if isinstance(any_of, list):
        return any(isinstance(teil, dict) and teil.get("type") == "null" for teil in any_of)
    return False


def _kern(knoten: dict[str, Any]) -> dict[str, Any]:
    """Der nicht-null-Zweig eines anyOf, sonst der Knoten selbst."""
    any_of = knoten.get("anyOf")
    if not isinstance(any_of, list):
        return knoten
    for teil in any_of:
        if isinstance(teil, dict) and teil.get("type") != "null":
            return teil
    return knoten


def _feld_typ(knoten: dict[str, Any]) -> tuple[str, list[str] | None]:
    kern = _kern(knoten)
    enum = kern.get("enum") or knoten.get("enum")
    if isinstance(enum, list) and enum:
        return "enum", [str(eintrag) for eintrag in enum]
    # integer|string (z. B. Postleitzahl) als Text, sonst gehen fuehrende Nullen verloren.
    any_of = knoten.get("anyOf")
    if isinstance(any_of, list):
        typen = {teil.get("type") for teil in any_of if isinstance(teil, dict)}
        if "string" in typen and ("integer" in typen or "number" in typen):
            return "string", None
    typ = kern.get("type")
    if typ == "array":
        return "string[]", None
    if typ in {"boolean", "integer", "number", "string", "object"}:
        return str(typ), None
    return "string", None


def _verboten(pfad: str) -> bool:
    if pfad in VERBOTENE_PFADE or pfad in GESPERRTE_FELDER:
        return True
    return any(pfad.startswith(f"{gesperrt}.") for gesperrt in VERBOTENE_PFADE | GESPERRTE_FELDER)


def _felder_sammeln(
    schema: dict[str, Any], knoten: dict[str, Any], prefix: str,
) -> list[dict[str, Any]]:
    knoten = _aufloesen(schema, knoten)
    eigenschaften = knoten.get("properties")
    if not isinstance(eigenschaften, dict):
        return []
    felder: list[dict[str, Any]] = []
    for name, roh in eigenschaften.items():
        if not isinstance(roh, dict):
            continue
        pfad = f"{prefix}.{name}" if prefix else name
        if _verboten(pfad):
            continue
        aufgeloest = _aufloesen(schema, roh)
        typ, enum = _feld_typ(aufgeloest)
        if typ == "object":
            felder.extend(_felder_sammeln(schema, aufgeloest, pfad))
            continue
        if typ == "string[]":
            # Nur einfache Zeichenkettenlisten. Objekte in Arrays gehoeren nicht ins Formular.
            items = _kern(aufgeloest).get("items")
            if isinstance(items, dict) and items.get("type") not in (None, "string"):
                continue
        feld: dict[str, Any] = {
            "pfad": pfad,
            "titel": BEZEICHNUNGEN.get(pfad) or str(aufgeloest.get("title") or name),
            "beschreibung": str(aufgeloest.get("description") or roh.get("description") or ""),
            "typ": typ,
            "vorgabe": aufgeloest.get("default", roh.get("default")),
            "null_erlaubt": _null_erlaubt(aufgeloest) or _null_erlaubt(roh),
            "langtext": pfad in _LANGTEXT,
        }
        if enum is not None:
            feld["enum"] = enum
            feld["enum_labels"] = {wert: ENUM_LABELS.get(wert, wert) for wert in enum}
        felder.append(feld)
    return felder


@lru_cache(maxsize = 1)
def gruppen_fuer_ui() -> list[dict[str, Any]]:
    """Baut die Formulargruppen aus dem Schema. Unbekannte Wurzeln bleiben draussen."""
    schema = schema_laden()
    eigenschaften = schema.get("properties")
    if not isinstance(eigenschaften, dict):
        return []
    gruppen: list[dict[str, Any]] = []
    for gruppe in GRUPPEN:
        wurzel = str(gruppe["wurzel"])
        knoten = eigenschaften.get(wurzel)
        if not isinstance(knoten, dict):
            continue
        felder = _felder_sammeln(schema, knoten, wurzel)
        if not felder:
            continue
        eintrag = dict(gruppe)
        eintrag["felder"] = felder
        gruppen.append(eintrag)
    return gruppen


def erlaubte_pfade() -> frozenset[str]:
    return frozenset(feld["pfad"] for gruppe in gruppen_fuer_ui() for feld in gruppe["felder"])


def _flach(werte: dict[str, Any], prefix: str = "") -> dict[str, Any]:
    ergebnis: dict[str, Any] = {}
    for schluessel, wert in werte.items():
        pfad = f"{prefix}.{schluessel}" if prefix else schluessel
        if isinstance(wert, dict):
            ergebnis.update(_flach(wert, pfad))
        else:
            ergebnis[pfad] = wert
    return ergebnis


def nesten(flach: dict[str, Any]) -> dict[str, Any]:
    baum: dict[str, Any] = {}
    for pfad, wert in flach.items():
        teile = pfad.split(".")
        knoten: dict[str, Any] = baum
        for teil in teile[:-1]:
            naechster = knoten.get(teil)
            if not isinstance(naechster, dict):
                naechster = {}
                knoten[teil] = naechster
            knoten = naechster
        knoten[teile[-1]] = wert
    return baum


def _wert_pruefen(pfad: str, wert: Any, feld: dict[str, Any]) -> Any:
    if wert is None:
        if feld.get("null_erlaubt"):
            return None
        raise FachlicherFehler(f"Das Feld „{feld['titel']}“ darf nicht leer sein.", feld = pfad)

    typ = feld["typ"]
    if typ == "boolean":
        if not isinstance(wert, bool):
            raise FachlicherFehler(f"„{feld['titel']}“ muss ja oder nein sein.", feld = pfad)
        return wert
    if typ == "integer":
        if isinstance(wert, bool) or not isinstance(wert, int):
            raise FachlicherFehler(f"„{feld['titel']}“ muss eine ganze Zahl sein.", feld = pfad)
        return wert
    if typ == "number":
        if isinstance(wert, bool) or not isinstance(wert, (int, float)):
            raise FachlicherFehler(f"„{feld['titel']}“ muss eine Zahl sein.", feld = pfad)
        return float(wert)
    if typ == "enum":
        erlaubt = feld.get("enum") or []
        if wert not in erlaubt:
            raise FachlicherFehler(
                f"„{feld['titel']}“ kennt den Wert „{wert}“ nicht.", feld = pfad,
            )
        return wert
    if typ == "string[]":
        if isinstance(wert, str):
            liste = [zeile.strip() for zeile in wert.splitlines() if zeile.strip()]
        elif isinstance(wert, list):
            liste = []
            for eintrag in wert:
                if not isinstance(eintrag, str):
                    raise FachlicherFehler(
                        f"„{feld['titel']}“ darf nur Textzeilen enthalten.", feld = pfad,
                    )
                if eintrag.strip():
                    liste.append(eintrag.strip())
        else:
            raise FachlicherFehler(f"„{feld['titel']}“ muss eine Liste sein.", feld = pfad)
        return liste
    if typ == "string":
        if not isinstance(wert, str):
            raise FachlicherFehler(f"„{feld['titel']}“ muss Text sein.", feld = pfad)
        return wert
    raise FachlicherFehler(f"Das Feld „{feld['titel']}“ hat einen unerwarteten Typ.", feld = pfad)


def _pfade_in(werte: dict[str, Any], prefix: str = "") -> list[str]:
    gefunden: list[str] = []
    for schluessel, wert in werte.items():
        pfad = f"{prefix}.{schluessel}" if prefix else str(schluessel)
        gefunden.append(pfad)
        if isinstance(wert, dict):
            gefunden.extend(_pfade_in(wert, pfad))
    return gefunden


def pruefen_und_saeubern(werte: dict[str, Any]) -> dict[str, Any]:
    """Weist gesperrte und unbekannte Felder ab. Gibt den bereinigten Baum zurueck."""
    if not isinstance(werte, dict):
        raise FachlicherFehler("Die Einstellungen müssen ein Objekt sein.")

    for pfad in _pfade_in(werte):
        if _verboten(pfad) or pfad in GESPERRTE_FELDER:
            raise FachlicherFehler(
                f"Das Feld „{pfad}“ darf nicht gesetzt werden.", feld = pfad,
            )

    erlaubt = erlaubte_pfade()
    felder = {feld["pfad"]: feld for gruppe in gruppen_fuer_ui() for feld in gruppe["felder"]}
    flach = _flach(werte)
    sauber: dict[str, Any] = {}
    for pfad, wert in flach.items():
        if pfad not in erlaubt:
            raise FachlicherFehler(
                f"Das Feld „{pfad}“ ist unbekannt und wird nicht gespeichert.", feld = pfad,
            )
        sauber[pfad] = _wert_pruefen(pfad, wert, felder[pfad])
    return nesten(sauber)


def fuer_ui(profil_wurzel: Path) -> dict[str, Any]:
    """Wie lesen, aber ohne Felder, die das Formular nicht kennt."""
    flach = _flach(lesen(profil_wurzel))
    erlaubt = erlaubte_pfade()
    return nesten({pfad: wert for pfad, wert in flach.items() if pfad in erlaubt})


def datei_fuer(profil_wurzel: Path) -> Path:
    return profil_wurzel / DATEINAME


def lesen(profil_wurzel: Path) -> dict[str, Any]:
    """Liest die Nutzerkonfiguration. Fehlt die Datei, ist das Ergebnis leer."""
    datei = datei_fuer(profil_wurzel)
    if not datei.is_file():
        return {}
    yaml = YAML(typ = "safe")
    with datei.open(encoding = "utf-8") as handle:
        geladen = yaml.load(handle)
    if geladen is None:
        return {}
    if not isinstance(geladen, dict):
        raise FachlicherFehler("Die gespeicherten Einstellungen sind unlesbar.", status = 500)
    # Defense in depth: selbst handeditierte Sperrfelder kommen nicht in den Lauf.
    gesperrte_entfernen(geladen)
    # Login-Klartext wuerde hier auch landen, wenn jemand die Datei von Hand
    # beschrieben hat. Entfernen, nicht in den Lauf mergen.
    login = geladen.get("login")
    if isinstance(login, dict):
        login.pop("username", None)
        login.pop("password", None)
        if not login:
            geladen.pop("login", None)
    return geladen


def schreiben(profil_wurzel: Path, werte: dict[str, Any]) -> dict[str, Any]:
    """Prueft, speichert und gibt den gespeicherten Baum zurueck."""
    sauber = pruefen_und_saeubern(werte)
    # Noch einmal die Sperrliste - falls die Pruefung und die Liste auseinanderlaufen.
    entfernt = gesperrte_entfernen(sauber)
    if entfernt:
        raise FachlicherFehler(
            f"Das Feld „{entfernt[0]}“ darf nicht gesetzt werden.", feld = entfernt[0],
        )
    profil_wurzel.mkdir(parents = True, exist_ok = True)
    datei = datei_fuer(profil_wurzel)
    yaml = YAML()
    yaml.default_flow_style = False
    with datei.open("w", encoding = "utf-8") as handle:
        handle.write(
            "# Nutzerkonfiguration von Anzeigen-Studio (AP-2.9).\n"
            "# Wird vor jedem Lauf in config.yaml gemischt. Nicht von Hand\n"
            "# an config.yaml aendern - die Datei wird ueberschrieben.\n",
        )
        yaml.dump(sauber, handle)
    return sauber
