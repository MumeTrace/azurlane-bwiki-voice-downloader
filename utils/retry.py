"""Shared conservative retry policy."""

from __future__ import annotations

from email.utils import parsedate_to_datetime
from datetime import datetime, timezone


RETRYABLE_HTTP_STATUS = frozenset({429, 500, 502, 503, 504})


def exponential_delay(attempt: int, base: float = 1.0, maximum: float = 30.0) -> float:
    """Return 1, 2, 4, 8... seconds for one-based attempt numbers."""

    return min(base * (2 ** max(0, attempt - 1)), maximum)


def retry_after_seconds(value: str | None) -> float | None:
    if not value:
        return None
    try:
        return max(0.0, float(value))
    except ValueError:
        pass
    try:
        when = parsedate_to_datetime(value)
        if when.tzinfo is None:
            when = when.replace(tzinfo=timezone.utc)
        return max(0.0, (when - datetime.now(timezone.utc)).total_seconds())
    except (TypeError, ValueError, OverflowError):
        return None

