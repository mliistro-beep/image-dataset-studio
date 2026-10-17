# Image Dataset Studio — Copyright (C) 2026 Mauro Liistro
# SPDX-License-Identifier: AGPL-3.0-only
"""Motore WD14: logica estratta 1:1 da BatchTaggingThread / ModelLoaderThread dello script originale."""
import csv
import os
import time
import urllib.request
from typing import Callable, List, Optional, Tuple

import numpy as np
from PIL import Image

from ..config import CACHE_BASE_DIR
from ..i18n import tr

try:
    import onnxruntime as ort
except ImportError:
    ort = None

RATING_TAGS = {"general", "sensitive", "questionable", "explicit"}


# ---------------------------------------------------------------------------
# Download e caricamento
# ---------------------------------------------------------------------------

def model_paths(repo_id: str) -> Tuple[str, str]:
    safe_name = repo_id.replace("/", "_")
    onnx_path = os.path.join(CACHE_BASE_DIR, f"{safe_name}_model.onnx")
    csv_path = os.path.join(CACHE_BASE_DIR, f"{safe_name}_tags.csv")
    return onnx_path, csv_path


def download_file(url: str, dest_path: str, file_desc: str,
                  progress_cb: Callable[[str, float], None],
                  log_cb: Callable[[str], None],
                  should_stop: Callable[[], bool]):
    tmp_path = dest_path + ".tmp"
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) WD14-AutoTagger/2.0"}
    )

    with urllib.request.urlopen(req) as response, open(tmp_path, "wb") as out_file:
        total_size = int(response.headers.get("Content-Length", 0))
        bytes_downloaded = 0
        chunk_size = 1024 * 512
        start_time = time.time()
        last_log_time = 0.0

        while True:
            if should_stop():
                raise InterruptedError(tr("wd14.download_cancelled"))

            chunk = response.read(chunk_size)
            if not chunk:
                break
            out_file.write(chunk)
            bytes_downloaded += len(chunk)

            if total_size > 0:
                percent = (bytes_downloaded / total_size) * 100
                mb_downloaded = bytes_downloaded / (1024 * 1024)
                mb_total = total_size / (1024 * 1024)
                elapsed = time.time() - start_time
                speed_mb = (mb_downloaded / elapsed) if elapsed > 0 else 0.0

                status_msg = tr("wd14.download_status", file=file_desc, done=f"{mb_downloaded:.1f}", total=f"{mb_total:.1f}",
                                percent=f"{percent:.1f}", speed=f"{speed_mb:.2f}")
                progress_cb(status_msg, percent)

                if time.time() - last_log_time > 1.5:
                    last_log_time = time.time()
                    log_cb(f"  📥 {status_msg}")

    if os.path.exists(dest_path):
        os.remove(dest_path)
    os.rename(tmp_path, dest_path)


def ensure_model_files(repo_id: str, progress_cb, log_cb, should_stop) -> Optional[Tuple[str, str]]:
    """Scarica model.onnx e selected_tags.csv se mancanti. Ritorna None se interrotto."""
    os.makedirs(CACHE_BASE_DIR, exist_ok=True)
    base_url = f"https://huggingface.co/{repo_id}/resolve/main/"
    onnx_path, csv_path = model_paths(repo_id)

    if not os.path.exists(onnx_path) or os.path.getsize(onnx_path) == 0:
        log_cb(tr("wd14.downloading_onnx"))
        download_file(base_url + "model.onnx", onnx_path, "model.onnx", progress_cb, log_cb, should_stop)
    else:
        log_cb(tr("wd14.onnx_cached"))

    if should_stop():
        return None

    if not os.path.exists(csv_path) or os.path.getsize(csv_path) == 0:
        log_cb(tr("wd14.downloading_csv"))
        download_file(base_url + "selected_tags.csv", csv_path, "selected_tags.csv", progress_cb, log_cb, should_stop)
    else:
        log_cb(tr("wd14.csv_cached"))

    if should_stop():
        return None
    return onnx_path, csv_path


