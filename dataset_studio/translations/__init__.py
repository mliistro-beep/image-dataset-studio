# Image Dataset Studio — Copyright (C) 2026 Mauro Liistro
# SPDX-License-Identifier: AGPL-3.0-only
"""Traduzioni oltre a italiano e inglese: un modulo per lingua con STRINGS = {chiave: testo}.
Le chiavi e i segnaposto sono quelli di i18n_strings.py (tests/test_i18n.py controlla che coincidano)."""
from . import de, es, fr, ja, pt_BR, zh_CN

TRANSLATIONS = {
    "es": es.STRINGS,
    "de": de.STRINGS,
    "fr": fr.STRINGS,
    "pt_BR": pt_BR.STRINGS,
    "zh_CN": zh_CN.STRINGS,
    "ja": ja.STRINGS,
}
