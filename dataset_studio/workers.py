# Image Dataset Studio — Copyright (C) 2026 Mauro Liistro
# SPDX-License-Identifier: AGPL-3.0-only
"""Thread di lavoro: caricamento modelli, batch tag, batch caption, analisi singola immagine."""
import os
import time
from datetime import datetime, timedelta
from typing import List, Optional

from PIL import Image
from PySide6.QtCore import QThread, Signal
from PySide6.QtGui import QImage

from .config import AVAILABLE_MODELS
from .dataset import layout
from .engines import wd14
from .i18n import tr
from .images import flatten_to_rgb
from .model_manager import manager


def pil_to_qimage(img: Image.Image, max_side: Optional[int] = None) -> QImage:
    img = img.convert("RGB")
    if max_side:
        img = img.copy()
        img.thumbnail((max_side, max_side))
    data = img.tobytes("raw", "RGB")
    # copy(): il QImage non deve dipendere dal buffer Python una volta passato al thread della GUI
    return QImage(data, img.width, img.height, img.width * 3, QImage.Format.Format_RGB888).copy()


class EtaEstimator:
    """Media mobile esponenziale dei secondi per immagine; la prima immagine (warm-up) è esclusa."""

    def __init__(self, alpha: float = 0.3):
        self.alpha = alpha
        self.avg: Optional[float] = None
        self.samples = 0
        self.first: Optional[float] = None

    def update(self, seconds: float):
        self.samples += 1
        if self.samples == 1:
            self.first = seconds
            return
        self.avg = seconds if self.avg is None else self.alpha * seconds + (1 - self.alpha) * self.avg

    @property
    def per_image(self) -> Optional[float]:
        return self.avg if self.avg is not None else self.first

    def remaining(self, left: int) -> Optional[float]:
        per = self.per_image
        return None if per is None else per * left


def format_eta(current: int, total: int, per_image: float, remaining: float) -> str:
    if per_image is None or per_image <= 0:
        return tr("eta.image_only", current=current, total=total)
    finish = datetime.now() + timedelta(seconds=remaining)
    return tr("eta.full", current=current, total=total, per=f"{per_image:.1f}",
              remaining=format_duration(remaining), finish=finish.strftime('%H:%M'))


def format_duration(seconds: float) -> str:
    seconds = int(round(seconds))
    if seconds < 60:
        return f"{seconds} s"
    minutes, sec = divmod(seconds, 60)
    if minutes < 60:
        return f"{minutes} min {sec:02d} s"
    hours, minutes = divmod(minutes, 60)
    return f"{hours} h {minutes:02d} min"


class _BaseWorker(QThread):
    progress_signal = Signal(str, float)
    log_signal = Signal(str)

    def __init__(self):
        super().__init__()
        self.stop_requested = False

    def request_stop(self):
        self.stop_requested = True

    def _should_stop(self) -> bool:
        return self.stop_requested


class BatchTaggingThread(_BaseWorker):
    """Carica WD14 (scaricando prima eventuali altri modelli) ed elabora le immagini in dataset_tags."""
    # current, total, filename, testo, anteprima, n_tag, s/img, secondi_residui
    step_signal = Signal(int, int, str, str, QImage, int, float, float)
    model_ready_signal = Signal(str)
    finished_signal = Signal(int, dict, str)   # elaborate, statistiche, errore ("" se ok)

    def __init__(self, original_dir: str, target_dir: str, files: List[str], model_title: str, config: dict):
        super().__init__()
        self.original_dir = original_dir
        self.target_dir = target_dir
        self.files = files
        self.model_title = model_title
        self.config = config

    def run(self):
        stats = {"mode": self.config["write_mode"], "total_written": 0, "new_added": 0, "existing_kept": 0}
        try:
            model = manager.get_wd14(self.model_title, self.progress_signal.emit, self.log_signal.emit, self._should_stop)
        except InterruptedError:
            # Stop premuto durante il download: non è un errore
            self.finished_signal.emit(0, stats, "")
            return
        except Exception as e:
            self.finished_signal.emit(0, stats, tr("worker.model_load_error", error=e))
            return
        if model is None:
            self.finished_signal.emit(0, stats, "")
            return
        self.model_ready_signal.emit(model.provider)

        target_size = AVAILABLE_MODELS[self.model_title]["size"]
        write_mode = self.config["write_mode"]
        banned_set = wd14.build_banned_set(self.config.get("banned_tags", []))
        eta = EtaEstimator()
        total_files = len(self.files)
        processed_count = 0

        for idx, filename in enumerate(self.files):
            if self.stop_requested:
                break
            t0 = time.time()
            try:
                layout.sync_image(filename, self.original_dir, self.target_dir, seed_txt=True)
                img_path = os.path.join(self.target_dir, filename)
                final_tags, caption_str, resized = wd14.tag_image(model, img_path, target_size, self.config, banned_set)

                txt_filename = layout.txt_name(filename)
                txt_path = os.path.join(self.target_dir, txt_filename)
                tags_written_for_file = len(final_tags)

                if write_mode == "append" and os.path.exists(txt_path):
                    with open(txt_path, "r", encoding="utf-8") as f:
                        old_content = f.read().strip()
                    if old_content:
                        caption_str, num_existing, num_new = wd14.merge_append(old_content, final_tags, self.config)
                        num_total = num_existing + num_new
                        stats["existing_kept"] += num_existing
                        stats["new_added"] += num_new
                        stats["total_written"] += num_total
                        tags_written_for_file = num_total
                        self.log_signal.emit(tr("worker.tag_append", file=txt_filename, new=num_new,
                                                existing=num_existing, total=num_total))
                    else:
                        stats["total_written"] += len(final_tags)
                        stats["new_added"] += len(final_tags)
                        self.log_signal.emit(tr("worker.tag_append_empty", file=txt_filename, count=len(final_tags)))
                else:
                    stats["total_written"] += len(final_tags)
                    self.log_signal.emit(tr("worker.tag_overwrite", file=txt_filename, count=len(final_tags)))

                with open(txt_path, "w", encoding="utf-8") as f:
                    f.write(caption_str)

                processed_count += 1
                eta.update(time.time() - t0)
                left = total_files - (idx + 1)
                self.step_signal.emit(idx + 1, total_files, filename, caption_str, pil_to_qimage(resized),
                                      tags_written_for_file, eta.per_image or 0.0, eta.remaining(left) or 0.0)
            except Exception as e:
                self.log_signal.emit(tr("worker.file_error", file=filename, error=e))

        self.finished_signal.emit(processed_count, stats, "")


