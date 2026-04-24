"""Extractor for ok.ru video embeds.

Okru returns IP-bound URLs that can only be fetched from the same
address that loaded the embed page, so the resulting stream is
``can_telegram_fetch=False`` – the bot must download it locally and
re-upload via multipart.
"""

from __future__ import annotations

import html
import json
import re
from typing import Optional

import httpx

from .base import ExtractedStream


_QUALITY_ORDER = ["mobile", "lowest", "low", "sd", "hd", "full", "quad", "ultra"]


class OkruExtractor:
    host = "ok.ru"

    def matches(self, url: str) -> bool:
        return "ok.ru" in url or "odnoklassniki.ru" in url

    async def extract(
        self, url: str, client: httpx.AsyncClient
    ) -> Optional[ExtractedStream]:
        resp = await client.get(
            url,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
                )
            },
            timeout=20,
        )
        if resp.status_code != 200:
            return None
        m = re.search(r'data-options="([^"]+)"', resp.text)
        if not m:
            return None
        try:
            options = json.loads(html.unescape(m.group(1)))
            flashvars = options.get("flashvars", {}) or {}
            meta = flashvars.get("metadata")
            if isinstance(meta, str):
                meta = json.loads(meta)
            videos = (meta or {}).get("videos") or []
        except (ValueError, KeyError):
            return None
        if not videos:
            return None

        # Pick the highest quality we recognise; fall back to the last entry.
        def score(v: dict) -> int:
            name = (v.get("name") or "").lower()
            return _QUALITY_ORDER.index(name) if name in _QUALITY_ORDER else -1

        best = max(videos, key=score)
        direct = best.get("url")
        if not direct:
            return None
        return ExtractedStream(
            url=direct,
            filename=None,
            mime_type="video/mp4",
            can_telegram_fetch=False,
        )
