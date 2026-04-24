"""Colab-friendly entrypoint.

The actual code lives in ``src/cloudstream_bot/``. This shim lets you
drop a single file into a Colab notebook and run the full package –
see the README for the three-cell quick start.
"""

from __future__ import annotations

import sys
from pathlib import Path


def _ensure_src_on_path() -> None:
    src = Path(__file__).resolve().parent / "src"
    if src.is_dir() and str(src) not in sys.path:
        sys.path.insert(0, str(src))


_ensure_src_on_path()

# re-export the public API so ``import colab_bot; await colab_bot.run()`` works
from cloudstream_bot.bot import main, run  # noqa: E402

__all__ = ["main", "run"]


if __name__ == "__main__":
    main()
