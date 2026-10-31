# Image Dataset Studio — Copyright (C) 2026 Mauro Liistro
# SPDX-License-Identifier: AGPL-3.0-only
"""Caption dei VLM su una sola riga: in Append ogni riga del .txt è una caption alternativa con la trigger word."""
import os

import pytest
from PIL import Image

from dataset_studio import workers
from dataset_studio.engines import vlm

# Risposta in paragrafi, come quelle di JoyCaption che hanno scritto righe senza trigger word nei .txt
PARAGRAPHS = "A woman stands by a pool.\n\nHer left wrist is adorned with bracelets.\n"


class _ParagraphBackend:
    def caption(self, image, instruction, max_new_tokens=256):
        return PARAGRAPHS


def _run_batch(tmp_path, monkeypatch, write_mode: str) -> str:
    original = tmp_path / "original_dataset"
    target = tmp_path / "dataset_captions"
    original.mkdir(exist_ok=True)
    Image.new("RGB", (8, 8)).save(original / "000.png")
    monkeypatch.setattr(workers.manager, "get_vlm", lambda *a, **k: _ParagraphBackend())
    monkeypatch.setattr(workers.manager, "describe", lambda: "finto")
    config = {"instruction": "", "max_tokens": 16, "prefix": "srv", "write_mode": write_mode}
    worker = workers.BatchCaptionThread(str(original), str(target), ["000.png"],
                                        {"model_key": "x", "device": "cpu", "low_memory": False}, config)
    worker.run()  # direttamente, senza thread: il test controlla solo cosa finisce nel .txt
    with open(os.path.join(target, "000.txt"), encoding="utf-8") as f:
        return f.read()


def test_batch_writes_a_paragraph_answer_on_one_line(tmp_path, monkeypatch):
    text = _run_batch(tmp_path, monkeypatch, "overwrite")
    assert text == "srv, A woman stands by a pool. Her left wrist is adorned with bracelets."


def test_batch_append_adds_exactly_one_line_with_the_prefix(tmp_path, monkeypatch):
    _run_batch(tmp_path, monkeypatch, "overwrite")
    lines = _run_batch(tmp_path, monkeypatch, "append").split("\n")
    assert len(lines) == 2
    assert all(line.startswith("srv, ") for line in lines)


def test_joins_paragraphs_into_one_line():
    # Forma reale di una risposta di JoyCaption: paragrafi separati da una riga vuota
    text = "A woman stands by a pool.\n\nHer left wrist is adorned with bracelets.\n\nThe lighting is natural."
    assert vlm.single_line_caption(text) == (
        "A woman stands by a pool. Her left wrist is adorned with bracelets. The lighting is natural."
    )


@pytest.mark.parametrize("text, expected", [
    ("first line\r\nsecond line", "first line second line"),
    ("tabs\tand   many    spaces", "tabs and many spaces"),
    ("  padded caption \n", "padded caption"),
    ("già su una riga, con àccenti", "già su una riga, con àccenti"),
    ("", ""),
    ("\n \n\t", ""),
])
def test_collapses_any_whitespace(text, expected):
    assert vlm.single_line_caption(text) == expected


def test_result_has_no_line_breaks():
    text = "a\nb\rc\x0bd\x0ce f g\x85h"
    assert vlm.single_line_caption(text).splitlines() == ["a b c d e f g h"]
