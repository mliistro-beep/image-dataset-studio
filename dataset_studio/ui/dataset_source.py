# Image Dataset Studio — Copyright (C) 2026 Mauro Liistro
# SPDX-License-Identifier: AGPL-3.0-only
"""Riquadro di selezione del dataset, condiviso da Batch Tag e Batch Caption."""
import os

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QGroupBox, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QFileDialog, QMessageBox
)

from ..config import TEMP_DATASET_DIR, ORIGINAL_DIR, IMAGE_EXTENSIONS
from ..dataset import layout
from ..dataset.archive import archive_filter, extract_archive, archive_stem, clean_dir
from ..i18n import tr


def show_layout_errors(parent, errors, title=None):
    preview = "\n".join(f"• {e}" for e in errors[:20])
    if len(errors) > 20:
        preview += "\n" + tr("source.more_errors", count=len(errors) - 20)
    QMessageBox.critical(parent, title or tr("source.errors_title"),
                         tr("source.errors_body", dir=ORIGINAL_DIR, count=len(errors), preview=preview))


def image_file_filter() -> str:
    exts = " ".join(f"*{e}" for e in sorted(IMAGE_EXTENSIONS))
    return tr("common.image_filter", exts=exts)


class DatasetSourceBox(QGroupBox):
    dataset_changed = Signal(str)   # cartella base del dataset
    log_signal = Signal(str)

    def __init__(self, title: str, parent=None):
        super().__init__(title, parent)
        self.base_dir = ""

        layout_v = QVBoxLayout(self)
        btn_row = QHBoxLayout()
        self.btn_select_dir = QPushButton(tr("source.folder"))
        self.btn_select_dir.setToolTip(tr("source.folder_tip", dir=ORIGINAL_DIR))
        self.btn_select_dir.clicked.connect(self.select_directory)
        btn_row.addWidget(self.btn_select_dir)

        self.btn_select_archive = QPushButton(tr("source.archive"))
        self.btn_select_archive.setToolTip(tr("source.archive_tip"))
        self.btn_select_archive.clicked.connect(self.select_archive)
        btn_row.addWidget(self.btn_select_archive)
        layout_v.addLayout(btn_row)

        self.btn_import_new = QPushButton(tr("source.import_new"))
        self.btn_import_new.setToolTip(tr("source.import_new_tip"))
        self.btn_import_new.setEnabled(False)
        self.btn_import_new.clicked.connect(self.import_new)
        layout_v.addWidget(self.btn_import_new)

        self.lbl_info = QLabel(tr("source.none"))
        self.lbl_info.setWordWrap(True)
        self.lbl_info.setStyleSheet("color: #aaaaaa;")
        layout_v.addWidget(self.lbl_info)

    # ------------------------------------------------------------------
    def original_dir(self) -> str:
        return layout.paths_for(self.base_dir)[0] if self.base_dir else ""

    def set_base(self, base_dir: str, emit: bool = True):
        self.base_dir = base_dir
        self.btn_import_new.setEnabled(bool(base_dir))
        if base_dir:
            errors, warnings = layout.validate_original(self.original_dir())
            for w in warnings:
                self.log_signal.emit(f"⚠️ {w}")
            if errors:
                self.log_signal.emit(tr("source.log_blocked", count=len(errors), dir=ORIGINAL_DIR))
        if emit:
            self.dataset_changed.emit(base_dir)

    def set_summary(self, text: str):
        self.lbl_info.setText(text)

    def set_controls_enabled(self, enabled: bool):
        self.btn_select_dir.setEnabled(enabled)
        self.btn_select_archive.setEnabled(enabled)
        self.btn_import_new.setEnabled(enabled and bool(self.base_dir))

    # ------------------------------------------------------------------
    def select_directory(self):
        folder = QFileDialog.getExistingDirectory(self, tr("source.pick_folder"))
        if not folder:
            return

        base = layout.resolve_base_dir(folder)
        if base:
            self.log_signal.emit(tr("source.log_existing", path=base))
            self.set_base(base)
            return

        sources = layout.find_source_images(folder)
        if not sources:
            QMessageBox.warning(self, tr("common.no_images_title"), tr("source.no_images_folder"))
            return
        self._first_import(sources, folder, tr("source.desc_folder", name=os.path.basename(folder)))

    def select_archive(self):
        file_path, _ = QFileDialog.getOpenFileName(self, tr("source.pick_archive"), "", archive_filter())
        if not file_path:
            return
        try:
            names = extract_archive(file_path, TEMP_DATASET_DIR)
        except Exception as e:
            self.log_signal.emit(tr("source.log_archive_error", error=e))
            QMessageBox.critical(self, tr("source.archive_error_title"), tr("source.archive_error_body", error=e))
            return
        if not names:
            QMessageBox.warning(self, tr("common.no_images_title"), tr("source.no_images_archive"))
            clean_dir(TEMP_DATASET_DIR)
            return

        sources = [os.path.join(TEMP_DATASET_DIR, n) for n in names]
        base = os.path.join(os.path.dirname(file_path), archive_stem(file_path))
        try:
            if layout.resolve_base_dir(base) == base:
                answer = QMessageBox.question(
                    self, tr("source.exists_title"), tr("source.exists_body", path=base, count=len(names)),
                    QMessageBox.Yes | QMessageBox.No | QMessageBox.Cancel, QMessageBox.No)
                if answer == QMessageBox.Yes:
                    created = layout.import_new_images(sources, base)
                    self.log_signal.emit(tr("source.log_imported", count=len(created), first=created[0], last=created[-1]))
                if answer != QMessageBox.Cancel:
                    self.set_base(base)
            else:
                self._first_import(sources, base, tr("source.desc_archive", name=os.path.basename(file_path)))
        except layout.DatasetLayoutError as e:
            show_layout_errors(self, e.errors)
        finally:
            clean_dir(TEMP_DATASET_DIR)

    def _first_import(self, sources, base, source_desc):
        answer = QMessageBox.question(
            self, tr("source.create_title"),
            tr("source.create_body", source=source_desc, count=len(sources), path=os.path.join(base, ORIGINAL_DIR)),
            QMessageBox.Yes | QMessageBox.No, QMessageBox.Yes)
        if answer != QMessageBox.Yes:
            return
        try:
            created = layout.first_import(sources, base)
        except layout.DatasetLayoutError as e:
            show_layout_errors(self, e.errors)
            return
        except Exception as e:
            QMessageBox.critical(self, tr("common.error"), tr("source.create_error", error=e))
            return
        self.log_signal.emit(tr("source.log_created", path=base, count=len(created), dir=ORIGINAL_DIR))
        self.set_base(base)

    def import_new(self):
        if not self.base_dir:
            return
        files, _ = QFileDialog.getOpenFileNames(self, tr("source.pick_new"), "", image_file_filter())
        if not files:
            return
        try:
            created = layout.import_new_images(files, self.base_dir)
        except layout.DatasetLayoutError as e:
            show_layout_errors(self, e.errors)
            return
        except Exception as e:
            QMessageBox.critical(self, tr("common.error"), tr("source.import_error", error=e))
            return
        self.log_signal.emit(tr("source.log_imported", count=len(created), first=created[0], last=created[-1]))
        self.set_base(self.base_dir)
