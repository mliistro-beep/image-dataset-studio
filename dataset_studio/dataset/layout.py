# Image Dataset Studio — Copyright (C) 2026 Mauro Liistro
# SPDX-License-Identifier: AGPL-3.0-only
"""Struttura cartelle del dataset: original_dataset / dataset_tags / dataset_captions.

Regole:
- original_dataset è la fonte di verità e contiene solo immagini con nome sequenziale NNN.ext
- dataset_tags e dataset_captions contengono copie con lo stesso nome + il relativo .txt
- le immagini nuove ricevono il numero successivo all'ultimo presente
"""
import csv
import os
import re
import shutil
from datetime import datetime
from typing import List, Optional, Tuple

from ..config import IMAGE_EXTENSIONS, ORIGINAL_DIR, TAGS_DIR, CAPTIONS_DIR, RENAME_MAP_FILE
from ..i18n import tr

SEQ_NAME_RE = re.compile(r"^\d{3,}$")
# Altre estensioni immagine riconosciute ma non supportate: vanno segnalate, non ignorate
OTHER_IMAGE_EXTENSIONS = {".bmp", ".gif", ".tif", ".tiff", ".avif", ".heic", ".jxl"}
# File ammessi in original_dataset oltre alle immagini
ALLOWED_EXTRA_FILES = {RENAME_MAP_FILE}


class DatasetLayoutError(Exception):
    """Errore bloccante sulla struttura del dataset (nomi non conformi, ecc.)."""

    def __init__(self, errors: List[str]):
        self.errors = errors
        super().__init__("\n".join(errors))


def is_image(filename: str) -> bool:
    return os.path.splitext(filename)[1].lower() in IMAGE_EXTENSIONS


def list_images(folder: str) -> List[str]:
    if not os.path.isdir(folder):
        return []
    return sorted(f for f in os.listdir(folder)
                  if os.path.isfile(os.path.join(folder, f)) and is_image(f))


def natural_key(path: str) -> List[object]:
    """Chiave di ordinamento "umana": img2 prima di img10, senza distinguere maiuscole."""
    return [int(part) if part.isdigit() else part.casefold() for part in re.split(r"(\d+)", path)]


def seq_name(index: int, ext: str) -> str:
    return f"{index:03d}{ext.lower()}"


def txt_name(image_name: str) -> str:
    return os.path.splitext(image_name)[0] + ".txt"


def resolve_base_dir(folder: str) -> Optional[str]:
    """Se `folder` è (o è dentro) un dataset strutturato ritorna la cartella base, altrimenti None."""
    folder = os.path.abspath(folder)
    if os.path.basename(folder) in (ORIGINAL_DIR, TAGS_DIR, CAPTIONS_DIR):
        parent = os.path.dirname(folder)
        if os.path.isdir(os.path.join(parent, ORIGINAL_DIR)):
            return parent
    if os.path.isdir(os.path.join(folder, ORIGINAL_DIR)):
        return folder
    return None


def paths_for(base_dir: str) -> Tuple[str, str, str]:
    return (os.path.join(base_dir, ORIGINAL_DIR),
            os.path.join(base_dir, TAGS_DIR),
            os.path.join(base_dir, CAPTIONS_DIR))


def validate_original(original_dir: str) -> Tuple[List[str], List[str]]:
    """Controlla i nomi in original_dataset. Ritorna (errori_bloccanti, avvisi)."""
    errors: List[str] = []
    warnings: List[str] = []

    if not os.path.isdir(original_dir):
        return [tr("layout.dir_not_found", path=original_dir)], []

    stems = {}
    for f in sorted(os.listdir(original_dir)):
        full = os.path.join(original_dir, f)
        if not os.path.isfile(full) or f in ALLOWED_EXTRA_FILES or f.startswith("."):
            continue
        stem, ext = os.path.splitext(f)
        ext_l = ext.lower()

        if ext_l == ".txt":
            continue
        if ext_l in OTHER_IMAGE_EXTENSIONS:
            errors.append(tr("layout.unsupported_format", f=f, exts=", ".join(sorted(IMAGE_EXTENSIONS))))
            continue
        if ext_l not in IMAGE_EXTENSIONS:
            continue
        if not SEQ_NAME_RE.match(stem):
            errors.append(tr("layout.bad_name", f=f, ext=ext_l))
            continue
        index = int(stem)
        if stem != f"{index:03d}":
            errors.append(tr("layout.bad_padding", f=f, correct=seq_name(index, ext_l)))
            continue
        if index in stems:
            errors.append(tr("layout.duplicate", f=f, other=stems[index]))
            continue
        stems[index] = f

    for f in sorted(os.listdir(original_dir)):
        stem, ext = os.path.splitext(f)
        if ext.lower() == ".txt" and SEQ_NAME_RE.match(stem) and int(stem) not in stems:
            warnings.append(tr("layout.orphan_txt", f=f))

    if stems:
        missing = sorted(set(range(min(stems), max(stems) + 1)) - set(stems))
        if missing:
            preview = ", ".join(f"{m:03d}" for m in missing[:15]) + ("..." if len(missing) > 15 else "")
            warnings.append(tr("layout.gaps", missing=preview))

    return errors, warnings


