from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Protocol

import httpx


@dataclass
class ExtractedStream:
    url: str
    """Direct URL to the media file."""

    is_hls: bool = False
    """True if ``url`` is an HLS manifest (``.m3u8``)."""

    content_length: Optional[int] = None
    """File size in bytes, when known."""

    filename: Optional[str] = None
    mime_type: Optional[str] = None

    can_telegram_fetch: bool = True
    """False when the direct URL is IP-bound or otherwise requires the
    bot to download it itself before re-uploading (e.g. Okru)."""


class Extractor(Protocol):
    host: str

    def matches(self, url: str) -> bool: ...
    async def extract(
        self, url: str, client: httpx.AsyncClient
    ) -> Optional[ExtractedStream]: ...
