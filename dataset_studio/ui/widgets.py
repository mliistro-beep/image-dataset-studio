# Image Dataset Studio — Copyright (C) 2026 Mauro Liistro
# SPDX-License-Identifier: AGPL-3.0-only
"""Widget riutilizzabili, copiati invariati dallo script originale, e caricamento miniature in background."""
import os
from typing import Dict, Iterable, Tuple

from PySide6.QtCore import Qt, QObject, QRunnable, QThreadPool, Signal, Slot
from PySide6.QtGui import QPixmap, QColor, QWheelEvent, QPainter, QImage, QImageReader
from PySide6.QtWidgets import QTableWidgetItem, QGraphicsView, QGraphicsScene, QGraphicsPixmapItem


class _ThumbnailTask(QRunnable):
    def __init__(self, loader: "ThumbnailLoader", generation: int, key: str, path: str, mtime: float):
        super().__init__()
        self.loader, self.generation, self.key, self.path, self.mtime = loader, generation, key, path, mtime

    def run(self):
        # QImage (a differenza di QPixmap) si può usare fuori dal thread della GUI.
        # setScaledSize fa decodificare i JPEG già ridotti: molto più veloce che caricare l'immagine intera.
        reader = QImageReader(self.path)
        reader.setAutoTransform(True)
        size = reader.size()
        if size.isValid():
            size.scale(self.loader.size, self.loader.size, Qt.AspectRatioMode.KeepAspectRatio)
            reader.setScaledSize(size)
        image = reader.read()
        self.loader._task_done.emit(self.generation, self.key, self.path, self.mtime, image)


class ThumbnailLoader(QObject):
    """Genera le miniature delle gallerie in un pool di thread, con cache per percorso e data di modifica.
    Ogni chiamata a load() annulla le richieste precedenti non ancora consegnate."""
    loaded = Signal(str, QImage)   # chiave, miniatura
    _task_done = Signal(int, str, str, float, QImage)

    def __init__(self, size: int, parent=None):
        super().__init__(parent)
        self.size = size
        self.generation = 0
        self._cache: Dict[str, Tuple[float, QImage]] = {}
        self._pool = QThreadPool(self)
        self._pool.setMaxThreadCount(max(1, min(4, QThreadPool.globalInstance().maxThreadCount() // 2)))
        self._task_done.connect(self._on_task_done)

    def load(self, items: Iterable[Tuple[str, str]]):
        """items: coppie (chiave, percorso). Le miniature in cache vengono consegnate subito."""
        self.generation += 1
        self._pool.clear()
        for key, path in items:
            try:
                mtime = os.path.getmtime(path)
            except OSError:
                continue
            cached = self._cache.get(path)
            if cached and cached[0] == mtime:
                self.loaded.emit(key, cached[1])
            else:
                self._pool.start(_ThumbnailTask(self, self.generation, key, path, mtime))

    @Slot(int, str, str, float, QImage)
    def _on_task_done(self, generation: int, key: str, path: str, mtime: float, image: QImage):
        if image.isNull():
            return
        self._cache[path] = (mtime, image)
        if generation == self.generation:
            self.loaded.emit(key, image)


class NumericTableWidgetItem(QTableWidgetItem):
    """QTableWidgetItem personalizzato per consentire un corretto ordinamento numerico."""
    def __lt__(self, other):
        try:
            val_self = self.data(Qt.ItemDataRole.UserRole)
            val_other = other.data(Qt.ItemDataRole.UserRole)
            if val_self is not None and val_other is not None:
                return float(val_self) < float(val_other)
        except (TypeError, ValueError):
            pass
        return super().__lt__(other)


class ZoomableImageView(QGraphicsView):
    """Widget personalizzato per mostrare immagini con supporto a Zoom, Pan e Reset."""
    def __init__(self, parent=None):
        super().__init__(parent)
        # Non `self.scene`: nasconderebbe il metodo QGraphicsView.scene()
        self._scene = QGraphicsScene(self)
        self.setScene(self._scene)

        self.pixmap_item = QGraphicsPixmapItem()
        self._scene.addItem(self.pixmap_item)

        # Impostazioni di visualizzazione fluide
        self.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        self.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setMinimumSize(220, 220)
        self.setStyleSheet("background-color: #1e1e1e; border: 1px solid #444;")

    def setPixmap(self, pixmap: QPixmap):
        self._scene.clear()
        self.pixmap_item = QGraphicsPixmapItem(pixmap)
        self._scene.addItem(self.pixmap_item)
        self._scene.setSceneRect(self.pixmap_item.boundingRect())
        self.reset_zoom()

    def reset_zoom(self):
        """Ripristina la trasformazione e adatta l'immagine alla dimensione della vista."""
        self.resetTransform()
        if not self._scene.sceneRect().isEmpty():
            self.fitInView(self._scene.sceneRect(), Qt.AspectRatioMode.KeepAspectRatio)

    def setText(self, text: str):
        # Fallback per azzerare o mostrare testi (es. "Nessuna foto")
        self._scene.clear()
        text_item = self._scene.addText(text)
        text_item.setDefaultTextColor(QColor(220, 220, 220))

    def wheelEvent(self, event: QWheelEvent):
        # Ctrl + Rotellina per Zoom in / Zoom out
        if event.modifiers() == Qt.KeyboardModifier.ControlModifier:
            zoom_in_factor = 1.15
            zoom_out_factor = 1.0 / zoom_in_factor

            if event.angleDelta().y() > 0:
                self.scale(zoom_in_factor, zoom_in_factor)
            else:
                self.scale(zoom_out_factor, zoom_out_factor)
        else:
            super().wheelEvent(event)

    def mouseDoubleClickEvent(self, event):
        """Doppio click per ripristinare lo zoom iniziale."""
        if event.button() == Qt.MouseButton.LeftButton:
            self.reset_zoom()
        super().mouseDoubleClickEvent(event)

    def keyPressEvent(self, event):
        """Scorciatoia da tastiera: Ctrl+R o R per il reset dello zoom."""
        if event.key() == Qt.Key.Key_R:
            self.reset_zoom()
        else:
            super().keyPressEvent(event)

    def resizeEvent(self, event):
        """Mantiene l'adattamento corretto se la finestra viene ridimensionata."""
        super().resizeEvent(event)
        # Se l'utente non ha applicato uno zoom manuale custom (matrice identità), adatta la scena
        if self.transform().isIdentity():
            self.reset_zoom()