def next_index(original_dir: str) -> int:
    indices = [int(os.path.splitext(f)[0]) for f in list_images(original_dir)
               if SEQ_NAME_RE.match(os.path.splitext(f)[0])]
    return max(indices) + 1 if indices else 0


def _append_rename_map(original_dir: str, rows: List[Tuple[str, str]]):
    map_path = os.path.join(original_dir, RENAME_MAP_FILE)
    new_file = not os.path.exists(map_path)
    stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(map_path, "a", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        if new_file:
            writer.writerow(["new_name", "original_file", "imported_at"])
        for new_name, src in rows:
            writer.writerow([new_name, src, stamp])


def _copy_numbered(src_paths: List[str], original_dir: str, start: int) -> List[str]:
    os.makedirs(original_dir, exist_ok=True)
    created = []
    rows = []
    for offset, src in enumerate(src_paths):
        new_name = seq_name(start + offset, os.path.splitext(src)[1])
        shutil.copy2(src, os.path.join(original_dir, new_name))
        # Un eventuale .txt accanto all'immagine sorgente la segue con lo stesso numero
        src_txt = os.path.splitext(src)[0] + ".txt"
        if os.path.exists(src_txt):
            shutil.copy2(src_txt, os.path.join(original_dir, txt_name(new_name)))
        created.append(new_name)
        rows.append((new_name, src))
    _append_rename_map(original_dir, rows)
    return created


def first_import(src_paths: List[str], base_dir: str) -> List[str]:
    """Crea original_dataset copiando e rinominando in sequenza le immagini sorgente (che restano intatte)."""
    original_dir = os.path.join(base_dir, ORIGINAL_DIR)
    if list_images(original_dir):
        raise DatasetLayoutError([tr("layout.already_has_images", path=original_dir)])
    return _copy_numbered(sorted(src_paths, key=natural_key), original_dir, 0)


def import_new_images(src_paths: List[str], base_dir: str) -> List[str]:
    """Aggiunge immagini a un dataset esistente, numerandole dopo l'ultima presente."""
    original_dir = os.path.join(base_dir, ORIGINAL_DIR)
    errors, _ = validate_original(original_dir)
    if errors:
        raise DatasetLayoutError(errors)
    bad = [p for p in src_paths if not is_image(p)]
    if bad:
        raise DatasetLayoutError([tr("layout.import_bad_format", f=os.path.basename(p)) for p in bad])
    return _copy_numbered(sorted(src_paths, key=natural_key), original_dir, next_index(original_dir))


def pending_images(original_dir: str, target_dir: str, reprocess_all: bool) -> List[str]:
    """Immagini di original_dataset da elaborare: quelle senza .txt nella cartella target (o tutte)."""
    images = list_images(original_dir)
    if reprocess_all:
        return images
    return [f for f in images if not os.path.exists(os.path.join(target_dir, txt_name(f)))]


def sync_image(image_name: str, original_dir: str, target_dir: str, seed_txt: bool):
    """Copia l'immagine nella cartella target. Con seed_txt copia anche il .txt di original_dataset
    se nella target non esiste ancora (utile per la modalità Append)."""
    os.makedirs(target_dir, exist_ok=True)
    src = os.path.join(original_dir, image_name)
    dst = os.path.join(target_dir, image_name)
    if not os.path.exists(dst) or os.path.getmtime(src) > os.path.getmtime(dst):
        shutil.copy2(src, dst)
    if seed_txt:
        src_txt = os.path.join(original_dir, txt_name(image_name))
        dst_txt = os.path.join(target_dir, txt_name(image_name))
        if os.path.exists(src_txt) and not os.path.exists(dst_txt):
            shutil.copy2(src_txt, dst_txt)


def find_source_images(folder: str) -> List[str]:
    """Immagini (path assoluti) in una cartella non strutturata, per il primo import."""
    return [os.path.join(folder, f) for f in list_images(folder)]
