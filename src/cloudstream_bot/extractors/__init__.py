"""Direct-video extractors.

An *extractor* turns an embed URL (Okru, Pixeldrain, …) into an
:class:`ExtractedStream` – a descriptor of a direct media URL that
Telegram's ``sendVideo`` can ingest (or that the bot can download and
re-upload itself).
"""

from __future__ import annotations

from typing import List, Optional

import httpx

from .base import ExtractedStream, Extractor
from .pixeldrain import PixeldrainExtractor
from .okru import OkruExtractor


_EXTRACTORS: List[Extractor] = [
    PixeldrainExtractor(),
    OkruExtractor(),
]


def get_extractor(url: str) -> Optional[Extractor]:
    for ex in _EXTRACTORS:
        if ex.matches(url):
            return ex
    return None


async def extract(url: str, client: httpx.AsyncClient) -> Optional[ExtractedStream]:
    ex = get_extractor(url)
    if ex is None:
        return None
    try:
        return await ex.extract(url, client)
    except Exception:
        return None


__all__ = ["ExtractedStream", "Extractor", "extract", "get_extractor"]
