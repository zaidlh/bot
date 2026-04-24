"""Runtime configuration."""

from __future__ import annotations

import os
from pathlib import Path


DEFAULT_LANG = "en"
AVAILABLE_LANGS = ("en", "ar", "fr")

# Where per-user preferences live (language, default quality…).
PREFS_PATH = Path(
    os.environ.get("CLOUDSTREAM_BOT_PREFS", Path.home() / ".cloudstream-bot-prefs.json")
)

# Where transient downloads land.
DOWNLOAD_DIR = Path(
    os.environ.get("CLOUDSTREAM_BOT_DOWNLOADS", "/tmp/cloudstream-bot")
)


# ---------------------------------------------------------------------------
# Telegram Bot API endpoints
# ---------------------------------------------------------------------------
#
# Set ``TELEGRAM_API_BASE_URL`` (and usually ``TELEGRAM_FILE_API_BASE_URL``) to
# point at a self-hosted `telegram-bot-api` server – the cloud API caps
# uploads at 50 MB, a local server goes up to 2 GB. Example:
#
#     export TELEGRAM_API_BASE_URL=http://127.0.0.1:8081/bot
#     export TELEGRAM_FILE_API_BASE_URL=http://127.0.0.1:8081/file/bot
#
TELEGRAM_API_BASE_URL = os.environ.get("TELEGRAM_API_BASE_URL") or None
TELEGRAM_FILE_API_BASE_URL = os.environ.get("TELEGRAM_FILE_API_BASE_URL") or None


def is_local_mode() -> bool:
    """Are we talking to a self-hosted Bot API server?"""
    return bool(TELEGRAM_API_BASE_URL)


# Cloud API caps: 50 MB per upload, 20 MB when ingesting from a URL.
# Local server is effectively unlimited (2 GB hard cap).
_CLOUD_UPLOAD_LIMIT = 48 * 1024 * 1024
_CLOUD_URL_UPLOAD_LIMIT = 20 * 1024 * 1024
_LOCAL_UPLOAD_LIMIT = int(2_000 * 1024 * 1024)

MAX_UPLOAD_BYTES = _LOCAL_UPLOAD_LIMIT if is_local_mode() else _CLOUD_UPLOAD_LIMIT
TELEGRAM_URL_UPLOAD_LIMIT = (
    _LOCAL_UPLOAD_LIMIT if is_local_mode() else _CLOUD_URL_UPLOAD_LIMIT
)
