# SPDX-FileCopyrightText: © Anzeigen-Studio contributors
# SPDX-ArtifactOfProjectHomePage: https://github.com/TingelTangelBob/Kleinanzeigen.de-botUI/
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# Tests des KI-Entwurfsmoduls (AP-4.1, AP-4.4, AP-4.7).
#
# Kein Test ruft den Anbieter. Was hier geprueft wird, ist alles, was zwischen
# Foto und Anzeigendatei liegt - und genau das ist der Teil, der uns gehoert.

from __future__ import annotations

import io
from typing import Any

import pytest

from anzeigen_studio.ai import bilder as ki_bilder
from anzeigen_studio.ai import entwurf as entwurf_dienst
from anzeigen_studio.ai.anbieter import _antwort_lesen, _fehler_aus_antwort
from anzeigen_studio.bestand import anlegen as anlegen_dienst
from anzeigen_studio.core.errors import FachlicherFehler


def _foto(breite: int = 2000, hoehe: int = 1500, *, mit_exif: bool = False) -> bytes:
    """Erzeugt ein JPEG, auf Wunsch mit Metadaten.

    Gesetzt werden Kameramodell und Aufnahmezeit - stellvertretend fuer alles,
    was ein Handyfoto sonst noch mitbringt. Was den Test eigentlich antreibt,
    sind die GPS-Koordinaten echter Aufnahmen: Sie stehen im selben EXIF-Block
    und sind bei einem Foto aus der eigenen Wohnung die Wohnadresse. Geprueft
    wird deshalb, dass ueberhaupt nichts uebrig bleibt - nicht, dass eine
    bestimmte Angabe entfernt wurde.
    """
    from PIL import Image

    bild = Image.new("RGB", (breite, hoehe), (120, 90, 60))
    puffer = io.BytesIO()
    if mit_exif:
        exif = Image.Exif()
        exif[0x010F] = "TestKamera"                     # Make
        exif[0x0132] = "2026:08:27 21:15:00"            # DateTime
        bild.save(puffer, format = "JPEG", exif = exif)
    else:
        bild.save(puffer, format = "JPEG")
    return puffer.getvalue()


# ------------------------------------------------------------ Bildvorbereitung

def test_bild_wird_auf_die_vorgegebene_kante_verkleinert() -> None:
    ergebnis = ki_bilder.vorbereiten(_foto(2000, 1500), kante = 768)
    assert max(ergebnis.breite, ergebnis.hoehe) == 768
    # Seitenverhaeltnis bleibt: 2000x1500 ist 4:3, also 768x576.
    assert (ergebnis.breite, ergebnis.hoehe) == (768, 576)
    assert ergebnis.bytes_nachher < ergebnis.bytes_vorher


def test_kleines_bild_wird_nicht_vergroessert() -> None:
    """Hochskalieren kostet Token, ohne Bildinformation hinzuzufuegen."""
    ergebnis = ki_bilder.vorbereiten(_foto(300, 200), kante = 768)
    assert (ergebnis.breite, ergebnis.hoehe) == (300, 200)


def test_exif_daten_ueberleben_die_vorbereitung_nicht() -> None:
    """Der Kern von AP-4.7: Ein Handyfoto traegt die Wohnadresse im EXIF."""
    from PIL import Image

    vorher = Image.open(io.BytesIO(_foto(mit_exif = True)))
    assert dict(vorher.getexif()), "Testaufbau kaputt: das Bild hat gar kein EXIF"

    ergebnis = ki_bilder.vorbereiten(_foto(mit_exif = True), kante = 768)
    roh = ergebnis.daten_url.split(",", 1)[1]
    import base64
    nachher = Image.open(io.BytesIO(base64.b64decode(roh)))
    assert not dict(nachher.getexif())


def test_zu_grosses_bild_wird_abgewiesen() -> None:
    with pytest.raises(FachlicherFehler) as fehler:
        ki_bilder.vorbereiten(b"x" * (ki_bilder.MAX_EINGABE_BYTES + 1), kante = 768)
    assert fehler.value.status == 413


