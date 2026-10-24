# Image Dataset Studio — Copyright (C) 2026 Mauro Liistro
# SPDX-License-Identifier: AGPL-3.0-only
from PIL import Image

from dataset_studio.images import flatten_to_rgb


def test_rgba_transparent_becomes_white_opaque_kept():
    img = Image.new("RGBA", (2, 1), (0, 0, 0, 0))
    img.putpixel((1, 0), (10, 20, 30, 255))
    out = flatten_to_rgb(img)
    assert out.mode == "RGB"
    assert out.getpixel((0, 0)) == (255, 255, 255)
    assert out.getpixel((1, 0)) == (10, 20, 30)


def test_la_and_palette_with_transparency():
    assert flatten_to_rgb(Image.new("LA", (1, 1), (0, 0))).getpixel((0, 0)) == (255, 255, 255)
    pal = Image.new("P", (1, 1), 0)
    pal.info["transparency"] = 0
    assert flatten_to_rgb(pal).getpixel((0, 0)) == (255, 255, 255)


def test_plain_rgb_and_grayscale_unchanged():
    assert flatten_to_rgb(Image.new("RGB", (1, 1), (1, 2, 3))).getpixel((0, 0)) == (1, 2, 3)
    assert flatten_to_rgb(Image.new("L", (1, 1), 7)).getpixel((0, 0)) == (7, 7, 7)
