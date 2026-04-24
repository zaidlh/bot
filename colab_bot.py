"""Single-file Telegram bot wrapping the two Cloudstream 3 plugins that
ship in this repo (``Aia2tv 2.cs3`` → ``Asia2tvProvider`` and
``Animewitcher.cs3`` → ``AnimeWitcherProvider``).

Everything is in this one file so it's easy to upload to Google Colab:

.. code-block:: python

    # Colab cell 1 – install deps
    !pip -q install "python-telegram-bot>=21.4,<22" "httpx>=0.27,<0.29" \
        "beautifulsoup4>=4.12,<5" nest_asyncio

    # Colab cell 2 – set the token and run
    import os
    os.environ["TELEGRAM_BOT_TOKEN"] = "123456:ABC...your-bot-token"
    !python colab_bot.py

Or paste the whole file into a cell and call ``await run()`` – the
script detects an already-running event loop (Colab / Jupyter) and
plays nicely with it via ``nest_asyncio``.

Outside Colab, just ``pip install`` the same three libraries, export
``TELEGRAM_BOT_TOKEN`` and run ``python colab_bot.py``.

Commands:

* ``/start``, ``/help`` – usage
* ``/asia <query>``     – search Asia2TV (ww1.asia2tv.pw)
* ``/anime <query>``    – search AnimeWitcher (animewitcher.com)

Picking a result shows episodes; picking an episode shows the available
embed / direct-link servers. No media is re-hosted – the bot returns
the same links the Cloudstream plugins would otherwise resolve on
Android.
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
import signal
import sys
import urllib.parse
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

import httpx
from bs4 import BeautifulSoup
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ParseMode
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
)


log = logging.getLogger("cloudstream_bot")


# =============================================================================
# Asia2TV scraper (port of com.asia2tv.Asia2tvProvider)
# =============================================================================
ASIA_MAIN_URL = "https://ww1.asia2tv.pw"
_BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    )
}


@dataclass
class Asia2TVSearchResult:
    title: str
    url: str
    poster: Optional[str] = None


@dataclass
class Asia2TVEpisode:
    number: int
    url: str


@dataclass
class Asia2TVTitle:
    title: str
    url: str
    poster: Optional[str] = None
    plot: Optional[str] = None
    tags: List[str] = field(default_factory=list)
    episodes: List[Asia2TVEpisode] = field(default_factory=list)


@dataclass
class Asia2TVServer:
    name: str
    url: str


class Asia2TVScraper:
    """HTML scraper for ww1.asia2tv.pw (WordPress)."""

    def __init__(self, main_url: str = ASIA_MAIN_URL, timeout: float = 20.0) -> None:
        self.main_url = main_url.rstrip("/")
        self._client = httpx.AsyncClient(
            headers=_BROWSER_HEADERS, timeout=timeout, follow_redirects=True
        )

    async def aclose(self) -> None:
        await self._client.aclose()

    async def search(self, query: str, limit: int = 20) -> List[Asia2TVSearchResult]:
        resp = await self._client.get(f"{self.main_url}/", params={"s": query})
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
        out: List[Asia2TVSearchResult] = []
        for item in soup.select("div.box-item"):
            link = item.select_one("div.postmovie-photo a")
            if link is None or not link.get("href"):
                continue
            title_el = item.select_one("div.postmovie-photo h3")
            title = (
                title_el.get_text(" ", strip=True)
                if title_el
                else link.get("title") or ""
            ).strip()
            img = item.select_one("div.image img")
            poster = None
            if img is not None:
                poster = img.get("data-src") or img.get("src")
            out.append(
                Asia2TVSearchResult(title=title, url=link["href"].strip(), poster=poster)
            )
            if len(out) >= limit:
                break
        return out

    async def load(self, url: str) -> Asia2TVTitle:
        resp = await self._client.get(url)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")

        title_el = soup.select_one("h1") or soup.select_one("title")
        title = title_el.get_text(" ", strip=True) if title_el else url

        poster = None
        poster_el = soup.select_one("div.single-thumb-bg > img")
        if poster_el is not None:
            poster = poster_el.get("data-src") or poster_el.get("src")

        plot_el = soup.select_one("div.getcontent p")
        plot = plot_el.get_text(" ", strip=True) if plot_el else None

        tags = [
            a.get_text(strip=True)
            for a in soup.select("div.box-tags a")
            if a.get_text(strip=True)
        ]

        episodes: List[Asia2TVEpisode] = []
        for idx, a in enumerate(soup.select("div.loop-episode a"), start=1):
            href = a.get("href")
            if not href:
                continue
            episodes.append(
                Asia2TVEpisode(
                    number=idx, url=urllib.parse.urljoin(self.main_url, href.strip())
                )
            )
        # Site lists newest first; reverse for ascending order.
        episodes.reverse()
        for i, ep in enumerate(episodes, start=1):
            ep.number = i

        return Asia2TVTitle(
            title=title, url=url, poster=poster, plot=plot, tags=tags, episodes=episodes
        )

    async def load_links(self, episode_url: str) -> List[Asia2TVServer]:
        resp = await self._client.get(episode_url)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
        out: List[Asia2TVServer] = []
        seen: set[str] = set()
        for li in soup.select("li.serverslist[data-server], [data-server]"):
            url = (li.get("data-server") or "").strip()
            if not url or url in seen:
                continue
            seen.add(url)
            out.append(
                Asia2TVServer(name=li.get_text(" ", strip=True) or "Server", url=url)
            )
        return out


# =============================================================================
# AnimeWitcher scraper (port of com.animewitcher.AnimeWitcherProvider)
# =============================================================================
FIREBASE_PROJECT_ID = "animewitcher-1c66d"
FIRESTORE_BASE = (
    f"https://firestore.googleapis.com/v1/projects/{FIREBASE_PROJECT_ID}"
    "/databases/(default)/documents"
)
DEFAULT_ALGOLIA_APP_ID = "XC5QF67TBB"
DEFAULT_ALGOLIA_API_KEY = "3c3b61d7c280fd05ea1d496a40bd2b64"
_ALGOLIA_EXTRA_HEADERS = {
    "User-Agent": "Algolia for Android (3.27.0); Android (13)",
    "Content-Type": "application/json; charset=UTF-8",
}
_SEARCH_ATTRIBUTES = (
    '["objectID","name","poster_uri","type","details","tags","story",'
    '"english_title","_highlightResult"]'
)


@dataclass
class AnimeSearchResult:
    object_id: str
    name: str
    english_title: Optional[str] = None
    type: Optional[str] = None
    poster: Optional[str] = None
    story: Optional[str] = None


@dataclass
class AnimeEpisode:
    doc_id: str
    number: int
    name: Optional[str] = None
    thumb: Optional[str] = None


@dataclass
class AnimeTitle:
    object_id: str
    name: str
    english_title: Optional[str] = None
    type: Optional[str] = None
    poster: Optional[str] = None
    story: Optional[str] = None
    tags: List[str] = field(default_factory=list)
    episodes: List[AnimeEpisode] = field(default_factory=list)


@dataclass
class AnimeServer:
    name: str
    quality: Optional[str]
    link: str
    open_browser: bool = False


def _sv(fields: dict, key: str) -> Optional[str]:
    v = fields.get(key)
    return v.get("stringValue") if isinstance(v, dict) else None


def _iv(fields: dict, key: str) -> Optional[int]:
    v = fields.get(key)
    if not isinstance(v, dict):
        return None
    raw = v.get("integerValue") or v.get("doubleValue")
    try:
        return int(raw) if raw is not None else None
    except (TypeError, ValueError):
        return None


def _bv(fields: dict, key: str, default: bool = False) -> bool:
    v = fields.get(key)
    if not isinstance(v, dict) or "booleanValue" not in v:
        return default
    return bool(v["booleanValue"])


def _string_list(field_value: Optional[dict]) -> List[str]:
    if not isinstance(field_value, dict):
        return []
    out: List[str] = []
    for v in field_value.get("arrayValue", {}).get("values", []) or []:
        if isinstance(v, dict) and v.get("stringValue"):
            out.append(v["stringValue"])
    return out


class AnimeWitcherScraper:
    """Async scraper for animewitcher.com (Algolia + Firestore REST)."""

    def __init__(self, timeout: float = 20.0) -> None:
        self._client = httpx.AsyncClient(timeout=timeout, follow_redirects=True)
        self._algolia_app_id = DEFAULT_ALGOLIA_APP_ID
        self._algolia_api_key = DEFAULT_ALGOLIA_API_KEY
        self._keys_refreshed = False

    async def aclose(self) -> None:
        await self._client.aclose()

    async def refresh_algolia_keys(self) -> None:
        """Mirrors ``AnimeWitcherProvider.refreshAlgoliaKeys``."""
        try:
            resp = await self._client.get(f"{FIRESTORE_BASE}/Settings/constants")
            resp.raise_for_status()
            ss = (
                resp.json()
                .get("fields", {})
                .get("search_settings", {})
                .get("mapValue", {})
                .get("fields", {})
            )
            new_app_id = (ss.get("app_id_v3") or ss.get("app_id") or {}).get(
                "stringValue"
            )
            new_api_key = (ss.get("api_key") or {}).get("stringValue")
            if new_app_id and new_api_key:
                self._algolia_app_id = new_app_id
                self._algolia_api_key = new_api_key
        except Exception:
            pass
        finally:
            self._keys_refreshed = True

    def _algolia_headers(self) -> dict:
        return {
            "X-Algolia-Application-Id": self._algolia_app_id,
            "X-Algolia-API-Key": self._algolia_api_key,
            **_ALGOLIA_EXTRA_HEADERS,
        }

    def _algolia_url(self, index: str) -> str:
        return (
            f"https://{self._algolia_app_id.lower()}-dsn.algolia.net/1/indexes/"
            f"{index}/query"
        )

    async def search(self, query: str, limit: int = 20) -> List[AnimeSearchResult]:
        if not self._keys_refreshed:
            await self.refresh_algolia_keys()
        encoded_query = urllib.parse.quote(query, safe="")
        encoded_attrs = urllib.parse.quote(_SEARCH_ATTRIBUTES, safe="")
        payload = {
            "params": (
                f"attributesToRetrieve={encoded_attrs}&hitsPerPage={limit}"
                f"&page=0&query={encoded_query}"
            )
        }
        resp = await self._client.post(
            self._algolia_url("series"),
            headers=self._algolia_headers(),
            json=payload,
        )
        resp.raise_for_status()
        out: List[AnimeSearchResult] = []
        for h in resp.json().get("hits", []) or []:
            out.append(
                AnimeSearchResult(
                    object_id=h.get("objectID") or "",
                    name=h.get("name") or h.get("english_title") or "Unknown",
                    english_title=h.get("english_title"),
                    type=h.get("type"),
                    poster=h.get("poster_uri"),
                    story=h.get("story"),
                )
            )
        return out

    async def load(self, object_id: str) -> AnimeTitle:
        resp = await self._client.get(
            f"{FIRESTORE_BASE}/anime_list/{urllib.parse.quote(object_id, safe='')}"
        )
        resp.raise_for_status()
        fields = resp.json().get("fields", {}) or {}
        title = AnimeTitle(
            object_id=object_id,
            name=_sv(fields, "name") or object_id,
            english_title=_sv(fields, "english_title"),
            type=_sv(fields, "type"),
            poster=_sv(fields, "poster_uri"),
            story=_sv(fields, "story"),
            tags=_string_list(fields.get("tags")),
        )
        title.episodes = await self.fetch_episodes(object_id)
        return title

    async def fetch_episodes(self, object_id: str) -> List[AnimeEpisode]:
        url = (
            f"{FIRESTORE_BASE}/anime_list/"
            f"{urllib.parse.quote(object_id, safe='')}/episodes?pageSize=300"
        )
        out: List[AnimeEpisode] = []
        next_token: Optional[str] = None
        for _ in range(20):
            params = {"pageToken": next_token} if next_token else None
            resp = await self._client.get(url, params=params)
            if resp.status_code != 200:
                break
            data = resp.json()
            for doc in data.get("documents", []) or []:
                fields = doc.get("fields", {}) or {}
                doc_id = doc.get("name", "").rsplit("/", 1)[-1]
                num = _iv(fields, "number")
                if num is None:
                    m = re.match(r"^\D*(\d+)", doc_id)
                    num = int(m.group(1)) if m else len(out) + 1
                out.append(
                    AnimeEpisode(
                        doc_id=doc_id,
                        number=num,
                        name=_sv(fields, "name") or _sv(fields, "title_en"),
                        thumb=_sv(fields, "thumb_uri"),
                    )
                )
            next_token = data.get("nextPageToken")
            if not next_token:
                break
        out.sort(key=lambda e: e.number)
        return out

    async def fetch_servers(
        self, object_id: str, episode_doc_id: str
    ) -> List[AnimeServer]:
        oid = urllib.parse.quote(object_id, safe="")
        eid = urllib.parse.quote(episode_doc_id, safe="")
        out: List[AnimeServer] = []

        agg_url = (
            f"{FIRESTORE_BASE}/anime_list/{oid}/episodes/{eid}/servers2/all_servers"
        )
        resp = await self._client.get(agg_url)
        if resp.status_code == 200:
            fields = resp.json().get("fields", {}) or {}
            values = (
                fields.get("servers", {}).get("arrayValue", {}).get("values", [])
            )
            for v in values:
                f = v.get("mapValue", {}).get("fields", {})
                if not _bv(f, "visible", default=True):
                    continue
                link = _sv(f, "link")
                if not link:
                    continue
                out.append(
                    AnimeServer(
                        name=_sv(f, "name") or "Server",
                        quality=_sv(f, "quality"),
                        link=link,
                        open_browser=_bv(f, "open_browser", default=False),
                    )
                )
            if out:
                return out

        coll_url = (
            f"{FIRESTORE_BASE}/anime_list/{oid}/episodes/{eid}/servers?pageSize=100"
        )
        resp = await self._client.get(coll_url)
        if resp.status_code == 200:
            for doc in resp.json().get("documents", []) or []:
                f = doc.get("fields", {}) or {}
                if not _bv(f, "visible", default=True):
                    continue
                link = _sv(f, "link")
                if not link:
                    continue
                out.append(
                    AnimeServer(
                        name=_sv(f, "name") or "Server",
                        quality=_sv(f, "quality"),
                        link=link,
                        open_browser=_bv(f, "open_browser", default=False),
                    )
                )
        return out


# =============================================================================
# Telegram handlers
# =============================================================================
WELCOME = (
    "<b>Cloudstream → Telegram bridge</b>\n\n"
    "This bot wraps the two Cloudstream 3 extensions that ship with this repo:\n"
    "• <b>Asia2TV</b> (Asian drama, ww1.asia2tv.pw)\n"
    "• <b>AnimeWitcher</b> (anime, animewitcher.com)\n\n"
    "Commands:\n"
    "  /asia <i>query</i> – search Asia2TV\n"
    "  /anime <i>query</i> – search AnimeWitcher\n"
    "  /help – show this message\n\n"
    "Results come back as buttons. Pick a title to see episodes, then pick "
    "an episode to get stream / embed links."
)

# in-memory store – callback_data has a 64-byte limit, so we key everything
# off short random tokens and look them up here.
_SESSIONS: Dict[str, Tuple[str, Any]] = {}


def _remember(kind: str, value: Any) -> str:
    token = uuid.uuid4().hex[:8]
    _SESSIONS[token] = (kind, value)
    return token


def _recall(token: str) -> Optional[Tuple[str, Any]]:
    return _SESSIONS.get(token)


async def _cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    assert update.message is not None
    await update.message.reply_html(WELCOME)


async def _cmd_asia(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    assert update.message is not None
    query = " ".join(context.args or []).strip()
    if not query:
        await update.message.reply_text("Usage: /asia <query>")
        return
    asia: Asia2TVScraper = context.application.bot_data["asia"]
    try:
        results = await asia.search(query, limit=15)
    except Exception as e:
        log.exception("asia2tv search failed")
        await update.message.reply_text(f"Asia2TV search failed: {e}")
        return
    if not results:
        await update.message.reply_text("No results.")
        return
    kb = [
        [
            InlineKeyboardButton(
                (r.title or "(untitled)")[:60],
                callback_data=f"a2:t:{_remember('a2_title', r.url)}",
            )
        ]
        for r in results
    ]
    await update.message.reply_text(
        f"Asia2TV results for <b>{query}</b>:",
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup(kb),
    )


async def _cb_asia_title(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    q = update.callback_query
    assert q is not None and q.data is not None
    await q.answer()
    entry = _recall(q.data.split(":", 2)[2])
    if entry is None:
        await q.edit_message_text("Session expired, please search again.")
        return
    _, url = entry
    asia: Asia2TVScraper = context.application.bot_data["asia"]
    try:
        title = await asia.load(url)
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

    kb: List[List[InlineKeyboardButton]] = []
    row: List[InlineKeyboardButton] = []
    for ep in title.episodes:
        row.append(
            InlineKeyboardButton(
                f"Ep {ep.number:02d}",
                callback_data=f"a2:e:{_remember('a2_ep', ep.url)}",
            )
        )
        if len(row) == 5:
            kb.append(row)
            row = []
    if row:
        kb.append(row)

    await q.edit_message_text(
        header + "\n\nPick an episode:",
        parse_mode=ParseMode.HTML,
        disable_web_page_preview=True,
        reply_markup=InlineKeyboardMarkup(kb),
    )


async def _cb_asia_episode(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    q = update.callback_query
    assert q is not None and q.data is not None
    await q.answer("Fetching servers…")
    entry = _recall(q.data.split(":", 2)[2])
    if entry is None:
        await q.edit_message_text("Session expired, please search again.")
        return
    _, url = entry
    asia: Asia2TVScraper = context.application.bot_data["asia"]
    try:
        servers = await asia.load_links(url)
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
        "\n".join(lines), parse_mode=ParseMode.HTML, disable_web_page_preview=True
    )


async def _cmd_anime(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    assert update.message is not None
    query = " ".join(context.args or []).strip()
    if not query:
        await update.message.reply_text("Usage: /anime <query>")
        return
    aw: AnimeWitcherScraper = context.application.bot_data["anime"]
    try:
        results = await aw.search(query, limit=15)
    except Exception as e:
        log.exception("animewitcher search failed")
        await update.message.reply_text(f"AnimeWitcher search failed: {e}")
        return
    if not results:
        await update.message.reply_text("No results.")
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
                    callback_data=f"aw:t:{_remember('aw_title', r.object_id)}",
                )
            ]
        )
    await update.message.reply_text(
        f"AnimeWitcher results for <b>{query}</b>:",
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup(kb),
    )


async def _cb_anime_title(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    q = update.callback_query
    assert q is not None and q.data is not None
    await q.answer()
    entry = _recall(q.data.split(":", 2)[2])
    if entry is None:
        await q.edit_message_text("Session expired, please search again.")
        return
    _, object_id = entry
    aw: AnimeWitcherScraper = context.application.bot_data["anime"]
    try:
        title = await aw.load(object_id)
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

    kb: List[List[InlineKeyboardButton]] = []
    row: List[InlineKeyboardButton] = []
    for ep in title.episodes:
        row.append(
            InlineKeyboardButton(
                f"Ep {ep.number:02d}",
                callback_data="aw:e:" + _remember("aw_ep", (object_id, ep.doc_id)),
            )
        )
        if len(row) == 5:
            kb.append(row)
            row = []
    if row:
        kb.append(row)

    await q.edit_message_text(
        header + "\n\nPick an episode:",
        parse_mode=ParseMode.HTML,
        disable_web_page_preview=True,
        reply_markup=InlineKeyboardMarkup(kb),
    )


async def _cb_anime_episode(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    q = update.callback_query
    assert q is not None and q.data is not None
    await q.answer("Fetching servers…")
    entry = _recall(q.data.split(":", 2)[2])
    if entry is None:
        await q.edit_message_text("Session expired, please search again.")
        return
    _, (object_id, episode_doc_id) = entry
    aw: AnimeWitcherScraper = context.application.bot_data["anime"]
    try:
        servers = await aw.fetch_servers(object_id, episode_doc_id)
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
        "\n".join(lines), parse_mode=ParseMode.HTML, disable_web_page_preview=True
    )


# =============================================================================
# Entrypoint
# =============================================================================
def _resolve_token() -> str:
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    if token:
        return token
    # In Colab / Jupyter, prompt interactively instead of crashing.
    if sys.stdin and sys.stdin.isatty():
        try:
            token = input("TELEGRAM_BOT_TOKEN: ").strip()
            if token:
                os.environ["TELEGRAM_BOT_TOKEN"] = token
                return token
        except EOFError:
            pass
    raise SystemExit(
        "TELEGRAM_BOT_TOKEN is not set. Get one from @BotFather, then either "
        "export it or set os.environ['TELEGRAM_BOT_TOKEN'] in your Colab cell."
    )


def _ensure_nest_asyncio() -> None:
    """Allow nested event loops in Colab / Jupyter."""
    try:
        import nest_asyncio  # type: ignore

        nest_asyncio.apply()
    except ImportError:
        pass


def _build_app(token: str) -> Tuple[Application, Asia2TVScraper, AnimeWitcherScraper]:
    asia = Asia2TVScraper()
    anime = AnimeWitcherScraper()
    app = Application.builder().token(token).build()
    app.bot_data["asia"] = asia
    app.bot_data["anime"] = anime
    app.add_handler(CommandHandler("start", _cmd_start))
    app.add_handler(CommandHandler("help", _cmd_start))
    app.add_handler(CommandHandler("asia", _cmd_asia))
    app.add_handler(CommandHandler("anime", _cmd_anime))
    app.add_handler(CallbackQueryHandler(_cb_asia_title, pattern=r"^a2:t:"))
    app.add_handler(CallbackQueryHandler(_cb_asia_episode, pattern=r"^a2:e:"))
    app.add_handler(CallbackQueryHandler(_cb_anime_title, pattern=r"^aw:t:"))
    app.add_handler(CallbackQueryHandler(_cb_anime_episode, pattern=r"^aw:e:"))
    return app, asia, anime


async def run() -> None:
    """Start the bot. Safe to ``await`` from a Colab / Jupyter cell."""
    logging.basicConfig(
        level=os.environ.get("LOG_LEVEL", "INFO"),
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )
    _ensure_nest_asyncio()
    app, asia, anime = _build_app(_resolve_token())

    log.info("Starting bot…")
    await app.initialize()
    await app.start()
    assert app.updater is not None
    await app.updater.start_polling(drop_pending_updates=True)

    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, stop.set)
        except (NotImplementedError, RuntimeError):
            # No signal handlers in notebooks / Windows – stop when
            # the caller cancels the task instead.
            pass

    try:
        await stop.wait()
    except asyncio.CancelledError:
        pass
    finally:
        log.info("Shutting down…")
        await app.updater.stop()
        await app.stop()
        await app.shutdown()
        await asia.aclose()
        await anime.aclose()


def main() -> None:
    _ensure_nest_asyncio()
    try:
        asyncio.run(run())
    except RuntimeError:
        # Already inside a running loop (Colab / Jupyter notebook kernel):
        # schedule the coroutine on the existing loop instead.
        loop = asyncio.get_event_loop()
        loop.run_until_complete(run())


if __name__ == "__main__":
    main()
