# Image Dataset Studio — Copyright (C) 2026 Mauro Liistro
# SPDX-License-Identifier: AGPL-3.0-only
"""Finestra principale: tre schede + log condiviso + stato del modello in memoria."""
import os
import sys

from PySide6.QtCore import Qt, QProcess
from PySide6.QtGui import QFont, QPalette, QColor
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QTabWidget, QTextEdit, QGroupBox, QSplitter,
    QLabel, QPushButton, QMessageBox, QComboBox, QApplication, QProxyStyle, QStyle, QStyleFactory,
    QStyleOptionGroupBox
)

from ..config import APP_NAME, load_settings, save_settings
from ..i18n import LANGUAGE_NAMES, tr
from ..engines import wd14, vlm
from ..model_manager import manager
from .batch_caption_tab import BatchCaptionTab
from .batch_tag_tab import BatchTagTab
from .license_dialog import AboutDialog
from .single_image_tab import SingleImageTab

# Un titolo di riquadro non impone più della sua parte iniziale come larghezza minima
_GROUPBOX_TITLE_MIN_WIDTH = 120
_GROUPBOX_TITLE_PADDING = 4


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(tr("main.window_title", app=APP_NAME))
        self.resize(1400, 920)

        central = QWidget(self)
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(6, 6, 6, 6)
        root.setSpacing(6)

        header = QHBoxLayout()
        title = QLabel(f"🤖 {APP_NAME}")
        title.setStyleSheet("font-size: 15px; font-weight: bold; color: #00ff66;")
        header.addWidget(title)
        header.addStretch()
        self.combo_lang = QComboBox()
        self.combo_lang.setToolTip("Language")
        self.combo_lang.addItem(tr("main.lang_auto"), "auto")
        for code, name in LANGUAGE_NAMES.items():
            self.combo_lang.addItem(name, code)
        # Qt misura le emoji (🌐, bandiere) più strette di come le disegna: senza margine il testo resta tagliato
        self.combo_lang.setMinimumWidth(self.combo_lang.sizeHint().width() + self.combo_lang.fontMetrics().height())
        self.combo_lang.setCurrentIndex(max(self.combo_lang.findData(load_settings().get("language", "auto")), 0))
        self.combo_lang.currentIndexChanged.connect(self._on_language_changed)
        header.addWidget(self.combo_lang)
        btn_about = QPushButton(tr("main.about"))
        btn_about.clicked.connect(lambda: AboutDialog(self).exec())
        header.addWidget(btn_about)
        header.addSpacing(12)
        self.lbl_loaded_model = QLabel(tr("main.no_model"))
        self.lbl_loaded_model.setStyleSheet("color: #aaaaaa;")
        header.addWidget(self.lbl_loaded_model)
        self.btn_unload = QPushButton(tr("main.unload"))
        self.btn_unload.setToolTip(tr("main.unload_tip"))
        self.btn_unload.setEnabled(False)
        self.btn_unload.clicked.connect(self._unload_model)
        header.addWidget(self.btn_unload)
        root.addLayout(header)

        splitter = QSplitter(Qt.Orientation.Vertical)
        self.tabs = QTabWidget()
        self.tab_tag = BatchTagTab()
        self.tab_caption = BatchCaptionTab()
        self.tab_single = SingleImageTab(self.tab_tag, self.tab_caption)
        self.tabs.addTab(self.tab_tag, tr("main.tab_tag"))
        self.tabs.addTab(self.tab_caption, tr("main.tab_caption"))
        self.tabs.addTab(self.tab_single, tr("main.tab_single"))
        splitter.addWidget(self.tabs)

        box_log = QGroupBox(tr("main.log"))
        log_layout = QVBoxLayout(box_log)
        log_layout.setContentsMargins(6, 6, 6, 6)
        self.txt_log = QTextEdit()
        self.txt_log.setReadOnly(True)
        self.txt_log.setFont(QFont("Monospace", 8))
        self.txt_log.setStyleSheet("background-color: #1e1e1e; color: #00ff66;")
        log_layout.addWidget(self.txt_log)
        splitter.addWidget(box_log)
        splitter.setStretchFactor(0, 5)
        splitter.setStretchFactor(1, 1)
        splitter.setCollapsible(0, False)
        splitter.setSizes([760, 140])
        root.addWidget(splitter)

        for tab in (self.tab_tag, self.tab_caption, self.tab_single):
            tab.log_signal.connect(self.log)

        # Lo stesso dataset viene aperto in entrambe le schede Batch
        self.tab_tag.source_box.dataset_changed.connect(self.tab_caption.set_dataset)
        self.tab_caption.source_box.dataset_changed.connect(self.tab_tag.set_dataset)

        manager.status_changed.connect(self._on_model_status)
        self._check_environment()

    def log(self, text: str):
        self.txt_log.append(text)
        self.txt_log.verticalScrollBar().setValue(self.txt_log.verticalScrollBar().maximum())

    def _check_environment(self):
        if wd14.ort is None:
            self.log(tr("main.ort_missing_log"))
            QMessageBox.warning(self, tr("main.ort_missing_title"), tr("main.ort_missing_body"))
        else:
            self.log(tr("main.ort_ok", providers=", ".join(wd14.ort.get_available_providers())))

        missing = vlm.vlm_dependencies_missing()
        if missing:
            self.log(f"⚠️ {missing}")
        else:
            device = tr("main.cuda_yes") if vlm.cuda_available() else tr("main.cuda_no")
            self.log(tr("main.torch_ok", torch=vlm.torch.__version__, transformers=vlm.transformers.__version__, device=device))
            reason = vlm.gpu_profile_unavailable_reason()
            if reason:
                self.log(f"ℹ️ {reason}")

    def _busy(self) -> bool:
        workers = [self.tab_tag.worker, self.tab_caption.worker, self.tab_single.worker]
        return any(w is not None and w.isRunning() for w in workers)

    def _on_model_status(self, text: str):
        self.lbl_loaded_model.setText(tr("main.in_memory", model=text) if text else tr("main.no_model"))
        self.btn_unload.setEnabled(bool(text))

    def _unload_model(self):
        if self._busy():
            QMessageBox.information(self, tr("common.busy_title"), tr("main.wait_busy"))
            return
        manager.unload(self.log)

    def _on_language_changed(self):
        save_settings({"language": self.combo_lang.currentData()})
        answer = QMessageBox.question(self, tr("main.restart_title"), tr("main.restart_body"),
                                      QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                                      QMessageBox.StandardButton.Yes)
        if answer == QMessageBox.StandardButton.Yes and self.close():
            QProcess.startDetached(sys.executable, sys.argv)
            QApplication.quit()

    def closeEvent(self, event):
        if not self.tab_tag.widget_massedit.maybe_save():
            event.ignore()
            return
        if self._busy():
            answer = QMessageBox.question(self, tr("common.busy_title"), tr("main.quit_busy"),
                                          QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                                          QMessageBox.StandardButton.No)
            if answer != QMessageBox.StandardButton.Yes:
                event.ignore()
                return
            workers = [w for w in (self.tab_tag.worker, self.tab_caption.worker, self.tab_single.worker)
                       if w is not None and w.isRunning()]
            for w in workers:
                w.request_stop()
            for w in workers:
                w.wait(30000)
            if any(w.isRunning() for w in workers):
                # Un caricamento o un'inferenza non si possono interrompere a metà: distruggere un QThread
                # ancora attivo farebbe abortire Qt, quindi si termina il processo direttamente
                os._exit(0)
        event.accept()


