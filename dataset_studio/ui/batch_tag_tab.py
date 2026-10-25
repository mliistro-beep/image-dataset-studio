# Image Dataset Studio — Copyright (C) 2026 Mauro Liistro
# SPDX-License-Identifier: AGPL-3.0-only
"""Scheda Batch Tag: auto-tagging WD14 (motore invariato) + Mass Tag Editor."""
import os

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QVBoxLayout, QHBoxLayout, QGridLayout, QGroupBox, QLabel, QPushButton, QComboBox,
    QSlider, QCheckBox, QRadioButton, QLineEdit, QSpinBox, QStackedWidget, QMessageBox
)

from ..config import AVAILABLE_MODELS, TAGS_DIR, load_settings, save_settings
from ..dataset import layout
from ..dataset.archive import create_archive
from ..i18n import tr
from ..model_manager import manager
from ..workers import BatchTaggingThread
from .batch_base import BatchTabBase
from .mass_edit import MassEditWidget


def split_csv(text: str):
    return [t.strip() for t in text.split(",") if t.strip()]


class BatchTagTab(BatchTabBase):
    EDITOR_TITLE = "tag.editor_title"
    EDITOR_PLACEHOLDER = "tag.editor_placeholder"
    TARGET_LABEL = TAGS_DIR
    START_LABEL = "tag.start"

    def __init__(self, parent=None):
        self._loading_settings = True
        super().__init__(parent)
        self._load_saved_settings()
        self._loading_settings = False

    # ------------------------------------------------------------------
    # UI
    # ------------------------------------------------------------------
    def build_sidebar(self, sidebar_layout):
        group_model = QGroupBox(tr("tag.model_box"))
        model_layout = QVBoxLayout(group_model)
        self.combo_model = QComboBox()
        for key, info in AVAILABLE_MODELS.items():
            label = f"{info['name']} ({tr(info['hint'])})" if info["hint"] else info["name"]
            self.combo_model.addItem(label, key)
        self.combo_model.currentIndexChanged.connect(self._save_settings)
        model_layout.addWidget(self.combo_model)
        self.lbl_model_status = QLabel(tr("common.model_autoload"))
        self.lbl_model_status.setWordWrap(True)
        self.lbl_model_status.setStyleSheet("color: #aaaaaa; font-style: italic;")
        model_layout.addWidget(self.lbl_model_status)
        sidebar_layout.addWidget(group_model)

        group_thresh = QGroupBox(tr("tag.thresh_box"))
        thresh_layout = QGridLayout(group_thresh)
        thresh_layout.addWidget(QLabel(tr("tag.general")), 0, 0)
        self.lbl_gen_val = QLabel("0.30")
        thresh_layout.addWidget(self.lbl_gen_val, 0, 1, Qt.AlignRight)
        self.slider_gen = QSlider(Qt.Horizontal)
        self.slider_gen.setRange(10, 90)
        self.slider_gen.setValue(30)
        self.slider_gen.valueChanged.connect(self._on_gen_thresh_changed)
        thresh_layout.addWidget(self.slider_gen, 1, 0, 1, 2)
        thresh_layout.addWidget(QLabel(tr("tag.character")), 2, 0)
        self.lbl_char_val = QLabel("0.30")
        thresh_layout.addWidget(self.lbl_char_val, 2, 1, Qt.AlignRight)
        self.slider_char = QSlider(Qt.Horizontal)
        self.slider_char.setRange(10, 90)
        self.slider_char.setValue(30)
        self.slider_char.valueChanged.connect(self._on_char_thresh_changed)
        thresh_layout.addWidget(self.slider_char, 3, 0, 1, 2)
        lbl_thresh_info = QLabel(tr("tag.thresh_hint"))
        lbl_thresh_info.setWordWrap(True)
        lbl_thresh_info.setStyleSheet("color: #ffaa00; font-size: 10px; font-style: italic;")
        thresh_layout.addWidget(lbl_thresh_info, 4, 0, 1, 2)
        sidebar_layout.addWidget(group_thresh)

        group_opts = QGroupBox(tr("tag.opts_box"))
        opts_layout = QVBoxLayout(group_opts)
        self.chk_underscore = QCheckBox(tr("tag.underscore"))
        self.chk_underscore.setChecked(True)
        self.chk_underscore.toggled.connect(self._save_settings)
        opts_layout.addWidget(self.chk_underscore)
        self.chk_exclude_ratings = QCheckBox(tr("tag.exclude_ratings"))
        self.chk_exclude_ratings.setChecked(True)
        self.chk_exclude_ratings.toggled.connect(self._save_settings)
        opts_layout.addWidget(self.chk_exclude_ratings)

        min_tags_layout = QHBoxLayout()
        min_tags_layout.addWidget(QLabel(tr("tag.min_tags")))
        self.spin_min_tags = QSpinBox()
        self.spin_min_tags.setRange(0, 100)
        self.spin_min_tags.setValue(10)
        self.spin_min_tags.setToolTip(tr("tag.min_tags_tip"))
        self.spin_min_tags.valueChanged.connect(self._save_settings)
        min_tags_layout.addWidget(self.spin_min_tags)
        opts_layout.addLayout(min_tags_layout)

        max_tags_layout = QHBoxLayout()
        max_tags_layout.addWidget(QLabel(tr("tag.max_tags")))
        self.spin_max_tags = QSpinBox()
        self.spin_max_tags.setRange(0, 500)
        self.spin_max_tags.setValue(0)
        self.spin_max_tags.setToolTip(tr("tag.max_tags_tip"))
        self.spin_max_tags.valueChanged.connect(self._save_settings)
        max_tags_layout.addWidget(self.spin_max_tags)
        opts_layout.addLayout(max_tags_layout)

        opts_layout.addWidget(QLabel(tr("common.write_mode")))
        self.rb_overwrite = QRadioButton(tr("common.overwrite"))
        self.rb_overwrite.setChecked(True)
        self.rb_append = QRadioButton(tr("tag.append"))
        self.rb_overwrite.toggled.connect(self._save_settings)
        opts_layout.addWidget(self.rb_overwrite)
        opts_layout.addWidget(self.rb_append)

        self.chk_compress_output = QCheckBox(tr("common.compress"))
        self.chk_compress_output.toggled.connect(self._save_settings)
        opts_layout.addWidget(self.chk_compress_output)
        sidebar_layout.addWidget(group_opts)

        self.btn_mass_edit = QPushButton(tr("tag.mass_edit"))
        self.btn_mass_edit.setCheckable(True)
        self.btn_mass_edit.setFixedHeight(32)
        self.btn_mass_edit.setStyleSheet("font-weight: bold; font-size: 12px;")
        self.btn_mass_edit.toggled.connect(self._toggle_mass_edit)
        sidebar_layout.addWidget(self.btn_mass_edit)

    def build_bottom_panel(self):
        box_custom_tags = QGroupBox(tr("tag.rules_box"))
        custom_tags_layout = QGridLayout(box_custom_tags)
        custom_tags_layout.setContentsMargins(8, 8, 8, 8)
        custom_tags_layout.setHorizontalSpacing(12)
        custom_tags_layout.setVerticalSpacing(6)

        custom_tags_layout.addWidget(QLabel(tr("tag.trigger")), 0, 0)
        self.entry_trigger = QLineEdit()
        self.entry_trigger.setPlaceholderText(tr("tag.trigger_ph"))
        self.entry_trigger.setToolTip(tr("tag.trigger_tip"))
        self.entry_trigger.textChanged.connect(self._save_settings)
        custom_tags_layout.addWidget(self.entry_trigger, 0, 1)

        custom_tags_layout.addWidget(QLabel(tr("tag.banned")), 0, 2)
        self.entry_banned = QLineEdit()
        self.entry_banned.setPlaceholderText(tr("tag.banned_ph"))
        self.entry_banned.setToolTip(tr("tag.banned_tip"))
        self.entry_banned.textChanged.connect(self._save_settings)
        custom_tags_layout.addWidget(self.entry_banned, 0, 3)

        custom_tags_layout.addWidget(QLabel(tr("tag.prepend")), 1, 0)
        self.entry_prepend = QLineEdit()
        self.entry_prepend.setPlaceholderText(tr("tag.prepend_ph"))
        self.entry_prepend.setToolTip(tr("tag.prepend_tip"))
        self.entry_prepend.textChanged.connect(self._save_settings)
        custom_tags_layout.addWidget(self.entry_prepend, 1, 1)

        custom_tags_layout.addWidget(QLabel(tr("tag.postpend")), 1, 2)
        self.entry_postpend = QLineEdit()
        self.entry_postpend.setPlaceholderText(tr("tag.postpend_ph"))
        self.entry_postpend.setToolTip(tr("tag.postpend_tip"))
        self.entry_postpend.textChanged.connect(self._save_settings)
        custom_tags_layout.addWidget(self.entry_postpend, 1, 3)
        return box_custom_tags

    def build_main_area(self, main_layout, central_widget):
        self.stack = QStackedWidget()
        self.stack.addWidget(central_widget)
        self.widget_massedit = MassEditWidget()
        self.widget_massedit.log_signal.connect(self.log_signal)
        self.widget_massedit.dataset_updated_signal.connect(self._on_massedit_dataset_updated)
        self.stack.addWidget(self.widget_massedit)
        main_layout.addWidget(self.stack, stretch=1)

    def count_text(self, text):
        return tr("tag.count", count=len(split_csv(text)))

    def target_dir(self):
        return layout.paths_for(self.base_dir)[1] if self.base_dir else ""

    # ------------------------------------------------------------------
    # Mass Edit
    # ------------------------------------------------------------------
    def _toggle_mass_edit(self, checked: bool):
        if not checked and not self.widget_massedit.maybe_save():
            # Annullato: si resta in Mass Edit con le modifiche in memoria
            self.btn_mass_edit.blockSignals(True)
            self.btn_mass_edit.setChecked(True)
            self.btn_mass_edit.blockSignals(False)
            return
        self.stack.setCurrentIndex(1 if checked else 0)
        if checked:
            self._auto_save_current_file()
            self._reload_mass_edit()
        elif self.base_dir and self.list_gallery.currentItem():
            # Mass Edit può aver riscritto il .txt mostrato nell'editor
            self._on_gallery_selection_changed()

    def _reload_mass_edit(self):
        tags_dir = self.target_dir()
        images = layout.list_images(tags_dir)
        if images:
            self.widget_massedit.load_dataset(tags_dir, images)
            self.log_signal.emit(tr("tag.log_mass_edit", count=len(images), dir=TAGS_DIR))

    def _on_massedit_dataset_updated(self):
        if self.base_dir:
            self.refresh_gallery()

    def _load_dataset(self, base_dir):
        # Il dataset è già cambiato: si può solo salvare o scartare, non annullare
        self.widget_massedit.maybe_save(allow_cancel=False)
        super()._load_dataset(base_dir)
        if self.btn_mass_edit.isChecked():
            self._reload_mass_edit()

    def set_processing(self, active: bool):
        super().set_processing(active)
        # Durante il tagging i .txt cambiano sotto Mass Edit: modifiche in memoria li sovrascriverebbero
        self.widget_massedit.setEnabled(not active)

    # ------------------------------------------------------------------
    # Impostazioni (stesse chiavi dello script originale)
    # ------------------------------------------------------------------
    def _on_gen_thresh_changed(self, value: int):
        self.lbl_gen_val.setText(f"{value/100:.2f}")
        self._save_settings()

    def _on_char_thresh_changed(self, value: int):
        self.lbl_char_val.setText(f"{value/100:.2f}")
        self._save_settings()

    def _load_saved_settings(self):
        settings = load_settings()
        if not settings:
            return
        saved_model = settings.get("last_model", "")
        idx = self.combo_model.findData(saved_model)
        if idx >= 0:
            self.combo_model.setCurrentIndex(idx)
        self.slider_gen.setValue(int(settings.get("gen_thresh", 30)))
        self.slider_char.setValue(int(settings.get("char_thresh", 30)))
        self.lbl_gen_val.setText(f"{self.slider_gen.value()/100:.2f}")
        self.lbl_char_val.setText(f"{self.slider_char.value()/100:.2f}")
        self.chk_exclude_ratings.setChecked(bool(settings.get("exclude_ratings", True)))
        self.entry_banned.setText(settings.get("banned_tags_str", ""))
        self.entry_trigger.setText(settings.get("trigger_str", ""))
        self.entry_prepend.setText(settings.get("prepend_tags_str", ""))
        self.entry_postpend.setText(settings.get("postpend_tags_str", ""))
        self.spin_min_tags.setValue(int(settings.get("min_tags", 10)))
        self.spin_max_tags.setValue(int(settings.get("max_tags", 0)))
        self.chk_underscore.setChecked(bool(settings.get("replace_underscore", True)))
        self.rb_append.setChecked(settings.get("tag_write_mode") == "append")
        self.chk_compress_output.setChecked(bool(settings.get("tag_compress_output", False)))

    def _save_settings(self):
        if self._loading_settings:
            return
        save_settings({
            "last_model": self.combo_model.currentData(),
            "gen_thresh": self.slider_gen.value(),
            "char_thresh": self.slider_char.value(),
            "exclude_ratings": self.chk_exclude_ratings.isChecked(),
            "banned_tags_str": self.entry_banned.text(),
            "trigger_str": self.entry_trigger.text(),
            "prepend_tags_str": self.entry_prepend.text(),
            "postpend_tags_str": self.entry_postpend.text(),
            "min_tags": self.spin_min_tags.value(),
            "max_tags": self.spin_max_tags.value(),
            "replace_underscore": self.chk_underscore.isChecked(),
            "tag_write_mode": "append" if self.rb_append.isChecked() else "overwrite",
            "tag_compress_output": self.chk_compress_output.isChecked(),
        })

    def tagging_config(self) -> dict:
        """Configurazione WD14 corrente (usata anche dalla scheda Singola Immagine)."""
        return {
            "gen_thresh": self.slider_gen.value() / 100.0,
            "char_thresh": self.slider_char.value() / 100.0,
            "min_tags": self.spin_min_tags.value(),
            "max_tags": self.spin_max_tags.value(),
            "replace_under": self.chk_underscore.isChecked(),
            "exclude_ratings": self.chk_exclude_ratings.isChecked(),
            "banned_tags": split_csv(self.entry_banned.text()),
            "trigger_word": self.entry_trigger.text().strip(),
            "prepend_tags": split_csv(self.entry_prepend.text()),
            "postpend_tags": split_csv(self.entry_postpend.text()),
            "write_mode": "overwrite" if self.rb_overwrite.isChecked() else "append",
        }

    # ------------------------------------------------------------------
    # Elaborazione
    # ------------------------------------------------------------------
    def start_processing(self):
        if not self.widget_massedit.maybe_save():
            return
        files = self.prepare_run()
        if not files:
            return
        model_title = self.combo_model.currentData()
        self.log_signal.emit(tr("tag.log_start", count=len(files), model=AVAILABLE_MODELS[model_title]["name"]))
        self.lbl_model_status.setText(tr("common.model_loading"))
        self.lbl_model_status.setStyleSheet("color: #ff8800; font-weight: bold;")
        self.set_processing(True)

        self.worker = BatchTaggingThread(self.original_dir(), self.target_dir(), files, model_title, self.tagging_config())
        self.worker.progress_signal.connect(self.on_progress)
        self.worker.log_signal.connect(self.log_signal)
        self.worker.model_ready_signal.connect(self._on_model_ready)
        self.worker.step_signal.connect(self._on_tagging_step)
        self.worker.finished_signal.connect(self._on_tagging_finished)
        manager.register_worker(self.worker)
        self.worker.start()

    def _on_model_ready(self, provider: str):
        self.lbl_model_status.setText(tr("tag.model_ready", provider=provider))
        self.lbl_model_status.setStyleSheet("color: #00aa00; font-weight: bold;")
        self.log_signal.emit(tr("tag.log_model_ready", provider=provider))

    def _on_tagging_step(self, current, total, filename, caption, q_img, tag_count, per_image, remaining):
        self.show_step(current, total, filename, caption, q_img, per_image, remaining, tr("tag.step_extra", count=tag_count))
        self.lbl_count_header.setText(tr("tag.generated", count=tag_count))

    def _on_tagging_finished(self, processed_count: int, stats: dict, error: str):
        self.set_processing(False)
        self.progress_bar.setValue(0)
        if error:
            self.lbl_progress_status.setText(tr("common.load_error_status"))
            self.lbl_model_status.setText(tr("common.load_error_short"))
            self.lbl_model_status.setStyleSheet("color: #cc0000; font-weight: bold;")
            self.log_signal.emit(f"❌ {error}")
            QMessageBox.critical(self, tr("common.model_error_title"), error)
            return

        mode = stats.get("mode", "overwrite")
        total_written = stats.get("total_written", 0)
        new_added = stats.get("new_added", 0)
        existing_kept = stats.get("existing_kept", 0)
        if mode == "append":
            self.log_signal.emit(tr("tag.summary_append", count=processed_count, total=total_written,
                                    new=new_added, existing=existing_kept))
        else:
            self.log_signal.emit(tr("tag.summary_overwrite", count=processed_count, total=total_written))

        archive_path = ""
        if self.chk_compress_output.isChecked() and processed_count:
            try:
                archive_path = create_archive(self.target_dir(), self.base_dir)
                self.log_signal.emit(tr("common.archive_created", path=archive_path))
            except Exception as e:
                self.log_signal.emit(tr("common.archive_error", error=e))

        self.refresh_gallery()
        self.refresh_summary()
        if self.btn_mass_edit.isChecked():
            self._reload_mass_edit()
        self.lbl_progress_status.setText(tr("common.completed", count=processed_count))

        info_msg = tr("tag.done_body", count=processed_count) + "\n"
        if mode == "append":
            info_msg += tr("tag.done_append", new=new_added, total=total_written) + "\n\n"
        else:
            info_msg += tr("tag.done_overwrite", total=total_written) + "\n\n"
        info_msg += f"Output: {self.target_dir()}\n"
        if archive_path:
            info_msg += "\n" + tr("common.archive_created_msg", name=os.path.basename(archive_path)) + "\n"
        QMessageBox.information(self, tr("common.done_title"), info_msg)