def test_kaputte_datei_wird_abgewiesen() -> None:
    with pytest.raises(FachlicherFehler) as fehler:
        ki_bilder.vorbereiten(b"das ist kein Bild", kante = 768)
    assert fehler.value.status == 415


def test_mehr_bilder_als_erlaubt_werden_gekappt_statt_abgelehnt() -> None:
    inhalte = [_foto(400, 300) for _ in range(ki_bilder.MAX_BILDER + 3)]
    assert len(ki_bilder.alle_vorbereiten(inhalte, kante = 768)) == ki_bilder.MAX_BILDER


def test_ohne_bild_gibt_es_nichts_zu_erkennen() -> None:
    with pytest.raises(FachlicherFehler):
        ki_bilder.alle_vorbereiten([], kante = 768)


# ------------------------------------------------------------------- Entwurf

def _antwort(**abweichungen: Any) -> dict[str, Any]:
    daten: dict[str, Any] = {
        "titel": "Bosch Akkuschrauber PSR 18",
        "beschreibung": "Akkuschrauber mit Ladegerät. Gebrauchsspuren am Gehäuse.",
        "zustand": "gut",
        "kategorie": "Heimwerken > Werkzeug",
        "preis_euro": 35.0,
        "preis_begruendung": "Vergleichbare Geräte liegen bei 30 bis 45 Euro.",
        "sicherheit": "hoch",
        "fragen": [],
    }
    daten.update(abweichungen)
    return daten


def test_entwurf_wird_gelesen() -> None:
    e = entwurf_dienst.aus_antwort(_antwort())
    assert e.titel.startswith("Bosch")
    assert e.zustand == "gut"
    assert e.preis_euro == 35.0


def test_unbekannte_zustandsstufe_wird_verworfen_statt_uebernommen() -> None:
    e = entwurf_dienst.aus_antwort(_antwort(zustand = "bombastisch"))
    assert e.zustand is None


def test_wahrheitswert_ist_kein_preis() -> None:
    """`isinstance(True, int)` ist wahr - ohne Sonderbehandlung waere das 1 Euro."""
    assert entwurf_dienst.aus_antwort(_antwort(preis_euro = True)).preis_euro is None


def test_negativer_preis_wird_verworfen() -> None:
    assert entwurf_dienst.aus_antwort(_antwort(preis_euro = -5)).preis_euro is None


def test_zu_langer_titel_wird_gekuerzt() -> None:
    e = entwurf_dienst.aus_antwort(_antwort(titel = "A" * 200))
    assert len(e.titel) == entwurf_dienst.TITEL_MAX


def test_fehlender_titel_ist_ein_anbieterfehler() -> None:
    daten = _antwort()
    del daten["titel"]
    with pytest.raises(FachlicherFehler) as fehler:
        entwurf_dienst.aus_antwort(daten)
    assert fehler.value.status == 502


def test_platzhalter_wird_entfernt_und_als_massfrage_ausgegeben() -> None:
    e = entwurf_dienst.aus_antwort(_antwort(
        beschreibung = "Heller Esstisch. Der Esstisch hat die Maße [Länge x Breite x Höhe].",
    ))

    assert "[Länge x Breite x Höhe]" not in e.beschreibung
    assert e.beschreibung.startswith("Heller Esstisch.")
    assert e.beschreibung.endswith(entwurf_dienst.PRIVATVERKAUF_HINWEIS)
    assert len(e.fragen) == 1
    assert e.fragen[0].feld == "beschreibung"
    assert e.fragen[0].freitext_erlaubt
    assert e.fragen[0].optionen == []
    assert "nachmessen" in e.fragen[0].frage


def test_massantwort_wird_als_lesbarer_satz_eingesetzt() -> None:
    e = entwurf_dienst.aus_antwort(_antwort(fragen = [
        {"id": "masse", "frage": "Welche Maße hat der Tisch?", "feld": "beschreibung",
         "freitext_erlaubt": True, "optionen": []},
    ]))

    fertig = entwurf_dienst.anwenden(e, {"masse": "180 x 90 x 75 cm"})

    assert "Maße (Länge × Breite × Höhe): 180 × 90 × 75 cm." in fertig.beschreibung
    assert fertig.beschreibung.endswith(entwurf_dienst.PRIVATVERKAUF_HINWEIS)


