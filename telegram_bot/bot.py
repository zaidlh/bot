"""Bot entrypoint.

Run with ``python -m telegram_bot.bot`` after setting ``TELEGRAM_BOT_TOKEN``
in the environment (or in a ``.env`` file next to this package).
"""

from __future__ import annotations

import asyncio
import logging
import os
import signal
from pathlib import Path

from telegram.ext import Application

from .handlers import BotDeps, register
from .scrapers import AnimeWitcherScraper, Asia2TVScraper


log = logging.getLogger("telegram_bot")


def _load_dotenv() -> None:
    """Minimal ``.env`` loader – avoids a hard dependency on python-dotenv."""
    path = Path.cwd() / ".env"
    if not path.is_file():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)


async def _run() -> None:
    logging.basicConfig(
        level=os.environ.get("LOG_LEVEL", "INFO"),
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )
    _load_dotenv()

    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not token:
        raise SystemExit(
            "TELEGRAM_BOT_TOKEN is not set. Create one via @BotFather "
            "and export it (or add it to .env)."
        )

    deps = BotDeps(
        asia2tv=Asia2TVScraper(),
        animewitcher=AnimeWitcherScraper(),
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
        except NotImplementedError:
            # Windows doesn't support signal handlers on the default loop.
            pass
    await stop.wait()

    log.info("Shutting down…")
    await app.updater.stop()
    await app.stop()
    await app.shutdown()
    await deps.asia2tv.aclose()
    await deps.animewitcher.aclose()


def main() -> None:
    asyncio.run(_run())


if __name__ == "__main__":
    main()
