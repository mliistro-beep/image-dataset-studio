# Image Dataset Studio — Copyright (C) 2026 Mauro Liistro
# SPDX-License-Identifier: AGPL-3.0-only
"""Guardia sulla chiusura pulita in run.py.

Il crash alla chiusura (SIGSEGV/SIGBUS in ~QObject) è intermittente e compare quasi solo con i modelli
veri, quindi non si riproduce in pytest: la prova reale è tools/exit_repro.py. Qui si controlla solo
che la correzione resti al suo posto.
"""
import ast
import os
from typing import Any, List

RUN_PY = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "run.py")


def main_function() -> ast.FunctionDef:
    with open(RUN_PY, encoding="utf-8") as f:
        tree = ast.parse(f.read())
    return next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "main")


def calls(node: ast.AST) -> list:
    """Chiamate come 'modulo.funzione', nell'ordine del sorgente."""
    found: List[Any] = [n for n in ast.walk(node)
             if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and isinstance(n.func.value, ast.Name)]
    found.sort(key=lambda n: (n.lineno, n.col_offset))
    return [f"{n.func.value.id}.{n.func.attr}" for n in found]


def test_main_window_is_deleted_after_event_loop():
    names = calls(main_function())

    assert "shiboken6.delete" in names, "run.main() deve distruggere la finestra con shiboken6.delete"
    assert names.index("app.exec") < names.index("shiboken6.delete")


def test_main_exits_without_waiting_for_background_downloads():
    # Dopo uno Stop i thread di huggingface_hub continuano a scaricare e Python li aspetterebbe all'uscita
    names = calls(main_function())

    assert "vlm.downloads_in_background" in names
    assert "os._exit" in names
    assert names.index("shiboken6.delete") < names.index("os._exit")


def test_main_does_not_call_sys_exit():
    # sys.exit dentro main() salterebbe la distruzione esplicita della finestra
    assert "sys.exit" not in calls(main_function())
