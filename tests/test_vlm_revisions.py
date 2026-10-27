# Image Dataset Studio — Copyright (C) 2026 Mauro Liistro
# SPDX-License-Identifier: AGPL-3.0-only
"""Ogni modello VLM si scarica e si carica a una revisione fissa, non dall'ultimo commit di "main"."""
import re
import sys
import types
from typing import Any

import pytest

from dataset_studio import config
from dataset_studio.engines import vlm


class _FakePretrained:
    """Registra gli argomenti di from_pretrained al posto delle classi di transformers."""
    calls: list = []

    @classmethod
    def from_pretrained(cls, repo, **kwargs):
        cls.calls.append((cls.__name__, repo, kwargs.get("revision")))
        return cls()

    def to(self, *args, **kwargs):
        return self

    def eval(self):
        return self


@pytest.fixture
def fake_hf(monkeypatch):
    """transformers e torch finti: il test gira anche nel .venv leggero senza scaricare nulla."""
    _FakePretrained.calls = []
    names = ["AutoProcessor", "AutoModelForCausalLM", "Florence2ForConditionalGeneration",
             "LlavaForConditionalGeneration"]
    fake_transformers: Any = types.ModuleType("transformers")
    for name in names:
        setattr(fake_transformers, name, type(name, (_FakePretrained,), {}))
    fake_transformers.BitsAndBytesConfig = lambda **kwargs: None
    monkeypatch.setitem(sys.modules, "transformers", fake_transformers)
    monkeypatch.setattr(vlm, "torch", types.SimpleNamespace(float16="f16", float32="f32", bfloat16="bf16"))

    snapshots = []
    monkeypatch.setattr(vlm, "download_snapshot",
                        lambda repo, revision, *args: snapshots.append((repo, revision)))
    return snapshots


def test_every_vlm_model_has_a_pinned_revision():
    missing = [key for key, info in config.VLM_MODELS.items() if not info.get("revision")]

    assert missing == []


def test_every_vlm_revision_is_a_commit_hash():
    # Un tag o un branch su HF si può spostare: solo l'hash del commit fissa davvero i file
    not_hashes = {key: info.get("revision") for key, info in config.VLM_MODELS.items()
                  if not re.fullmatch(r"[0-9a-f]{40}", info.get("revision") or "")}

    assert not_hashes == {}


@pytest.mark.parametrize("model_key", sorted(config.VLM_MODELS))
def test_load_uses_the_pinned_revision_everywhere(fake_hf, model_key):
    info = config.VLM_MODELS[model_key]
    backend = vlm.create_backend(model_key, "cpu")

    backend.load(lambda msg: None, lambda msg, pct: None)

    assert fake_hf == [(info["repo"], info.get("revision"))]
    assert _FakePretrained.calls
    for name, repo, revision in _FakePretrained.calls:
        assert (repo, revision) == (info["repo"], info.get("revision")), name
