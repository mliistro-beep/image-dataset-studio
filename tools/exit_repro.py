# Image Dataset Studio — Copyright (C) 2026 Mauro Liistro
# SPDX-License-Identifier: AGPL-3.0-only
"""Prova manuale del crash di Python alla chiusura dell'app (SIGSEGV/SIGBUS in ~QObject).

Avvia l'app come run.py senza display, opzionalmente esegue un tagging WD14 vero sulla scheda
Singola Immagine, chiude la finestra e controlla come esce il processo. Il crash è intermittente
(prima della correzione circa 3 volte su 8, quasi solo dopo aver caricato un modello), quindi va
ripetuto più volte e va lanciato con l'installazione reale (torch, onnxruntime-gpu):

    ~/image-dataset-studio/venv/bin/python -I tools/exit_repro.py tags --runs 8
    ~/image-dataset-studio/venv/bin/python -I tools/exit_repro.py idle --runs 20

Modalità: "idle" apre e chiude la finestra; "tags" fa prima un tagging WD14 (usa i modelli già in
~/.cache/wd14_tagger, senza scaricarli). Ogni prova usa una HOME temporanea, così settings.json
dell'utente non viene toccato. I core dump dei crash sono visibili con `coredumpctl list`.
Da rilanciare ogni volta che si tocca la chiusura (run.py, MainWindow.closeEvent, ModelManager).
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile

REPO_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CHILD_TIMEOUT_S = 300


def prepare_home(real_cache: str) -> str:
    """HOME temporanea con licenza accettata e link ai modelli WD14 già scaricati."""
    home = tempfile.mkdtemp(prefix="ids-exit-repro-")
    cache = os.path.join(home, ".cache", "wd14_tagger")
    os.makedirs(cache)
    if os.path.isdir(real_cache):
        for name in os.listdir(real_cache):
            if name.endswith((".onnx", ".csv")):
                os.symlink(os.path.join(real_cache, name), os.path.join(cache, name))
    with open(os.path.join(cache, "settings.json"), "w", encoding="utf-8") as f:
        json.dump({"license_accepted": {"id": "AGPL-3.0-only"}}, f)
    return home


def run_child(mode: str) -> int:
    """Processo figlio: avvia l'app vera e la chiude dopo l'eventuale tagging."""
    sys.path.insert(0, REPO_DIR)
    os.chdir(REPO_DIR)
    from PIL import Image
    from PySide6.QtCore import QTimer
    from PySide6.QtGui import QPixmap
    from PySide6.QtWidgets import QMessageBox

    # Nessun dialogo modale: senza display bloccherebbe la prova
    for name in ("warning", "information", "critical"):
        setattr(QMessageBox, name, staticmethod(lambda *a, **k: QMessageBox.StandardButton.Ok))

    from dataset_studio.ui import main_window
    original_show = main_window.MainWindow.show

    def show(self):
        original_show(self)

        def drive():
            if mode != "tags":
                QTimer.singleShot(1500, self.close)
                return
            tab = self.tab_single
            tab._set_image(Image.new("RGB", (64, 64), (200, 100, 50)), "repro", QPixmap(64, 64))
            tab.mode_group.buttons()[0].setChecked(True)   # primo pulsante: tag WD14
            tab.analyze()
            tab.worker.result_signal.connect(lambda tags, caption: print("RESULT:", tags[:80], flush=True))
            tab.worker.finished.connect(lambda: QTimer.singleShot(500, self.close))
        QTimer.singleShot(300, drive)

    main_window.MainWindow.show = show   # type: ignore[method-assign]
    import run
    return run.main()


def describe(returncode: int) -> str:
    if returncode == 0:
        return "uscita pulita"
    if returncode < 0:
        return f"CRASH (segnale {-returncode})"
    return f"codice di uscita {returncode}"


def main() -> int:
    parser = argparse.ArgumentParser(description="Prova del crash di Python alla chiusura dell'app.")
    parser.add_argument("mode", choices=("idle", "tags"))
    parser.add_argument("--runs", type=int, default=8, help="numero di prove (default 8)")
    parser.add_argument("--child", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()

    if args.child:
        return run_child(args.mode)

    real_cache = os.path.join(os.path.expanduser("~"), ".cache", "wd14_tagger")
    crashes = 0
    for i in range(1, args.runs + 1):
        home = prepare_home(real_cache)
        env = dict(os.environ, HOME=home, QT_QPA_PLATFORM="offscreen")
        try:
            proc = subprocess.run([sys.executable, "-I", os.path.abspath(__file__), args.mode, "--child"],
                                  env=env, timeout=CHILD_TIMEOUT_S)
            result = describe(proc.returncode)
            crashes += proc.returncode < 0
        except subprocess.TimeoutExpired:
            result = f"TIMEOUT dopo {CHILD_TIMEOUT_S} s"
            crashes += 1
        finally:
            shutil.rmtree(home, ignore_errors=True)
        print(f"[{i}/{args.runs}] {result}", flush=True)

    print(f"\nProblemi alla chiusura: {crashes} su {args.runs}")
    return 1 if crashes else 0


if __name__ == "__main__":
    sys.exit(main())
