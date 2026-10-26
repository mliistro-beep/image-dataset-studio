# Image Dataset Studio — Copyright (C) 2026 Mauro Liistro
# SPDX-License-Identifier: AGPL-3.0-only
"""Localizzazione dell'interfaccia.

La lingua viene scelta una sola volta all'avvio (setting "language": auto | codice lingua);
"auto" segue la lingua del sistema operativo, con l'inglese se non è tra quelle supportate.
"""
from .i18n_strings import STRINGS

# Nome di ogni lingua scritto nella lingua stessa: è così che la cerca chi non capisce le altre
LANGUAGE_NAMES = {
    "it": "🇮🇹 Italiano",
    "en": "🇬🇧 English",
    "es": "🇪🇸 Español",
    "de": "🇩🇪 Deutsch",
    "fr": "🇫🇷 Français",
    "pt_BR": "🇧🇷 Português (Brasil)",
    "zh_CN": "🇨🇳 简体中文",
    "ja": "🇯🇵 日本語",
}
SUPPORTED_LANGUAGES = tuple(LANGUAGE_NAMES)
_current = "en"


def language_for_locale(locale_name: str) -> str:
    """Lingua supportata per un nome di locale come "pt_PT" o "de_AT"; varianti senza traduzione propria
    (portoghese europeo, cinese tradizionale) usano la più vicina disponibile."""
    if locale_name in SUPPORTED_LANGUAGES:
        return locale_name
    base = locale_name.split("_", 1)[0]
    if base in SUPPORTED_LANGUAGES:
        return base
    return next((lang for lang in SUPPORTED_LANGUAGES if base and lang.startswith(base + "_")), "en")


def detect_system_language() -> str:
    from PySide6.QtCore import QLocale
    return language_for_locale(QLocale.system().name())


def resolve_language(setting: str) -> str:
    return setting if setting in SUPPORTED_LANGUAGES else detect_system_language()


def set_language(lang: str):
    global _current
    _current = lang if lang in SUPPORTED_LANGUAGES else "en"


def current_language() -> str:
    return _current


def install_qt_translator(app) -> None:
    """Traduce i testi interni di Qt (pulsanti Sì/No/Annulla, menu contestuali) con i file forniti da PySide6."""
    from PySide6.QtCore import QLibraryInfo, QTranslator
    if _current == "en":
        return
    translator = QTranslator(app)   # il parent lo tiene in vita quanto l'applicazione
    if translator.load(f"qtbase_{_current}", QLibraryInfo.path(QLibraryInfo.TranslationsPath)):
        app.installTranslator(translator)


def tr(key: str, **kwargs) -> str:
    """Testo tradotto nella lingua attiva. Una chiave mancante viene restituita così com'è."""
    entry = STRINGS.get(key)
    if entry is None:
        return key
    text = entry.get(_current) or entry.get("en") or key
    return text.format(**kwargs) if kwargs else text