def test_privatverkauf_hinweis_steht_genau_einmal_am_ende() -> None:
    e = entwurf_dienst.aus_antwort(_antwort(
        beschreibung = "Text.\n\nPrivatverkauf, daher keine Garantie, Gewährleistung und Rücknahme.",
    ))

    assert e.beschreibung.count(entwurf_dienst.PRIVATVERKAUF_HINWEIS) == 1
    assert e.beschreibung.endswith(entwurf_dienst.PRIVATVERKAUF_HINWEIS)
    assert entwurf_dienst.als_anzeigenfelder(e)["description"] == e.beschreibung


def test_anweisung_fordert_private_sprache_und_verhindert_vorlagenvariablen() -> None:
    grundlage = entwurf_dienst.anweisung()
    assert "potentielle Käufer" in grundlage
    assert entwurf_dienst.PRIVATVERKAUF_HINWEIS in grundlage
    assert "[Länge x Breite x Höhe]" in grundlage


def test_leeres_stilprofil_haengt_keinen_leeren_absatz_an() -> None:
    assert entwurf_dienst.anweisung("") == entwurf_dienst.anweisung()
    assert entwurf_dienst.anweisung("   ") == entwurf_dienst.anweisung()


def test_stilteil_wird_an_die_grundanweisung_gehaengt() -> None:
    zusammen = entwurf_dienst.anweisung("Beispiel 1:\nSchlicht geschrieben.")
    assert zusammen.startswith(entwurf_dienst.anweisung())
    assert "Schlicht geschrieben." in zusammen


def test_frage_ohne_auswahl_und_ohne_freitext_faellt_weg() -> None:
    """Sie waere unbeantwortbar - und eine unbeantwortbare Frage blockiert."""
    e = entwurf_dienst.aus_antwort(_antwort(fragen = [
        {"id": "a", "frage": "Geht es?", "feld": "beschreibung",
         "freitext_erlaubt": False, "optionen": []},
    ]))
    assert e.fragen == []


def test_frage_mit_unbekanntem_feld_faellt_weg() -> None:
    e = entwurf_dienst.aus_antwort(_antwort(fragen = [
        {"id": "a", "frage": "?", "feld": "versandkosten",
         "freitext_erlaubt": True, "optionen": []},
    ]))
    assert e.fragen == []


# ------------------------------------------------------- Antworten anwenden

def _mit_fragen() -> entwurf_dienst.Entwurf:
    return entwurf_dienst.aus_antwort(_antwort(zustand = None, preis_euro = None, fragen = [
        {"id": "funktion", "frage": "Funktioniert das Gerät?", "feld": "beschreibung",
         "freitext_erlaubt": False,
         "optionen": [{"text": "Ja", "wert": "Das Gerät funktioniert einwandfrei."}]},
        {"id": "zustand", "frage": "Wie ist der Zustand?", "feld": "zustand",
         "freitext_erlaubt": False,
         "optionen": [{"text": "Gut", "wert": "gut"}]},
        {"id": "preis", "frage": "Welcher Preis?", "feld": "preis",
         "freitext_erlaubt": True,
         "optionen": [{"text": "35 Euro", "wert": "35"}]},
    ]))


def test_antworten_werden_ohne_zweiten_aufruf_eingesetzt() -> None:
    """Der ganze Sinn des Schemas: Beantworten kostet nichts mehr."""
    fertig = entwurf_dienst.anwenden(_mit_fragen(), {
        "funktion": "Das Gerät funktioniert einwandfrei.",
        "zustand": "gut",
        "preis": "42,50 €",
    })
    assert "funktioniert einwandfrei" in fertig.beschreibung
    assert fertig.zustand == "gut"
    assert fertig.preis_euro == 42.50


