"""Dump Asia2TV's catalog to ``data/asia2tv.json``.

Strategy:

1. Walk the WordPress ``post-sitemap*.xml`` files to enumerate every
   post URL.
2. Filter out individual episode pages by URL heuristic (the URL slug
   contains the Arabic word "الحلقة" — i.e. "the episode N").
3. Fetch each remaining URL and keep only those whose page actually
   has an episode list (``div.loop-episode``); the rest are tag
   archives, blog posts, etc.

Server URLs per episode are NOT resolved here (one extra fetch per
episode would multiply request volume by ~20×). The static site
links to the source episode page and falls back to the bot for direct
streaming.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import re
import sys
import time
import urllib.parse
from dataclasses import asdict
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from cloudstream_bot.scrapers import Asia2TVScraper  # noqa: E402
from cloudstream_bot.urls import prettify_url  # noqa: E402

log = logging.getLogger("dump_asia2tv")


async def _resolve_servers(
    scraper, episodes: list[dict], concurrency: int
) -> None:
    """Populate ``ep["servers"]`` by scraping each episode's player list."""
    sem = asyncio.Semaphore(concurrency)

    async def one(ep: dict) -> None:
        async with sem:
            try:
                servers = await scraper.load_links(ep["url"])
            except Exception as e:
                log.debug("load_links %s: %s", ep.get("url"), e)
                ep["servers"] = []
                return
        ep["servers"] = [
            {"name": s.name, "url": prettify_url(s.url)} for s in servers
        ]

    await asyncio.gather(*(one(ep) for ep in episodes))

EPISODE_MARKER = urllib.parse.quote("الحلقة").lower()  # "the episode"
SITEMAP_URL = "https://ww1.asia2tv.pw/sitemap.xml"


async def list_post_sitemaps(client: httpx.AsyncClient) -> list[str]:
    resp = await client.get(SITEMAP_URL)
    resp.raise_for_status()
    urls = re.findall(r"<loc>([^<]+)</loc>", resp.text)
    return [u for u in urls if "/post-sitemap" in u]


async def list_post_urls(client: httpx.AsyncClient, sitemap: str) -> list[str]:
    resp = await client.get(sitemap)
    resp.raise_for_status()
    return re.findall(r"<loc>([^<]+)</loc>", resp.text)


def likely_series_url(url: str) -> bool:
    """Cheap pre-filter: episode pages have "الحلقة-N" in the slug."""
    return EPISODE_MARKER not in url.lower()


async def main(
    limit: int | None,
    concurrency: int,
    output: Path,
    resolve_servers: bool,
) -> None:
    scraper = Asia2TVScraper(timeout=30.0)
    client = httpx.AsyncClient(
        headers={"User-Agent": "Mozilla/5.0"},
        follow_redirects=True,
        timeout=30.0,
    )
    try:
        sitemaps = await list_post_sitemaps(client)
        log.info("found %d post-sitemaps", len(sitemaps))

        candidate_urls: list[str] = []
        for sm in sitemaps:
            urls = await list_post_urls(client, sm)
            kept = [u for u in urls if likely_series_url(u)]
            candidate_urls.extend(kept)
            log.info("%s: %d urls (%d kept)", sm.rsplit("/", 1)[-1],
                     len(urls), len(kept))
            if limit and len(candidate_urls) >= limit * 4:
                # Over-collect 4× the limit so we have headroom after
                # filtering out non-series pages downstream.
                break

        log.info("filtering %d candidate URLs to actual series pages",
                 len(candidate_urls))

        sem = asyncio.Semaphore(concurrency)
        out: list[dict] = []
        seen_titles: set[str] = set()

        async def load_one(url: str) -> dict | None:
            async with sem:
                try:
                    title = await scraper.load(url)
                except Exception as e:
                    log.debug("load failed for %s: %s", url, e)
                    return None
                if not title.episodes:
                    return None
                key = title.title.strip().lower()
                if key in seen_titles:
                    return None
                seen_titles.add(key)
                return {
                    "id": url,
                    "title": title.title,
                    "url": title.url,
                    "poster": title.poster,
                    "plot": title.plot,
                    "tags": title.tags,
                    "episodes": [asdict(e) for e in title.episodes],
                }

        # Process in waves of `concurrency * 4` so we can short-circuit on limit.
        idx = 0
        while idx < len(candidate_urls) and (not limit or len(out) < limit):
            batch = candidate_urls[idx: idx + concurrency * 4]
            idx += len(batch)
            results = await asyncio.gather(*(load_one(u) for u in batch))
            kept = [d for d in results if d is not None]
            out.extend(kept)
            log.info("processed %d/%d urls — %d series so far",
                     idx, len(candidate_urls), len(out))
            if limit and len(out) >= limit:
                out = out[:limit]
                break

        if resolve_servers:
            log.info("resolving servers for %d series…", len(out))
            for j, doc in enumerate(out, start=1):
                await _resolve_servers(scraper, doc["episodes"], concurrency)
                if j % 10 == 0 or j == len(out):
                    log.info("server-resolved %d/%d series", j, len(out))

        output.parent.mkdir(parents=True, exist_ok=True)
        out.sort(key=lambda d: d["title"].lower())
        payload = {
            "source": "asia2tv",
            "scraped_at": int(time.time()),
            "count": len(out),
            "titles": out,
        }
        output.write_text(json.dumps(payload, ensure_ascii=False, indent=2))
        log.info("wrote %s (%d series, %d KB)", output, len(out),
                 output.stat().st_size // 1024)
    finally:
        await scraper.aclose()
        await client.aclose()


def cli() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--limit", type=int, default=None,
                   help="Max series to dump (default: full catalog)")
    p.add_argument("--concurrency", type=int, default=8)
    p.add_argument("--output", type=Path, default=Path("data/asia2tv.json"))
    p.add_argument("--resolve-servers", action="store_true",
                   help="Also scrape each episode's server list "
                        "(Okru, Vidmoly, Pixeldrain, …). Slow.")
    args = p.parse_args()
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )
    asyncio.run(main(args.limit, args.concurrency, args.output,
                     args.resolve_servers))


if __name__ == "__main__":
    cli()
