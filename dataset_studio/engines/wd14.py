# Image Dataset Studio — Copyright (C) 2026 Mauro Liistro
# SPDX-License-Identifier: AGPL-3.0-only
"""Motore WD14: logica estratta 1:1 da BatchTaggingThread / ModelLoaderThread dello script originale."""
import csv
import hashlib
import json
import os
import string
import time
import urllib.error
import urllib.request
from typing import Callable, List, Optional, Tuple

import numpy as np
from PIL import Image

from ..config import CACHE_BASE_DIR
from ..i18n import tr
from ..images import flatten_to_rgb

try:
    import onnxruntime as ort
except ImportError:
    ort = None

RATING_TAGS = {"general", "sensitive", "questionable", "explicit"}
DOWNLOAD_TIMEOUT_S = 30
DOWNLOAD_CHUNK_SIZE = 1024 * 512
VERIFY_TIMEOUT_S = 10
HASH_CHUNK_SIZE = 1024 * 1024
VERIFIED_SUFFIX = ".verified"
HTTP_HEADERS = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) WD14-AutoTagger/2.0"}


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
    req = urllib.request.Request(url, headers=HTTP_HEADERS)

    try:
        _stream_to_file(req, tmp_path, file_desc, progress_cb, log_cb, should_stop)
        os.replace(tmp_path, dest_path)
    except BaseException:
        # Errore di rete, Stop o rename fallito: niente .tmp a metà nella cache.
        # Una pulizia fallita non deve sostituire l'errore originale (uno Stop diventerebbe un errore)
        try:
            os.remove(tmp_path)
        except OSError:
            pass
        raise


def _stream_to_file(req: urllib.request.Request, tmp_path: str, file_desc: str,
                    progress_cb: Callable[[str, float], None],
                    log_cb: Callable[[str], None],
                    should_stop: Callable[[], bool]) -> None:
    # Il timeout vale per la connessione e per ogni lettura: una rete bloccata non blocca il worker per sempre
    with urllib.request.urlopen(req, timeout=DOWNLOAD_TIMEOUT_S) as response, open(tmp_path, "wb") as out_file:
        total_size = int(response.headers.get("Content-Length", 0))
        bytes_downloaded = 0
        start_time = time.time()
        last_log_time = 0.0

        while True:
            if should_stop():
                raise InterruptedError(tr("wd14.download_cancelled"))

            chunk = response.read(DOWNLOAD_CHUNK_SIZE)
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

    # Connessione chiusa prima della fine: il file sarebbe un modello troncato
    if total_size > 0 and bytes_downloaded != total_size:
        raise OSError(tr("wd14.download_incomplete", file=file_desc, done=bytes_downloaded, total=total_size))


# ---------------------------------------------------------------------------
# Verifica della cache: i file scaricati prima del controllo su Content-Length possono essere troncati
# ---------------------------------------------------------------------------

class _NoRedirect(urllib.request.HTTPRedirectHandler):
    # HF mette x-linked-etag sulla prima risposta (302/307): seguendo il redirect si perderebbe
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _head_headers(url: str):
    req = urllib.request.Request(url, method="HEAD", headers=HTTP_HEADERS)
    opener = urllib.request.build_opener(_NoRedirect)
    try:
        with opener.open(req, timeout=VERIFY_TIMEOUT_S) as response:
            return response.headers
    except urllib.error.HTTPError as e:
        e.close()
        if 300 <= e.code < 400:
            return e.headers
        raise


