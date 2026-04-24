"""AnimeWitcher handlers: search, title, episodes, send video, send all."""

from __future__ import annotations

import asyncio
import html
import io
import logging
from typing import List, Optional

from telegram import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    InputFile,
    Update,
)
from telegram.constants import ParseMode
from telegram.error import RetryAfter, TelegramError
from telegram.ext import ContextTypes

from ..i18n import t
from ..scrapers.animewitcher import AnimeEpisode, AnimeServer, AnimeTitle
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
            label = f"🎬 [{r.type}] {label}"
        else:
            label = f"🎬 {label}"
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


# ---------------------------------------------------------------------------
# Title view (cover + metadata + paginated episode grid)
# ---------------------------------------------------------------------------
def _render_title_caption(title: AnimeTitle, lang: str) -> str:
    esc = html.escape
    lines: List[str] = []
    main = title.english_title or title.name
    lines.append(f"🎬 <b>{esc(main)}</b>")
    meta_parts: List[str] = []
    if title.type:
        meta_parts.append(f"🗂 {esc(title.type)}")
    if title.episodes:
        meta_parts.append(f"🎞 {len(title.episodes)} eps")
    if meta_parts:
        lines.append("  ".join(meta_parts))
    if title.tags:
        lines.append("🏷 <i>" + esc(" • ".join(title.tags[:6])) + "</i>")
    if title.story:
        # Caption max is 1024 chars on a photo, keep story modest.
        story = title.story.strip()
        if len(story) > 600:
            story = story[:597] + "…"
        lines.append("\n📖 " + esc(story))
    return "\n".join(lines)


def _episodes_keyboard(
    title: AnimeTitle,
    *,
    lang: str,
    page: int,
    title_token: str,
) -> InlineKeyboardMarkup:
    rows: List[List[InlineKeyboardButton]] = []

    # Top action row: Send-all + Export + Back
    rows.append(
        [
            InlineKeyboardButton(
                t(lang, "send_all_button"),
                callback_data="aw:all:" + title_token,
            ),
        ]
    )
    rows.append(
        [
            InlineKeyboardButton(
                t(lang, "export_urls_button"),
                callback_data="aw:exp:" + title_token,
            ),
            InlineKeyboardButton(t(lang, "menu_back"), callback_data="menu:open"),
        ]
    )

    def _ep_button(ep: AnimeEpisode) -> InlineKeyboardButton:
        return InlineKeyboardButton(
            f"▶ {ep.number:02d}",
            callback_data="aw:e:" + remember("aw_ep", (title.object_id, ep.doc_id)),
        )

    def _nav_cb(new_page: int) -> str:
        return f"aw:p:{title_token}:{new_page}"

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
    _, object_id = entry
    deps = context.application.bot_data["deps"]
    try:
        title = await deps.animewitcher.load(object_id)
    except Exception as e:
        log.exception("animewitcher load failed")
        await q.edit_message_text(t(lang, "load_failed", err=e))
        return

    caption = _render_title_caption(title, lang)
    if not title.episodes:
        try:
            await q.edit_message_text(
                caption + "\n\n" + t(lang, "no_episodes"),
                parse_mode=ParseMode.HTML,
                disable_web_page_preview=True,
            )
        except TelegramError:
            pass
        return

    kb = _episodes_keyboard(title, lang=lang, page=0, title_token=token)

    # Replace the search-results message with a fresh cover-photo message.
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
            # Fallback to text if Telegram rejects the photo URL.
            log.warning("send_photo failed for %s, falling back to text", title.poster)
    await bot.send_message(
        chat_id,
        caption,
        parse_mode=ParseMode.HTML,
        disable_web_page_preview=True,
        reply_markup=kb,
    )


