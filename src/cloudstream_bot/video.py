"""Helpers for turning an embed URL into a Telegram video upload."""

from __future__ import annotations

import logging
import re
from typing import Optional, Tuple

import httpx
from telegram import Bot
from telegram.error import TelegramError

from . import extractors
from .config import DOWNLOAD_DIR, MAX_UPLOAD_BYTES, TELEGRAM_URL_UPLOAD_LIMIT


log = logging.getLogger(__name__)


_SAFE_FILENAME_RE = re.compile(r"[^A-Za-z0-9._-]+")


def _sanitize(name: str) -> str:
    return _SAFE_FILENAME_RE.sub("_", name)[:120]


async def probe_content_length(
    client: httpx.AsyncClient, url: str
) -> Optional[int]:
    try:
        resp = await client.head(url, follow_redirects=True, timeout=15)
        if resp.status_code >= 400:
            return None
        cl = resp.headers.get("content-length")
        return int(cl) if cl else None
    except httpx.HTTPError:
        return None


async def send_from_url(
    bot: Bot,
    chat_id: int,
    embed_url: str,
    *,
    client: httpx.AsyncClient,
    caption: Optional[str] = None,
    filename_hint: Optional[str] = None,
) -> Tuple[bool, Optional[str]]:
    """Try to resolve ``embed_url`` to a direct stream and upload it.

    Returns ``(success, error_key)`` where ``error_key`` is one of
    ``"unsupported"`` / ``"too_large"`` / ``"failed"`` when ``success``
    is ``False``.
    """
    stream = await extractors.extract(embed_url, client)
    if stream is None:
        return False, "unsupported"
    if stream.is_hls:
        # HLS → would need ffmpeg to remux; out of scope.
        return False, "unsupported"

    size = stream.content_length
    if size is None and stream.can_telegram_fetch:
        size = await probe_content_length(client, stream.url)
    if size is not None and size > MAX_UPLOAD_BYTES:
        return False, "too_large"

    if stream.can_telegram_fetch and (
        size is not None and size <= TELEGRAM_URL_UPLOAD_LIMIT
    ):
        # Let Telegram fetch the URL itself – the fastest path.
        try:
            await bot.send_video(
                chat_id=chat_id,
                video=stream.url,
                caption=caption,
                supports_streaming=True,
                read_timeout=120,
                write_timeout=120,
            )
            return True, None
        except TelegramError as e:
            log.warning("sendVideo(url=…) failed, falling back to download: %s", e)
            # fall through to download-and-upload

    # Download locally, stream-write, then upload.
    DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)
    fname = _sanitize(stream.filename or filename_hint or "video.mp4")
    if not fname.lower().endswith((".mp4", ".mkv", ".mov", ".webm")):
        fname = f"{fname}.mp4"
    tmp = DOWNLOAD_DIR / fname
    try:
        written = 0
        async with client.stream(
            "GET", stream.url, timeout=httpx.Timeout(None, connect=15)
        ) as r:
            if r.status_code >= 400:
                return False, "failed"
            with tmp.open("wb") as f:
                async for chunk in r.aiter_bytes(chunk_size=256 * 1024):
                    f.write(chunk)
                    written += len(chunk)
                    if written > MAX_UPLOAD_BYTES:
                        return False, "too_large"
        with tmp.open("rb") as fh:
            await bot.send_video(
                chat_id=chat_id,
                video=fh,
                caption=caption,
                filename=fname,
                supports_streaming=True,
                read_timeout=600,
                write_timeout=600,
            )
        return True, None
    except TelegramError as e:
        log.warning("sendVideo upload failed: %s", e)
        return False, "failed"
    except httpx.HTTPError as e:
        log.warning("download failed: %s", e)
        return False, "failed"
    finally:
        if tmp.exists():
            try:
                tmp.unlink()
            except OSError:
                pass
