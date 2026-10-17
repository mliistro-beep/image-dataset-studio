# Image Dataset Studio — Copyright (C) 2026 Mauro Liistro
# SPDX-License-Identifier: AGPL-3.0-only
"""Unico proprietario del modello in memoria: WD14 e VLM non vengono mai tenuti caricati insieme."""
import threading
from typing import Optional

from PySide6.QtCore import QObject, Signal

from .config import AVAILABLE_MODELS, VLM_MODELS
from .engines import wd14, vlm
from .i18n import tr


class ModelManager(QObject):
    # Testo descrittivo del modello attualmente in memoria (vuoto se nessuno)
    status_changed = Signal(str)

    def __init__(self):
        super().__init__()
        self._lock = threading.RLock()
        self.kind: Optional[str] = None   # None | "wd14" | "vlm"
        self.key: Optional[str] = None
        self.model = None
        self._workers = []

    def register_worker(self, worker):
        """Tiene traccia dei thread che usano i modelli: uno solo alla volta può lavorare."""
        self._workers = [w for w in self._workers if w.isRunning()] + [worker]

    def busy(self) -> bool:
        return any(w.isRunning() for w in self._workers)

    def is_loaded(self, kind: str, key: str) -> bool:
        return self.kind == kind and self.key == key and self.model is not None

    def unload(self, log_cb=None):
        with self._lock:
            if self.model is None:
                return
            label = self.describe()
            try:
                self.model.unload()
            finally:
                self.model = None
                self.kind = None
                self.key = None
                vlm.free_torch_memory()
            if log_cb:
                log_cb(tr("manager.unloaded", model=label))
            self.status_changed.emit("")

    def get_wd14(self, model_title: str, progress_cb, log_cb, should_stop) -> Optional[wd14.WD14Model]:
        """Ritorna il modello WD14 richiesto, scaricando prima qualsiasi altro modello. None se interrotto."""
        with self._lock:
            if self.is_loaded("wd14", model_title):
                return self.model
            self.unload(log_cb)

            paths = wd14.ensure_model_files(AVAILABLE_MODELS[model_title]["repo"], progress_cb, log_cb, should_stop)
            if paths is None:
                return None

            progress_cb(tr("manager.onnx_init"), 100.0)
            log_cb(tr("manager.onnx_loading"))
            self.model = wd14.WD14Model(*paths)
            self.kind, self.key = "wd14", model_title
            self.status_changed.emit(self.describe())
            return self.model

    def get_vlm(self, model_key: str, device: str, low_memory: bool, progress_cb, log_cb) -> vlm.VLMBackend:
        with self._lock:
            key = f"{model_key}@{device}{'-low' if low_memory else ''}"
            if self.is_loaded("vlm", key):
                return self.model
            self.unload(log_cb)

            missing = vlm.vlm_dependencies_missing()
            if missing:
                raise ImportError(missing)

            backend = vlm.create_backend(model_key, device, low_memory)
            try:
                backend.load(log_cb, progress_cb)
            except Exception:
                backend.unload()
                raise
            self.model = backend
            self.kind, self.key = "vlm", key
            self.status_changed.emit(self.describe())
            return self.model

    def describe(self) -> str:
        if self.model is None:
            return ""
        if self.kind == "wd14":
            return f"WD14 · {AVAILABLE_MODELS[self.key]['name']}"
        model_key, device = self.key.split("@")
        return f"VLM · {VLM_MODELS[model_key]['label']} [{device.upper()}]"


# Istanza unica condivisa da tutte le schede
manager = ModelManager()