class BatchCaptionThread(_BaseWorker):
    step_signal = Signal(int, int, str, str, QImage, float, float)
    model_ready_signal = Signal(str)
    finished_signal = Signal(int, str)   # elaborate, errore ("" se ok)

    def __init__(self, original_dir: str, target_dir: str, files: List[str], vlm_params: dict, config: dict):
        super().__init__()
        self.original_dir = original_dir
        self.target_dir = target_dir
        self.files = files
        self.vlm_params = vlm_params
        self.config = config

    def run(self):
        p = self.vlm_params
        try:
            backend = manager.get_vlm(p["model_key"], p["device"], p["low_memory"],
                                      self.progress_signal.emit, self.log_signal.emit, self._should_stop)
        except InterruptedError:
            self.finished_signal.emit(0, "")
            return
        except Exception as e:
            self.finished_signal.emit(0, tr("worker.vlm_load_error", error=e))
            return
        self.model_ready_signal.emit(manager.describe())

        instruction = self.config["instruction"]
        max_tokens = self.config["max_tokens"]
        prefix = self.config["prefix"].strip()
        write_mode = self.config["write_mode"]
        eta = EtaEstimator()
        total_files = len(self.files)
        processed_count = 0

        for idx, filename in enumerate(self.files):
            if self.stop_requested:
                break
            t0 = time.time()
            try:
                layout.sync_image(filename, self.original_dir, self.target_dir, seed_txt=False)
                img_path = os.path.join(self.target_dir, filename)
                with Image.open(img_path) as im:
                    image = flatten_to_rgb(im)

                caption = backend.caption(image, instruction, max_tokens)
                if prefix:
                    caption = f"{prefix}, {caption}"

                txt_filename = layout.txt_name(filename)
                txt_path = os.path.join(self.target_dir, txt_filename)
                if write_mode == "append" and os.path.exists(txt_path):
                    with open(txt_path, "r", encoding="utf-8") as f:
                        old_content = f.read().strip()
                    if old_content:
                        caption = old_content + "\n" + caption
                    self.log_signal.emit(tr("worker.caption_append", file=txt_filename))
                else:
                    self.log_signal.emit(tr("worker.caption_overwrite", file=txt_filename, words=len(caption.split())))

                with open(txt_path, "w", encoding="utf-8") as f:
                    f.write(caption)

                processed_count += 1
                eta.update(time.time() - t0)
                left = total_files - (idx + 1)
                self.step_signal.emit(idx + 1, total_files, filename, caption, pil_to_qimage(image, 768),
                                      eta.per_image or 0.0, eta.remaining(left) or 0.0)
            except Exception as e:
                self.log_signal.emit(tr("worker.file_error", file=filename, error=e))

        self.finished_signal.emit(processed_count, "")


class SingleAnalysisThread(_BaseWorker):
    """Analisi al volo di una singola immagine, senza scrivere nulla su disco.
    I modelli vengono caricati uno alla volta: mai WD14 e VLM in memoria insieme."""
    result_signal = Signal(str, str)   # tag, descrizione
    error_signal = Signal(str)

    def __init__(self, image: Image.Image, mode: str, wd14_title: str, wd14_config: dict,
                 vlm_params: dict, vlm_config: dict):
        super().__init__()
        self.image = image
        self.mode = mode   # "tags" | "caption" | "both"
        self.wd14_title = wd14_title
        self.wd14_config = wd14_config
        self.vlm_params = vlm_params
        self.vlm_config = vlm_config

    def _run_tags(self) -> str:
        model = manager.get_wd14(self.wd14_title, self.progress_signal.emit, self.log_signal.emit, self._should_stop)
        if model is None:
            return ""
        self.progress_signal.emit(tr("worker.single_tagging"), 100.0)
        _, caption, _ = wd14.tag_image(model, self.image, AVAILABLE_MODELS[self.wd14_title]["size"], self.wd14_config)
        return caption

    def _run_caption(self) -> str:
        p = self.vlm_params
        backend = manager.get_vlm(p["model_key"], p["device"], p["low_memory"],
                                  self.progress_signal.emit, self.log_signal.emit, self._should_stop)
        self.progress_signal.emit(tr("worker.single_captioning"), 100.0)
        return backend.caption(self.image, self.vlm_config["instruction"], self.vlm_config["max_tokens"])

    def run(self):
        try:
            tags, caption = "", ""
            if self.mode == "tags":
                tags = self._run_tags()
            elif self.mode == "caption":
                caption = self._run_caption()
            else:
                # Se in memoria c'è già il VLM lo usiamo per primo: si risparmia un carico/scarico
                if manager.kind == "vlm":
                    caption = self._run_caption()
                    if not self.stop_requested:
                        tags = self._run_tags()
                else:
                    tags = self._run_tags()
                    if not self.stop_requested:
                        caption = self._run_caption()
            self.result_signal.emit(tags, caption)
        except Exception as e:
            self.error_signal.emit(str(e))
