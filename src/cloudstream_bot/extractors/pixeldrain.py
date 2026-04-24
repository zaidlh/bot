"""Extractor for pixeldrain.com."""

from __future__ import annotations

import re
from typing import Optional

import httpx

from .base import ExtractedStream


_FILE_ID_RE = re.compile(r"pixeldrain\.com/(?:u|api/file)/([A-Za-z0-9]+)")


class PixeldrainExtractor:
    host = "pixeldrain.com"

    def matches(self, url: str) -> bool:
        return "pixeldrain.com" in url

    async def extract(
        self, url: str, client: httpx.AsyncClient
    ) -> Optional[ExtractedStream]:
        m = _FILE_ID_RE.search(url)
        if not m:
            return None
        file_id = m.group(1)
        info = await client.get(
            f"https://pixeldrain.com/api/file/{file_id}/info", timeout=15
        )
        if info.status_code != 200:
            return None
        data = info.json()
        if not data.get("success", True):
            return None
        return ExtractedStream(
            url=f"https://pixeldrain.com/api/file/{file_id}",
            content_length=data.get("size"),
            filename=data.get("name"),
            mime_type=data.get("mime_type"),
            can_telegram_fetch=True,
        )
