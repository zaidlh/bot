"""Small URL-display helpers."""

from __future__ import annotations

import re


_PD_VIEW_RE = re.compile(r"https?://pixeldrain\.com/u/([A-Za-z0-9]+)")


def prettify_url(url: str) -> str:
    """Rewrite URLs into the most useful form for the user.

    For pixeldrain the ``/u/<id>`` page is just a viewer; the ``/api/file/<id>``
    variant is a direct download that works in VLC / mpv / a browser tab
    without any intermediate page.
    """
    m = _PD_VIEW_RE.match(url)
    if m:
        return f"https://pixeldrain.com/api/file/{m.group(1)}"
    return url
