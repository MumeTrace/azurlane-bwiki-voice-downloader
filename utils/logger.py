"""Human-readable console events plus a rotating diagnostic log."""

from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path


def configure_logging(log_dir: Path) -> logging.Logger:
    log_dir.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger("azurlane_bwiki_voice_downloader")
    logger.setLevel(logging.DEBUG)
    if not logger.handlers:
        handler = RotatingFileHandler(
            log_dir / "app.log",
            maxBytes=2_000_000,
            backupCount=3,
            encoding="utf-8",
        )
        handler.setFormatter(
            logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
        )
        logger.addHandler(handler)
    return logger


class Reporter:
    def __init__(self, logger: logging.Logger) -> None:
        self.logger = logger

    def info(self, message: str) -> None:
        print(message, flush=True)
        self.logger.info(message)

    def warning(self, message: str) -> None:
        print(message, flush=True)
        self.logger.warning(message)

    def error(self, message: str) -> None:
        print(message, flush=True)
        self.logger.error(message)

