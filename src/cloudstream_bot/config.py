"""Runtime configuration."""

from __future__ import annotations

import os
from pathlib import Path


DEFAULT_LANG = "en"
AVAILABLE_LANGS = ("en", "ar", "fr")

# Bot API cap: ~50 MB for sendVideo/sendDocument uploads. Keep some headroom.
MAX_UPLOAD_BYTES = 48 * 1024 * 1024

# Preferred quality when the user hasn't explicitly picked one.
DEFAULT_QUALITY = "480p"
QUALITY_ORDER = ("360p", "480p", "720p", "1080p")

# Where per-user preferences live (language, default quality…).
PREFS_PATH = Path(
    os.environ.get("CLOUDSTREAM_BOT_PREFS", Path.home() / ".cloudstream-bot-prefs.json")
)

# Where transient downloads land.
DOWNLOAD_DIR = Path(
    os.environ.get("CLOUDSTREAM_BOT_DOWNLOADS", "/tmp/cloudstream-bot")
)

# ``sendVideo`` supports direct URL ingestion up to this size.
TELEGRAM_URL_UPLOAD_LIMIT = 20 * 1024 * 1024
