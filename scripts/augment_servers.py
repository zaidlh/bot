"""Add per-episode ``servers`` lists to existing dump JSONs.

Reads ``data/animewitcher.json`` and/or ``data/asia2tv.json`` produced
by the ``dump_*`` scripts and, for every episode, fetches the server
list (Pixeldrain, Bunny, Okru, Vidmoly, …) from the source. Pixeldrain
``/u/<id>`` links are rewritten to ``/api/file/<id>`` via
``cloudstream_bot.urls.prettify_url``.

Designed to be re-runnable: episodes that already have a non-empty
``servers`` list are skipped (use ``--force`` to redo).
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from cloudstream_bot.scrapers import (  # noqa: E402
    AnimeWitcherScraper,
    Asia2TVScraper,
)
from cloudstream_bot.urls import prettify_url  # noqa: E402

log = logging.getLogger("augment_servers")


async def augment_animewitcher(path: Path, concurrency: int, force: bool) -> None:
    payload = json.loads(path.read_text())
    titles = payload["titles"]
    scraper = AnimeWitcherScraper(timeout=30.0)
    sem = asyncio.Semaphore(concurrency)

    total_eps = sum(len(t.get("episodes", [])) for t in titles)
    todo_eps = sum(
        1
        for t in titles
        for e in t.get("episodes", [])
        if force or not e.get("servers")
    )
    log.info(
        "animewitcher: %d titles, %d episodes (%d to resolve)",
        len(titles),
        total_eps,
        todo_eps,
    )

    done = 0

    async def one(title: dict, ep: dict) -> None:
        nonlocal done
        if not force and ep.get("servers"):
            return
        async with sem:
            try:
                servers = await scraper.fetch_servers(title["id"], ep["doc_id"])
            except Exception as e:
                log.debug("fetch_servers %s/%s: %s",
                          title["id"], ep.get("doc_id"), e)
                ep["servers"] = []
                return
        ep["servers"] = [
            {
                "name": s.name,
                "quality": s.quality,
                "link": prettify_url(s.link),
            }
            for s in servers
        ]
        done += 1
        if done % 500 == 0:
            log.info("  %d/%d episodes resolved", done, todo_eps)

    try:
        await asyncio.gather(
            *(
                one(t, e)
                for t in titles
                for e in t.get("episodes", [])
            )
        )
    finally:
        await scraper.aclose()

    payload["scraped_at"] = int(time.time())
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2))
    log.info(
        "animewitcher: wrote %s (%d titles, %d KB)",
        path,
        len(titles),
        path.stat().st_size // 1024,
    )


async def augment_asia2tv(path: Path, concurrency: int, force: bool) -> None:
    payload = json.loads(path.read_text())
    titles = payload["titles"]
    scraper = Asia2TVScraper(timeout=30.0)
    sem = asyncio.Semaphore(concurrency)

    total_eps = sum(len(t.get("episodes", [])) for t in titles)
    todo_eps = sum(
        1
        for t in titles
        for e in t.get("episodes", [])
        if force or not e.get("servers")
    )
    log.info(
        "asia2tv: %d series, %d episodes (%d to resolve)",
        len(titles),
        total_eps,
        todo_eps,
    )

    done = 0

    async def one(ep: dict) -> None:
        nonlocal done
        if not force and ep.get("servers"):
            return
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
        done += 1
        if done % 500 == 0:
            log.info("  %d/%d episodes resolved", done, todo_eps)

    try:
        await asyncio.gather(
            *(
                one(e)
                for t in titles
                for e in t.get("episodes", [])
            )
        )
    finally:
        await scraper.aclose()

    payload["scraped_at"] = int(time.time())
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2))
    log.info(
        "asia2tv: wrote %s (%d series, %d KB)",
        path,
        len(titles),
        path.stat().st_size // 1024,
    )


def cli() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--anime", type=Path, default=Path("data/animewitcher.json"))
    p.add_argument("--asia", type=Path, default=Path("data/asia2tv.json"))
    p.add_argument("--concurrency", type=int, default=8)
    p.add_argument("--force", action="store_true",
                   help="Re-fetch even if servers are already populated")
    p.add_argument("--skip-anime", action="store_true")
    p.add_argument("--skip-asia", action="store_true")
    args = p.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )

    async def run() -> None:
        if not args.skip_anime and args.anime.exists():
            await augment_animewitcher(args.anime, args.concurrency, args.force)
        if not args.skip_asia and args.asia.exists():
            await augment_asia2tv(args.asia, args.concurrency, args.force)

    asyncio.run(run())


if __name__ == "__main__":
    cli()
