# Image Dataset Studio — Copyright (C) 2026 Mauro Liistro
# SPDX-License-Identifier: AGPL-3.0-only
"""Scheda Analisi Singola Immagine / Estrazione Prompt: nessun salvataggio su disco."""
import os
from datetime import datetime
from typing import Optional

from PIL import Image
from PySide6.QtCore import Qt, QSize, Signal
from PySide6.QtGui import QPixmap, QIcon, QFont, QGuiApplication, QKeySequence, QShortcut, QImage
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGroupBox, QLabel, QPushButton, QRadioButton, QButtonGroup,
    QCheckBox, QTextEdit, QListWidget, QListWidgetItem, QFileDialog, QMessageBox, QSplitter
)

from ..config import IMAGE_EXTENSIONS, AVAILABLE_MODELS, VLM_MODELS
from ..i18n import tr
from ..images import flatten_to_rgb
from ..model_manager import manager
from ..workers import SingleAnalysisThread
from .dataset_source import image_file_filter
from .widgets import ZoomableImageView

HISTORY_SIZE = 20
MODE_LABELS = {"tags": "single.mode_tags_short", "caption": "single.mode_caption_short", "both": "single.mode_both_short"}


def qimage_to_pil(qimg: QImage) -> Image.Image:
    # RGBA8888 conserva l'alfa, che flatten_to_rgb compone su bianco
    qimg = qimg.convertToFormat(QImage.Format.Format_RGBA8888)
    ptr = qimg.constBits()
    data = bytes(ptr)[: qimg.bytesPerLine() * qimg.height()]
    img = Image.frombuffer("RGBA", (qimg.width(), qimg.height()), data, "raw", "RGBA", qimg.bytesPerLine(), 1)
    return flatten_to_rgb(img)


class DropImageView(ZoomableImageView):
    """Anteprima che accetta il trascinamento di un file immagine."""
    file_dropped = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dragMoveEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event):
        for url in event.mimeData().urls():
            path = url.toLocalFile()
            if os.path.splitext(path)[1].lower() in IMAGE_EXTENSIONS:
                self.file_dropped.emit(path)
                event.acceptProposedAction()
                return


