# Image Dataset Studio — Copyright (C) 2026 Mauro Liistro
# SPDX-License-Identifier: AGPL-3.0-only
"""I crediti restano allineati con i modelli configurati e con le dipendenze installate."""
import os
import re

from dataset_studio import config

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _requirement_names() -> set:
    names = set()
    for file_name in ("requirements-base.txt", "requirements.txt", "requirements-gpu.txt"):
        with open(os.path.join(_ROOT, file_name), encoding="utf-8") as f:
            for line in f:
                line = line.split("#", 1)[0].strip()
                if line and not line.startswith("-"):
                    names.add(re.split(r"[<>=!~\[ ]", line, maxsplit=1)[0].lower())
    return names


def test_every_configured_model_repo_is_credited():
    repos = {m["repo"] for m in config.AVAILABLE_MODELS.values()} | {m["repo"] for m in config.VLM_MODELS.values()}
    credited = {repo for credit in config.MODEL_CREDITS for repo in credit["repos"]}

    assert sorted(repos - credited) == []


def test_every_requirement_is_credited():
    credited = {pkg.lower() for credit in config.LIBRARY_CREDITS for pkg in credit["packages"]}

    assert sorted(_requirement_names() - credited) == []


def test_credits_have_name_license_and_https_link():
    for credit in config.MODEL_CREDITS + config.LIBRARY_CREDITS:
        assert credit["name"] and credit["license"]
        assert credit["url"].startswith("https://")
