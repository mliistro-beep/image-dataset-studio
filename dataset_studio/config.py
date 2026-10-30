# Image Dataset Studio — Copyright (C) 2026 Mauro Liistro
# SPDX-License-Identifier: AGPL-3.0-only
import json
import os
import platform
import shutil
import tempfile
from typing import Dict, List, TypedDict


class WD14ModelInfo(TypedDict):
    repo: str
    size: int
    name: str
    hint: str


class VLMModelInfo(TypedDict):
    label: str
    backend: str
    repo: str
    revision: str


class _VLMProfileBase(TypedDict):
    label: str
    models: List[str]
    device: str


class VLMProfile(_VLMProfileBase, total=False):
    low_memory: bool


class _ModelCreditBase(TypedDict):
    name: str
    author: str
    url: str
    license: str
    repos: List[str]


class ModelCredit(_ModelCreditBase, total=False):
    license_note: str


class LibraryCredit(TypedDict):
    name: str
    url: str
    license: str
    packages: List[str]


APP_NAME = "Image Dataset Studio"
APP_VERSION = "0.1.0"
LICENSE_ID = "AGPL-3.0-only"
COPYRIGHT_YEAR = "2026"
COPYRIGHT_HOLDER = "Mauro Liistro"
REPO_URL = "https://github.com/mliistro-beep/image-dataset-studio"
ISSUES_URL = REPO_URL + "/issues"
AUTHOR_URL = "https://github.com/mliistro-beep"

