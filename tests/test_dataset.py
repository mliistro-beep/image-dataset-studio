# Image Dataset Studio — Copyright (C) 2026 Mauro Liistro
# SPDX-License-Identifier: AGPL-3.0-only
"""Struttura del dataset (original_dataset / dataset_tags) e archivi."""
import csv
import os
import zipfile

import pytest
from PIL import Image

from dataset_studio.config import ORIGINAL_DIR, RENAME_MAP_FILE
from dataset_studio.dataset import archive, layout


def make_image(path, color=(200, 0, 0)):
    Image.new("RGB", (4, 4), color).save(path)
    return str(path)


def test_first_import_numbers_copies_txt_and_writes_rename_map(tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    a = make_image(src / "b.png")
    b = make_image(src / "a.jpg")
    (src / "a.txt").write_text("1girl", encoding="utf-8")
    base = tmp_path / "ds"

    created = layout.first_import([a, b], str(base))

    original = base / ORIGINAL_DIR
    assert created == ["000.jpg", "001.png"]
    assert (original / "000.txt").read_text(encoding="utf-8") == "1girl"
    with open(original / RENAME_MAP_FILE, encoding="utf-8") as f:
        rows = list(csv.reader(f))
    assert rows[0] == ["new_name", "original_file", "imported_at"]
    assert [r[:2] for r in rows[1:]] == [["000.jpg", b], ["001.png", a]]
    assert layout.resolve_base_dir(str(original)) == str(base)

    with pytest.raises(layout.DatasetLayoutError):
        layout.first_import([a], str(base))


def test_validate_original_errors_and_warnings(tmp_path):
    original = tmp_path / ORIGINAL_DIR
    original.mkdir()
    for name in ("000.jpg", "001.png", "001.jpg", "03.jpg", "photo.jpg", "005.gif", "003.png"):
        make_image(original / name)
    (original / "009.txt").write_text("orphan", encoding="utf-8")

    errors, warnings = layout.validate_original(str(original))

    joined = "\n".join(errors)
    assert "001.png" in joined          # duplicato di 001.jpg
    assert "03.jpg" in joined           # padding errato
    assert "photo.jpg" in joined        # nome non sequenziale
    assert "005.gif" in joined          # formato non supportato
    assert any("009.txt" in w for w in warnings)
    assert any("002" in w for w in warnings)   # buco nella numerazione


def test_import_new_images_continues_numbering(tmp_path):
    base = tmp_path / "ds"
    layout.first_import([make_image(tmp_path / "x.jpg")], str(base))
    created = layout.import_new_images([make_image(tmp_path / "y.webp")], str(base))
    assert created == ["001.webp"]
    with pytest.raises(layout.DatasetLayoutError):
        (tmp_path / "z.bmp").write_bytes(b"x")
        layout.import_new_images([str(tmp_path / "z.bmp")], str(base))


def test_pending_images_and_sync(tmp_path):
    base = tmp_path / "ds"
    layout.first_import([make_image(tmp_path / "x.jpg"), make_image(tmp_path / "y.jpg")], str(base))
    original, tags, _ = layout.paths_for(str(base))
    (base / ORIGINAL_DIR / "000.txt").write_text("seed", encoding="utf-8")

    assert layout.pending_images(original, tags, False) == ["000.jpg", "001.jpg"]
    layout.sync_image("000.jpg", original, tags, seed_txt=True)
    assert os.path.exists(os.path.join(tags, "000.jpg"))
    assert open(os.path.join(tags, "000.txt"), encoding="utf-8").read() == "seed"
    assert layout.pending_images(original, tags, False) == ["001.jpg"]
    assert layout.pending_images(original, tags, True) == ["000.jpg", "001.jpg"]


def test_extract_zip_keeps_matching_txt(tmp_path):
    img = make_image(tmp_path / "pic.png")
    zpath = tmp_path / "set.zip"
    with zipfile.ZipFile(zpath, "w") as zf:
        zf.write(img, "folder/pic.png")
        zf.writestr("folder/pic.txt", "1girl")
        zf.writestr("folder/notes.txt", "ignored")
    dest = tmp_path / "out"

    names = archive.extract_archive(str(zpath), str(dest))

    assert names == ["pic.png"]
    assert sorted(os.listdir(dest)) == ["pic.png", "pic.txt"]


def test_write_zip_roundtrip_and_archive_stem(tmp_path):
    folder = tmp_path / "data"
    folder.mkdir()
    (folder / "a.txt").write_text("x", encoding="utf-8")
    out = tmp_path / "out.zip"
    archive.write_zip(str(folder), str(out))
    with zipfile.ZipFile(out) as zf:
        assert zf.namelist() == ["a.txt"]
    assert archive.archive_stem("/x/my.set.tar.gz") == "my.set"
    assert archive.archive_stem("/x/data.ZIP") == "data"


def test_first_import_uses_natural_order(tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    paths = [make_image(src / n) for n in ("img10.png", "img2.png", "IMG1.png")]

    layout.first_import(paths, str(tmp_path / "ds"))

    with open(tmp_path / "ds" / ORIGINAL_DIR / RENAME_MAP_FILE, encoding="utf-8") as f:
        rows = list(csv.reader(f))[1:]
    assert [os.path.basename(r[1]) for r in rows] == ["IMG1.png", "img2.png", "img10.png"]


def test_import_new_images_uses_natural_order(tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    base = tmp_path / "ds"
    layout.first_import([make_image(src / "first.png")], str(base))
    paths = [make_image(src / n) for n in ("x11.png", "x9.png")]

    created = layout.import_new_images(paths, str(base))

    assert created == ["001.png", "002.png"]
    with open(base / ORIGINAL_DIR / RENAME_MAP_FILE, encoding="utf-8") as f:
        rows = list(csv.reader(f))[2:]
    assert [os.path.basename(r[1]) for r in rows] == ["x9.png", "x11.png"]


def test_natural_key_handles_non_decimal_digits():
    # "²" è una cifra per isdigit() ma non per \d né per int()
    names = ["a1²3.png", "a10.png", "a2.png"]

    assert sorted(names, key=layout.natural_key) == ["a1²3.png", "a2.png", "a10.png"]


def test_natural_order_is_deterministic_for_case_only_differences():
    names = ["/s/img1.png", "/s/IMG1.png"]

    assert sorted(names, key=layout.natural_key) == sorted(reversed(names), key=layout.natural_key)
