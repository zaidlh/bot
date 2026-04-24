# Cloudstream → Telegram bridge

[![CI](https://github.com/zaidlh/bot/actions/workflows/ci.yml/badge.svg)](https://github.com/zaidlh/bot/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](./LICENSE)
[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/)

A Telegram bot that ports the two Cloudstream 3 plugins shipped in
this repo to Python, so you can browse and stream the same content
from any chat.

| Plugin bundle                            | Kotlin class                            | Source                     |
|------------------------------------------|------------------------------------------|----------------------------|
| [`reference/Aia2tv 2.cs3`](./reference)  | `com.asia2tv.Asia2tvProvider`            | <https://ww1.asia2tv.pw>   |
| [`reference/Animewitcher.cs3`](./reference) | `com.animewitcher.AnimeWitcherProvider` | <https://animewitcher.com> |

## Contents

- [Features](#features)
- [Commands](#commands)
- [Run on Google Colab](#run-on-google-colab)
- [Run locally](#run-locally)
- [Project layout](#project-layout)
- [How the ports work](#how-the-ports-work)
- [Notes & limits](#notes--limits)
- [License](#license)

## Features

- `/asia <query>` – search **Asia2TV** (Asian drama / movies).
- `/anime <query>` – search **AnimeWitcher** (anime series / movies).
- Inline navigation: search → title → episodes → servers.
- **Send as video**: for supported hosts the bot uploads an actual
  `.mp4` to Telegram instead of just a link. Currently implemented:
  - Pixeldrain (direct API, Telegram fetches the file).
  - Ok.ru (embedded player – bot downloads and re-uploads).
- **Send all episodes**: one-click bulk download of every episode of a
  series (sequential, with progress updates and URL fallback for
  hosts that can't be resolved).
- **Three UI languages**: English, العربية, Français – pick with
  `/lang` and the choice is remembered per user.
- **Colab-friendly**: drop `colab_bot.py` into a notebook and run.

## Commands

| Command            | What it does                                     |
|--------------------|--------------------------------------------------|
| `/start`, `/help`  | Show the welcome message                         |
| `/menu`            | Open the main menu (buttons)                     |
| `/lang`            | Switch interface language                        |
| `/asia <query>`    | Search Asia2TV                                   |
| `/anime <query>`   | Search AnimeWitcher                              |

Inline buttons on each title / episode expose **Send video** and
**Open** – the bot uploads the video when the host is supported and
the file fits under Telegram's 50 MB Bot API cap, otherwise it falls
back to a clickable link.

## Run on Google Colab

1. Create a bot with [@BotFather](https://t.me/BotFather) and copy the
   token.
2. Open a fresh Colab notebook and paste each snippet into its own
   cell:

   ```python
   # Cell 1 – clone the repo
   !git clone --depth 1 https://github.com/zaidlh/bot.git
   %cd bot
   ```

   ```python
   # Cell 2 – install deps
   !pip -q install -r requirements.txt
   ```

   ```python
   # Cell 3 – set token and run
   import os
   os.environ["TELEGRAM_BOT_TOKEN"] = "123456:ABC-your-token-here"
   !python colab_bot.py
   ```

   Colab cell 3 keeps the bot running until you stop it (■ in the
   toolbar). Chat with the bot from Telegram while the cell is live.

   Prefer running inside the notebook (so you can stop / restart
   without losing state)? Replace cell 3 with:

   ```python
   import os, colab_bot
   os.environ["TELEGRAM_BOT_TOKEN"] = "123456:ABC-your-token-here"
   await colab_bot.run()
   ```

   `nest_asyncio.apply()` is called automatically, so nested loops in
   Colab / Jupyter just work.

## Run locally

Requires Python 3.10+.

```bash
git clone https://github.com/zaidlh/bot
cd bot
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env
$EDITOR .env   # paste your @BotFather token
python colab_bot.py   # or: python -m cloudstream_bot
```

Long polling is used, so no public URL / webhook is required.

## Project layout

```
bot/
├── colab_bot.py              # one-liner launcher (imports src/)
├── src/
│   └── cloudstream_bot/
│       ├── bot.py            # app setup, entrypoint
│       ├── config.py         # env vars & constants
│       ├── session.py        # per-user prefs + callback-token store
│       ├── video.py          # embed URL → sendVideo pipeline
│       ├── handlers/
│       │   ├── common.py     # /start, /help, /menu, /lang
│       │   ├── asia.py       # Asia2TV search flow
│       │   └── anime.py      # AnimeWitcher search flow + send-all
│       ├── scrapers/
│       │   ├── asia2tv.py
│       │   └── animewitcher.py
│       ├── extractors/
│       │   ├── pixeldrain.py # direct API
│       │   └── okru.py       # data-options JSON
│       └── i18n/
│           ├── en.json
│           ├── ar.json
│           └── fr.json
├── reference/                # original .cs3 Cloudstream plugins
├── requirements.txt
├── pyproject.toml
├── LICENSE
└── .github/workflows/ci.yml  # ruff + import smoke test
```

## How the ports work

- **Asia2TV** is a WordPress site, so
  [`scrapers/asia2tv.py`](src/cloudstream_bot/scrapers/asia2tv.py) is
  a direct HTML port of the Kotlin plugin: `/?s=…` for search,
  `div.loop-episode a` for the episode list,
  `li.serverslist[data-server]` for the embed URLs (Okru, Vidmoly,
  LuluStream, VK, …).
- **AnimeWitcher** is backed by Algolia (index `series`) and
  Firestore REST (project `animewitcher-1c66d`). The scraper in
  [`scrapers/animewitcher.py`](src/cloudstream_bot/scrapers/animewitcher.py)
  mirrors the plugin's `refreshAlgoliaKeys` routine: it reads the
  current `app_id` / `api_key` from
  `Settings/constants.search_settings` in Firestore before the first
  search, then queries Algolia and Firestore exactly the same way the
  `.cs3` does (`anime_list/{id}/episodes`,
  `anime_list/{id}/episodes/{ep}/servers2/all_servers`).
- **Extractors** live under
  [`extractors/`](src/cloudstream_bot/extractors). Each one exposes
  a simple `matches(url)` / `extract(url, client)` pair so more hosts
  can be added incrementally.

## Notes & limits

- Telegram's Bot API caps `sendVideo` at **50 MB** per file. 1080p
  episodes frequently exceed that; the bot auto-picks the lowest
  available quality when bulk-sending and falls back to a link when
  the file is too large.
- Not every embed host is supported. Vidmoly, LuluStream, VK and
  some ad-gated "Server X" redirects use anti-scraping measures; the
  bot keeps returning the URL for those.
- HLS streams (e.g. Bunny.net CDN) are not transcoded – adding that
  would require `ffmpeg` and is out of scope for a Colab-friendly
  deployment.
- Neither the `.cs3` plugins nor this bot host any media; everything
  is fetched from the original sites at request time. If those sites
  go down or change their HTML / Firestore schema, the scrapers will
  need updating.

## License

[MIT](./LICENSE)
