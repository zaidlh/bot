"""Telegram command / callback handlers."""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from typing import Any, Dict, Tuple

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ParseMode
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
)

from .scrapers import AnimeWitcherScraper, Asia2TVScraper


log = logging.getLogger(__name__)

# in-memory session store keyed by short token; callback_data has a 64-byte
# limit so we cannot pass URLs or Firestore IDs directly.
_SESSIONS: Dict[str, Tuple[str, Any]] = {}


def _remember(kind: str, value: Any) -> str:
    token = uuid.uuid4().hex[:8]
    _SESSIONS[token] = (kind, value)
    return token


def _recall(token: str) -> Tuple[str, Any] | None:
    return _SESSIONS.get(token)


@dataclass
class BotDeps:
    asia2tv: Asia2TVScraper
    animewitcher: AnimeWitcherScraper


# ---------------------------------------------------------------------------
# commands
# ---------------------------------------------------------------------------
WELCOME = (
    "<b>Cloudstream → Telegram bridge</b>\n\n"
    "This bot wraps the two Cloudstream 3 extensions that ship with this "
    "repo:\n"
    "• <b>Asia2TV</b> (Asian drama, ww1.asia2tv.pw)\n"
    "• <b>AnimeWitcher</b> (anime, animewitcher.com)\n\n"
    "Commands:\n"
    "  /asia <i>query</i> – search Asia2TV\n"
    "  /anime <i>query</i> – search AnimeWitcher\n"
    "  /help – show this message\n\n"
    "Results come back as buttons. Pick a title to see episodes, then pick "
    "an episode to get stream / embed links."
)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    assert update.message is not None
    await update.message.reply_html(WELCOME)


async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    assert update.message is not None
    await update.message.reply_html(WELCOME)


