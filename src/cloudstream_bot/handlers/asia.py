"""Asia2TV search → title → episode → servers → send-video handlers."""

from __future__ import annotations

import html
import io
import logging
from typing import List

from telegram import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    InputFile,
    Update,
)
from telegram.constants import ParseMode
from telegram.error import TelegramError
from telegram.ext import ContextTypes

from ..i18n import t
from ..scrapers.asia2tv import Asia2TVEpisode, Asia2TVTitle
from ..session import get_lang, recall, remember
from ..urls import prettify_url
from ..video import send_from_url
from ._paging import paginate_episodes


log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Search
# ---------------------------------------------------------------------------
async def run_search(update: Update, context: ContextTypes.DEFAULT_TYPE, query: str) -> None:
    assert update.message is not None and update.effective_user is not None
    lang = get_lang(update.effective_user.id)
    deps = context.application.bot_data["deps"]
    try:
        results = await deps.asia2tv.search(query, limit=15)
    except Exception as e:
        log.exception("asia2tv search failed")
        await update.message.reply_text(t(lang, "search_failed", err=e))
        return
    if not results:
        await update.message.reply_text(t(lang, "no_results"))
        return
    kb: List[List[InlineKeyboardButton]] = [
        [
            InlineKeyboardButton(
                f"🎬 {(r.title or '—')[:58]}",
                callback_data=f"a2:t:{remember('a2_title', r.url)}",
            )
        ]
        for r in results
    ]
    kb.append([InlineKeyboardButton(t(lang, "menu_back"), callback_data="menu:open")])
    await update.message.reply_text(
        t(lang, "asia_results_for", query=html.escape(query)),
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup(kb),
    )


