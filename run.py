# Image Dataset Studio — Copyright (C) 2026 Mauro Liistro
# SPDX-License-Identifier: AGPL-3.0-only
"""Avvio di Image Dataset Studio: python run.py"""
import os
import sys

try:
    import shiboken6
    from PySide6.QtWidgets import QApplication, QDialog
except ImportError:
    print("❌ PySide6 is not installed in the current environment / PySide6 non è installata.")
    print("pip install -r requirements.txt")
    sys.exit(1)

from dataset_studio.config import load_settings
from dataset_studio.i18n import install_qt_translator, resolve_language, set_language


def main() -> int:
    app = QApplication(sys.argv)
    # La lingua va impostata prima di creare qualsiasi widget
    set_language(resolve_language(load_settings().get("language", "auto")))
    install_qt_translator(app)

    from dataset_studio.engines import vlm
    from dataset_studio.ui.license_dialog import LicenseAcceptDialog, license_accepted
    from dataset_studio.ui.main_window import MainWindow, apply_dark_palette

    apply_dark_palette(app)
    if not license_accepted() and LicenseAcceptDialog().exec() != QDialog.DialogCode.Accepted:
        return 0

    window = MainWindow()
    window.show()
    exit_code = app.exec()
    # I widget vanno distrutti finché QApplication esiste: lasciati allo spegnimento dell'interprete,
    # PySide li distrugge in ordine casuale e Python va in crash (SIGSEGV/SIGBUS/abort in ~QObject).
    # "del window" non basta: segnali collegati al ModelManager globale e lambda la tengono in vita.
    shiboken6.delete(window)
    if vlm.downloads_in_background():
        # Un download fermato dallo Stop continua nei thread di huggingface_hub, che Python aspetterebbe
        # fino alla fine (GB) con la finestra già chiusa. Il parziale rimasto si cancella al prossimo download.
        sys.stdout.flush()
        sys.stderr.flush()
        os._exit(exit_code)
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
