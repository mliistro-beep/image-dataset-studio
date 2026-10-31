# Image Dataset Studio — Copyright (C) 2026 Mauro Liistro
# SPDX-License-Identifier: AGPL-3.0-only
"""Scheda Batch Caption: caption in linguaggio naturale con VLM, salvate in dataset_captions."""
import os
import re
from typing import cast

from PySide6.QtGui import QStandardItemModel
from PySide6.QtWidgets import (
    QVBoxLayout, QHBoxLayout, QGroupBox, QLabel, QPushButton, QComboBox, QCheckBox,
    QRadioButton, QLineEdit, QSpinBox, QPlainTextEdit, QMessageBox, QDialog, QDialogButtonBox,
    QFormLayout
)

from ..config import (VLM_PROFILES, VLM_MODELS, INSTRUCTION_PRESETS, FLORENCE_TASKS, CAPTIONS_DIR,
                      load_settings, save_settings)
from ..dataset import layout
from ..dataset.archive import create_archive
from ..model_manager import manager
from ..engines import vlm
from ..i18n import tr
from ..workers import BatchCaptionThread
from .batch_base import BatchTabBase


class VLMSettingsBox(QGroupBox):
    """Profilo hardware, modello, istruzione e lunghezza massima. Riutilizzato dalla scheda Singola Immagine."""

    def __init__(self, title: str, parent=None):
        super().__init__(title, parent)
        self._loading = True
        v = QVBoxLayout(self)

        v.addWidget(QLabel(tr("vlmbox.profile")))
        self.combo_profile = QComboBox()
        gpu_reason = vlm.gpu_profile_unavailable_reason()
        for key, prof in VLM_PROFILES.items():
            self.combo_profile.addItem(tr(prof["label"]), key)
            if key == "gpu" and gpu_reason:
                idx = self.combo_profile.count() - 1
                item = cast(QStandardItemModel, self.combo_profile.model()).item(idx)
                item.setEnabled(False)
                item.setToolTip(gpu_reason)
                self.combo_profile.setItemText(idx, tr(prof["label"]) + tr("vlmbox.unavailable"))
        self.combo_profile.currentIndexChanged.connect(self._on_profile_changed)
        v.addWidget(self.combo_profile)

        v.addWidget(QLabel(tr("vlmbox.model")))
        self.combo_model = QComboBox()
        self.combo_model.currentIndexChanged.connect(self._on_model_changed)
        v.addWidget(self.combo_model)

        self.lbl_deps = QLabel("")
        self.lbl_deps.setWordWrap(True)
        self.lbl_deps.setStyleSheet("color: #ff6666; font-size: 11px;")
        missing = vlm.vlm_dependencies_missing()
        self.lbl_deps.setText(f"⚠️ {missing}" if missing else "")
        self.lbl_deps.setVisible(bool(missing))
        v.addWidget(self.lbl_deps)

        # Florence-2: solo livello di dettaglio
        self.lbl_detail = QLabel(tr("vlmbox.detail"))
        v.addWidget(self.lbl_detail)
        self.combo_detail = QComboBox()
        for key, task in FLORENCE_TASKS.items():
            self.combo_detail.addItem(tr(key), task)
        self.combo_detail.setCurrentIndex(self.combo_detail.findData("<MORE_DETAILED_CAPTION>"))
        self.combo_detail.currentIndexChanged.connect(self.save)
        v.addWidget(self.combo_detail)

        # Altri modelli: istruzione libera
        self.lbl_instr = QLabel(tr("vlmbox.instruction"))
        v.addWidget(self.lbl_instr)
        self.combo_preset = QComboBox()
        self.combo_preset.addItem(tr("vlmbox.preset"))
        for key in INSTRUCTION_PRESETS:
            self.combo_preset.addItem(tr(key), key)
        self.combo_preset.activated.connect(self._apply_preset)
        v.addWidget(self.combo_preset)
        self.txt_instruction = QPlainTextEdit()
        self.txt_instruction.setPlaceholderText(tr("vlmbox.instruction_ph"))
        self.txt_instruction.setPlainText(INSTRUCTION_PRESETS["preset.detailed"])
        self.txt_instruction.setFixedHeight(80)
        self.txt_instruction.textChanged.connect(self.save)
        v.addWidget(self.txt_instruction)

        tok_row = QHBoxLayout()
        tok_row.addWidget(QLabel(tr("vlmbox.max_tokens")))
        self.spin_tokens = QSpinBox()
        self.spin_tokens.setRange(16, 1024)
        self.spin_tokens.setValue(256)
        self.spin_tokens.valueChanged.connect(self.save)
        tok_row.addWidget(self.spin_tokens)
        v.addLayout(tok_row)

        self._restore()
        self._loading = False
        self._on_profile_changed()

    # ------------------------------------------------------------------
    def profile_key(self) -> str:
        return self.combo_profile.currentData()

    def model_key(self) -> str:
        return self.combo_model.currentData()

    def _on_profile_changed(self):
        prev = self.combo_model.currentData() or load_settings().get("vlm_model")
        self.combo_model.blockSignals(True)
        self.combo_model.clear()
        for i, key in enumerate(VLM_PROFILES[self.profile_key()]["models"]):
            label = VLM_MODELS[key]["label"] + (tr("vlmbox.recommended") if i == 0 else "")
            self.combo_model.addItem(label, key)
        idx = self.combo_model.findData(prev)
        self.combo_model.setCurrentIndex(max(idx, 0))
        self.combo_model.blockSignals(False)
        self._on_model_changed()

    def _on_model_changed(self):
        if self.model_key() is None:
            return
        free = vlm.model_supports_free_prompt(self.model_key())
        for w in (self.lbl_instr, self.combo_preset, self.txt_instruction):
            w.setVisible(free)
        for w in (self.lbl_detail, self.combo_detail):
            w.setVisible(not free)
        self.save()

    def _apply_preset(self, index: int):
        if index > 0:
            self.txt_instruction.setPlainText(INSTRUCTION_PRESETS[self.combo_preset.currentData()])
        self.combo_preset.setCurrentIndex(0)

    def instruction(self) -> str:
        if vlm.model_supports_free_prompt(self.model_key()):
            return self.txt_instruction.toPlainText().strip()
        return self.combo_detail.currentData()

    def vlm_params(self) -> dict:
        prof = VLM_PROFILES[self.profile_key()]
        return {"model_key": self.model_key(), "device": prof["device"], "low_memory": prof.get("low_memory", False)}

    def vlm_config(self) -> dict:
        return {"instruction": self.instruction(), "max_tokens": self.spin_tokens.value()}

    def ready_or_warn(self, parent) -> bool:
        missing = vlm.vlm_dependencies_missing()
        if missing:
            QMessageBox.warning(parent, tr("vlmbox.missing_title"), missing)
            return False
        return True

    # ------------------------------------------------------------------
    def _restore(self):
        s = load_settings()
        idx = self.combo_profile.findData(s.get("vlm_profile", "universal"))
        if idx >= 0 and cast(QStandardItemModel, self.combo_profile.model()).item(idx).isEnabled():
            self.combo_profile.setCurrentIndex(idx)
        if s.get("vlm_instruction"):
            self.txt_instruction.setPlainText(s["vlm_instruction"])
        detail_idx = self.combo_detail.findData(s.get("vlm_detail"))
        if detail_idx >= 0:
            self.combo_detail.setCurrentIndex(detail_idx)
        self.spin_tokens.setValue(int(s.get("vlm_max_tokens", 256)))

    def save(self):
        if self._loading:
            return
        save_settings({
            "vlm_profile": self.profile_key(),
            "vlm_model": self.model_key(),
            "vlm_instruction": self.txt_instruction.toPlainText(),
            "vlm_detail": self.combo_detail.currentData(),
            "vlm_max_tokens": self.spin_tokens.value(),
        })