class WD14Model:
    """Sessione ONNX + etichette. Posseduto da ModelManager."""

    def __init__(self, onnx_path: str, csv_path: str):
        if ort is None:
            raise ImportError(tr("wd14.ort_missing"))

        providers = ['CUDAExecutionProvider', 'ROCMExecutionProvider', 'CPUExecutionProvider']
        available_providers = ort.get_available_providers()
        active_providers = [p for p in providers if p in available_providers]

        self.session = ort.InferenceSession(onnx_path, providers=active_providers)
        self.provider = active_providers[0]

        self.tags_data = []
        with open(csv_path, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                self.tags_data.append({
                    "name": row["name"],
                    "category": row["category"]
                })

    def unload(self):
        self.session = None
        self.tags_data = []


# ---------------------------------------------------------------------------
# Inferenza e post-processing
# ---------------------------------------------------------------------------

def preprocess_image(img_path_or_pil, target_size: int):
    """Ritorna (pil_originale, tensore, immagine_ridimensionata). Accetta un path o una PIL.Image."""
    if isinstance(img_path_or_pil, Image.Image):
        img = img_path_or_pil.convert("RGB")
    else:
        img = Image.open(img_path_or_pil).convert("RGB")

    w, h = img.size
    max_dim = max(w, h)
    padded_img = Image.new("RGB", (max_dim, max_dim), (255, 255, 255))
    padded_img.paste(img, ((max_dim - w) // 2, (max_dim - h) // 2))

    resized = padded_img.resize((target_size, target_size), Image.Resampling.BICUBIC)

    img_arr = np.array(resized, dtype=np.float32)
    img_arr = img_arr[:, :, ::-1]
    img_arr = np.expand_dims(img_arr, axis=0)

    return img, img_arr, resized


def infer_probs(session, img_tensor):
    input_name = session.get_inputs()[0].name
    output_name = session.get_outputs()[0].name
    probs = session.run([output_name], {input_name: img_tensor})[0][0]

    if np.max(probs) > 1.0 or np.min(probs) < 0.0:
        probs = 1.0 / (1.0 + np.exp(-probs))
    return probs


def build_banned_set(banned_tags_raw: List[str]) -> set:
    banned_set = set()
    for bt in banned_tags_raw:
        bt_clean = bt.strip().lower()
        if bt_clean:
            banned_set.add(bt_clean)
            banned_set.add(bt_clean.replace("_", " "))
            banned_set.add(bt_clean.replace(" ", "_"))
    return banned_set


def select_tags(probs, tags_data: List[dict], config: dict, banned_set: set) -> List[str]:
    """Soglie, esclusione rating/bannati, garanzia tag minimi e limite massimo."""
    gen_thresh = config["gen_thresh"]
    char_thresh = config["char_thresh"]
    min_tags = config.get("min_tags", 10)
    max_tags = config.get("max_tags", 0)
    replace_under = config["replace_under"]
    exclude_ratings = config["exclude_ratings"]

    character_tags = []
    general_tags = []

    # 1. Filtro primario per soglia
    for tag_idx, prob in enumerate(probs):
        info = tags_data[tag_idx]
        cat = info["category"]
        tag_name = info["name"]
        tag_lower = tag_name.lower()

        if exclude_ratings and (cat in ("2", "9") or tag_lower in RATING_TAGS):
            continue

        if tag_lower in banned_set or tag_lower.replace("_", " ") in banned_set:
            continue

        thresh = char_thresh if cat == "1" else gen_thresh

        if prob >= thresh:
            clean_tag = tag_name.replace("_", " ") if replace_under else tag_name
            if cat == "1":
                character_tags.append((prob, clean_tag))
            else:
                general_tags.append((prob, clean_tag))

    character_tags.sort(key=lambda x: x[0], reverse=True)
    general_tags.sort(key=lambda x: x[0], reverse=True)

    final_tags = [t[1] for t in character_tags] + [t[1] for t in general_tags]

    # 2. Garanzia Tag Minimi
    if min_tags > 0 and len(final_tags) < min_tags:
        candidates = []
        for tag_idx, prob in enumerate(probs):
            info = tags_data[tag_idx]
            cat = info["category"]
            tag_name = info["name"]
            tag_lower = tag_name.lower()

            if exclude_ratings and (cat in ("2", "9") or tag_lower in RATING_TAGS):
                continue
            if tag_lower in banned_set or tag_lower.replace("_", " ") in banned_set:
                continue

            clean_tag = tag_name.replace("_", " ") if replace_under else tag_name
            candidates.append((prob, clean_tag))

        candidates.sort(key=lambda x: x[0], reverse=True)

        already_selected = set(final_tags)
        for prob, clean_tag in candidates:
            if len(final_tags) >= min_tags:
                break
            if clean_tag not in already_selected:
                final_tags.append(clean_tag)
                already_selected.add(clean_tag)

    # 3. Limite Massimo Tag
    if max_tags > 0 and len(final_tags) > max_tags:
        final_tags = final_tags[:max_tags]

    return final_tags


def assemble_caption(final_tags: List[str], config: dict) -> str:
    """Trigger Word, Prepend, Tag Modello, Postpend (senza duplicati)."""
    trigger_word = config["trigger_word"]
    prepend_tags_raw = config.get("prepend_tags", [])
    postpend_tags_raw = config.get("postpend_tags", [])

    existing_lower = set()
    assembled_tags = []

    if trigger_word:
        assembled_tags.append(trigger_word)
        existing_lower.add(trigger_word.lower())

    for pt in prepend_tags_raw:
        if pt and pt.lower() not in existing_lower:
            assembled_tags.append(pt)
            existing_lower.add(pt.lower())

    for tag in final_tags:
        if tag.lower() not in existing_lower:
            assembled_tags.append(tag)
            existing_lower.add(tag.lower())

    for pt in postpend_tags_raw:
        if pt and pt.lower() not in existing_lower:
            assembled_tags.append(pt)
            existing_lower.add(pt.lower())

    return ", ".join(assembled_tags)


def merge_append(old_content: str, final_tags: List[str]) -> Tuple[str, int, int]:
    """Logica Append: mantiene i tag esistenti e aggiunge solo i nuovi. Ritorna (testo, n_esistenti, n_nuovi)."""
    existing_tags = [t.strip() for t in old_content.split(",") if t.strip()]
    existing_lower = {t.lower() for t in existing_tags}
    new_tags = [t for t in final_tags if t.lower() not in existing_lower]
    return ", ".join(existing_tags + new_tags), len(existing_tags), len(new_tags)


def tag_image(model: WD14Model, image, target_size: int, config: dict, banned_set: Optional[set] = None):
    """Pipeline completa su una singola immagine. Ritorna (final_tags, caption_assemblata, immagine_ridimensionata)."""
    if banned_set is None:
        banned_set = build_banned_set(config.get("banned_tags", []))
    _, img_tensor, resized = preprocess_image(image, target_size)
    probs = infer_probs(model.session, img_tensor)
    final_tags = select_tags(probs, model.tags_data, config, banned_set)
    return final_tags, assemble_caption(final_tags, config), resized
