# SPDX-FileCopyrightText: © Anzeigen-Studio contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
# SPDX-ArtifactOfProjectHomePage: https://github.com/TingelTangelBob/Kleinanzeigen.de-botUI/
"""Read-only synchronisation of the account listing order.

The manage-ads JSON endpoint is the cheapest reliable source available to the
bot: it is authenticated, already used for ownership/state checks, and its
``sort=DEFAULT`` result is the order shown by Kleinanzeigen.  This module only
stores numeric IDs and never downloads an ad page or changes a listing.
"""

from __future__ import annotations

import json
import logging
import os
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from . import published_ads

if TYPE_CHECKING:
    from .utils.web_scraping_mixin import WebScrapingMixin

LOG = logging.getLogger(__name__)

# Dot-file: it cannot match the bot's ad file glob and contains no credentials.
DATEINAME = ".anzeigen-studio-plattform-reihenfolge.json"


def datei_fuer(config_datei: str | Path) -> Path:
    """Return the sidecar path next to the active config file."""
    return Path(config_datei).resolve().parent / DATEINAME


def ids_aus_ads(ads: list[dict[str, Any]]) -> list[int]:
    """Extract valid IDs while retaining the endpoint's order."""
    ids: list[int] = []
    gesehen: set[int] = set()
    for ad in ads:
        try:
            ad_id = int(ad["id"])
        except (KeyError, TypeError, ValueError):
            continue
        if ad_id > 0 and ad_id not in gesehen:
            ids.append(ad_id)
            gesehen.add(ad_id)
    return ids


def speichern(datei: Path, ads: list[dict[str, Any]]) -> None:
    """Atomically persist the ordered IDs after a complete fetch."""
    ids = ids_aus_ads(ads)
    if len(ids) != len(ads):
        raise ValueError("Die Plattformantwort enthält ungültige oder doppelte Anzeigen-IDs.")
    datei.parent.mkdir(parents = True, exist_ok = True)
    payload = {
        "version": 1,
        "geprueft_am": datetime.now(UTC).isoformat(timespec = "seconds"),
        "ids": ids,
    }
    fd, name = tempfile.mkstemp(prefix = f".{datei.name}.", dir = datei.parent)
    try:
        with os.fdopen(fd, "w", encoding = "utf-8") as ausgabe:
            json.dump(payload, ausgabe, ensure_ascii = False, separators = (",", ":"))
            ausgabe.write("\n")
            ausgabe.flush()
            os.fsync(ausgabe.fileno())
        os.replace(name, datei)
    except BaseException:
        try:
            os.unlink(name)
        except FileNotFoundError:
            pass
        raise


async def synchronisieren(
    web: WebScrapingMixin,
    root_url: str,
    datei: Path,
) -> int:
    """Fetch all ordered pages and write the sidecar; return the ad count."""
    ads = await published_ads.fetch_published_ads(web, root_url, strict = True)
    speichern(datei, ads)
    anzahl = len(ads)
    LOG.info("Saved platform order for %s ads.", anzahl)
    return anzahl
