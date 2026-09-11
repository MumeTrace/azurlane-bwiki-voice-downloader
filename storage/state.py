"""Advisory task state and durable failure records."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .metadata import atomic_write_json, load_json


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class TaskStateStore:
    def __init__(self, path: Path) -> None:
        self.path = path

    def _load(self) -> dict[str, Any]:
        return load_json(self.path) or {"version": 1, "ships": {}}

    def begin_all(self, total: int) -> None:
        state = self._load()
        state.update({"mode": "all", "total": total, "updated_at": utc_now()})
        state.setdefault("ships", {})
        atomic_write_json(self.path, state)

    def update_ship(
        self,
        ship: str,
        status: str,
        *,
        page_url: str | None = None,
        summary: dict[str, int] | None = None,
        error: str | None = None,
    ) -> None:
        state = self._load()
        ships = state.setdefault("ships", {})
        record: dict[str, Any] = {"status": status, "updated_at": utc_now()}
        if page_url:
            record["page_url"] = page_url
        if summary is not None:
            record["summary"] = summary
        if error:
            record["error"] = error
        ships[ship] = record
        state["updated_at"] = utc_now()
        atomic_write_json(self.path, state)


class FailedStore:
    def __init__(self, path: Path) -> None:
        self.path = path

    def replace_ship_failures(self, ship: str, failures: list[dict[str, Any]]) -> None:
        state = load_json(self.path) or {"version": 1, "ships": {}}
        ships = state.setdefault("ships", {})
        if failures:
            ships[ship] = {"updated_at": utc_now(), "items": failures}
        else:
            ships.pop(ship, None)
        state["updated_at"] = utc_now()
        atomic_write_json(self.path, state)
