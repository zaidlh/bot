# bot

A Telegram bot that wraps the two Cloudstream 3 extensions shipped in
this repo:

| File                 | Plugin class                         | Source site            |
|----------------------|--------------------------------------|------------------------|
| `Aia2tv 2.cs3`       | `com.asia2tv.Asia2tvProvider`        | <https://ww1.asia2tv.pw> |
| `Animewitcher.cs3`   | `com.animewitcher.AnimeWitcherProvider` | <https://animewitcher.com> |

`.cs3` files are Cloudstream plugin bundles (a DEX file plus a JSON
manifest) and only run inside the Cloudstream Android app. This repo
re-implements the same scrapers in Python and exposes them as Telegram
commands so you can browse titles and fetch streaming links from any
chat.

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

## How the ports work

* **Asia2TV** is a WordPress site, so the scraper in
  `telegram_bot/scrapers/asia2tv.py` is a straight HTML port of the
  Kotlin plugin (`/?s=…` for search, `div.loop-episode a` for the
  episode list, `li.serverslist[data-server]` for the embed URLs).
* **AnimeWitcher** is backed by **Algolia** (index `series`) for search
  and **Firestore REST** for title / episode / server data. The
  scraper in `telegram_bot/scrapers/animewitcher.py` mirrors the
  plugin's `refreshAlgoliaKeys` routine: it reads the current
  `app_id` / `api_key` from `Settings/constants.search_settings` in
  Firestore before every cold start, then queries Algolia and
  Firestore exactly the same way the `.cs3` does.

## Running locally

Requires Python 3.10+.

```bash
git clone https://github.com/zaidlh/bot
cd bot
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env
# edit .env and paste the token you got from @BotFather
python -m telegram_bot.bot
```

The bot uses long polling, so you do **not** need a public URL or a
webhook. Stop it with `Ctrl+C`.

## Project layout

```
telegram_bot/
├── __init__.py
├── bot.py                 # entrypoint, wires scrapers into python-telegram-bot
├── handlers.py            # /start, /help, /asia, /anime + callback flows
└── scrapers/
    ├── __init__.py
    ├── asia2tv.py         # port of Asia2tvProvider (HTML)
    └── animewitcher.py    # port of AnimeWitcherProvider (Algolia + Firestore)
```

## Notes / caveats

* The bot does **not** attempt to extract final `.m3u8` / `.mp4` URLs
  from each embed host. The Cloudstream app ships a large library of
  per-host extractors for that; re-implementing all of them is out of
  scope here. Users get a clickable embed URL they can open in a
  browser or any video player that supports the host.
* Algolia credentials rotate. `AnimeWitcherScraper` refreshes them
  automatically, but if the site operator changes the Firestore schema
  the scraper may need to be updated.
* Both sites host content in Arabic, matching the `lang = "ar"` field
  of the original Kotlin providers – no translation is performed.
