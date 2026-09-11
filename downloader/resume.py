"""Helpers for safe HTTP Range continuation."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from storage.metadata import atomic_write_json, load_json


CONTENT_RANGE = re.compile(r"^bytes (\d+)-(\d+)/(\d+|\*)$")
UNSATISFIED_RANGE = re.compile(r"^bytes \*/(\d+)$")


@dataclass(frozen=True, slots=True)
class PartialMetadata:
    url: str
    etag: str | None = None
    last_modified: str | None = None


def partial_metadata_path(part_path: Path) -> Path:
    return part_path.with_name(f"{part_path.name}.meta.json")


def load_partial_metadata(part_path: Path) -> PartialMetadata | None:
    value = load_json(partial_metadata_path(part_path))
    if value is None or not isinstance(value.get("url"), str):
        return None
    return PartialMetadata(
        url=value["url"],
        etag=value.get("etag") if isinstance(value.get("etag"), str) else None,
        last_modified=(
            value.get("last_modified")
            if isinstance(value.get("last_modified"), str)
            else None
        ),
    )


def save_partial_metadata(part_path: Path, metadata: PartialMetadata) -> None:
    atomic_write_json(
        partial_metadata_path(part_path),
        {
            "url": metadata.url,
            "etag": metadata.etag,
            "last_modified": metadata.last_modified,
        },
    )


def parse_content_range(value: str | None) -> tuple[int, int, int | None] | None:
    if not value:
        return None
    match = CONTENT_RANGE.match(value.strip())
    if match is None:
        return None
    total = None if match.group(3) == "*" else int(match.group(3))
    return int(match.group(1)), int(match.group(2)), total


def parse_unsatisfied_total(value: str | None) -> int | None:
    if not value:
        return None
    match = UNSATISFIED_RANGE.match(value.strip())
    return int(match.group(1)) if match else None

