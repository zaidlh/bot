"""Dump AnimeWitcher's full catalog to ``data/animewitcher.json``.

The script enumerates every title in the Algolia ``series`` index
(empty query, paginated), then loads each title's full document from
Firestore to capture the episode list.

Usage::

    python -m scripts.dump_animewitcher --limit 50      # quick sample
    python -m scripts.dump_animewitcher                # full catalog

Output schema (see ``web/`` for the consumer): a list of objects with
``id``, ``name``, ``english_title``, ``type``, ``poster``, ``story``,
``tags`` and an ``episodes`` array. Each episode has ``number``,
``doc_id``, ``name``, ``thumb`` and (when available) ``bunny_video_id``.
Server URLs are NOT resolved here — that costs one extra Firestore
fetch per episode and is left to a follow-up dump if needed.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
import time
from dataclasses import asdict
from pathlib import Path

# Allow ``python -m scripts.dump_animewitcher`` from the repo root.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from cloudstream_bot.scrapers import AnimeWitcherScraper  # noqa: E402
from cloudstream_bot.urls import prettify_url  # noqa: E402

log = logging.getLogger("dump_animewitcher")


async def _resolve_servers(
    scraper, object_id: str, episodes: list[dict], concurrency: int
) -> int:
    """Populate ``ep["servers"]`` for each episode. Returns count loaded."""
    sem = asyncio.Semaphore(concurrency)
    loaded = 0

    async def one(ep: dict) -> None:
        nonlocal loaded
        async with sem:
            try:
                servers = await scraper.fetch_servers(object_id, ep["doc_id"])
            except Exception as e:
                log.debug("fetch_servers %s/%s: %s", object_id, ep["doc_id"], e)
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
        loaded += 1

    await asyncio.gather(*(one(ep) for ep in episodes))
    return loaded


async def main(
    limit: int | None,
    concurrency: int,
    output: Path,
    resolve_servers: bool,
) -> None:
    scraper = AnimeWitcherScraper(timeout=30.0)
    try:
        # 1. Enumerate the catalog.
        ids: list[tuple[str, str]] = []  # (object_id, fallback_name)
        page = 0
        while True:
            hits, total_pages = await scraper.browse_page(page, hits_per_page=100)
            for h in hits:
                ids.append((h.object_id, h.name))
            log.info("browsed page %d/%d, +%d hits (total %d)",
                     page + 1, total_pages, len(hits), len(ids))
            page += 1
            if page >= total_pages or (limit and len(ids) >= limit):
                break
        if limit:
            ids = ids[:limit]
        log.info("enumerated %d titles; fetching details…", len(ids))

        # 2. Load each title (parallel, bounded).
        sem = asyncio.Semaphore(concurrency)
        out: list[dict] = []
        ok = 0
        fail = 0

        async def load_one(object_id: str, fallback: str) -> dict | None:
            nonlocal ok, fail
            async with sem:
                try:
                    title = await scraper.load(object_id)
                except Exception as e:
                    log.warning("load failed for %s: %s", object_id, e)
                    fail += 1
                    return None
                ok += 1
                return {
                    "id": title.object_id,
                    "name": title.name,
                    "english_title": title.english_title,
                    "type": title.type,
                    "poster": title.poster,
                    "story": title.story,
                    "tags": title.tags,
                    "episodes": [
                        asdict(e) for e in title.episodes
                    ],
                }

        tasks = [load_one(oid, name) for oid, name in ids]
        for i, fut in enumerate(asyncio.as_completed(tasks), start=1):
            doc = await fut
            if doc is not None:
                out.append(doc)
            if i % 25 == 0 or i == len(tasks):
                log.info("loaded %d/%d (ok=%d fail=%d)", i, len(tasks), ok, fail)

        # 2b. Optionally resolve servers per episode.
        if resolve_servers:
            log.info("resolving servers for %d titles…", len(out))
            for j, doc in enumerate(out, start=1):
                await _resolve_servers(
                    scraper, doc["id"], doc["episodes"], concurrency
                )
                if j % 10 == 0 or j == len(out):
                    log.info("server-resolved %d/%d titles", j, len(out))

        # 3. Write.
        output.parent.mkdir(parents=True, exist_ok=True)
        # Stable sort so diffs are clean.
        out.sort(key=lambda d: (d["english_title"] or d["name"]).lower())
        payload = {
            "source": "animewitcher",
            "scraped_at": int(time.time()),
            "count": len(out),
            "titles": out,
        }
        output.write_text(json.dumps(payload, ensure_ascii=False, indent=2))
        log.info("wrote %s (%d titles, %d KB)", output, len(out),
                 output.stat().st_size // 1024)
    finally:
        await scraper.aclose()


def cli() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--limit", type=int, default=None,
                   help="Max titles to dump (default: full catalog)")
    p.add_argument("--concurrency", type=int, default=8)
    p.add_argument("--output", type=Path,
                   default=Path("data/animewitcher.json"))
    p.add_argument("--resolve-servers", action="store_true",
                   help="Also fetch the per-episode server list "
                        "(Pixeldrain, Bunny, …). Adds ~30 min per 1k titles.")
    args = p.parse_args()
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )
    asyncio.run(main(args.limit, args.concurrency, args.output,
                     args.resolve_servers))


if __name__ == "__main__":
    cli()