# ---------------------------------------------------------------------------
# Asia2TV flow
# ---------------------------------------------------------------------------
async def asia_search(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    assert update.message is not None
    query = " ".join(context.args or []).strip()
    if not query:
        await update.message.reply_text("Usage: /asia <query>")
        return
    deps: BotDeps = context.application.bot_data["deps"]
    try:
        results = await deps.asia2tv.search(query, limit=15)
    except Exception as e:
        log.exception("asia2tv search failed")
        await update.message.reply_text(f"Asia2TV search failed: {e}")
        return
    if not results:
        await update.message.reply_text("No results.")
        return
    keyboard = [
        [
            InlineKeyboardButton(
                r.title[:60] or "(untitled)",
                callback_data=f"a2:t:{_remember('a2_title', r.url)}",
            )
        ]
        for r in results
    ]
    await update.message.reply_text(
        f"Asia2TV results for <b>{query}</b>:",
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup(keyboard),
    )


async def asia_title(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    q = update.callback_query
    assert q is not None and q.data is not None
    await q.answer()
    token = q.data.split(":", 2)[2]
    entry = _recall(token)
    if entry is None:
        await q.edit_message_text("Session expired, please search again.")
        return
    _, url = entry
    deps: BotDeps = context.application.bot_data["deps"]
    try:
        title = await deps.asia2tv.load(url)
    except Exception as e:
        log.exception("asia2tv load failed")
        await q.edit_message_text(f"Failed to load title: {e}")
        return

    header = f"<b>{title.title}</b>"
    if title.tags:
        header += f"\n<i>{' • '.join(title.tags)}</i>"
    if title.plot:
        header += f"\n\n{title.plot}"

    if not title.episodes:
        await q.edit_message_text(
            header + "\n\n(no episodes found)",
            parse_mode=ParseMode.HTML,
            disable_web_page_preview=True,
        )
        return

    keyboard = []
    row: list[InlineKeyboardButton] = []
    for ep in title.episodes:
        row.append(
            InlineKeyboardButton(
                f"Ep {ep.number:02d}",
                callback_data=f"a2:e:{_remember('a2_ep', ep.url)}",
            )
        )
        if len(row) == 5:
            keyboard.append(row)
            row = []
    if row:
        keyboard.append(row)

    await q.edit_message_text(
        header + "\n\nPick an episode:",
        parse_mode=ParseMode.HTML,
        disable_web_page_preview=True,
        reply_markup=InlineKeyboardMarkup(keyboard),
    )


async def asia_episode(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    q = update.callback_query
    assert q is not None and q.data is not None
    await q.answer("Fetching servers…")
    token = q.data.split(":", 2)[2]
    entry = _recall(token)
    if entry is None:
        await q.edit_message_text("Session expired, please search again.")
        return
    _, url = entry
    deps: BotDeps = context.application.bot_data["deps"]
    try:
        servers = await deps.asia2tv.load_links(url)
    except Exception as e:
        log.exception("asia2tv load_links failed")
        await q.edit_message_text(f"Failed to load servers: {e}")
        return
    if not servers:
        await q.edit_message_text("No embed servers were published for this episode.")
        return
    lines = [f"<b>Embed servers</b> ({len(servers)}):\n"]
    for s in servers:
        lines.append(f"• <b>{s.name}</b> — {s.url}")
    await q.edit_message_text(
        "\n".join(lines),
        parse_mode=ParseMode.HTML,
        disable_web_page_preview=True,
    )


# ---------------------------------------------------------------------------
# AnimeWitcher flow
# ---------------------------------------------------------------------------
async def anime_search(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    assert update.message is not None
    query = " ".join(context.args or []).strip()
    if not query:
        await update.message.reply_text("Usage: /anime <query>")
        return
    deps: BotDeps = context.application.bot_data["deps"]
    try:
        results = await deps.animewitcher.search(query, limit=15)
    except Exception as e:
        log.exception("animewitcher search failed")
        await update.message.reply_text(f"AnimeWitcher search failed: {e}")
        return
    if not results:
        await update.message.reply_text("No results.")
        return
    keyboard = []
    for r in results:
        label = r.english_title or r.name
        if r.type:
            label = f"[{r.type}] {label}"
        keyboard.append(
            [
                InlineKeyboardButton(
                    label[:60],
                    callback_data=f"aw:t:{_remember('aw_title', r.object_id)}",
                )
            ]
        )
    await update.message.reply_text(
        f"AnimeWitcher results for <b>{query}</b>:",
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup(keyboard),
    )


async def anime_title(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    q = update.callback_query
    assert q is not None and q.data is not None
    await q.answer()
    token = q.data.split(":", 2)[2]
    entry = _recall(token)
    if entry is None:
        await q.edit_message_text("Session expired, please search again.")
        return
    _, object_id = entry
    deps: BotDeps = context.application.bot_data["deps"]
    try:
        title = await deps.animewitcher.load(object_id)
    except Exception as e:
        log.exception("animewitcher load failed")
        await q.edit_message_text(f"Failed to load title: {e}")
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
            header + "\n\n(no episodes available)",
            parse_mode=ParseMode.HTML,
            disable_web_page_preview=True,
        )
        return

    keyboard = []
    row: list[InlineKeyboardButton] = []
    for ep in title.episodes:
        row.append(
            InlineKeyboardButton(
                f"Ep {ep.number:02d}",
                callback_data=(
                    "aw:e:" + _remember("aw_ep", (object_id, ep.doc_id))
                ),
            )
        )
        if len(row) == 5:
            keyboard.append(row)
            row = []
    if row:
        keyboard.append(row)

    await q.edit_message_text(
        header + "\n\nPick an episode:",
        parse_mode=ParseMode.HTML,
        disable_web_page_preview=True,
        reply_markup=InlineKeyboardMarkup(keyboard),
    )


async def anime_episode(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    q = update.callback_query
    assert q is not None and q.data is not None
    await q.answer("Fetching servers…")
    token = q.data.split(":", 2)[2]
    entry = _recall(token)
    if entry is None:
        await q.edit_message_text("Session expired, please search again.")
        return
    _, payload = entry
    object_id, episode_doc_id = payload
    deps: BotDeps = context.application.bot_data["deps"]
    try:
        servers = await deps.animewitcher.fetch_servers(object_id, episode_doc_id)
    except Exception as e:
        log.exception("animewitcher fetch_servers failed")
        await q.edit_message_text(f"Failed to load servers: {e}")
        return
    if not servers:
        await q.edit_message_text("No servers were published for this episode.")
        return
    lines = [f"<b>Servers</b> ({len(servers)}):\n"]
    for s in servers:
        q_label = f" ({s.quality})" if s.quality else ""
        lines.append(f"• <b>{s.name}</b>{q_label} — {s.link}")
    await q.edit_message_text(
        "\n".join(lines),
        parse_mode=ParseMode.HTML,
        disable_web_page_preview=True,
    )


# ---------------------------------------------------------------------------
# registration
# ---------------------------------------------------------------------------
def register(app: Application, deps: BotDeps) -> None:
    app.bot_data["deps"] = deps
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("asia", asia_search))
    app.add_handler(CommandHandler("anime", anime_search))
    app.add_handler(CallbackQueryHandler(asia_title, pattern=r"^a2:t:"))
    app.add_handler(CallbackQueryHandler(asia_episode, pattern=r"^a2:e:"))
    app.add_handler(CallbackQueryHandler(anime_title, pattern=r"^aw:t:"))
    app.add_handler(CallbackQueryHandler(anime_episode, pattern=r"^aw:e:"))