class FindReplaceDialog(QDialog):
    """Trova e sostituisci (testo o regex) su tutte le caption di dataset_captions."""

    def __init__(self, folder: str, parent=None):
        super().__init__(parent)
        self.folder = folder
        self.setWindowTitle(tr("find.title"))
        self.resize(480, 180)
        form = QFormLayout(self)
        self.entry_find = QLineEdit()
        self.entry_replace = QLineEdit()
        self.chk_regex = QCheckBox(tr("find.regex"))
        self.chk_case = QCheckBox(tr("find.case"))
        form.addRow(tr("find.find"), self.entry_find)
        form.addRow(tr("find.replace"), self.entry_replace)
        form.addRow(self.chk_regex)
        form.addRow(self.chk_case)
        self.lbl_preview = QLabel("")
        form.addRow(self.lbl_preview)
        for w in (self.entry_find, self.chk_regex, self.chk_case):
            (w.textChanged if isinstance(w, QLineEdit) else w.toggled).connect(self._update_preview)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText(tr("find.apply"))
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        form.addRow(buttons)

    def _pattern(self):
        text = self.entry_find.text()
        if not text:
            return None
        flags = 0 if self.chk_case.isChecked() else re.IGNORECASE
        return re.compile(text if self.chk_regex.isChecked() else re.escape(text), flags)

    def _txt_files(self):
        return [os.path.join(self.folder, f) for f in sorted(os.listdir(self.folder)) if f.endswith(".txt")]

    def _update_preview(self):
        try:
            pattern = self._pattern()
        except re.error as e:
            self.lbl_preview.setText(tr("find.bad_regex", error=e))
            return
        if pattern is None:
            self.lbl_preview.setText("")
            return
        occurrences, files = 0, 0
        for path in self._txt_files():
            with open(path, "r", encoding="utf-8") as f:
                n = len(pattern.findall(f.read()))
            occurrences += n
            files += 1 if n else 0
        self.lbl_preview.setText(tr("find.preview", count=occurrences, files=files))

    def apply(self) -> int:
        pattern = self._pattern()
        if pattern is None:
            return 0
        replacement = self.entry_replace.text()
        changed = 0
        for path in self._txt_files():
            with open(path, "r", encoding="utf-8") as f:
                old = f.read()
            if self.chk_regex.isChecked():
                new = pattern.sub(replacement, old)
            else:
                new = pattern.sub(lambda _m: replacement, old)
            if new != old:
                with open(path, "w", encoding="utf-8") as f:
                    f.write(new)
                changed += 1
        return changed


