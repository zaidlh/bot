"""Per-user preferences + an in-memory short-token store.

Preferences (currently just ``lang``) are persisted to a single JSON
file so they survive bot restarts. The token store is transient –
Telegram ``callback_data`` is capped at 64 bytes, so handlers store
real values (URLs, Firestore IDs…) in this dict and pass a short
hex token around.
"""

from __future__ import annotations

import json
import uuid
from threading import Lock
from typing import Any, Dict, Optional, Tuple

from .config import AVAILABLE_LANGS, DEFAULT_LANG, PREFS_PATH


_prefs_lock = Lock()
_prefs_cache: Optional[Dict[str, Dict[str, Any]]] = None


def _load_prefs() -> Dict[str, Dict[str, Any]]:
    global _prefs_cache
    if _prefs_cache is None:
        if PREFS_PATH.is_file():
            try:
                _prefs_cache = json.loads(PREFS_PATH.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                _prefs_cache = {}
        else:
            _prefs_cache = {}
    return _prefs_cache


def _save_prefs() -> None:
    assert _prefs_cache is not None
    PREFS_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = PREFS_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(_prefs_cache, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(PREFS_PATH)


def get_lang(user_id: int) -> str:
    with _prefs_lock:
        prefs = _load_prefs()
        lang = prefs.get(str(user_id), {}).get("lang") or DEFAULT_LANG
    if lang not in AVAILABLE_LANGS:
        return DEFAULT_LANG
    return lang


def set_lang(user_id: int, lang: str) -> None:
    if lang not in AVAILABLE_LANGS:
        raise ValueError(f"unsupported language: {lang}")
    with _prefs_lock:
        prefs = _load_prefs()
        prefs.setdefault(str(user_id), {})["lang"] = lang
        _save_prefs()


# ---------------------------------------------------------------------------
# transient callback-data tokens
# ---------------------------------------------------------------------------
_SESSIONS: Dict[str, Tuple[str, Any]] = {}


def remember(kind: str, value: Any) -> str:
    token = uuid.uuid4().hex[:10]
    _SESSIONS[token] = (kind, value)
    return token


def recall(token: str) -> Optional[Tuple[str, Any]]:
    return _SESSIONS.get(token)
