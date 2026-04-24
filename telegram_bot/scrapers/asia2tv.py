"""Asia2TV scraper.

Port of the Cloudstream 3 ``Asia2tvProvider`` Kotlin plugin
(``com.asia2tv.Asia2tv``) distributed as ``Aia2tv 2.cs3``.

The original plugin targets ``https://ww1.asia2tv.pw``. Only the three
user-facing flows are implemented here:

* ``search`` – full-site search (``/?s=<query>``)
* ``load``   – title page → plot / poster / episode list
* ``load_links`` – episode page → list of embed URLs

Extracting actual video streams from each embed host (Okru, Vidmoly,
LuluStream, VK, etc.) is intentionally left to the user: the bot returns
the embed URLs so the viewer can open them in a browser / external
player.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional
from urllib.parse import urljoin

import httpx
from bs4 import BeautifulSoup


MAIN_URL = "https://ww1.asia2tv.pw"
HEADERS = {
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
    """Async HTML scraper for asia2tv.pw."""

    def __init__(self, main_url: str = MAIN_URL, timeout: float = 20.0) -> None:
        self.main_url = main_url.rstrip("/")
        self._client = httpx.AsyncClient(
            headers=HEADERS,
            timeout=timeout,
            follow_redirects=True,
        )

    async def aclose(self) -> None:
        await self._client.aclose()

    # ------------------------------------------------------------------
    # public API
    # ------------------------------------------------------------------
    async def search(self, query: str, limit: int = 20) -> List[Asia2TVSearchResult]:
        resp = await self._client.get(f"{self.main_url}/", params={"s": query})
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
        results: List[Asia2TVSearchResult] = []
        for item in soup.select("div.box-item"):
            link = item.select_one("div.postmovie-photo a")
            if link is None or not link.get("href"):
                continue
            url = link["href"].strip()
            # title is in the h3 text or the link's title attribute
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
            results.append(Asia2TVSearchResult(title=title, url=url, poster=poster))
            if len(results) >= limit:
                break
        return results

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
            a.get_text(strip=True) for a in soup.select("div.box-tags a") if a.get_text(strip=True)
        ]

        episodes: List[Asia2TVEpisode] = []
        for idx, a in enumerate(soup.select("div.loop-episode a"), start=1):
            href = a.get("href")
            if not href:
                continue
            # the original plugin keeps the DOM order but numbers sequentially
            episodes.append(
                Asia2TVEpisode(number=idx, url=urljoin(self.main_url, href.strip()))
            )
        # The site lists newest first; reverse to get ascending order.
        episodes.reverse()
        for new_num, ep in enumerate(episodes, start=1):
            ep.number = new_num

        return Asia2TVTitle(
            title=title,
            url=url,
            poster=poster,
            plot=plot,
            tags=tags,
            episodes=episodes,
        )

    async def load_links(self, episode_url: str) -> List[Asia2TVServer]:
        resp = await self._client.get(episode_url)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
        servers: List[Asia2TVServer] = []
        seen: set[str] = set()
        for li in soup.select("li.serverslist[data-server], [data-server]"):
            url = (li.get("data-server") or "").strip()
            if not url or url in seen:
                continue
            seen.add(url)
            # name is typically the trailing class word (e.g. "Vidmoly") or the text
            name = li.get_text(" ", strip=True) or "Server"
            servers.append(Asia2TVServer(name=name, url=url))
        return servers
