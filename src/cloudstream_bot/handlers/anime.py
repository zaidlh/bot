"""AnimeWitcher handlers: search, title, episodes, send video, send all."""

from __future__ import annotations

import asyncio
import logging
from typing import List, Optional

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ParseMode
from telegram.error import RetryAfter, TelegramError
from telegram.ext import ContextTypes

from ..i18n import t
from ..scrapers.animewitcher import AnimeServer
from ..session import get_lang, recall, remember
from ..urls import prettify_url
from ..video import send_from_url


log = logging.getLogger(__name__)


async def run_search(update: Update, context: ContextTypes.DEFAULT_TYPE, query: str) -> None:
    assert update.message is not None and update.effective_user is not None
    lang = get_lang(update.effective_user.id)
    deps = context.application.bot_data["deps"]
    try:
        results = await deps.animewitcher.search(query, limit=15)
    except Exception as e:
        log.exception("animewitcher search failed")
        await update.message.reply_text(t(lang, "search_failed", err=e))
        return
    if not results:
        await update.message.reply_text(t(lang, "no_results"))
        return
    kb: List[List[InlineKeyboardButton]] = []
    for r in results:
        label = r.english_title or r.name
        if r.type:
            label = f"[{r.type}] {label}"
        kb.append(
            [
                InlineKeyboardButton(
                    label[:60],
                    callback_data=f"aw:t:{remember('aw_title', r.object_id)}",
                )
            ]
        )
    kb.append([InlineKeyboardButton(t(lang, "menu_back"), callback_data="menu:open")])
    await update.message.reply_text(
        t(lang, "anime_results_for", query=query),
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup(kb),
    )


async def cmd_search(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    assert update.message is not None and update.effective_user is not None
    lang = get_lang(update.effective_user.id)
    query = " ".join(context.args or []).strip()
    if not query:
        await update.message.reply_text(t(lang, "usage_anime"))
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
    _, object_id = entry
    deps = context.application.bot_data["deps"]
    try:
        title = await deps.animewitcher.load(object_id)
    except Exception as e:
        log.exception("animewitcher load failed")
        await q.edit_message_text(t(lang, "load_failed", err=e))
        return

    header = f"<b>{title.english_title or title.name}</b>"
    if title.type:
        header += f"  <i>{title.type}</i>"
    if title.tags:
        header += f"\n<i>{' • '.join(title.tags)}</i>"
    if title.story:
        header += f"\n\n{title.story[:500]}"

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
                callback_data="aw:e:" + remember("aw_ep", (object_id, ep.doc_id)),
            )
        )
        if len(row) == 5:
            kb.append(row)
            row = []
    if row:
        kb.append(row)

    # Send-all sits on its own row at the bottom.
    kb.append(
        [
            InlineKeyboardButton(
                t(lang, "send_all_button"),
                callback_data="aw:all:" + remember("aw_all", object_id),
            )
        ]
    )

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
    _, (object_id, episode_doc_id) = entry
    deps = context.application.bot_data["deps"]
    try:
        servers = await deps.animewitcher.fetch_servers(object_id, episode_doc_id)
    except Exception as e:
        log.exception("animewitcher fetch_servers failed")
        await q.edit_message_text(t(lang, "servers_failed", err=e))
        return
    if not servers:
        await q.edit_message_text(t(lang, "no_servers"))
        return

    lines = [t(lang, "embed_servers_header", count=len(servers)), ""]
    kb: List[List[InlineKeyboardButton]] = []
    for s in servers:
        qlabel = f" ({s.quality})" if s.quality else ""
        display = prettify_url(s.link)
        lines.append(f"• <b>{s.name}</b>{qlabel} — <code>{display}</code>")
        label = f"{s.name}{qlabel}"
        kb.append(
            [
                InlineKeyboardButton(
                    f"{t(lang, 'send_video_button')}: {label[:22]}",
                    callback_data="aw:v:" + remember("aw_v", s.link),
                ),
                InlineKeyboardButton(t(lang, "open_in_browser"), url=display),
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
        q.get_bot(), q.message.chat_id, url, client=deps.client
    )
    if not ok:
        if err_key == "too_large":
            await q.message.reply_html(t(lang, "extract_too_large", size_mb=">48", url=url))
        elif err_key == "unsupported":
            await q.message.reply_text(t(lang, "extract_unsupported"))
        else:
            await q.message.reply_html(t(lang, "extract_failed", url=url))


# ---------------------------------------------------------------------------
# "Send all episodes" bulk flow
# ---------------------------------------------------------------------------
_QUALITY_HIGH_TO_LOW = ["1080p", "720p", "540p", "480p", "360p"]


def _quality_rank_high(q: Optional[str]) -> int:
    return _QUALITY_HIGH_TO_LOW.index(q) if q in _QUALITY_HIGH_TO_LOW else 99


def _pick_best_server(servers: List[AnimeServer]) -> Optional[AnimeServer]:
    """Prefer the highest quality that's extractable.

    When no server is extractable we still return the highest-quality
    one so its URL can be posted as a fallback.
    """
    from ..extractors import get_extractor

    extractable = sorted(
        (s for s in servers if get_extractor(s.link) is not None),
        key=lambda s: _quality_rank_high(s.quality),
    )
    if extractable:
        return extractable[0]
    if not servers:
        return None
    return sorted(servers, key=lambda s: _quality_rank_high(s.quality))[0]


async def cb_send_all(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    q = update.callback_query
    assert q is not None and q.data is not None and update.effective_user is not None
    lang = get_lang(update.effective_user.id)
    await q.answer()
    entry = recall(q.data.split(":", 2)[2])
    if entry is None:
        await q.edit_message_text(t(lang, "session_expired"))
        return
    _, object_id = entry
    deps = context.application.bot_data["deps"]
    episodes = await deps.animewitcher.fetch_episodes(object_id)
    confirm_token = remember("aw_allc", (object_id, len(episodes)))
    kb = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    t(lang, "send_all_yes"),
                    callback_data=f"aw:allc:{confirm_token}:yes",
                )
            ],
            [
                InlineKeyboardButton(
                    t(lang, "send_all_cancel"),
                    callback_data=f"aw:allc:{confirm_token}:no",
                )
            ],
        ]
    )
    await q.edit_message_text(
        t(lang, "send_all_confirm", count=len(episodes)),
        parse_mode=ParseMode.HTML,
        reply_markup=kb,
    )