class SingleImageTab(QWidget):
    log_signal = Signal(str)

    def __init__(self, tag_tab, caption_tab, parent=None):
        super().__init__(parent)
        # Le impostazioni WD14 e VLM vengono lette dalle schede Batch
        self.tag_tab = tag_tab
        self.caption_tab = caption_tab
        self.current_image: Optional[Image.Image] = None
        self.current_name = ""
        self.history = []   # lista di dict, solo in memoria
        self.worker = None
        self._build_ui()

        QShortcut(QKeySequence.StandardKey.Paste, self).activated.connect(self.paste_from_clipboard)

    def _build_ui(self):
        root = QHBoxLayout(self)
        root.setContentsMargins(4, 4, 4, 4)
        splitter = QSplitter(Qt.Orientation.Horizontal)

        # --- Colonna sinistra: immagine ---
        left = QGroupBox(tr("single.image_box"))
        lv = QVBoxLayout(left)
        self.view = DropImageView()
        self.view.setMinimumSize(320, 320)
        self.view.setText(tr("single.drop_here"))
        self.view.file_dropped.connect(self.load_file)
        lv.addWidget(self.view)
        row = QHBoxLayout()
        btn_open = QPushButton(tr("single.open"))
        btn_open.clicked.connect(self.open_file)
        btn_paste = QPushButton(tr("single.paste"))
        btn_paste.clicked.connect(self.paste_from_clipboard)
        row.addWidget(btn_open)
        row.addWidget(btn_paste)
        lv.addLayout(row)
        self.lbl_image_name = QLabel(tr("common.no_image"))
        self.lbl_image_name.setStyleSheet("color: #aaaaaa;")
        lv.addWidget(self.lbl_image_name)
        splitter.addWidget(left)

        # --- Colonna centrale: opzioni e risultato ---
        center = QWidget()
        cv = QVBoxLayout(center)
        cv.setContentsMargins(0, 0, 0, 0)

        opts = QGroupBox(tr("single.what_box"))
        ov = QVBoxLayout(opts)
        self.mode_group = QButtonGroup(self)
        # Una scelta per riga: in tedesco o francese tre sulla stessa riga non entrano nella colonna
        modes_layout = QVBoxLayout()
        for key in ("tags", "caption", "both"):
            rb = QRadioButton(tr(f"single.mode_{key}"))
            rb.setProperty("mode", key)
            self.mode_group.addButton(rb)
            modes_layout.addWidget(rb)
            if key == "both":
                rb.setChecked(True)
        ov.addLayout(modes_layout)
        self.chk_rules = QCheckBox(tr("single.apply_rules"))
        ov.addWidget(self.chk_rules)
        self.lbl_models = QLabel("")
        self.lbl_models.setWordWrap(True)
        self.lbl_models.setStyleSheet("color: #aaaaaa; font-size: 11px;")
        self.lbl_models.setToolTip(tr("single.models_hint"))
        ov.addWidget(self.lbl_models)
        cv.addWidget(opts)

        self.btn_analyze = QPushButton(tr("single.analyze"))
        self.btn_analyze.setFixedHeight(40)
        self.btn_analyze.setStyleSheet("font-weight: bold; font-size: 13px;")
        self.btn_analyze.setEnabled(False)
        self.btn_analyze.clicked.connect(self.analyze)
        cv.addWidget(self.btn_analyze)

        self.lbl_status = QLabel(tr("common.ready"))
        self.lbl_status.setStyleSheet("font-weight: bold;")
        self.lbl_status.setWordWrap(True)
        cv.addWidget(self.lbl_status)

        res = QGroupBox(tr("single.result_box"))
        rv = QVBoxLayout(res)
        self.txt_result = QTextEdit()
        self.txt_result.setFont(QFont("Monospace", 10))
        self.txt_result.setPlaceholderText(tr("single.result_ph"))
        rv.addWidget(self.txt_result)
        self.btn_copy = QPushButton(tr("single.copy"))
        self.btn_copy.setFixedHeight(36)
        self.btn_copy.setStyleSheet("font-weight: bold; background-color: #0d6efd; color: white;")
        self.btn_copy.clicked.connect(self.copy_result)
        rv.addWidget(self.btn_copy)
        cv.addWidget(res, stretch=1)
        splitter.addWidget(center)

        # --- Colonna destra: storico della sessione ---
        hist = QGroupBox(tr("single.history_box", n=HISTORY_SIZE))
        hv = QVBoxLayout(hist)
        self.list_history = QListWidget()
        self.list_history.setIconSize(QSize(56, 56))
        self.list_history.itemClicked.connect(self._restore_history)
        hv.addWidget(self.list_history)
        btn_clear = QPushButton(tr("single.clear_history"))
        btn_clear.clicked.connect(self._clear_history)
        hv.addWidget(btn_clear)
        splitter.addWidget(hist)

        splitter.setSizes([420, 520, 260])
        root.addWidget(splitter)

    def showEvent(self, event):
        super().showEvent(event)
        self._update_models_label()

    def _update_models_label(self):
        wd = AVAILABLE_MODELS[self.tag_tab.combo_model.currentData()]["name"]
        vlm_label = VLM_MODELS[self.caption_tab.vlm_box.model_key()]["label"]
        self.lbl_models.setText(tr("single.models_in_use", wd14=wd, vlm=vlm_label))

    # ------------------------------------------------------------------
    def mode(self) -> str:
        button = self.mode_group.checkedButton()
        assert button is not None   # i pulsanti sono esclusivi e uno è selezionato alla costruzione
        return button.property("mode")

    def open_file(self):
        path, _ = QFileDialog.getOpenFileName(self, tr("single.open_title"), "", image_file_filter())
        if path:
            self.load_file(path)

    def load_file(self, path: str):
        try:
            with Image.open(path) as im:
                image = flatten_to_rgb(im)
        except Exception as e:
            QMessageBox.warning(self, tr("common.error"), tr("single.open_error", error=e))
            return
        self._set_image(image, os.path.basename(path), QPixmap(path))

    def paste_from_clipboard(self):
        if self.worker and self.worker.isRunning():
            return
        clipboard = QGuiApplication.clipboard()
        mime = clipboard.mimeData()
        # Con gli appunti vuoti (o senza proprietario, es. Wayland) Qt può restituire None
        if mime is None:
            self.lbl_status.setText(tr("single.no_clipboard_image"))
            return
        if mime.hasImage():
            qimg = clipboard.image()
            if not qimg.isNull():
                self._set_image(qimage_to_pil(qimg), tr("single.clipboard_image"), QPixmap.fromImage(qimg))
                return
        if mime.hasUrls():
            for url in mime.urls():
                if os.path.splitext(url.toLocalFile())[1].lower() in IMAGE_EXTENSIONS:
                    self.load_file(url.toLocalFile())
                    return
        self.lbl_status.setText(tr("single.no_clipboard_image"))

    def _set_image(self, image: Image.Image, name: str, pixmap: QPixmap):
        self.current_image = image
        self.current_name = name
        self.view.setPixmap(pixmap)
        self.lbl_image_name.setText(f"{name} — {image.width}×{image.height}")
        self.btn_analyze.setEnabled(True)
        self.lbl_status.setText(tr("single.image_ready"))

    # ------------------------------------------------------------------
    def analyze(self):
        if self.current_image is None or (self.worker and self.worker.isRunning()):
            return
        if manager.busy():
            QMessageBox.information(self, tr("common.busy_title"), tr("common.busy_body"))
            return
        mode = self.mode()
        if mode != "tags" and not self.caption_tab.vlm_box.ready_or_warn(self):
            return

        wd14_config = self.tag_tab.tagging_config()
        if not self.chk_rules.isChecked():
            wd14_config.update(trigger_word="", prepend_tags=[], postpend_tags=[])

        self._update_models_label()
        self.btn_analyze.setEnabled(False)
        self.lbl_status.setText(tr("single.analyzing"))
        self.worker = SingleAnalysisThread(
            self.current_image, mode,
            self.tag_tab.combo_model.currentData(), wd14_config,
            self.caption_tab.vlm_box.vlm_params(), self.caption_tab.vlm_box.vlm_config(),
        )
        self.worker.progress_signal.connect(lambda msg, _p: self.lbl_status.setText(msg))
        self.worker.log_signal.connect(self.log_signal)
        self.worker.result_signal.connect(lambda t, c: self._on_result(t, c, mode))
        self.worker.error_signal.connect(self._on_error)
        self.worker.finished.connect(lambda: self.btn_analyze.setEnabled(self.current_image is not None))
        manager.register_worker(self.worker)
        self.worker.start()

    def _on_result(self, tags: str, caption: str, mode: str):
        # Ordine richiesto: tag prima, descrizione naturale dopo
        prompt = "\n\n".join(p for p in (tags.strip(), caption.strip()) if p)
        self.txt_result.setPlainText(prompt)
        self.lbl_status.setText(tr("single.done"))
        self.log_signal.emit(tr("single.log_done", name=self.current_name, mode=tr(MODE_LABELS[mode])))
        self._add_history(prompt, mode)

    def _on_error(self, message: str):
        self.lbl_status.setText(tr("single.error_status"))
        self.log_signal.emit(tr("single.log_error", error=message))
        QMessageBox.critical(self, tr("single.error_title"), message)

    def copy_result(self):
        text = self.txt_result.toPlainText().strip()
        if not text:
            return
        QGuiApplication.clipboard().setText(text)
        self.lbl_status.setText(tr("single.copied"))

    # ------------------------------------------------------------------
    def _add_history(self, prompt: str, mode: str):
        # Copie ridotte per contenere la RAM (1536 = risoluzione massima di Anima)
        assert self.current_image is not None   # la cronologia si aggiorna solo dopo un'analisi
        stored = self.current_image.copy()
        stored.thumbnail((1536, 1536))
        thumb = stored.copy()
        thumb.thumbnail((256, 256))
        entry = {"image": stored, "thumb": thumb, "name": self.current_name,
                 "prompt": prompt, "mode": mode, "time": datetime.now().strftime("%H:%M:%S")}
        self.history.insert(0, entry)
        del self.history[HISTORY_SIZE:]
        self._refresh_history()

    def _refresh_history(self):
        self.list_history.clear()
        for i, e in enumerate(self.history):
            item = QListWidgetItem(f"{e['time']} · {tr(MODE_LABELS[e['mode']])}\n{e['name']}")
            data = e["thumb"].tobytes("raw", "RGB")
            qimg = QImage(data, e["thumb"].width, e["thumb"].height, e["thumb"].width * 3,
                          QImage.Format.Format_RGB888).copy()
            item.setIcon(QIcon(QPixmap.fromImage(qimg)))
            item.setToolTip(e["prompt"][:500])
            item.setData(Qt.ItemDataRole.UserRole, i)
            self.list_history.addItem(item)

    def _restore_history(self, item: QListWidgetItem):
        e = self.history[item.data(Qt.ItemDataRole.UserRole)]
        img = e["image"]
        data = img.tobytes("raw", "RGB")
        qimg = QImage(data, img.width, img.height, img.width * 3, QImage.Format.Format_RGB888).copy()
        self._set_image(img, e["name"], QPixmap.fromImage(qimg))
        self.txt_result.setPlainText(e["prompt"])
        self.lbl_status.setText(tr("single.restored", time=e['time']))

    def _clear_history(self):
        self.history.clear()
        self.list_history.clear()