class EmojiSafeStyle(QProxyStyle):
    """Fusion con i titoli dei QGroupBox adatti alle emoji e alle traduzioni lunghe.

    Fusion misura il titolo con boundingRect(), che con le emoji dà ~10 px meno di quanto viene disegnato:
    l'ultima lettera restava tagliata. Inoltre un titolo lungo imponeva la propria larghezza come minimo del
    riquadro e allargava la finestra (francese, spagnolo): ora decide il contenuto e il titolo si accorcia con "…".
    """

    def __init__(self):
        super().__init__(QStyleFactory.create("Fusion"))

    def sizeFromContents(self, type_, option, size, widget=None):
        result = super().sizeFromContents(type_, option, size, widget)
        if type_ == QStyle.ContentsType.CT_GroupBox:
            result.setWidth(min(result.width(), _GROUPBOX_TITLE_MIN_WIDTH))
        return result

    def subControlRect(self, control, option, sub_control, widget=None):
        rect = super().subControlRect(control, option, sub_control, widget)
        if (control == QStyle.ComplexControl.CC_GroupBox and sub_control == QStyle.SubControl.SC_GroupBoxLabel
                and option.text):
            frame = super().subControlRect(control, option, QStyle.SubControl.SC_GroupBoxFrame, widget)
            needed = option.fontMetrics.horizontalAdvance(option.text) + _GROUPBOX_TITLE_PADDING
            rect.setWidth(min(max(rect.width(), needed), frame.right() - rect.left()))
        return rect

    def drawComplexControl(self, control, option, painter, widget=None):
        if control == QStyle.ComplexControl.CC_GroupBox and option.text:
            frame = self.subControlRect(control, option, QStyle.SubControl.SC_GroupBoxFrame, widget)
            label = self.subControlRect(control, option, QStyle.SubControl.SC_GroupBoxLabel, widget)
            available = frame.right() - label.left() - _GROUPBOX_TITLE_PADDING
            elided = option.fontMetrics.elidedText(option.text, Qt.TextElideMode.ElideRight, available)
            if elided != option.text:
                option = QStyleOptionGroupBox(option)
                option.text = elided
        super().drawComplexControl(control, option, painter, widget)


def apply_dark_palette(app):
    app.setStyle(EmojiSafeStyle())
    dark_palette = QPalette()
    dark_palette.setColor(QPalette.ColorRole.Window, QColor(45, 45, 45))
    dark_palette.setColor(QPalette.ColorRole.WindowText, QColor(220, 220, 220))
    dark_palette.setColor(QPalette.ColorRole.Base, QColor(25, 25, 25))
    dark_palette.setColor(QPalette.ColorRole.AlternateBase, QColor(45, 45, 45))
    # Sfondo scuro: con lo stesso colore del testo (220) i tooltip erano rettangoli grigi senza testo leggibile
    dark_palette.setColor(QPalette.ColorRole.ToolTipBase, QColor(30, 30, 30))
    dark_palette.setColor(QPalette.ColorRole.ToolTipText, QColor(220, 220, 220))
    dark_palette.setColor(QPalette.ColorRole.Text, QColor(220, 220, 220))
    dark_palette.setColor(QPalette.ColorRole.Button, QColor(45, 45, 45))
    dark_palette.setColor(QPalette.ColorRole.ButtonText, QColor(220, 220, 220))
    dark_palette.setColor(QPalette.ColorRole.BrightText, QColor(255, 0, 0))
    dark_palette.setColor(QPalette.ColorRole.Link, QColor(42, 130, 218))
    dark_palette.setColor(QPalette.ColorRole.Highlight, QColor(42, 130, 218))
    dark_palette.setColor(QPalette.ColorRole.HighlightedText, QColor(255, 255, 255))
    app.setPalette(dark_palette)
