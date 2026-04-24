"""Common / shared handlers: /start, /help, /menu, /lang."""

from __future__ import annotations

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

from ..i18n import t
from ..session import get_lang, set_lang


def _lang_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("🇬🇧 English", callback_data="lang:en"),
                InlineKeyboardButton("🇸🇦 العربية", callback_data="lang:ar"),
                InlineKeyboardButton("🇫🇷 Français", callback_data="lang:fr"),
            ]
        ]
    )


def _menu_keyboard(lang: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton(t(lang, "menu_search_asia"), callback_data="menu:asia")],
            [InlineKeyboardButton(t(lang, "menu_search_anime"), callback_data="menu:anime")],
            [InlineKeyboardButton(t(lang, "menu_language"), callback_data="menu:lang")],
        ]
    )


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    assert update.message is not None and update.effective_user is not None
    lang = get_lang(update.effective_user.id)
    await update.message.reply_html(t(lang, "welcome"))


async def cmd_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    assert update.message is not None and update.effective_user is not None
    lang = get_lang(update.effective_user.id)
    await update.message.reply_text(
        t(lang, "menu_title"),
        parse_mode=ParseMode.HTML,
        reply_markup=_menu_keyboard(lang),
    )


async def cmd_lang(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    assert update.message is not None
    await update.message.reply_text(
        "🌐  Pick a language / اختر اللغة / Choisissez la langue:",
        reply_markup=_lang_keyboard(),
    )


async def cb_lang(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    q = update.callback_query
    assert q is not None and q.data is not None and update.effective_user is not None
    _, new_lang = q.data.split(":", 1)
    set_lang(update.effective_user.id, new_lang)
    await q.answer()
    await q.edit_message_text(t(new_lang, "language_updated"))


async def cb_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    q = update.callback_query
    assert q is not None and q.data is not None and update.effective_user is not None
    lang = get_lang(update.effective_user.id)
    _, target = q.data.split(":", 1)
    await q.answer()
    if target == "asia":
        await q.edit_message_text(t(lang, "usage_asia"))
    elif target == "anime":
        await q.edit_message_text(t(lang, "usage_anime"))
    elif target == "lang":
        await q.edit_message_text(
            "🌐  Pick a language / اختر اللغة / Choisissez la langue:",
            reply_markup=_lang_keyboard(),
        )
