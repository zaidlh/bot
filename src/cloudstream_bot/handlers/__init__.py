"""Handler registration."""

from __future__ import annotations

from dataclasses import dataclass

import httpx
from telegram.ext import Application, CallbackQueryHandler, CommandHandler

from ..scrapers import AnimeWitcherScraper, Asia2TVScraper
from . import anime, asia, common


@dataclass
class BotDeps:
    asia2tv: Asia2TVScraper
    animewitcher: AnimeWitcherScraper
    client: httpx.AsyncClient


def register(app: Application, deps: BotDeps) -> None:
    app.bot_data["deps"] = deps

    app.add_handler(CommandHandler("start", common.cmd_start))
    app.add_handler(CommandHandler("help", common.cmd_start))
    app.add_handler(CommandHandler("menu", common.cmd_menu))
    app.add_handler(CommandHandler("lang", common.cmd_lang))
    app.add_handler(CommandHandler("asia", asia.cmd_search))
    app.add_handler(CommandHandler("anime", anime.cmd_search))

    app.add_handler(CallbackQueryHandler(common.cb_lang, pattern=r"^lang:"))
    app.add_handler(CallbackQueryHandler(common.cb_menu, pattern=r"^menu:"))

    app.add_handler(CallbackQueryHandler(asia.cb_title, pattern=r"^a2:t:"))
    app.add_handler(CallbackQueryHandler(asia.cb_episode, pattern=r"^a2:e:"))
    app.add_handler(CallbackQueryHandler(asia.cb_send_video, pattern=r"^a2:v:"))

    app.add_handler(CallbackQueryHandler(anime.cb_title, pattern=r"^aw:t:"))
    app.add_handler(CallbackQueryHandler(anime.cb_episode, pattern=r"^aw:e:"))
    app.add_handler(CallbackQueryHandler(anime.cb_send_video, pattern=r"^aw:v:"))
    app.add_handler(CallbackQueryHandler(anime.cb_send_all, pattern=r"^aw:all:"))
    app.add_handler(CallbackQueryHandler(anime.cb_send_all_confirm, pattern=r"^aw:allc:"))