async def cb_send_all_confirm(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    q = update.callback_query
    assert (
        q is not None
        and q.data is not None
        and update.effective_user is not None
        and q.message is not None
    )
    lang = get_lang(update.effective_user.id)
    parts = q.data.split(":")
    # "aw:allc:<token>:<decision>"
    token = parts[2]
    decision = parts[3]
    entry = recall(token)
    if entry is None:
        await q.answer()
        await q.edit_message_text(t(lang, "session_expired"))
        return
    await q.answer()
    if decision != "yes":
        await q.edit_message_text(t(lang, "send_all_cancelled"))
        return

    _, (object_id, _) = entry
    deps = context.application.bot_data["deps"]
    episodes = await deps.animewitcher.fetch_episodes(object_id)
    total = len(episodes)
    progress_msg = await q.edit_message_text(
        t(lang, "send_all_progress", current=0, total=total)
    )
    sent, failed = 0, 0

    for idx, ep in enumerate(episodes, start=1):
        try:
            servers = await deps.animewitcher.fetch_servers(object_id, ep.doc_id)
        except Exception:
            servers = []
        best = _pick_best_server(servers)
        ok = False
        if best is not None:
            caption = f"Ep {ep.number:02d} — {ep.name or ''}".strip()
            try:
                ok, _ = await send_from_url(
                    q.get_bot(),
                    q.message.chat_id,
                    best.link,
                    client=deps.client,
                    caption=caption,
                )
            except RetryAfter as ra:
                await asyncio.sleep(ra.retry_after + 1)
                try:
                    ok, _ = await send_from_url(
                        q.get_bot(),
                        q.message.chat_id,
                        best.link,
                        client=deps.client,
                        caption=caption,
                    )
                except TelegramError:
                    ok = False
            except TelegramError:
                ok = False
        if ok:
            sent += 1
        else:
            failed += 1
            # fall back: post the link so the user can still access it
            if best is not None:
                try:
                    await q.message.reply_html(
                        f"Ep {ep.number:02d}: {best.link}",
                        disable_web_page_preview=True,
                    )
                except TelegramError:
                    pass

        # Update progress every few episodes to avoid spamming editMessage.
        if idx == total or idx % 3 == 0:
            try:
                await progress_msg.edit_text(
                    t(lang, "send_all_progress", current=idx, total=total)
                )
            except TelegramError:
                pass
        # Gentle pacing.
        await asyncio.sleep(1.0)

    try:
        await progress_msg.edit_text(
            t(lang, "send_all_done", sent=sent, total=total, failed=failed)
        )
    except TelegramError:
        pass
