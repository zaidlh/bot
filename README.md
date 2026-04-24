# bot

A single-file Telegram bot that wraps the two Cloudstream 3 extensions
shipped in this repo:

| File               | Plugin class                              | Source site              |
|--------------------|-------------------------------------------|--------------------------|
| `Aia2tv 2.cs3`     | `com.asia2tv.Asia2tvProvider`             | <https://ww1.asia2tv.pw> |
| `Animewitcher.cs3` | `com.animewitcher.AnimeWitcherProvider`   | <https://animewitcher.com> |

`.cs3` files are Cloudstream plugin bundles (a DEX file plus a JSON
manifest) and only run inside the Cloudstream Android app. This repo
re-implements the same scrapers in Python and exposes them as Telegram
commands – everything lives in one file: **`colab_bot.py`**.

## Commands

| Command            | What it does                                  |
|--------------------|-----------------------------------------------|
| `/start`, `/help`  | Show the welcome message                      |
| `/asia <query>`    | Search Asia2TV for Asian drama / movies       |
| `/anime <query>`   | Search AnimeWitcher for anime series / movies |

Search results come back as inline-keyboard buttons. Picking a title
loads its plot / tags / episode list; picking an episode shows the
available embed or direct-link servers (Okru, Vidmoly, LuluStream, VK,
Krakenfiles, Pixeldrain, …). The bot does not re-host any media – it
only returns the same links the Cloudstream plugins would otherwise
resolve inside the Android app.

## Run it on Google Colab

1. Create a bot with [@BotFather](https://t.me/BotFather) and copy the
   token.
2. Open a fresh Colab notebook and paste each of the following into
   its own cell.

   ```python
   # Cell 1 – grab the single-file bot from this repo
   !wget -q https://raw.githubusercontent.com/zaidlh/bot/main/colab_bot.py
   ```

   ```python
   # Cell 2 – install deps
   !pip -q install "python-telegram-bot>=21.4,<22" "httpx>=0.27,<0.29" \
       "beautifulsoup4>=4.12,<5" nest_asyncio
   ```

   ```python
   # Cell 3 – set the token and run
   import os
   os.environ["TELEGRAM_BOT_TOKEN"] = "123456:ABC-paste-your-token-here"
   !python colab_bot.py
   ```

   The third cell keeps the bot running until you stop it (■ in
   Colab's toolbar). Chat with your bot from Telegram while the cell
   is live.

   You can also skip the `!python` subprocess and run the coroutine
   directly inside the notebook – handy when you want to stop and
   restart without losing state:

   ```python
   import colab_bot
   await colab_bot.run()
   ```

   `colab_bot` calls `nest_asyncio.apply()` automatically when it's
   available, so this works inside Colab / Jupyter kernels.

## Run it locally

Requires Python 3.10+.

```bash
git clone https://github.com/zaidlh/bot
cd bot
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

export TELEGRAM_BOT_TOKEN=123456:ABC-paste-your-token-here
python colab_bot.py
```

Long polling is used, so no public URL / webhook is needed. Stop the
bot with `Ctrl+C`.

## How the ports work

* **Asia2TV** is a WordPress site, so the scraper is a straight HTML
  port of the Kotlin plugin (`/?s=…` for search, `div.loop-episode a`
  for the episode list, `li.serverslist[data-server]` for the embed
  URLs).
* **AnimeWitcher** is backed by **Algolia** (index `series`) for
  search and **Firestore REST** for title / episode / server data.
  The scraper mirrors the plugin's `refreshAlgoliaKeys` routine: it
  reads the current `app_id` / `api_key` from
  `Settings/constants.search_settings` in Firestore before the first
  search, then queries Algolia and Firestore exactly the same way the
  `.cs3` does.

## Notes / caveats

* The bot does **not** unwrap each embed to a `.m3u8` / `.mp4` URL.
  The Cloudstream app ships a large library of per-host extractors
  for that; re-implementing all of them is out of scope. Users get a
  clickable embed URL they can open in a browser or any video player
  that supports the host.
* Algolia credentials rotate. `colab_bot.py` refreshes them
  automatically, but if the site operator changes the Firestore
  schema the scraper may need to be updated.
* Both sites host content in Arabic, matching the `lang = "ar"` field
  of the original Kotlin providers – no translation is performed.
