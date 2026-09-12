"""Small console compatibility helpers for legacy Windows code pages."""

from __future__ import annotations

import sys
from collections.abc import Iterable
from typing import TextIO


def configure_console_output(streams: Iterable[TextIO] | None = None) -> None:
    """Prevent an unsupported display character from terminating the program."""

    targets = streams if streams is not None else (sys.stdout, sys.stderr)
    for stream in targets:
        reconfigure = getattr(stream, "reconfigure", None)
        if not callable(reconfigure):
            continue
        try:
            reconfigure(errors="replace")
        except (OSError, ValueError):
            continue