async def cb_page(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle episode-grid page navigation."""
    q = update.callback_query
    assert q is not None and q.data is not None and update.effective_user is not None
    await q.answer()
    # "aw:p:<token>:<page>"
    parts = q.data.split(":")
    token = parts[2]
    page = int(parts[3])
    lang = get_lang(update.effective_user.id)
    entry = recall(token)
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

    kb = _episodes_keyboard(title, lang=lang, page=page, title_token=token)
    # If the message is a photo, edit only the reply markup (caption is long).
    try:
        await q.edit_message_reply_markup(reply_markup=kb)
    except TelegramError:
        pass


async def cb_noop(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Absorb clicks on the disabled 'page X/N' indicator."""
    if update.callback_query is not None:
        await update.callback_query.answer()


# ---------------------------------------------------------------------------
# Episode server list
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
    _, (object_id, episode_doc_id) = entry
    deps = context.application.bot_data["deps"]
    try:
        servers = await deps.animewitcher.fetch_servers(object_id, episode_doc_id)
    except Exception as e:
        log.exception("animewitcher fetch_servers failed")
        await q.message.reply_text(t(lang, "servers_failed", err=e))
        return
    if not servers:
        await q.message.reply_text(t(lang, "no_servers"))
        return

    lines = [t(lang, "embed_servers_header", count=len(servers)), ""]
    kb: List[List[InlineKeyboardButton]] = []
    for s in servers:
        qlabel = f" ({s.quality})" if s.quality else ""
        display = prettify_url(s.link)
        lines.append(f"• <b>{html.escape(s.name)}</b>{qlabel} — <code>{html.escape(display)}</code>")
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

    # Send as a new message so the title/cover remains visible above.
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
        q.get_bot(), q.message.chat_id, url, client=deps.client
    )
    if not ok:
        display = prettify_url(url)
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
# Quality picker (used by send-all and export)
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


# ---------------------------------------------------------------------------
# "Send all episodes" bulk flow
# ---------------------------------------------------------------------------
async def cb_send_all(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    q = update.callback_query
    assert (
        q is not None
        and q.data is not None
        and update.effective_user is not None
        and q.message is not None
    )
    lang = get_lang(update.effective_user.id)
    await q.answer()
    entry = recall(q.data.split(":", 2)[2])
    if entry is None:
        await q.message.reply_text(t(lang, "session_expired"))
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
    await q.message.reply_html(
        t(lang, "send_all_confirm", count=len(episodes)),
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
            # fall back: post the link (prettified to /api/file/<id> for PD)
            if best is not None:
                try:
                    await q.message.reply_html(
                        f"Ep {ep.number:02d}: {prettify_url(best.link)}",
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


# ---------------------------------------------------------------------------
# Export all episode URLs as a .txt document
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
    _, object_id = entry
    deps = context.application.bot_data["deps"]
    try:
        title = await deps.animewitcher.load(object_id)
    except Exception as e:
        log.exception("animewitcher load failed")
        await q.message.reply_text(t(lang, "load_failed", err=e))
        return

    progress = await q.message.reply_text(
        t(lang, "export_progress", current=0, total=len(title.episodes))
    )

    lines: List[str] = [
        f"# {title.english_title or title.name}",
        f"# Total episodes: {len(title.episodes)}",
        "",
    ]
    for idx, ep in enumerate(title.episodes, start=1):
        try:
            servers = await deps.animewitcher.fetch_servers(object_id, ep.doc_id)
        except Exception:
            servers = []
        best = _pick_best_server(servers)
        url = prettify_url(best.link) if best else ""
        quality = f" [{best.quality}]" if best and best.quality else ""
        lines.append(f"Ep {ep.number:03d}{quality}: {url}".rstrip())
        if idx % 10 == 0 or idx == len(title.episodes):
            try:
                await progress.edit_text(
                    t(
                        lang,
                        "export_progress",
                        current=idx,
                        total=len(title.episodes),
                    )
                )
            except TelegramError:
                pass

    buf = io.BytesIO(("\n".join(lines) + "\n").encode("utf-8"))
    filename = (title.english_title or title.name).strip() or "episodes"
    safe_name = "".join(c if c.isalnum() or c in " -_." else "_" for c in filename)
    safe_name = (safe_name[:60] or "episodes") + ".txt"
    await q.message.reply_document(
        document=InputFile(buf, filename=safe_name),
        caption=t(lang, "export_done", count=len(title.episodes)),
        parse_mode=ParseMode.HTML,
    )
    try:
        await progress.delete()
    except TelegramError:
        pass
