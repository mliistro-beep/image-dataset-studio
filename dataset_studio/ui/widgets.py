# Image Dataset Studio — Copyright (C) 2026 Mauro Liistro
# SPDX-License-Identifier: AGPL-3.0-only
"""Widget riutilizzabili, copiati invariati dallo script originale."""
from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap, QColor, QWheelEvent, QPainter
from PySide6.QtWidgets import QTableWidgetItem, QGraphicsView, QGraphicsScene, QGraphicsPixmapItem


class NumericTableWidgetItem(QTableWidgetItem):
    """QTableWidgetItem personalizzato per consentire un corretto ordinamento numerico."""
    def __lt__(self, other):
        try:
            val_self = self.data(Qt.UserRole)
            val_other = other.data(Qt.UserRole)
            if val_self is not None and val_other is not None:
                return float(val_self) < float(val_other)
        except (TypeError, ValueError):
            pass
        return super().__lt__(other)


class ZoomableImageView(QGraphicsView):
    """Widget personalizzato per mostrare immagini con supporto a Zoom, Pan e Reset."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.scene = QGraphicsScene(self)
        self.setScene(self.scene)

        self.pixmap_item = QGraphicsPixmapItem()
        self.scene.addItem(self.pixmap_item)

        # Impostazioni di visualizzazione fluide
        self.setRenderHint(QPainter.SmoothPixmapTransform)
        self.setRenderHint(QPainter.Antialiasing)
        self.setDragMode(QGraphicsView.ScrollHandDrag)
        self.setAlignment(Qt.AlignCenter)
        self.setMinimumSize(220, 220)
        self.setStyleSheet("background-color: #1e1e1e; border: 1px solid #444;")

    def setPixmap(self, pixmap: QPixmap):
        self.scene.clear()
        self.pixmap_item = QGraphicsPixmapItem(pixmap)
        self.scene.addItem(self.pixmap_item)
        self.scene.setSceneRect(self.pixmap_item.boundingRect())
        self.reset_zoom()

    def reset_zoom(self):
        """Ripristina la trasformazione e adatta l'immagine alla dimensione della vista."""
        self.resetTransform()
        if not self.scene.sceneRect().isEmpty():
            self.fitInView(self.scene.sceneRect(), Qt.KeepAspectRatio)

    def setText(self, text: str):
        # Fallback per azzerare o mostrare testi (es. "Nessuna foto")
        self.scene.clear()
        text_item = self.scene.addText(text)
        text_item.setDefaultTextColor(QColor(220, 220, 220))

    def wheelEvent(self, event: QWheelEvent):
        # Ctrl + Rotellina per Zoom in / Zoom out
        if event.modifiers() == Qt.ControlModifier:
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
        if event.button() == Qt.LeftButton:
            self.reset_zoom()
        super().mouseDoubleClickEvent(event)

    def keyPressEvent(self, event):
        """Scorciatoia da tastiera: Ctrl+R o R per il reset dello zoom."""
        if event.key() == Qt.Key_R:
            self.reset_zoom()
        else:
            super().keyPressEvent(event)

    def resizeEvent(self, event):
        """Mantiene l'adattamento corretto se la finestra viene ridimensionata."""
        super().resizeEvent(event)
        # Se l'utente non ha applicato uno zoom manuale custom (matrice identità), adatta la scena
        if self.transform().isIdentity():
            self.reset_zoom()
