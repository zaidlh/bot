"""Asia2TV search → title → episode → servers → send-video handlers."""

from __future__ import annotations

import logging
from typing import List

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

from ..i18n import t
from ..session import get_lang, recall, remember
from ..urls import prettify_url
from ..video import send_from_url


log = logging.getLogger(__name__)


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
                (r.title or "—")[:60],
                callback_data=f"a2:t:{remember('a2_title', r.url)}",
            )
        ]
        for r in results
    ]
    kb.append([InlineKeyboardButton(t(lang, "menu_back"), callback_data="menu:open")])
    await update.message.reply_text(
        t(lang, "asia_results_for", query=query),
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


async def cb_title(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    q = update.callback_query
    assert q is not None and q.data is not None and update.effective_user is not None
    lang = get_lang(update.effective_user.id)
    await q.answer()
    entry = recall(q.data.split(":", 2)[2])
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

    header = f"<b>{title.title}</b>"
    if title.tags:
        header += f"\n<i>{' • '.join(title.tags)}</i>"
    if title.plot:
        header += f"\n\n{title.plot}"

    if not title.episodes:
        await q.edit_message_text(
            header + "\n\n" + t(lang, "no_episodes"),
            parse_mode=ParseMode.HTML,
            disable_web_page_preview=True,
        )
        return

    kb: List[List[InlineKeyboardButton]] = []
    row: List[InlineKeyboardButton] = []
    for ep in title.episodes:
        row.append(
            InlineKeyboardButton(
                f"Ep {ep.number:02d}",
                callback_data=f"a2:e:{remember('a2_ep', ep.url)}",
            )
        )
        if len(row) == 5:
            kb.append(row)
            row = []
    if row:
        kb.append(row)

    await q.edit_message_text(
        header + "\n\n" + t(lang, "pick_episode"),
        parse_mode=ParseMode.HTML,
        disable_web_page_preview=True,
        reply_markup=InlineKeyboardMarkup(kb),
    )


async def cb_episode(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    q = update.callback_query
    assert q is not None and q.data is not None and update.effective_user is not None
    lang = get_lang(update.effective_user.id)
    await q.answer(t(lang, "fetching_servers"))
    entry = recall(q.data.split(":", 2)[2])
    if entry is None:
        await q.edit_message_text(t(lang, "session_expired"))
        return
    _, url = entry
    deps = context.application.bot_data["deps"]
    try:
        servers = await deps.asia2tv.load_links(url)
    except Exception as e:
        log.exception("asia2tv load_links failed")
        await q.edit_message_text(t(lang, "servers_failed", err=e))
        return
    if not servers:
        await q.edit_message_text(t(lang, "no_servers"))
        return

    lines = [t(lang, "embed_servers_header", count=len(servers)), ""]
    kb: List[List[InlineKeyboardButton]] = []
    for s in servers:
        display = prettify_url(s.url)
        lines.append(f"• <b>{s.name}</b> — <code>{display}</code>")
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

    await q.edit_message_text(
        "\n".join(lines),
        parse_mode=ParseMode.HTML,
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
        await q.edit_message_text(t(lang, "session_expired"))
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
        if err_key == "too_large":
            await q.message.reply_html(t(lang, "extract_too_large", size_mb=">48", url=url))
        elif err_key == "unsupported":
            await q.message.reply_text(t(lang, "extract_unsupported"))
        else:
            await q.message.reply_html(t(lang, "extract_failed", url=url))
