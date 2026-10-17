# Image Dataset Studio — Copyright (C) 2026 Mauro Liistro
# SPDX-License-Identifier: AGPL-3.0-only
"""Avvio di Image Dataset Studio: python run.py"""
import sys

try:
    from PySide6.QtWidgets import QApplication, QDialog
except ImportError:
    print("❌ PySide6 is not installed in the current environment / PySide6 non è installata.")
    print("pip install -r requirements.txt")
    sys.exit(1)

from dataset_studio.config import load_settings
from dataset_studio.i18n import resolve_language, set_language


def main():
    app = QApplication(sys.argv)
    # La lingua va impostata prima di creare qualsiasi widget
    set_language(resolve_language(load_settings().get("language", "auto")))

    from dataset_studio.ui.license_dialog import LicenseAcceptDialog, license_accepted
    from dataset_studio.ui.main_window import MainWindow, apply_dark_palette

    apply_dark_palette(app)
    if not license_accepted() and LicenseAcceptDialog().exec() != QDialog.Accepted:
        sys.exit(0)

    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
