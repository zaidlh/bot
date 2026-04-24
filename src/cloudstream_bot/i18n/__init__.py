"""Tiny i18n helper — each language lives in its own JSON file."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Dict

from ..config import AVAILABLE_LANGS, DEFAULT_LANG


_HERE = Path(__file__).parent
_CACHE: Dict[str, Dict[str, str]] = {}


def _load(lang: str) -> Dict[str, str]:
    if lang not in _CACHE:
        path = _HERE / f"{lang}.json"
        _CACHE[lang] = json.loads(path.read_text(encoding="utf-8"))
    return _CACHE[lang]


def t(lang: str, key: str, **kwargs: object) -> str:
    """Translate ``key`` in ``lang``, falling back to English then the key itself."""
    if lang not in AVAILABLE_LANGS:
        lang = DEFAULT_LANG
    entry = _load(lang).get(key)
    if entry is None and lang != DEFAULT_LANG:
        entry = _load(DEFAULT_LANG).get(key)
    if entry is None:
        return key
    try:
        return entry.format(**kwargs)
    except KeyError:
        return entry
