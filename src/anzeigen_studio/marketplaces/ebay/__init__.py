# SPDX-FileCopyrightText: © Anzeigen-Studio contributors
# SPDX-ArtifactOfProjectHomePage: https://github.com/TingelTangelBob/Kleinanzeigen.de-botUI/
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# eBay Sell-API Adapter (Phase 6 / AP-E-*). Credential-Store (E-02), OAuth (E-03),
# Client/Dry-Run (E-04), Mapping (E-05).

from anzeigen_studio.marketplaces.ebay.models import (
    HINWEIS_BILDER,
    HINWEIS_GEBUEHREN_DRY_RUN,
    HINWEIS_STANDORT,
    MARKETPLACE_ID_DE,
    MVP_SCOPES,
    SCHEMA_VERSION,
    WAEHRUNG_EUR,
    EbayUmgebung,
    EbayVerbindung,
    EbayZugangStatus,
)

__all__ = [
    "HINWEIS_BILDER",
    "HINWEIS_GEBUEHREN_DRY_RUN",
    "HINWEIS_STANDORT",
    "MARKETPLACE_ID_DE",
    "MVP_SCOPES",
    "SCHEMA_VERSION",
    "WAEHRUNG_EUR",
    "EbayUmgebung",
    "EbayVerbindung",
    "EbayZugangStatus",
]
