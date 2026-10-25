# Image Dataset Studio — Copyright (C) 2026 Mauro Liistro
# SPDX-License-Identifier: AGPL-3.0-only
"""Lettura e scrittura di settings.json."""
import json
import os

import pytest

from dataset_studio import config


@pytest.fixture
def settings_file(tmp_path, monkeypatch):
    cache = tmp_path / "cache"
    monkeypatch.setattr(config, "CACHE_BASE_DIR", str(cache))
    monkeypatch.setattr(config, "SETTINGS_FILE", str(cache / "settings.json"))
    return cache / "settings.json"


def test_save_settings_merges_keys(settings_file):
    config.save_settings({"language": "it"})
    config.save_settings({"vlm_model": "florence"})

    assert json.loads(settings_file.read_text(encoding="utf-8")) == {"language": "it", "vlm_model": "florence"}


def test_save_settings_keeps_old_file_when_write_fails(settings_file):
    config.save_settings({"language": "it"})

    # Un valore non serializzabile fa fallire json.dump a metà scrittura
    config.save_settings({"broken": object()})

    assert json.loads(settings_file.read_text(encoding="utf-8")) == {"language": "it"}
    assert os.listdir(settings_file.parent) == ["settings.json"]
