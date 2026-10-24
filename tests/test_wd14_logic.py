# Image Dataset Studio — Copyright (C) 2026 Mauro Liistro
# SPDX-License-Identifier: AGPL-3.0-only
"""Logica WD14 senza modello: selezione dei tag, composizione della caption, modalità Append."""
import numpy as np
from PIL import Image

from dataset_studio.engines import wd14

# category: "0" generale, "1" personaggio, "9" rating
TAGS = [
    {"name": "general", "category": "9"},
    {"name": "explicit", "category": "9"},
    {"name": "hatsune_miku", "category": "1"},
    {"name": "1girl", "category": "0"},
    {"name": "long_hair", "category": "0"},
    {"name": "blue_eyes", "category": "0"},
    {"name": "smile", "category": "0"},
]
PROBS = np.array([0.95, 0.01, 0.80, 0.99, 0.70, 0.40, 0.10])


def config(**overrides):
    base = {"gen_thresh": 0.35, "char_thresh": 0.5, "min_tags": 0, "max_tags": 0,
            "replace_under": True, "exclude_ratings": True,
            "trigger_word": "", "prepend_tags": [], "postpend_tags": []}
    base.update(overrides)
    return base


def test_select_tags_thresholds_order_and_ratings():
    tags = wd14.select_tags(PROBS, TAGS, config(), set())
    # personaggi prima, poi generali per probabilità; rating esclusi; underscore sostituiti
    assert tags == ["hatsune miku", "1girl", "long hair", "blue eyes"]


def test_select_tags_keeps_ratings_and_underscores_when_asked():
    tags = wd14.select_tags(PROBS, TAGS, config(exclude_ratings=False, replace_under=False), set())
    assert "general" in tags and "long_hair" in tags


def test_select_tags_banned_matches_both_spellings():
    banned = wd14.build_banned_set(["Long Hair", "blue_eyes"])
    tags = wd14.select_tags(PROBS, TAGS, config(), banned)
    assert "long hair" not in tags and "blue eyes" not in tags


def test_select_tags_min_and_max():
    tags = wd14.select_tags(PROBS, TAGS, config(gen_thresh=0.9, char_thresh=0.9, min_tags=3), set())
    assert tags == ["1girl", "hatsune miku", "long hair"]
    tags = wd14.select_tags(PROBS, TAGS, config(max_tags=2), set())
    assert tags == ["hatsune miku", "1girl"]


def test_assemble_caption_order_and_case_insensitive_dedup():
    cfg = config(trigger_word="mytrigger", prepend_tags=["masterpiece", "1GIRL"], postpend_tags=["smile", "MyTrigger"])
    caption = wd14.assemble_caption(["1girl", "long hair"], cfg)
    assert caption == "mytrigger, masterpiece, 1GIRL, long hair, smile"


def test_merge_append_adds_only_new_model_tags():
    text, existing, new = wd14.merge_append("1girl, red dress", ["1girl", "long hair"])
    assert text == "1girl, red dress, long hair"
    assert (existing, new) == (2, 1)


def test_merge_append_applies_trigger_prepend_and_postpend():
    cfg = config(trigger_word="mytrigger", prepend_tags=["masterpiece"], postpend_tags=["best quality"])
    text, existing, new = wd14.merge_append("1girl, red dress", ["1girl", "long hair"], cfg)
    assert text == "mytrigger, masterpiece, 1girl, red dress, long hair, best quality"
    assert (existing, new) == (2, 4)


def test_merge_append_does_not_duplicate_rules_already_present():
    cfg = config(trigger_word="mytrigger", postpend_tags=["best quality"])
    text, _, new = wd14.merge_append("MyTrigger, 1girl, best quality", ["1girl"], cfg)
    assert text == "MyTrigger, 1girl, best quality"
    assert new == 0


def test_preprocess_pads_and_flattens_transparency_to_white():
    img = Image.new("RGBA", (20, 10), (0, 0, 0, 0))   # completamente trasparente, RGB nero
    _, tensor, resized = wd14.preprocess_image(img, 8)
    assert tensor.shape == (1, 8, 8, 3) and tensor.dtype == np.float32
    assert np.all(tensor == 255.0)
    assert resized.getpixel((4, 4)) == (255, 255, 255)


def test_preprocess_outputs_bgr():
    img = Image.new("RGB", (4, 4), (255, 0, 0))
    _, tensor, _ = wd14.preprocess_image(img, 4)
    assert tuple(tensor[0, 0, 0]) == (0.0, 0.0, 255.0)
