"""HTML port of ``com.asia2tv.Asia2tvProvider``."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional
from urllib.parse import urljoin

import httpx
from bs4 import BeautifulSoup


MAIN_URL = "https://ww1.asia2tv.pw"
BROWSER_UA = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)


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
    def __init__(self, main_url: str = MAIN_URL, timeout: float = 20.0) -> None:
        self.main_url = main_url.rstrip("/")
        self._client = httpx.AsyncClient(
            headers={"User-Agent": BROWSER_UA},
            timeout=timeout,
            follow_redirects=True,
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
        for a in soup.select("div.loop-episode a"):
            href = a.get("href")
            if href:
                episodes.append(
                    Asia2TVEpisode(
                        number=0, url=urljoin(self.main_url, href.strip())
                    )
                )
        # Site lists newest first – reverse for ascending order.
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