# Le chiavi restano quelle dello script originale (sono salvate nei settings come "last_model");
# "name" + "hint" (chiave i18n) formano il testo mostrato nell'interfaccia.
AVAILABLE_MODELS: Dict[str, WD14ModelInfo] = {
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
# revision: commit (o tag) fisso su HuggingFace, così un aggiornamento del repo non cambia il modello
# né il codice scaricato senza che lo si sia provato. Per aggiornarlo, prova il nuovo commit e cambia qui.
VLM_MODELS: Dict[str, VLMModelInfo] = {
    "florence2_large": {
        "label": "Florence-2-large (0.77B)",
        "backend": "florence2",
        "repo": "florence-community/Florence-2-large",
        "revision": "4271c66b88cdbc05735372ec13b2360108de5317",
    },
    "florence2_base": {
        "label": "Florence-2-base (0.23B)",
        "backend": "florence2",
        "repo": "florence-community/Florence-2-base",
        "revision": "00921df66db728a9ceb750f5eca43e5c203a2051",
    },
    "moondream2": {
        "label": "moondream2 (1.8B)",
        "backend": "moondream2",
        "repo": "vikhyatk/moondream2",
        # Stessi pesi del tag 2025-06-21; il codice remoto di quel tag non si carica con transformers 5
        "revision": "5d6c926f44e26b07957b0dd315bbedcb4c17a5fe",
    },
    "joycaption": {
        "label": "JoyCaption Beta One (Llama 3.1 8B, 4-bit)",
        "backend": "joycaption",
        "repo": "fancyfeast/llama-joycaption-beta-one-hf-llava",
        "revision": "ebf414ea497a020da0f82df3913e5b6cb8e9663a",
    },
}

# Crediti mostrati in Informazioni. I modelli non sono distribuiti con il programma: si scaricano da HuggingFace
# con la loro licenza. "license_note" è una chiave i18n per i casi in cui la licenza va spiegata.
MODEL_CREDITS: List[ModelCredit] = [
    {
        "name": "WD14 Tagger v2 (ConvNeXtV2, SwinV2, MOAT)",
        "author": "SmilingWolf",
        "url": "https://huggingface.co/SmilingWolf",
        "license": "Apache-2.0",
        "repos": [m["repo"] for m in AVAILABLE_MODELS.values()],
    },
    {
        "name": "Florence-2 (base, large)",
        "author": "Microsoft · florence-community",
        "url": "https://huggingface.co/microsoft/Florence-2-large",
        "license": "MIT",
        "repos": ["florence-community/Florence-2-large", "florence-community/Florence-2-base"],
    },
    {
        "name": "moondream2",
        "author": "vikhyatk (Moondream)",
        "url": "https://huggingface.co/vikhyatk/moondream2",
        "license": "Apache-2.0",
        "repos": ["vikhyatk/moondream2"],
    },
    {
        "name": "JoyCaption Beta One",
        "author": "fancyfeast",
        "url": "https://huggingface.co/fancyfeast/llama-joycaption-beta-one-hf-llava",
        "license": "Llama 3.1 Community License",
        "license_note": "credits.joycaption_license",
        "repos": ["fancyfeast/llama-joycaption-beta-one-hf-llava"],
    },
]

# Librerie usate a runtime; "packages" sono i nomi nei requirements (un test controlla che ci siano tutti)
LIBRARY_CREDITS: List[LibraryCredit] = [
    {"name": "Qt for Python (PySide6)", "url": "https://doc.qt.io/qtforpython-6/", "license": "LGPL-3.0",
     "packages": ["PySide6-Essentials"]},
    {"name": "ONNX Runtime", "url": "https://onnxruntime.ai", "license": "MIT",
     "packages": ["onnxruntime", "onnxruntime-gpu"]},
    {"name": "PyTorch", "url": "https://pytorch.org", "license": "BSD-3-Clause", "packages": ["torch"]},
    {"name": "Transformers", "url": "https://github.com/huggingface/transformers", "license": "Apache-2.0",
     "packages": ["transformers"]},
    {"name": "Accelerate", "url": "https://github.com/huggingface/accelerate", "license": "Apache-2.0",
     "packages": ["accelerate"]},
    {"name": "huggingface_hub", "url": "https://github.com/huggingface/huggingface_hub", "license": "Apache-2.0",
     "packages": ["huggingface_hub"]},
    {"name": "bitsandbytes", "url": "https://github.com/bitsandbytes-foundation/bitsandbytes", "license": "MIT",
     "packages": ["bitsandbytes"]},
    {"name": "NumPy", "url": "https://numpy.org", "license": "BSD-3-Clause", "packages": ["numpy"]},
    {"name": "Pillow", "url": "https://python-pillow.org", "license": "MIT-CMU", "packages": ["Pillow"]},
    {"name": "tqdm", "url": "https://github.com/tqdm/tqdm", "license": "MPL-2.0 AND MIT", "packages": ["tqdm"]},
]

# Profili hardware: il primo modello della lista è quello consigliato. "label" è una chiave i18n.
VLM_PROFILES: Dict[str, VLMProfile] = {
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
# Cartella separata: l'import di un archivio nelle schede Batch svuota TEMP_DATASET_DIR
MASS_EDIT_TEMP_DIR = os.path.join(CACHE_BASE_DIR, "temp_mass_edit")
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
    tmp_path = None
    try:
        os.makedirs(CACHE_BASE_DIR, exist_ok=True)
        settings = load_settings()
        settings.update(updates)
        # Scrittura atomica: un errore o una chiusura a metà non lasciano settings.json troncato.
        # realpath: se settings.json è un link simbolico si aggiorna il file a cui punta, senza rompere il link
        target = os.path.realpath(SETTINGS_FILE)
        fd, tmp_path = tempfile.mkstemp(prefix=".settings-", suffix=".tmp", dir=os.path.dirname(target))
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(settings, f, indent=2)
            f.flush()
            os.fsync(f.fileno())
        if os.path.exists(target):
            shutil.copymode(target, tmp_path)   # mkstemp crea il file 0600
        os.replace(tmp_path, target)
        tmp_path = None
    except Exception as e:
        print(f"⚠️ settings save error: {e}")
    finally:
        if tmp_path:
            try:
                os.remove(tmp_path)
            except OSError:
                pass   # già segnalato sopra; un .tmp rimasto non è grave