class BatchCaptionTab(BatchTabBase):
    EDITOR_TITLE = "cap.editor_title"
    EDITOR_PLACEHOLDER = "cap.editor_placeholder"
    TARGET_LABEL = CAPTIONS_DIR
    START_LABEL = "cap.start"

    def build_sidebar(self, sidebar_layout):
        self.vlm_box = VLMSettingsBox(tr("cap.model_box"))
        sidebar_layout.addWidget(self.vlm_box)

        self.lbl_model_status = QLabel(tr("common.model_autoload"))
        self.lbl_model_status.setWordWrap(True)
        self.lbl_model_status.setStyleSheet("color: #aaaaaa; font-style: italic;")
        sidebar_layout.addWidget(self.lbl_model_status)

        group_opts = QGroupBox(tr("cap.opts_box"))
        opts = QVBoxLayout(group_opts)
        saved = load_settings()
        opts.addWidget(QLabel(tr("cap.prefix")))
        self.entry_prefix = QLineEdit()
        self.entry_prefix.setPlaceholderText(tr("tag.trigger_ph"))
        self.entry_prefix.setText(saved.get("caption_prefix", ""))
        self.entry_prefix.textChanged.connect(lambda t: save_settings({"caption_prefix": t}))
        opts.addWidget(self.entry_prefix)
        opts.addWidget(QLabel(tr("common.write_mode")))
        self.rb_overwrite = QRadioButton(tr("common.overwrite"))
        self.rb_overwrite.setChecked(True)
        self.rb_append = QRadioButton(tr("cap.append"))
        opts.addWidget(self.rb_overwrite)
        opts.addWidget(self.rb_append)
        # Solo dopo addWidget: prima i due pulsanti non hanno un genitore comune e non si escludono a vicenda
        self.rb_append.setChecked(saved.get("caption_write_mode") == "append")
        self.rb_append.toggled.connect(
            lambda on: save_settings({"caption_write_mode": "append" if on else "overwrite"}))
        self.chk_compress_output = QCheckBox(tr("common.compress"))
        self.chk_compress_output.setChecked(bool(saved.get("caption_compress_output", False)))
        self.chk_compress_output.toggled.connect(lambda on: save_settings({"caption_compress_output": on}))
        opts.addWidget(self.chk_compress_output)
        sidebar_layout.addWidget(group_opts)

    def build_editor_extras(self, layout_v):
        btn = QPushButton(tr("cap.find_replace"))
        btn.clicked.connect(self._find_replace)
        layout_v.addWidget(btn)

    def count_text(self, text):
        words = len(text.split())
        return tr("cap.count", words=words, chars=len(text))

    def target_dir(self):
        return layout.paths_for(self.base_dir)[2] if self.base_dir else ""

    def _find_replace(self):
        if not self.base_dir or not os.path.isdir(self.target_dir()):
            QMessageBox.information(self, tr("cap.no_captions_title"), tr("cap.no_captions_body"))
            return
        if not self.maybe_save_text():
            return
        dlg = FindReplaceDialog(self.target_dir(), self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            try:
                changed = dlg.apply()
            except re.error as e:
                QMessageBox.warning(self, tr("find.bad_regex_title"), str(e))
                return
            self.log_signal.emit(tr("cap.log_replaced", count=changed, dir=CAPTIONS_DIR))
            self.refresh_gallery()

    # ------------------------------------------------------------------
    def start_processing(self):
        if not self.vlm_box.ready_or_warn(self):
            return
        files = self.prepare_run()
        if not files:
            return
        params = self.vlm_box.vlm_params()
        config = dict(self.vlm_box.vlm_config(),
                      prefix=self.entry_prefix.text(),
                      write_mode="overwrite" if self.rb_overwrite.isChecked() else "append")
        self.log_signal.emit(tr("cap.log_start", count=len(files), model=VLM_MODELS[params['model_key']]['label']))
        self.lbl_model_status.setText(tr("common.model_loading"))
        self.lbl_model_status.setStyleSheet("color: #ff8800; font-weight: bold;")
        self.set_processing(True)
        self.vlm_box.setEnabled(False)

        self.worker = BatchCaptionThread(self.original_dir(), self.target_dir(), files, params, config)
        self.worker.progress_signal.connect(self.on_progress)
        self.worker.log_signal.connect(self.log_signal)
        self.worker.model_ready_signal.connect(self._on_model_ready)
        self.worker.step_signal.connect(self.show_step)
        self.worker.finished_signal.connect(self._on_finished)
        manager.register_worker(self.worker)
        self.worker.start()

    def _on_model_ready(self, desc: str):
        self.lbl_model_status.setText(tr("cap.model_ready", desc=desc))
        self.lbl_model_status.setStyleSheet("color: #00aa00; font-weight: bold;")
        self.lbl_eta.setText(tr("cap.first_image"))
        self.log_signal.emit(tr("cap.log_model_ready", desc=desc))

    def _on_finished(self, processed_count: int, error: str):
        self.set_processing(False)
        self.vlm_box.setEnabled(True)
        self.progress_bar.setValue(0)
        if error:
            self.lbl_progress_status.setText(tr("common.load_error_status"))
            self.lbl_model_status.setText(tr("common.load_error_short"))
            self.lbl_model_status.setStyleSheet("color: #cc0000; font-weight: bold;")
            self.log_signal.emit(f"❌ {error}")
            QMessageBox.critical(self, tr("common.model_error_title"), error)
            return

        self.log_signal.emit(tr("cap.summary", count=processed_count, dir=CAPTIONS_DIR))
        archive_path = ""
        if self.chk_compress_output.isChecked() and processed_count:
            try:
                archive_path = create_archive(self.target_dir(), self.base_dir)
                self.log_signal.emit(tr("common.archive_created", path=archive_path))
            except Exception as e:
                self.log_signal.emit(tr("common.archive_error", error=e))
        self.refresh_gallery()
        self.refresh_summary()
        self.lbl_progress_status.setText(tr("common.completed", count=processed_count))
        msg = tr("cap.done_body", count=processed_count) + f"\n\nOutput: {self.target_dir()}\n"
        msg += "\n" + tr("cap.done_review")
        if archive_path:
            msg += "\n\n" + tr("common.archive_created_msg", name=os.path.basename(archive_path))
        QMessageBox.information(self, tr("common.done_title"), msg)
