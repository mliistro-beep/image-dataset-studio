# Image Dataset Studio — Copyright (C) 2026 Mauro Liistro
# SPDX-License-Identifier: AGPL-3.0-only
"""Scrittura dei .txt del dataset: un errore a metà non deve lasciare il file troncato."""
import os
import stat

import pytest

from dataset_studio.dataset import layout


def mode(path) -> int:
    return stat.S_IMODE(os.stat(path).st_mode)


def test_writes_and_overwrites_text(tmp_path):
    path = tmp_path / "001.txt"

    layout.write_text_atomic(str(path), "1girl, solo")
    layout.write_text_atomic(str(path), "caffè, ok")

    assert path.read_text(encoding="utf-8") == "caffè, ok"
    assert os.listdir(tmp_path) == ["001.txt"]


def test_failed_write_keeps_the_previous_content(tmp_path):
    path = tmp_path / "001.txt"
    path.write_text("tag esistenti", encoding="utf-8")

    # Un surrogato isolato non si codifica in UTF-8: l'errore arriva durante la scrittura
    with pytest.raises(UnicodeEncodeError):
        layout.write_text_atomic(str(path), "nuovo \ud800")

    assert path.read_text(encoding="utf-8") == "tag esistenti"
    assert os.listdir(tmp_path) == ["001.txt"]


def test_failed_replace_leaves_no_temporary_file(tmp_path, monkeypatch):
    path = tmp_path / "001.txt"
    path.write_text("tag esistenti", encoding="utf-8")

    def broken_replace(src, dst):
        raise OSError("disco pieno")

    monkeypatch.setattr(layout.os, "replace", broken_replace)
    with pytest.raises(OSError):
        layout.write_text_atomic(str(path), "nuovo")

    assert path.read_text(encoding="utf-8") == "tag esistenti"
    assert os.listdir(tmp_path) == ["001.txt"]


def test_keeps_the_permissions_of_an_existing_file(tmp_path):
    path = tmp_path / "001.txt"
    path.write_text("x", encoding="utf-8")
    os.chmod(path, 0o640)

    layout.write_text_atomic(str(path), "y")

    assert mode(path) == 0o640


def test_new_file_follows_the_umask_like_open(tmp_path):
    reference = tmp_path / "open.txt"
    with open(reference, "w", encoding="utf-8") as f:
        f.write("x")

    layout.write_text_atomic(str(tmp_path / "new.txt"), "x")

    # mkstemp crea i file 0600: sarebbero illeggibili per gli altri utenti, a differenza di open()
    assert mode(tmp_path / "new.txt") == mode(reference)


def test_writes_through_a_symlink_without_replacing_it(tmp_path):
    real = tmp_path / "real.txt"
    real.write_text("x", encoding="utf-8")
    link = tmp_path / "001.txt"
    link.symlink_to(real)

    layout.write_text_atomic(str(link), "y")

    assert link.is_symlink()
    assert real.read_text(encoding="utf-8") == "y"
