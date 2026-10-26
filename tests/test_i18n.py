# Image Dataset Studio — Copyright (C) 2026 Mauro Liistro
# SPDX-License-Identifier: AGPL-3.0-only
"""Catalogo dei testi: completezza delle lingue, segnaposto, scelta della lingua."""
import re
import string

import pytest

from dataset_studio import i18n
from dataset_studio.i18n_strings import STRINGS
from dataset_studio.translations import TRANSLATIONS

_HTML_TAG = re.compile(r"</?([a-zA-Z0-9]+)")


def _placeholders(text: str) -> set:
    return {name for _, name, _, _ in string.Formatter().parse(text) if name is not None}


def test_every_supported_language_has_a_name_and_a_catalog():
    assert i18n.SUPPORTED_LANGUAGES[:2] == ("it", "en")
    assert set(i18n.LANGUAGE_NAMES) == set(i18n.SUPPORTED_LANGUAGES)
    assert set(TRANSLATIONS) == set(i18n.SUPPORTED_LANGUAGES) - {"it", "en"}


@pytest.mark.parametrize("lang", sorted(TRANSLATIONS))
def test_translation_covers_exactly_the_catalog_keys(lang):
    keys = set(TRANSLATIONS[lang])

    assert sorted(set(STRINGS) - keys) == [], "chiavi non tradotte"
    assert sorted(keys - set(STRINGS)) == [], "chiavi inesistenti nel catalogo"


@pytest.mark.parametrize("lang", i18n.SUPPORTED_LANGUAGES)
def test_translations_keep_placeholders_and_html_tags(lang):
    for key, entry in STRINGS.items():
        text, reference = entry[lang], entry["en"]
        assert text.strip(), f"{lang}/{key}: testo vuoto"
        assert _placeholders(text) == _placeholders(reference), f"{lang}/{key}: segnaposto diversi"
        assert sorted(_HTML_TAG.findall(text)) == sorted(_HTML_TAG.findall(reference)), f"{lang}/{key}: tag HTML diversi"


@pytest.mark.parametrize("lang", i18n.SUPPORTED_LANGUAGES)
def test_no_lone_ampersand(lang):
    # Nei pulsanti e nei titoli Qt legge "&" come scorciatoia e mostra "Editor _Cleaner": va scritto "&&"
    lone = [key for key, entry in STRINGS.items() if re.search(r"(?<!&)&(?!&)", entry[lang].replace("&&", ""))]

    assert lone == []


@pytest.mark.parametrize("locale_name, expected", [
    ("it_IT", "it"), ("it_CH", "it"), ("en_US", "en"), ("es_MX", "es"), ("de_AT", "de"), ("fr_CA", "fr"),
    ("pt_BR", "pt_BR"), ("pt_PT", "pt_BR"), ("zh_CN", "zh_CN"), ("zh_TW", "zh_CN"), ("ja_JP", "ja"),
    ("ru_RU", "en"), ("C", "en"), ("", "en"),
])
def test_language_for_locale(locale_name, expected):
    assert i18n.language_for_locale(locale_name) == expected


def test_resolve_language_keeps_explicit_choice_and_detects_auto(monkeypatch):
    monkeypatch.setattr(i18n, "detect_system_language", lambda: "de")

    assert i18n.resolve_language("ja") == "ja"
    assert i18n.resolve_language("auto") == "de"
    assert i18n.resolve_language("xx") == "de"


def test_tr_uses_current_language_and_formats(monkeypatch):
    monkeypatch.setattr(i18n, "_current", "de")

    assert i18n.tr("batch.image_n_of", n=3, total=9) == STRINGS["batch.image_n_of"]["de"].format(n=3, total=9)
    assert i18n.tr("chiave.inesistente") == "chiave.inesistente"
