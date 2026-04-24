"""Bot entrypoint."""

from __future__ import annotations

import asyncio
import logging
import os
import signal
import sys
from pathlib import Path

import httpx
from telegram.ext import Application

from .handlers import BotDeps, register
from .scrapers import AnimeWitcherScraper, Asia2TVScraper


log = logging.getLogger("cloudstream_bot")


def _load_dotenv() -> None:
    """Minimal ``.env`` loader — avoids a hard dep on python-dotenv."""
    for candidate in (Path.cwd() / ".env", Path(__file__).resolve().parents[2] / ".env"):
        if not candidate.is_file():
            continue
        for raw in candidate.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))
        break


def _resolve_token() -> str:
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    if token:
        return token
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
        "export it or set os.environ['TELEGRAM_BOT_TOKEN']."
    )


def _ensure_nest_asyncio() -> None:
    try:
        import nest_asyncio  # type: ignore

        nest_asyncio.apply()
    except ImportError:
        pass


async def run() -> None:
    logging.basicConfig(
        level=os.environ.get("LOG_LEVEL", "INFO"),
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )
    _load_dotenv()
    _ensure_nest_asyncio()

    token = _resolve_token()
    client = httpx.AsyncClient(
        timeout=httpx.Timeout(30.0, connect=15.0),
        follow_redirects=True,
    )
    deps = BotDeps(
        asia2tv=Asia2TVScraper(),
        animewitcher=AnimeWitcherScraper(),
        client=client,
    )
    app = Application.builder().token(token).build()
    register(app, deps)

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
        await deps.asia2tv.aclose()
        await deps.animewitcher.aclose()
        await client.aclose()


def main() -> None:
    _ensure_nest_asyncio()
    try:
        asyncio.run(run())
    except RuntimeError:
        asyncio.get_event_loop().run_until_complete(run())


if __name__ == "__main__":
    main()
