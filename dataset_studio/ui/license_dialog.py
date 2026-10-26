# Image Dataset Studio — Copyright (C) 2026 Mauro Liistro
# SPDX-License-Identifier: AGPL-3.0-only
"""Accettazione della licenza al primo avvio e finestra Informazioni (con crediti e licenza)."""
import os
from datetime import datetime
from html import escape

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QLabel, QPlainTextEdit, QCheckBox, QDialogButtonBox, QPushButton, QTabWidget,
    QTextBrowser, QWidget
)

from ..config import (
    APP_NAME, APP_VERSION, LICENSE_ID, COPYRIGHT_HOLDER, COPYRIGHT_YEAR, REPO_URL, ISSUES_URL, AUTHOR_URL,
    MODEL_CREDITS, LIBRARY_CREDITS, load_settings, save_settings
)
from ..i18n import tr

LICENSE_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "LICENSE")


def license_text() -> str:
    try:
        with open(LICENSE_PATH, "r", encoding="utf-8") as f:
            return f.read()
    except OSError:
        return tr("license.file_missing", url="https://www.gnu.org/licenses/agpl-3.0.txt")


def license_accepted() -> bool:
    accepted = load_settings().get("license_accepted")
    return isinstance(accepted, dict) and accepted.get("id") == LICENSE_ID


def _notice_label(text: str) -> QLabel:
    lbl = QLabel(text)
    lbl.setWordWrap(True)
    lbl.setTextFormat(Qt.RichText)
    lbl.setOpenExternalLinks(True)
    return lbl


def _license_view() -> QPlainTextEdit:
    view = QPlainTextEdit(license_text())
    view.setReadOnly(True)
    view.setFont(QFont("Monospace", 9))
    return view


class LicenseAcceptDialog(QDialog):
    """Mostrato al primo avvio: senza accettazione l'applicazione non parte."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr("license.accept_title", app=APP_NAME))
        self.resize(760, 640)
        v = QVBoxLayout(self)
        v.addWidget(_notice_label(tr("license.summary", app=APP_NAME, license=LICENSE_ID,
                                     holder=COPYRIGHT_HOLDER, year=COPYRIGHT_YEAR)))
        v.addWidget(_license_view(), stretch=1)

        self.chk_accept = QCheckBox(tr("license.checkbox"))
        v.addWidget(self.chk_accept)

        buttons = QDialogButtonBox()
        self.btn_accept = QPushButton(tr("license.accept"))
        self.btn_accept.setEnabled(False)
        btn_reject = QPushButton(tr("license.reject"))
        buttons.addButton(self.btn_accept, QDialogButtonBox.AcceptRole)
        buttons.addButton(btn_reject, QDialogButtonBox.RejectRole)
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.reject)
        self.chk_accept.toggled.connect(self.btn_accept.setEnabled)
        v.addWidget(buttons)

    def _accept(self):
        save_settings({"license_accepted": {"id": LICENSE_ID, "date": datetime.now().isoformat(timespec="seconds")}})
        self.accept()


def _credit_item(credit: dict) -> str:
    license_text = escape(credit["license"])
    if credit.get("license_note"):
        license_text += f" — <i>{escape(tr(credit['license_note']))}</i>"
    author = f" · {escape(credit['author'])}" if credit.get("author") else ""
    return f"<li><a href='{credit['url']}'>{escape(credit['name'])}</a>{author} — {license_text}</li>"


def credits_html() -> str:
    """Modelli, librerie e traduzioni: i dati vengono da config, qui si aggiungono solo i titoli tradotti."""
    models = "".join(_credit_item(c) for c in MODEL_CREDITS)
    libraries = "".join(_credit_item(c) for c in LIBRARY_CREDITS)
    return (f"<h3>{tr('credits.models_title')}</h3><p>{tr('credits.models_note')}</p><ul>{models}</ul>"
            f"<h3>{tr('credits.libraries_title')}</h3><p>{tr('credits.libraries_note')}</p><ul>{libraries}</ul>"
            f"<h3>{tr('credits.translations_title')}</h3><p>{tr('credits.translations_body', issues_url=ISSUES_URL)}</p>")


class AboutDialog(QDialog):
    """Note legali richieste dalla AGPL (§5d) per le interfacce interattive, crediti e testo della licenza."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr("about.title", app=APP_NAME))
        self.resize(760, 640)
        v = QVBoxLayout(self)
        tabs = QTabWidget()

        info = QWidget()
        info_layout = QVBoxLayout(info)
        info_layout.addWidget(_notice_label(tr("about.body", app=APP_NAME, version=APP_VERSION, license=LICENSE_ID,
                                               holder=COPYRIGHT_HOLDER, year=COPYRIGHT_YEAR, url=REPO_URL,
                                               author_url=AUTHOR_URL, issues_url=ISSUES_URL)))
        info_layout.addStretch()
        tabs.addTab(info, tr("about.tab_info"))

        credits_view = QTextBrowser()
        credits_view.setOpenExternalLinks(True)
        credits_view.setHtml(credits_html())
        tabs.addTab(credits_view, tr("about.tab_credits"))

        tabs.addTab(_license_view(), tr("about.tab_license"))
        v.addWidget(tabs, stretch=1)

        buttons = QDialogButtonBox(QDialogButtonBox.Close)
        buttons.rejected.connect(self.reject)
        v.addWidget(buttons)
