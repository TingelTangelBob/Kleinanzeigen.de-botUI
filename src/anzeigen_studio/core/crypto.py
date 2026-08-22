# SPDX-FileCopyrightText: © Anzeigen-Studio contributors
# SPDX-ArtifactOfProjectHomePage: https://github.com/TingelTangelBob/Kleinanzeigen.de-botUI/
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# Verschluesselung der Zugangsdaten (AP-1.4).
#
# AES-256-GCM, also authentifizierte Verschluesselung: Manipulation am Chiffrat
# faellt beim Entschluesseln auf, statt stillschweigend Unsinn zu liefern.
#
# Der Schluessel kommt aus der Umgebung und hat bewusst KEINEN Vorgabewert. Ein
# fest eingebauter Standardschluessel waere schlimmer als gar keine
# Verschluesselung, weil er Sicherheit vortaeuscht: Wer das Datenvolume hat,
# haette bei bekanntem Schluessel auch die Zugangsdaten.

from __future__ import annotations

import base64
import os
from dataclasses import dataclass

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from anzeigen_studio.core.errors import FachlicherFehler

#: AES-256 braucht 32 Byte Schluesselmaterial.
_SCHLUESSEL_BYTES = 32

#: GCM-Standard. 12 Byte Nonce, je Verschluesselung neu und zufaellig.
_NONCE_BYTES = 12

#: Kennzeichnet das Format am Anfang des Chiffrats. Erlaubt spaeter einen
#: Verfahrenswechsel, ohne bestehende Daten raten zu muessen.
_VERSION = b"\x01"


class SchluesselFehlt(RuntimeError):
    """Es ist kein Schluessel konfiguriert."""


class SchluesselUngueltig(RuntimeError):
    """Der konfigurierte Schluessel hat nicht das erwartete Format."""


@dataclass(frozen = True, slots = True)
class Tresor:
    """Verschluesselt und entschluesselt mit einem festen Schluessel."""

    _schluessel: bytes

    @classmethod
    def aus_text(cls, schluessel_text: str) -> Tresor:
        """Baut einen Tresor aus dem Base64-Text der Umgebungsvariable."""
        try:
            roh = base64.b64decode(schluessel_text, validate = True)
        except (ValueError, TypeError) as fehler:
            raise SchluesselUngueltig(
                "ANZEIGEN_STUDIO_SECRET_KEY ist kein gültiges Base64. "
                "Erzeugen mit: openssl rand -base64 32",
            ) from fehler

        if len(roh) != _SCHLUESSEL_BYTES:
            raise SchluesselUngueltig(
                f"ANZEIGEN_STUDIO_SECRET_KEY muss {_SCHLUESSEL_BYTES} Byte lang sein, "
                f"ist aber {len(roh)} Byte. Erzeugen mit: openssl rand -base64 32",
            )

        return cls(_schluessel = roh)

    def verschluesseln(self, klartext: str) -> bytes:
        nonce = os.urandom(_NONCE_BYTES)
        chiffre = AESGCM(self._schluessel).encrypt(nonce, klartext.encode("utf-8"), None)
        # Version und Nonce wandern mit - beide sind nicht geheim, werden aber
        # zum Entschluesseln gebraucht.
        return _VERSION + nonce + chiffre

    def entschluesseln(self, gespeichert: bytes) -> str:
        if len(gespeichert) < len(_VERSION) + _NONCE_BYTES + 1:
            raise FachlicherFehler("Die gespeicherten Zugangsdaten sind beschädigt.", status = 500)

        version = gespeichert[: len(_VERSION)]
        if version != _VERSION:
            raise FachlicherFehler(
                "Die gespeicherten Zugangsdaten haben ein unbekanntes Format.", status = 500,
            )

        nonce = gespeichert[len(_VERSION) : len(_VERSION) + _NONCE_BYTES]
        chiffre = gespeichert[len(_VERSION) + _NONCE_BYTES :]
        try:
            klartext = AESGCM(self._schluessel).decrypt(nonce, chiffre, None)
        except InvalidTag as fehler:
            # Haeufigster Fall: der Schluessel wurde gewechselt. Das muss man
            # dem Nutzer sagen koennen, ohne dass er ins Log schauen muss.
            raise FachlicherFehler(
                "Die Zugangsdaten lassen sich nicht entschlüsseln. "
                "Vermutlich wurde ANZEIGEN_STUDIO_SECRET_KEY geändert. "
                "Bitte die Zugangsdaten neu eintragen.",
                status = 500,
            ) from fehler
        return klartext.decode("utf-8")


def tresor_oder_fehler(schluessel_text: str | None) -> Tresor:
    """Liefert einen Tresor oder wirft mit einer verstaendlichen Meldung.

    Wird an jeder Stelle gerufen, die Geheimnisse ablegen oder lesen will -
    ohne Schluessel gibt es dort keinen Weg weiter. Klartext ist ausdruecklich
    keine Rueckfalloption.
    """
    if not schluessel_text:
        raise FachlicherFehler(
            "Es ist kein Verschlüsselungsschlüssel konfiguriert. "
            "Ohne ANZEIGEN_STUDIO_SECRET_KEY können keine Zugangsdaten gespeichert werden.",
            status = 503,
        )
    try:
        return Tresor.aus_text(schluessel_text)
    except SchluesselUngueltig as fehler:
        raise FachlicherFehler(str(fehler), status = 503) from fehler