async def cmd_search(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    assert update.message is not None and update.effective_user is not None
    lang = get_lang(update.effective_user.id)
    query = " ".join(context.args or []).strip()
    if not query:
        await update.message.reply_text(t(lang, "usage_asia"))
        return
    await run_search(update, context, query)


# ---------------------------------------------------------------------------
# Title view
# ---------------------------------------------------------------------------
def _render_title_caption(title: Asia2TVTitle) -> str:
    esc = html.escape
    lines: List[str] = [f"🎬 <b>{esc(title.title)}</b>"]
    meta: List[str] = []
    if title.episodes:
        meta.append(f"🎞 {len(title.episodes)} eps")
    if meta:
        lines.append("  ".join(meta))
    if title.tags:
        lines.append("🏷 <i>" + esc(" • ".join(title.tags[:6])) + "</i>")
    if title.plot:
        plot = title.plot.strip()
        if len(plot) > 600:
            plot = plot[:597] + "…"
        lines.append("\n📖 " + esc(plot))
    return "\n".join(lines)


def _episodes_keyboard(
    title: Asia2TVTitle, *, lang: str, page: int, title_token: str
) -> InlineKeyboardMarkup:
    rows: List[List[InlineKeyboardButton]] = []
    rows.append(
        [
            InlineKeyboardButton(
                t(lang, "export_urls_button"),
                callback_data="a2:exp:" + title_token,
            ),
            InlineKeyboardButton(t(lang, "menu_back"), callback_data="menu:open"),
        ]
    )

    def _ep_button(ep: Asia2TVEpisode) -> InlineKeyboardButton:
        return InlineKeyboardButton(
            f"▶ {ep.number:02d}",
            callback_data=f"a2:e:{remember('a2_ep', ep.url)}",
        )

    def _nav_cb(new_page: int) -> str:
        return f"a2:p:{title_token}:{new_page}"

    rows.extend(
        paginate_episodes(
            title.episodes,
            page=page,
            make_button=_ep_button,
            nav_callback=_nav_cb,
        )
    )
    return InlineKeyboardMarkup(rows)


async def cb_title(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    q = update.callback_query
    assert (
        q is not None
        and q.data is not None
        and update.effective_user is not None
        and q.message is not None
    )
    lang = get_lang(update.effective_user.id)
    await q.answer()
    token = q.data.split(":", 2)[2]
    entry = recall(token)
    if entry is None:
        await q.edit_message_text(t(lang, "session_expired"))
        return
    _, url = entry
    deps = context.application.bot_data["deps"]
    try:
        title = await deps.asia2tv.load(url)
    except Exception as e:
        log.exception("asia2tv load failed")
        await q.edit_message_text(t(lang, "load_failed", err=e))
        return

    caption = _render_title_caption(title)
    if not title.episodes:
        await q.edit_message_text(
            caption + "\n\n" + t(lang, "no_episodes"),
            parse_mode=ParseMode.HTML,
            disable_web_page_preview=True,
        )
        return

    kb = _episodes_keyboard(title, lang=lang, page=0, title_token=token)
    chat_id = q.message.chat_id
    bot = q.get_bot()
    try:
        await q.message.delete()
    except TelegramError:
        pass
    if title.poster:
        try:
            await bot.send_photo(
                chat_id,
                photo=title.poster,
                caption=caption,
                parse_mode=ParseMode.HTML,
                reply_markup=kb,
            )
            return
        except TelegramError:
            log.warning("asia2tv send_photo failed, falling back to text")
    await bot.send_message(
        chat_id,
        caption,
        parse_mode=ParseMode.HTML,
        disable_web_page_preview=True,
        reply_markup=kb,
    )


async def cb_page(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    q = update.callback_query
    assert (
        q is not None
        and q.data is not None
        and update.effective_user is not None
        and q.message is not None
    )
    await q.answer()
    parts = q.data.split(":")
    token = parts[2]
    page = int(parts[3])
    lang = get_lang(update.effective_user.id)
    entry = recall(token)
    if entry is None:
        # Title message is a photo; use reply_text rather than edit_message_text.
        await q.message.reply_text(t(lang, "session_expired"))
        return
    _, url = entry
    deps = context.application.bot_data["deps"]
    try:
        title = await deps.asia2tv.load(url)
    except Exception as e:
        log.exception("asia2tv load failed")
        await q.message.reply_text(t(lang, "load_failed", err=e))
        return
    kb = _episodes_keyboard(title, lang=lang, page=page, title_token=token)
    try:
        await q.edit_message_reply_markup(reply_markup=kb)
    except TelegramError:
        pass


# ---------------------------------------------------------------------------
# Episode servers
# ---------------------------------------------------------------------------
async def cb_episode(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    q = update.callback_query
    assert (
        q is not None
        and q.data is not None
        and update.effective_user is not None
        and q.message is not None
    )
    lang = get_lang(update.effective_user.id)
    await q.answer(t(lang, "fetching_servers"))
    entry = recall(q.data.split(":", 2)[2])
    if entry is None:
        await q.message.reply_text(t(lang, "session_expired"))
        return
    _, url = entry
    deps = context.application.bot_data["deps"]
    try:
        servers = await deps.asia2tv.load_links(url)
    except Exception as e:
        log.exception("asia2tv load_links failed")
        await q.message.reply_text(t(lang, "servers_failed", err=e))
        return
    if not servers:
        await q.message.reply_text(t(lang, "no_servers"))
        return

    lines = [t(lang, "embed_servers_header", count=len(servers)), ""]
    kb: List[List[InlineKeyboardButton]] = []
    for s in servers:
        display = prettify_url(s.url)
        lines.append(
            f"• <b>{html.escape(s.name)}</b> — <code>{html.escape(display)}</code>"
        )
        kb.append(
            [
                InlineKeyboardButton(
                    f"{t(lang, 'send_video_button')}: {s.name[:20]}",
                    callback_data=f"a2:v:{remember('a2_v', s.url)}",
                ),
                InlineKeyboardButton(
                    t(lang, "open_in_browser"), url=display
                ),
            ]
        )

    await q.message.reply_html(
        "\n".join(lines),
        disable_web_page_preview=True,
        reply_markup=InlineKeyboardMarkup(kb),
    )


async def cb_send_video(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    q = update.callback_query
    assert (
        q is not None
        and q.data is not None
        and update.effective_user is not None
        and q.message is not None
    )
    lang = get_lang(update.effective_user.id)
    await q.answer(t(lang, "fetching_video"))
    entry = recall(q.data.split(":", 2)[2])
    if entry is None:
        await q.message.reply_text(t(lang, "session_expired"))
        return
    _, url = entry
    deps = context.application.bot_data["deps"]
    ok, err_key = await send_from_url(
        q.get_bot(),
        q.message.chat_id,
        url,
        client=deps.client,
        caption=None,
    )
    if not ok:
        display = html.escape(prettify_url(url))
        if err_key == "too_large":
            await q.message.reply_html(
                t(lang, "extract_too_large", size_mb=">48", url=display)
            )
        elif err_key == "unsupported":
            await q.message.reply_html(
                t(lang, "extract_unsupported_fallback", url=display)
            )
        else:
            await q.message.reply_html(t(lang, "extract_failed", url=display))


# ---------------------------------------------------------------------------
# Export all episode embed URLs as .txt
# ---------------------------------------------------------------------------
async def cb_export_urls(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    q = update.callback_query
    assert (
        q is not None
        and q.data is not None
        and update.effective_user is not None
        and q.message is not None
    )
    lang = get_lang(update.effective_user.id)
    await q.answer()
    token = q.data.split(":", 2)[2]
    entry = recall(token)
    if entry is None:
        await q.message.reply_text(t(lang, "session_expired"))
        return
    _, url = entry
    deps = context.application.bot_data["deps"]
    try:
        title = await deps.asia2tv.load(url)
    except Exception as e:
        log.exception("asia2tv load failed")
        await q.message.reply_text(t(lang, "load_failed", err=e))
        return

    lines: List[str] = [
        f"# {title.title}",
        f"# {title.url}",
        f"# Total episodes: {len(title.episodes)}",
        "",
    ]
    for ep in title.episodes:
        try:
            servers = await deps.asia2tv.load_links(ep.url)
        except Exception:
            servers = []
        lines.append(f"Ep {ep.number:03d}: {ep.url}")
        for s in servers:
            lines.append(f"  - {s.name}: {prettify_url(s.url)}")
        lines.append("")

    buf = io.BytesIO(("\n".join(lines) + "\n").encode("utf-8"))
    safe = "".join(c if c.isalnum() or c in " -_." else "_" for c in title.title)
    safe = (safe[:60] or "episodes") + ".txt"
    await q.message.reply_document(
        document=InputFile(buf, filename=safe),
        caption=t(lang, "export_done", count=len(title.episodes)),
        parse_mode=ParseMode.HTML,
    )
