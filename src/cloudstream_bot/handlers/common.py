"""Common / shared handlers: /start, /help, /menu, /lang + search dispatcher."""

from __future__ import annotations

from telegram import (
    ForceReply,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Update,
)
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

from ..i18n import t
from ..session import get_lang, set_lang


# ---------------------------------------------------------------------------
# Keyboards
# ---------------------------------------------------------------------------
def lang_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("🇬🇧 English", callback_data="lang:en"),
                InlineKeyboardButton("🇸🇦 العربية", callback_data="lang:ar"),
                InlineKeyboardButton("🇫🇷 Français", callback_data="lang:fr"),
            ]
        ]
    )


def menu_keyboard(lang: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    t(lang, "menu_search_asia"), callback_data="menu:asia"
                )
            ],
            [
                InlineKeyboardButton(
                    t(lang, "menu_search_anime"), callback_data="menu:anime"
                )
            ],
            [
                InlineKeyboardButton(
                    t(lang, "menu_language"), callback_data="menu:lang"
                ),
                InlineKeyboardButton(t(lang, "menu_help"), callback_data="menu:help"),
            ],
        ]
    )


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    assert update.message is not None and update.effective_user is not None
    lang = get_lang(update.effective_user.id)
    await update.message.reply_text(
        t(lang, "welcome") + "\n\n" + t(lang, "menu_title"),
        parse_mode=ParseMode.HTML,
        reply_markup=menu_keyboard(lang),
    )


async def cmd_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    assert update.message is not None and update.effective_user is not None
    lang = get_lang(update.effective_user.id)
    await update.message.reply_text(
        t(lang, "menu_title"),
        parse_mode=ParseMode.HTML,
        reply_markup=menu_keyboard(lang),
    )


async def cmd_lang(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    assert update.message is not None
    await update.message.reply_text(
        "🌐  Pick a language / اختر اللغة / Choisissez la langue:",
        reply_markup=lang_keyboard(),
    )


# ---------------------------------------------------------------------------
# Callback handlers
# ---------------------------------------------------------------------------
async def cb_lang(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    q = update.callback_query
    assert q is not None and q.data is not None and update.effective_user is not None
    _, new_lang = q.data.split(":", 1)
    set_lang(update.effective_user.id, new_lang)
    await q.answer()
    await q.edit_message_text(
        t(new_lang, "language_updated"),
        reply_markup=InlineKeyboardMarkup(
            [[InlineKeyboardButton(t(new_lang, "menu_back"), callback_data="menu:open")]]
        ),
    )


async def cb_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    q = update.callback_query
    assert (
        q is not None
        and q.data is not None
        and update.effective_user is not None
        and q.message is not None
    )
    lang = get_lang(update.effective_user.id)
    _, target = q.data.split(":", 1)
    await q.answer()

    if target == "asia":
        # Delete the menu message and send a fresh one with ForceReply attached,
        # so the user's reply can be matched deterministically.
        await q.message.reply_text(
            t(lang, "search_prompt_asia"),
            reply_markup=ForceReply(selective=False, input_field_placeholder="asia2tv"),
        )
    elif target == "anime":
        await q.message.reply_text(
            t(lang, "search_prompt_anime"),
            reply_markup=ForceReply(
                selective=False, input_field_placeholder="animewitcher"
            ),
        )
    elif target == "lang":
        await q.edit_message_text(
            "🌐  Pick a language / اختر اللغة / Choisissez la langue:",
            reply_markup=lang_keyboard(),
        )
    elif target == "help":
        await q.edit_message_text(
            t(lang, "welcome"),
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup(
                [
                    [
                        InlineKeyboardButton(
                            t(lang, "menu_back"), callback_data="menu:open"
                        )
                    ]
                ]
            ),
        )
    elif target == "open":
        await q.edit_message_text(
            t(lang, "menu_title"),
            parse_mode=ParseMode.HTML,
            reply_markup=menu_keyboard(lang),
        )


# ---------------------------------------------------------------------------
# Search via reply-to-prompt (no command needed)
# ---------------------------------------------------------------------------
async def on_text_reply(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Route ``ForceReply`` replies to the matching search backend."""
    msg = update.message
    if msg is None or msg.reply_to_message is None or msg.text is None:
        return
    parent = msg.reply_to_message
    if parent.from_user is None or not parent.from_user.is_bot:
        return
    haystack = (parent.text or "").lower()
    query = msg.text.strip()
    if not query:
        return
    # Lazy import to avoid circular imports on module load.
    from . import anime as anime_handlers
    from . import asia as asia_handlers

    # "animewitcher" must be checked before "asia" to avoid false matches
    # on prompts that happen to contain both substrings.
    if "animewitcher" in haystack or "anime" in haystack:
        await anime_handlers.run_search(update, context, query)
    elif "asia2tv" in haystack or "asia" in haystack:
        await asia_handlers.run_search(update, context, query)
