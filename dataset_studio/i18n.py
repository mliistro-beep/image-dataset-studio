# Image Dataset Studio — Copyright (C) 2026 Mauro Liistro
# SPDX-License-Identifier: AGPL-3.0-only
"""Localizzazione italiano/inglese.

La lingua viene scelta una sola volta all'avvio (setting "language": auto | it | en);
"auto" usa l'italiano se il sistema operativo è in italiano, altrimenti l'inglese.
"""
from .i18n_strings import STRINGS

SUPPORTED_LANGUAGES = ("it", "en")
_current = "en"


def detect_system_language() -> str:
    from PySide6.QtCore import QLocale
    return "it" if QLocale.system().language() == QLocale.Italian else "en"


def resolve_language(setting: str) -> str:
    return setting if setting in SUPPORTED_LANGUAGES else detect_system_language()


def set_language(lang: str):
    global _current
    _current = lang if lang in SUPPORTED_LANGUAGES else "en"


def current_language() -> str:
    return _current


def tr(key: str, **kwargs) -> str:
    """Testo tradotto nella lingua attiva. Una chiave mancante viene restituita così com'è."""
    entry = STRINGS.get(key)
    if entry is None:
        return key
    text = entry.get(_current) or entry.get("en") or key
    return text.format(**kwargs) if kwargs else text