def test_unbekannte_kennung_wird_uebergangen() -> None:
    vorher = _mit_fragen()
    assert entwurf_dienst.anwenden(vorher, {"gibtsnicht": "egal"}).beschreibung == vorher.beschreibung


def test_freitext_auf_dem_zustandsfeld_wird_nur_bei_bekannter_stufe_uebernommen() -> None:
    assert entwurf_dienst.anwenden(_mit_fragen(), {"zustand": "ganz gut halt"}).zustand is None


def test_zustand_wandert_als_condition_s_in_die_felder() -> None:
    felder = entwurf_dienst.als_anzeigenfelder(entwurf_dienst.aus_antwort(_antwort()))
    assert felder["special_attributes"] == {"condition_s": "ok"}


def test_kategorie_wird_nicht_in_die_datei_geschrieben() -> None:
    """Ein geratener Kategoriepfad liesse den Lauf im Kategoriedialog stehen."""
    felder = entwurf_dienst.als_anzeigenfelder(entwurf_dienst.aus_antwort(_antwort()))
    assert "category" not in felder


# ----------------------------------------------------------- Antwort des Anbieters

def test_antwort_wird_auch_ohne_output_text_gelesen() -> None:
    antwort = _antwort_lesen({
        "output": [{"content": [{"text": '{"a": 1}'}]}],
        "usage": {"input_tokens": 10, "output_tokens": 5},
    }, "testmodell")
    assert antwort.daten == {"a": 1}
    assert antwort.token_eingabe == 10


def test_leere_antwort_ist_ein_anbieterfehler() -> None:
    with pytest.raises(FachlicherFehler) as fehler:
        _antwort_lesen({"output": []}, "testmodell")
    assert fehler.value.status == 502


def test_abgelehnter_schluessel_bekommt_einen_verstaendlichen_satz() -> None:
    fehler = _fehler_aus_antwort(401, '{"error": {"message": "Incorrect API key"}}')
    assert "Schlüssel" in fehler.args[0]


def test_fehlermeldung_traegt_den_schluessel_nicht_weiter() -> None:
    fehler = _fehler_aus_antwort(401, '{"error": {"message": "key sk-geheim123 invalid"}}')
    assert "sk-geheim123" not in fehler.args[0]


# --------------------------------------------------------------- Anlegen

def test_anzeige_landet_in_ads_nicht_in_downloaded_ads(tmp_path: Any) -> None:
    """`publish` sucht ausschliesslich unter ads/ - sonst bliebe sie unsichtbar."""
    angelegt = anlegen_dienst.anlegen(
        tmp_path,
        {"title": "Bosch Akkuschrauber", "description": "Text", "price": 35.0},
        [_foto(400, 300)],
    )
    assert angelegt.datei.startswith("ads/")
    assert (tmp_path / angelegt.datei).is_file()
    assert angelegt.bilder == 1


def test_angelegte_anzeige_hat_keine_id(tmp_path: Any) -> None:
    """Eine erfundene Nummer liesse den Bot die Anzeige fuer online halten."""
    angelegt = anlegen_dienst.anlegen(
        tmp_path, {"title": "Testgerät", "description": "Text"}, [_foto(400, 300)],
    )
    assert angelegt.id is None


def test_gleicher_titel_zweimal_ergibt_zwei_ordner(tmp_path: Any) -> None:
    felder = {"title": "Bosch Akkuschrauber", "description": "Text"}
    erste = anlegen_dienst.anlegen(tmp_path, felder, [_foto(400, 300)])
    zweite = anlegen_dienst.anlegen(tmp_path, felder, [_foto(400, 300)])
    assert erste.datei != zweite.datei


def test_umlaute_im_titel_ergeben_einen_brauchbaren_ordnernamen() -> None:
    assert anlegen_dienst.kurzname("Küchenmöbel für draußen!") == "kuechenmoebel-fuer-draussen"


def test_titel_ohne_verwertbare_zeichen_bekommt_einen_ersatznamen() -> None:
    assert anlegen_dienst.kurzname("!!! ??? ###") == "anzeige"
