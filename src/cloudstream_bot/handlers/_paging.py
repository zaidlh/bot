"""Episode-keyboard pagination helper.

Telegram caps inline keyboards at ~100 buttons per message, so long
series (Naruto has 220 episodes…) need paging. We render a fixed
window of episodes per page plus a nav row:

    [« Prev]   [Page X/N]   [Next »]
"""

from __future__ import annotations

from typing import Callable, List, Sequence, TypeVar

from telegram import InlineKeyboardButton


EP_PER_ROW = 5
ROWS_PER_PAGE = 5  # 5 * 5 = 25 episode buttons per page (+ headers/nav ≈ 30 total)

T = TypeVar("T")


def paginate_episodes(
    episodes: Sequence[T],
    *,
    page: int,
    make_button: Callable[[T], InlineKeyboardButton],
    nav_callback: Callable[[int], str],
    page_label: str = "• {current}/{total} •",
) -> List[List[InlineKeyboardButton]]:
    """Return the middle block of an episode keyboard for ``page``.

    Doesn't include header (send-all / export) rows — those are added
    by the caller because they're specific to the source.
    """
    per_page = EP_PER_ROW * ROWS_PER_PAGE
    total_pages = max(1, (len(episodes) + per_page - 1) // per_page)
    page = max(0, min(page, total_pages - 1))
    start = page * per_page
    end = start + per_page
    window = episodes[start:end]

    rows: List[List[InlineKeyboardButton]] = []
    current: List[InlineKeyboardButton] = []
    for ep in window:
        current.append(make_button(ep))
        if len(current) == EP_PER_ROW:
            rows.append(current)
            current = []
    if current:
        rows.append(current)

    if total_pages > 1:
        nav: List[InlineKeyboardButton] = []
        if page > 0:
            nav.append(
                InlineKeyboardButton("« Prev", callback_data=nav_callback(page - 1))
            )
        nav.append(
            InlineKeyboardButton(
                page_label.format(current=page + 1, total=total_pages),
                callback_data="noop",
            )
        )
        if page < total_pages - 1:
            nav.append(
                InlineKeyboardButton("Next »", callback_data=nav_callback(page + 1))
            )
        rows.append(nav)

    return rows
