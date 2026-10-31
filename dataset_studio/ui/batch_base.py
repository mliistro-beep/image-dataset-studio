# Image Dataset Studio — Copyright (C) 2026 Mauro Liistro
# SPDX-License-Identifier: AGPL-3.0-only
"""Struttura comune alle schede Batch Tag e Batch Caption:
sidebar con sorgente dataset, avanzamento con ETA, galleria, anteprima ed editor del .txt."""
import os
from typing import Dict, List

from PySide6.QtCore import Qt, QSize, Signal
from PySide6.QtGui import QPixmap, QIcon, QImage, QFont
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGroupBox, QLabel, QPushButton, QTextEdit,
    QProgressBar, QSplitter, QListWidget, QListWidgetItem, QCheckBox, QMessageBox, QScrollArea, QFrame
)

from ..dataset import layout
from ..i18n import tr
from ..model_manager import manager
from ..workers import format_eta
from .dataset_source import DatasetSourceBox, show_layout_errors
from .widgets import ThumbnailLoader, ZoomableImageView


class BatchTabBase(QWidget):
    log_signal = Signal(str)

    # Chiavi i18n impostate dalle sottoclassi
    EDITOR_TITLE = ""
    EDITOR_PLACEHOLDER = ""
    START_LABEL = ""
    TARGET_LABEL = ""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.base_dir = ""
        self.gallery_files: List[str] = []
        self.gallery_rows: Dict[str, int] = {}
        self.current_selected_filename = ""
        self.last_loaded_text = ""
        self.is_processing = False
        self.worker = None
        self.thumbnails = ThumbnailLoader(48, self)
        self.thumbnails.loaded.connect(self._on_thumbnail_loaded)
        self._build_ui()

    # ------------------------------------------------------------------
    # Costruzione UI
    # ------------------------------------------------------------------
    def _build_ui(self):
        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(4, 4, 4, 4)

        sidebar = QWidget()
        self.sidebar_layout = QVBoxLayout(sidebar)
        self.sidebar_layout.setContentsMargins(5, 5, 5, 5)

        self.source_box = DatasetSourceBox(tr("batch.dataset_box"))
        self.source_box.log_signal.connect(self.log_signal)
        self.source_box.dataset_changed.connect(self._on_dataset_changed)
        self.sidebar_layout.addWidget(self.source_box)

        self.build_sidebar(self.sidebar_layout)

        self.chk_reprocess_all = QCheckBox(tr("batch.reprocess_all"))
        self.chk_reprocess_all.toggled.connect(self.refresh_summary)
        self.sidebar_layout.addWidget(self.chk_reprocess_all)

        self.btn_start = QPushButton(tr(self.START_LABEL))
        self.btn_start.setFixedHeight(40)
        self.btn_start.setEnabled(False)
        self.btn_start.setStyleSheet("font-weight: bold; font-size: 13px;")
        self.btn_start.clicked.connect(self.start_processing)
        self.sidebar_layout.addWidget(self.btn_start)

        self.btn_stop = QPushButton(tr("batch.stop"))
        self.btn_stop.setEnabled(False)
        self.btn_stop.clicked.connect(self.stop_operations)
        self.sidebar_layout.addWidget(self.btn_stop)
        self.sidebar_layout.addStretch()

        scroll = QScrollArea()
        scroll.setWidget(sidebar)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setFixedWidth(350)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        main_layout.addWidget(scroll)

        central_splitter = QSplitter(Qt.Orientation.Vertical)
        top_widget = QWidget()
        top_layout = QVBoxLayout(top_widget)
        top_layout.setContentsMargins(0, 0, 0, 0)
        top_layout.setSpacing(4)

        # Avanzamento + ETA ben visibile
        progress_layout = QHBoxLayout()
        self.lbl_progress_status = QLabel(tr("common.ready"))
        self.lbl_progress_status.setStyleSheet("font-weight: bold;")
        progress_layout.addWidget(self.lbl_progress_status)
        self.progress_bar = QProgressBar()
        self.progress_bar.setFixedHeight(14)
        self.progress_bar.setValue(0)
        progress_layout.addWidget(self.progress_bar)
        top_layout.addLayout(progress_layout)

        self.lbl_eta = QLabel("")
        self.lbl_eta.setStyleSheet("font-size: 15px; font-weight: bold; color: #ffcc00;")
        self.lbl_eta.setVisible(False)
        top_layout.addWidget(self.lbl_eta)

        preview_splitter = QSplitter(Qt.Orientation.Horizontal)

        box_gallery = QGroupBox(tr("batch.gallery"))
        box_gallery_layout = QVBoxLayout(box_gallery)
        self.list_gallery = QListWidget()
        self.list_gallery.setIconSize(QSize(48, 48))
        self.list_gallery.itemSelectionChanged.connect(self._on_gallery_selection_changed)
        box_gallery_layout.addWidget(self.list_gallery)
        nav_btns_layout = QHBoxLayout()
        btn_prev = QPushButton(tr("batch.prev"))
        btn_prev.clicked.connect(self._select_prev_image)
        btn_next = QPushButton(tr("batch.next"))
        btn_next.clicked.connect(self._select_next_image)
        nav_btns_layout.addWidget(btn_prev)
        nav_btns_layout.addWidget(btn_next)
        box_gallery_layout.addLayout(nav_btns_layout)
        self.lbl_gallery_count = QLabel(tr("common.no_image"))
        self.lbl_gallery_count.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_gallery_count.setStyleSheet("color: #888888; font-size: 11px;")
        box_gallery_layout.addWidget(self.lbl_gallery_count)
        preview_splitter.addWidget(box_gallery)

        box_preview = QGroupBox(tr("batch.preview"))
        box_preview_layout = QVBoxLayout(box_preview)
        box_preview_layout.setContentsMargins(6, 6, 6, 6)
        self.lbl_preview_img = ZoomableImageView()
        self.lbl_preview_img.setMinimumSize(280, 280)
        self.lbl_preview_img.setText(tr("common.no_image"))
        box_preview_layout.addWidget(self.lbl_preview_img)
        preview_splitter.addWidget(box_preview)

        box_text = QGroupBox(tr(self.EDITOR_TITLE))
        box_text_layout = QVBoxLayout(box_text)
        self.lbl_count_header = QLabel("")
        self.lbl_count_header.setStyleSheet("color: #00ff66; font-weight: bold; font-size: 11px;")
        box_text_layout.addWidget(self.lbl_count_header)
        self.txt_output = QTextEdit()
        self.txt_output.setFont(QFont("Monospace", 9))
        self.txt_output.setPlaceholderText(tr(self.EDITOR_PLACEHOLDER))
        self.txt_output.textChanged.connect(self._update_count_header)
        box_text_layout.addWidget(self.txt_output)
        self.btn_save_text = QPushButton(tr("batch.save"))
        self.btn_save_text.setStyleSheet("font-weight: bold; background-color: #0d6efd; color: white; padding: 6px;")
        self.btn_save_text.clicked.connect(self.save_current_text)
        box_text_layout.addWidget(self.btn_save_text)
        self.build_editor_extras(box_text_layout)
        self.lbl_save_status = QLabel(tr("batch.ready_to_edit"))
        self.lbl_save_status.setStyleSheet("color: #aaaaaa; font-size: 11px;")
        box_text_layout.addWidget(self.lbl_save_status)
        preview_splitter.addWidget(box_text)

        preview_splitter.setSizes([220, 380, 420])
        top_layout.addWidget(preview_splitter)
        central_splitter.addWidget(top_widget)

        extra = self.build_bottom_panel()
        if extra is not None:
            central_splitter.addWidget(extra)
            central_splitter.setStretchFactor(0, 5)
            central_splitter.setStretchFactor(1, 0)
            central_splitter.setCollapsible(0, False)

        self.central_page = central_splitter
        self.build_main_area(main_layout, central_splitter)

    # Hook per le sottoclassi ------------------------------------------

    def build_sidebar(self, layout_v: QVBoxLayout):
        pass

    def build_editor_extras(self, layout_v: QVBoxLayout):
        pass

    def build_bottom_panel(self):
        return None

    def build_main_area(self, main_layout: QHBoxLayout, central_widget: QWidget):
        main_layout.addWidget(central_widget, stretch=1)

    def count_text(self, text: str) -> str:
        return ""

    def target_dir(self) -> str:
        raise NotImplementedError

    def start_processing(self):
        raise NotImplementedError

    # ------------------------------------------------------------------
    # Dataset e galleria
    # ------------------------------------------------------------------
    def original_dir(self) -> str:
        return layout.paths_for(self.base_dir)[0] if self.base_dir else ""

    def set_dataset(self, base_dir: str):
        """Imposta il dataset senza riemettere il segnale (sincronizzazione fra schede)."""
        if self.is_processing or base_dir == self.base_dir:
            return
        self.source_box.set_base(base_dir, emit=False)
        self._load_dataset(base_dir)

    def _on_dataset_changed(self, base_dir: str):
        self._load_dataset(base_dir)

    def _load_dataset(self, base_dir: str):
        # Il dataset è già cambiato: si può solo salvare o scartare, non annullare
        self.maybe_save_text(allow_cancel=False)
        self.base_dir = base_dir
        self.refresh_gallery()
        self.refresh_summary()

    def refresh_summary(self):
        if not self.base_dir:
            self.source_box.set_summary(tr("source.none"))
            self._update_start_button()
            return
        images = layout.list_images(self.original_dir())
        pending = layout.pending_images(self.original_dir(), self.target_dir(), self.chk_reprocess_all.isChecked())
        self.source_box.set_summary(tr("batch.summary", name=os.path.basename(self.base_dir), images=len(images),
                                       target=self.TARGET_LABEL, pending=len(pending)))
        self._update_start_button()

    def refresh_gallery(self):
        self.maybe_save_text(allow_cancel=False)
        self.gallery_files = layout.list_images(self.original_dir()) if self.base_dir else []
        self.gallery_rows = {f: i for i, f in enumerate(self.gallery_files)}
        self.list_gallery.blockSignals(True)
        self.list_gallery.clear()
        for filename in self.gallery_files:
            self.list_gallery.addItem(QListWidgetItem(filename))
        self.list_gallery.blockSignals(False)
        self.thumbnails.load((f, os.path.join(self.original_dir(), f)) for f in self.gallery_files)

        self.current_selected_filename = ""
        self.last_loaded_text = ""
        if self.gallery_files:
            self.list_gallery.setCurrentRow(0)
            self._on_gallery_selection_changed()
        else:
            self.lbl_preview_img.setText(tr("common.no_image"))
            self.txt_output.setText("")
            self.lbl_gallery_count.setText("0 / 0")

    def _on_thumbnail_loaded(self, filename: str, image: QImage):
        row = self.gallery_rows.get(filename)
        item = self.list_gallery.item(row) if row is not None else None
        if item is not None and item.text() == filename:
            item.setIcon(QIcon(QPixmap.fromImage(image)))

    def _txt_path(self, filename: str) -> str:
        return os.path.join(self.target_dir(), layout.txt_name(filename))

    def _on_gallery_selection_changed(self):
        if self.is_processing:
            return
        if not self.maybe_save_text():
            # Il testo resta nell'editor: si torna all'immagine a cui appartiene
            row = self.gallery_rows.get(self.current_selected_filename)
            if row is not None:
                self.list_gallery.blockSignals(True)
                self.list_gallery.setCurrentRow(row)
                self.list_gallery.blockSignals(False)
            return

        current_item = self.list_gallery.currentItem()
        if not current_item or not self.base_dir:
            return

        filename = current_item.text()
        self.current_selected_filename = filename
        img_path = os.path.join(self.original_dir(), filename)
        txt_path = self._txt_path(filename)

        pixmap = QPixmap(img_path)
        if not pixmap.isNull():
            self.lbl_preview_img.setPixmap(pixmap)
        else:
            self.lbl_preview_img.setText(tr("batch.image_read_error"))

        content = ""
        if os.path.exists(txt_path):
            try:
                with open(txt_path, "r", encoding="utf-8") as f:
                    content = f.read()
            except Exception as e:
                content = tr("batch.txt_read_error", error=e)
        self.txt_output.setText(content)
        self.last_loaded_text = content

        row = self.list_gallery.currentRow()
        self.lbl_gallery_count.setText(tr("batch.image_n_of", n=row + 1, total=self.list_gallery.count()))
        state = "" if os.path.exists(txt_path) else tr("batch.not_processed")
        self.lbl_save_status.setText(tr("batch.active_file", path=f"{self.TARGET_LABEL}/{layout.txt_name(filename)}") + state)
        self.lbl_save_status.setStyleSheet("color: #aaaaaa; font-size: 11px;")
        self._update_count_header()

    def _select_prev_image(self):
        row = self.list_gallery.currentRow()
        if row > 0:
            self.list_gallery.setCurrentRow(row - 1)

    def _select_next_image(self):
        row = self.list_gallery.currentRow()
        if row < self.list_gallery.count() - 1:
            self.list_gallery.setCurrentRow(row + 1)

    def _update_count_header(self):
        self.lbl_count_header.setText(self.count_text(self.txt_output.toPlainText()))

    # ------------------------------------------------------------------
    # Salvataggio manuale e automatico
    # ------------------------------------------------------------------
    def _write_text(self, filename: str, text: str):
        # L'immagine deve esistere accanto al .txt nella cartella target
        layout.sync_image(filename, self.original_dir(), self.target_dir(), seed_txt=False)
        with open(self._txt_path(filename), "w", encoding="utf-8") as f:
            f.write(text)

    def save_current_text(self):
        if not self.current_selected_filename or not self.base_dir:
            return
        new_text = self.txt_output.toPlainText()
        txt_filename = layout.txt_name(self.current_selected_filename)
        try:
            self._write_text(self.current_selected_filename, new_text)
            self.last_loaded_text = new_text
            self.lbl_save_status.setText(tr("batch.saved", file=txt_filename))
            self.lbl_save_status.setStyleSheet("color: #00ff66; font-weight: bold; font-size: 11px;")
            self.log_signal.emit(tr("batch.log_saved", path=f"{self.TARGET_LABEL}/{txt_filename}"))
            self.refresh_summary()
        except Exception as e:
            self.lbl_save_status.setText(tr("batch.save_error", error=e))
            self.lbl_save_status.setStyleSheet("color: #ff4444; font-weight: bold; font-size: 11px;")

    def maybe_save_text(self, allow_cancel: bool = True) -> bool:
        """Salva il testo dell'editor se è cambiato. False se il salvataggio fallisce e l'utente sceglie di
        tenere il testo nell'editor (solo con allow_cancel)."""
        if not self.current_selected_filename or not self.base_dir or self.is_processing:
            return True
        current_text = self.txt_output.toPlainText()
        # Anche se il file era vuoto o assente: il testo scritto a mano non va perso cambiando immagine
        if current_text == self.last_loaded_text:
            return True
        txt_filename = layout.txt_name(self.current_selected_filename)
        try:
            self._write_text(self.current_selected_filename, current_text)
        except OSError as e:
            self.log_signal.emit(tr("batch.log_save_failed", file=txt_filename, error=e))
            return self._confirm_discard(txt_filename, e, allow_cancel)
        self.last_loaded_text = current_text
        self.log_signal.emit(tr("batch.log_autosaved", file=txt_filename))
        return True

    def _confirm_discard(self, txt_filename: str, error: OSError, allow_cancel: bool) -> bool:
        buttons = QMessageBox.StandardButton.Discard
        default = QMessageBox.StandardButton.Discard
        if allow_cancel:
            buttons |= QMessageBox.StandardButton.Cancel
            default = QMessageBox.StandardButton.Cancel
        answer = QMessageBox.warning(self, tr("batch.save_failed_title"),
                                     tr("batch.save_failed_body", file=txt_filename, error=error), buttons, default)
        if answer == QMessageBox.StandardButton.Cancel:
            return False
        # Scartato: un salvataggio successivo (es. refresh_gallery dopo il cambio di dataset, con base_dir già
        # nuovo) non deve riprovare a scriverlo
        self.last_loaded_text = self.txt_output.toPlainText()
        self.log_signal.emit(tr("batch.log_text_discarded", file=txt_filename))
        return True

    # ------------------------------------------------------------------
    # Elaborazione
    # ------------------------------------------------------------------
    def _update_start_button(self):
        self.btn_start.setEnabled(bool(self.base_dir) and not self.is_processing)

    def prepare_run(self):
        """Validazione bloccante e lista dei file da elaborare. Ritorna None se non si deve procedere."""
        if not self.base_dir:
            return None
        if manager.busy():
            QMessageBox.information(self, tr("common.busy_title"), tr("common.busy_body"))
            return None
        if not self.maybe_save_text():
            return None
        errors, warnings = layout.validate_original(self.original_dir())
        if errors:
            for e in errors:
                self.log_signal.emit(f"❌ {e}")
            show_layout_errors(self, errors)
            return None
        for w in warnings:
            self.log_signal.emit(f"⚠️ {w}")
        files = layout.pending_images(self.original_dir(), self.target_dir(), self.chk_reprocess_all.isChecked())
        if not files:
            QMessageBox.information(self, tr("batch.nothing_title"), tr("batch.nothing_body", target=self.TARGET_LABEL))
            return None
        return files

    def set_processing(self, active: bool):
        self.is_processing = active
        self.txt_output.setReadOnly(active)
        self.btn_save_text.setEnabled(not active)
        self.source_box.set_controls_enabled(not active)
        self.btn_stop.setEnabled(active)
        self.chk_reprocess_all.setEnabled(not active)
        self.lbl_eta.setVisible(active)
        if active:
            self.lbl_eta.setText(tr("batch.loading_model"))
        self._update_start_button()

    def show_step(self, current: int, total: int, filename: str, text: str, q_img: QImage,
                  per_image: float, remaining: float, status_extra: str = ""):
        self.progress_bar.setMaximum(total)
        self.progress_bar.setValue(current)
        self.lbl_progress_status.setText(tr("batch.processing", current=current, total=total, file=filename) + status_extra)
        self.lbl_eta.setText(format_eta(current, total, per_image, remaining))
        if not q_img.isNull():
            self.lbl_preview_img.setPixmap(QPixmap.fromImage(q_img))
        row = self.gallery_rows.get(filename)
        if row is not None:
            self.list_gallery.blockSignals(True)
            self.list_gallery.setCurrentRow(row)
            self.list_gallery.blockSignals(False)
            self.lbl_gallery_count.setText(tr("batch.image_n_of", n=row + 1, total=self.list_gallery.count()))
        self.current_selected_filename = filename
        self.txt_output.setText(text)
        self.last_loaded_text = text
        self.lbl_save_status.setText(tr("batch.active_file", path=f"{self.TARGET_LABEL}/{layout.txt_name(filename)}"))

    def on_progress(self, status_msg: str, percent: float):
        self.progress_bar.setMaximum(100)
        self.progress_bar.setValue(int(percent))
        self.lbl_progress_status.setText(status_msg)

    def stop_operations(self):
        self.log_signal.emit(tr("batch.log_stop"))
        if self.worker and self.worker.isRunning():
            self.worker.request_stop()
            self.lbl_eta.setText(tr("batch.stopping"))
