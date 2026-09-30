# SPDX-FileCopyrightText: © Anzeigen-Studio contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# Tests der installationsweiten KI-Konfiguration (Open Source / gehostet).

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pytest import MonkeyPatch

from anzeigen_studio.core.settings import Settings


def test_open_source_hat_keinen_betreiber_schluessel() -> None:
    cfg = Settings(
        data_dir = Path("/tmp/anzeigen-studio-test"),
        secret_key = "geheim",
        dev_mode = True,
        chromium = "/usr/bin/chromium",
    )

    assert not cfg.hosted
    assert cfg.openai_api_schluessel is None
    assert cfg.ki_max_bilder == 4


def test_gehostet_nutzt_den_betreiber_schluessel_und_begrenzt_bilder(
    monkeypatch: MonkeyPatch,
) -> None:
    monkeypatch.setenv("ANZEIGEN_STUDIO_GEHOSTET", "true")
    monkeypatch.setenv("ANZEIGEN_STUDIO_OPENAI_API_KEY", "sk-nicht-ausgeben")
    monkeypatch.setenv("ANZEIGEN_STUDIO_KI_MAX_BILDER", "2")
    monkeypatch.setenv("ANZEIGEN_STUDIO_SECRET_KEY", "geheim")

    cfg = Settings.from_env()

    assert cfg.hosted
    assert cfg.openai_api_schluessel == "sk-nicht-ausgeben"
    assert cfg.ki_max_bilder == 2
    assert cfg.missing_for_production() == []
    assert "sk-nicht-ausgeben" not in repr(cfg)


def test_gehostet_ohne_betreiber_schluessel_meldet_den_mangel(monkeypatch: MonkeyPatch) -> None:
    monkeypatch.setenv("ANZEIGEN_STUDIO_GEHOSTET", "true")
    monkeypatch.delenv("ANZEIGEN_STUDIO_OPENAI_API_KEY", raising = False)
    monkeypatch.setenv("ANZEIGEN_STUDIO_SECRET_KEY", "geheim")

    assert Settings.from_env().missing_for_production() == ["ANZEIGEN_STUDIO_OPENAI_API_KEY"]