def normalize_etag(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    value = value.strip()
    if value.startswith("W/"):
        value = value[2:]
    return value.strip('"').lower()


def _is_supported_digest(digest: Optional[str]) -> bool:
    return digest is not None and len(digest) in (40, 64) and all(c in string.hexdigits for c in digest)


def file_matches_digest(path: str, digest: str, should_stop: Callable[[], bool]) -> bool:
    """HF usa lo sha256 del contenuto per i file LFS e lo sha1 del blob git per i file normali."""
    if len(digest) == 64:
        hasher = hashlib.sha256()
    else:
        # sha1 per confrontarlo con l'id del blob git di HF, non come protezione crittografica
        hasher = hashlib.sha1(usedforsecurity=False)
        hasher.update(b"blob %d\0" % os.path.getsize(path))

    with open(path, "rb") as f:
        while chunk := f.read(HASH_CHUNK_SIZE):
            if should_stop():
                raise InterruptedError(tr("wd14.verify_cancelled"))
            hasher.update(chunk)
    return hasher.hexdigest() == digest.lower()


def is_marked_verified(path: str) -> bool:
    """Il marcatore vale solo se il file ha ancora la dimensione verificata."""
    try:
        with open(path + VERIFIED_SUFFIX, "r", encoding="utf-8") as f:
            marker = json.load(f)
        return marker["size"] == os.path.getsize(path)
    except (OSError, ValueError, KeyError, TypeError):
        return False


def _mark_verified(path: str, digest: str, log_cb: Callable[[str], None]) -> None:
    try:
        with open(path + VERIFIED_SUFFIX, "w", encoding="utf-8") as f:
            json.dump({"size": os.path.getsize(path), "etag": digest}, f)
    except OSError as e:
        # Non blocca il tagging: al prossimo avvio la verifica si ripete
        log_cb(tr("wd14.verify_mark_failed", file=os.path.basename(path), error=e))


def _fetch_digest(url: str, file_desc: str, log_cb: Callable[[str], None]) -> Optional[str]:
    """Hash atteso del file su HF, oppure None (con un avviso) se non si può ottenere."""
    try:
        headers = _head_headers(url)
    except OSError as e:
        log_cb(tr("wd14.verify_unavailable", file=file_desc, error=e))
        return None
    digest = normalize_etag(headers.get("X-Linked-Etag") or headers.get("ETag"))
    if not _is_supported_digest(digest):
        log_cb(tr("wd14.verify_unsupported", file=file_desc))
        return None
    return digest


def _ensure_file(url: str, path: str, file_desc: str, downloading_msg: str, cached_msg: str,
                 progress_cb, log_cb, should_stop) -> None:
    if is_marked_verified(path):
        log_cb(cached_msg)
        return

    digest = _fetch_digest(url, file_desc, log_cb)
    if os.path.exists(path) and os.path.getsize(path) > 0:
        if digest is None:
            # Senza rete si lavora con la cache; la verifica si ripete al prossimo avvio
            log_cb(cached_msg)
            log_cb(tr("wd14.cache_unverified", file=file_desc))
            return
        log_cb(tr("wd14.verifying", file=file_desc))
        if file_matches_digest(path, digest, should_stop):
            _mark_verified(path, digest, log_cb)
            log_cb(cached_msg)
            return
        log_cb(tr("wd14.cache_corrupt", file=file_desc))

    log_cb(downloading_msg)
    download_file(url, path, file_desc, progress_cb, log_cb, should_stop)
    if digest is None:
        return
    if not file_matches_digest(path, digest, should_stop):
        try:
            os.remove(path)
        except OSError:
            pass  # senza marcatore il file verrà comunque riverificato e riscaricato
        raise OSError(tr("wd14.download_corrupt", file=file_desc))
    _mark_verified(path, digest, log_cb)


def ensure_model_files(repo_id: str, progress_cb, log_cb, should_stop) -> Optional[Tuple[str, str]]:
    """Scarica model.onnx e selected_tags.csv se mancanti o danneggiati. Ritorna None se interrotto."""
    os.makedirs(CACHE_BASE_DIR, exist_ok=True)
    base_url = f"https://huggingface.co/{repo_id}/resolve/main/"
    onnx_path, csv_path = model_paths(repo_id)

    files = (
        ("model.onnx", onnx_path, tr("wd14.downloading_onnx"), tr("wd14.onnx_cached")),
        ("selected_tags.csv", csv_path, tr("wd14.downloading_csv"), tr("wd14.csv_cached")),
    )
    for name, path, downloading_msg, cached_msg in files:
        _ensure_file(base_url + name, path, name, downloading_msg, cached_msg, progress_cb, log_cb, should_stop)
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
        # Il provider effettivo: se CUDA non si inizializza (es. cuDNN mancante) onnxruntime ripiega sulla CPU
        self.provider = self.session.get_providers()[0]

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
        img = flatten_to_rgb(img_path_or_pil)
    else:
        with Image.open(img_path_or_pil) as im:
            img = flatten_to_rgb(im)

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
        for _prob, clean_tag in candidates:
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


def merge_append(old_content: str, final_tags: List[str], config: Optional[dict] = None) -> Tuple[str, int, int]:
    """Logica Append: mantiene i tag esistenti e aggiunge solo i nuovi. Ritorna (testo, n_esistenti, n_nuovi).
    Trigger Word e Prepend mancanti vanno in testa, Postpend in coda, come nella modalità Sovrascrivi."""
    config = config or {}
    existing_tags = [t.strip() for t in old_content.split(",") if t.strip()]
    seen = {t.lower() for t in existing_tags}

    def take_new(tags):
        added = []
        for t in tags:
            if t and t.lower() not in seen:
                added.append(t)
                seen.add(t.lower())
        return added

    trigger_word = config.get("trigger_word", "")
    front = take_new(([trigger_word] if trigger_word else []) + list(config.get("prepend_tags", [])))
    middle = take_new(final_tags)
    back = take_new(config.get("postpend_tags", []))
    new_count = len(front) + len(middle) + len(back)
    return ", ".join(front + existing_tags + middle + back), len(existing_tags), new_count


def tag_image(model: WD14Model, image, target_size: int, config: dict, banned_set: Optional[set] = None):
    """Pipeline completa su una singola immagine. Ritorna (final_tags, caption_assemblata, immagine_ridimensionata)."""
    if banned_set is None:
        banned_set = build_banned_set(config.get("banned_tags", []))
    _, img_tensor, resized = preprocess_image(image, target_size)
    probs = infer_probs(model.session, img_tensor)
    final_tags = select_tags(probs, model.tags_data, config, banned_set)
    return final_tags, assemble_caption(final_tags, config), resized
