# Image Dataset Studio — Copyright (C) 2026 Mauro Liistro
# SPDX-License-Identifier: AGPL-3.0-only
import json
import os
import platform

APP_NAME = "Image Dataset Studio"
APP_VERSION = "0.1.0"
LICENSE_ID = "AGPL-3.0-only"
COPYRIGHT_YEAR = "2026"
COPYRIGHT_HOLDER = "Mauro Liistro"
REPO_URL = "https://github.com/mliistro-beep/image-dataset-studio"

# Le chiavi restano quelle dello script originale (sono salvate nei settings come "last_model");
# "name" + "hint" (chiave i18n) formano il testo mostrato nell'interfaccia.
AVAILABLE_MODELS = {
    "WD14 ConvNeXtV2 (Consigliato per SDXL/Pony)": {
        "repo": "SmilingWolf/wd-v1-4-convnextv2-tagger-v2",
        "size": 448,
        "name": "WD14 ConvNeXtV2",
        "hint": "wd14.hint_convnext",
    },
    "WD14 SwinV2 (Ottimo per Anima/Anime)": {
        "repo": "SmilingWolf/wd-v1-4-swinv2-tagger-v2",
        "size": 448,
        "name": "WD14 SwinV2",
        "hint": "wd14.hint_swinv2",
    },
    "WD14 MOAT Tagger v2": {
        "repo": "SmilingWolf/wd-v1-4-moat-tagger-v2",
        "size": 448,
        "name": "WD14 MOAT Tagger v2",
        "hint": "",
    }
}

# Modelli VLM per il captioning in linguaggio naturale.
# backend: chiave della classe in engines/vlm.py
VLM_MODELS = {
    "florence2_large": {
        "label": "Florence-2-large (0.77B)",
        "backend": "florence2",
        "repo": "florence-community/Florence-2-large",
    },
    "florence2_base": {
        "label": "Florence-2-base (0.23B)",
        "backend": "florence2",
        "repo": "florence-community/Florence-2-base",
    },
    "moondream2": {
        "label": "moondream2 (1.8B)",
        "backend": "moondream2",
        "repo": "vikhyatk/moondream2",
        "revision": "2025-06-21",
    },
    "joycaption": {
        "label": "JoyCaption Beta One (Llama 3.1 8B, 4-bit)",
        "backend": "joycaption",
        "repo": "fancyfeast/llama-joycaption-beta-one-hf-llava",
    },
}

# Profili hardware: il primo modello della lista è quello consigliato. "label" è una chiave i18n.
VLM_PROFILES = {
    "universal": {
        "label": "profile.universal",
        "models": ["florence2_large", "moondream2"],
        "device": "cpu",
    },
    "gpu": {
        "label": "profile.gpu",
        "models": ["joycaption"],
        "device": "cuda",
    },
    "lowram": {
        "label": "profile.lowram",
        "models": ["moondream2", "florence2_base"],
        "device": "cpu",
        "low_memory": True,
    },
}

# Preset per il campo istruzione (chiave i18n del nome -> prompt in inglese, che i VLM capiscono meglio)
INSTRUCTION_PRESETS = {
    "preset.detailed": "Write a long detailed description for this image.",
    "preset.short": "Write a short one-sentence description for this image.",
    "preset.art_style": "Write a detailed description for this image, including the art style, medium, lighting and composition.",
    "preset.training": "Write a straightforward caption for this image. Describe the subjects, their appearance, pose, clothing and the background. Do not mention mood or speculate.",
    "preset.sd_prompt": "Output a stable diffusion prompt that is indistinguishable from a real stable diffusion prompt.",
}

# Livelli di dettaglio di Florence-2, che non accetta prompt liberi (chiave i18n -> task token)
FLORENCE_TASKS = {
    "florence.brief": "<CAPTION>",
    "florence.detailed": "<DETAILED_CAPTION>",
    "florence.more_detailed": "<MORE_DETAILED_CAPTION>",
}

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}

# Cartelle di output di un dataset
ORIGINAL_DIR = "original_dataset"
TAGS_DIR = "dataset_tags"
CAPTIONS_DIR = "dataset_captions"
RENAME_MAP_FILE = "rename_map.csv"

# Il percorso resta quello dello script originale per riusare i modelli già scaricati
CACHE_BASE_DIR = os.path.join(os.path.expanduser("~"), ".cache", "wd14_tagger")
TEMP_DATASET_DIR = os.path.join(CACHE_BASE_DIR, "temp_dataset")
SETTINGS_FILE = os.path.join(CACHE_BASE_DIR, "settings.json")

IS_MAC = platform.system() == "Darwin"


def load_settings() -> dict:
    if os.path.exists(SETTINGS_FILE):
        try:
            with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            print(f"⚠️ settings load error: {e}")
    return {}


def save_settings(updates: dict):
    """Aggiorna solo le chiavi passate, preservando quelle delle altre schede."""
    try:
        os.makedirs(CACHE_BASE_DIR, exist_ok=True)
        settings = load_settings()
        settings.update(updates)
        with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
            json.dump(settings, f, indent=2)
    except Exception as e:
        print(f"⚠️ settings save error: {e}")
