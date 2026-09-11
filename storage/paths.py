"""All output path construction is centralized here."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from utils.filename import safe_component


@dataclass(frozen=True, slots=True)
class StorageLayout:
    project_root: Path

    @property
    def voices_root(self) -> Path:
        return self.project_root / "voices"

    @property
    def state_root(self) -> Path:
        return self.project_root / "state"

    @property
    def logs_root(self) -> Path:
        return self.project_root / "logs"

    def ensure_roots(self) -> None:
        self.voices_root.mkdir(parents=True, exist_ok=True)
        self.state_root.mkdir(parents=True, exist_ok=True)
        self.logs_root.mkdir(parents=True, exist_ok=True)

    def ship_dir(self, ship_name: str) -> Path:
        return self.voices_root / safe_component(ship_name, max_length=80, fallback="未知舰娘")

    def metadata_path(self, ship_name: str) -> Path:
        return self.ship_dir(ship_name) / "metadata.json"

    def voice_set_dir(self, ship_name: str, directory_name: str) -> Path:
        return self.ship_dir(ship_name) / directory_name

    @property
    def task_state_path(self) -> Path:
        return self.state_root / "state.json"

    @property
    def failed_path(self) -> Path:
        return self.state_root / "failed.json"


def relative_posix(path: Path, base: Path) -> str:
    return path.relative_to(base).as_posix()


def safe_relative_path(base: Path, relative: str, suffix: str) -> Path | None:
    """Resolve an untrusted metadata path without allowing it outside a ship dir."""

    parts = [part for part in relative.split("/") if part not in {"", "."}]
    if any(part == ".." for part in parts):
        return None
    candidate = base.joinpath(*parts).resolve()
    try:
        candidate.relative_to(base.resolve())
    except ValueError:
        return None
    if candidate.suffix.lower() != suffix.lower():
        return None
    return candidate
