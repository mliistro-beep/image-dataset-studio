# Image Dataset Studio — Copyright (C) 2026 Mauro Liistro
# SPDX-License-Identifier: AGPL-3.0-only
"""Lettura e scrittura di settings.json."""
import json
import stat
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


def test_save_settings_keeps_file_permissions(settings_file):
    config.save_settings({"language": "it"})
    os.chmod(settings_file, 0o644)

    config.save_settings({"language": "en"})

    assert stat.S_IMODE(os.stat(settings_file).st_mode) == 0o644


def test_save_settings_never_raises_when_cleanup_fails(settings_file, monkeypatch):
    def fail(*args, **kwargs):
        raise OSError("boom")
    monkeypatch.setattr(config.os, "replace", fail)
    monkeypatch.setattr(config.os, "remove", fail)

    config.save_settings({"language": "it"})  # non deve sollevare


def test_save_settings_follows_symlink(settings_file, tmp_path):
    real = tmp_path / "dotfiles" / "settings.json"
    real.parent.mkdir()
    real.write_text("{}", encoding="utf-8")
    settings_file.parent.mkdir()
    settings_file.symlink_to(real)

    config.save_settings({"language": "it"})

    assert settings_file.is_symlink()
    assert json.loads(real.read_text(encoding="utf-8")) == {"language": "it"}
