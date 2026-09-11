"""Turn parsed Ship objects into audio, TXT, metadata, and failure state."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from bwiki.models import Ship, VoiceLine
from storage.metadata import MetadataStore, atomic_write_text
from storage.paths import StorageLayout, relative_posix, safe_relative_path
from storage.state import FailedStore, utc_now
from utils.filename import safe_component, unique_stem
from utils.logger import Reporter

from .audio import AudioDownloader, is_valid_mp3


@dataclass(frozen=True, slots=True)
class DownloadSummary:
    success: int
    skipped: int
    failed: int
    no_audio: int

    def as_dict(self) -> dict[str, int]:
        return {
            "success": self.success,
            "skipped": self.skipped,
            "failed": self.failed,
            "no_audio": self.no_audio,
        }


@dataclass(slots=True)
class PreparedVoice:
    voice: VoiceLine
    voice_set_name: str
    destination: Path
    text_path: Path
    record: dict[str, Any]
    force: bool = False


class DownloadManager:
    def __init__(
        self,
        layout: StorageLayout,
        audio_downloader: AudioDownloader,
        reporter: Reporter,
    ) -> None:
        self.layout = layout
        self.audio_downloader = audio_downloader
        self.reporter = reporter
        self.metadata_store = MetadataStore()
        self.failed_store = FailedStore(layout.failed_path)

    def _previous_records(
        self, metadata: dict[str, Any] | None
    ) -> dict[tuple[str, str], dict[str, Any]]:
        result: dict[tuple[str, str], dict[str, Any]] = {}
        if metadata is None:
            return result
        sets = metadata.get("voice_sets")
        if not isinstance(sets, dict):
            return result
        for set_name, records in sets.items():
            if not isinstance(set_name, str) or not isinstance(records, list):
                continue
            for record in records:
                if not isinstance(record, dict):
                    continue
                source_key = record.get("source_key")
                if isinstance(source_key, str):
                    result[(set_name, source_key)] = record
        return result

    def _voice_set_directories(
        self, ship: Ship, previous: dict[str, Any] | None
    ) -> dict[str, str]:
        previous_dirs = previous.get("voice_set_directories") if previous else None
        previous_dirs = previous_dirs if isinstance(previous_dirs, dict) else {}
        result: dict[str, str] = {}
        used: set[str] = set()
        for voice_set in ship.voice_sets:
            old = previous_dirs.get(voice_set.name)
            if isinstance(old, str):
                candidate = safe_component(old, max_length=80, fallback="语音集")
            else:
                candidate = safe_component(voice_set.name, max_length=80, fallback="语音集")
            base = candidate
            number = 1
            while candidate.casefold() in used:
                number += 1
                suffix = f"_{number}"
                candidate = f"{base[: 80 - len(suffix)].rstrip(' .')}{suffix}"
            used.add(candidate.casefold())
            result[voice_set.name] = candidate
        return result

    def _reuse_previous_paths(
        self,
        ship_dir: Path,
        previous: dict[str, Any] | None,
        voice_set_name: str,
        voice: VoiceLine,
    ) -> tuple[Path, Path, bool] | None:
        record = self._previous_records(previous).get(
            (voice_set_name, voice.source_key)
        )
        if record is None:
            return None
        mp3_relative = record.get("mp3")
        txt_relative = record.get("txt")
        if not isinstance(mp3_relative, str) or not isinstance(txt_relative, str):
            return None
        mp3_path = safe_relative_path(ship_dir, mp3_relative, ".mp3")
        txt_path = safe_relative_path(ship_dir, txt_relative, ".txt")
        if mp3_path is None or txt_path is None:
            return None
        previous_url = record.get("source_url")
        force = isinstance(previous_url, str) and previous_url != voice.audio_url
        return mp3_path, txt_path, force

    def _prepare_metadata(
        self, ship: Ship, previous: dict[str, Any] | None
    ) -> tuple[dict[str, Any], list[PreparedVoice]]:
        ship_dir = self.layout.ship_dir(ship.name)
        directories = self._voice_set_directories(ship, previous)
        metadata: dict[str, Any] = {
            "version": 1,
            "ship": ship.name,
            "display_name": ship.display_name,
            "source": ship.page_url,
            "fetched_at": utc_now(),
            "updated_at": utc_now(),
            "complete": False,
            "voice_set_directories": directories,
            "voice_sets": {},
            "stats": {},
        }
        prepared: list[PreparedVoice] = []

        for voice_set in ship.voice_sets:
            set_dir = self.layout.voice_set_dir(ship.name, directories[voice_set.name])
            used_stems: set[str] = set()
            records: list[dict[str, Any]] = []
            for voice in voice_set.voices:
                record: dict[str, Any] = {
                    "category": voice.category,
                    "text": voice.text,
                    "source_key": voice.source_key,
                    "data_key": voice.data_key,
                    "data_key_index": voice.data_key_index,
                    "source_url": voice.audio_url,
                    "mp3": None,
                    "txt": None,
                    "download_status": "no_audio" if voice.audio_url is None else "pending",
                    "size": None,
                    "error": None,
                }
                records.append(record)
                if voice.audio_url is None:
                    continue

                reused = self._reuse_previous_paths(
                    ship_dir, previous, voice_set.name, voice
                )
                if reused is not None:
                    destination, text_path, force = reused
                    stem = destination.stem
                    if stem.casefold() in used_stems:
                        reused = None
                    else:
                        used_stems.add(stem.casefold())
                if reused is None:
                    stem = unique_stem(voice.text, used_stems, max_length=100)
                    destination = set_dir / f"{stem}.mp3"
                    text_path = set_dir / f"{stem}.txt"
                    force = False

                record["mp3"] = relative_posix(destination, ship_dir)
                record["txt"] = relative_posix(text_path, ship_dir)
                prepared.append(
                    PreparedVoice(
                        voice=voice,
                        voice_set_name=voice_set.name,
                        destination=destination,
                        text_path=text_path,
                        record=record,
                        force=force,
                    )
                )
            metadata["voice_sets"][voice_set.name] = records
        self._refresh_metadata_status(metadata)
        return metadata, prepared

    @staticmethod
    def _refresh_metadata_status(metadata: dict[str, Any]) -> DownloadSummary:
        counts = {"success": 0, "skipped": 0, "failed": 0, "no_audio": 0}
        pending = 0
        for records in metadata.get("voice_sets", {}).values():
            for record in records:
                status = record.get("download_status")
                if status in counts:
                    counts[status] += 1
                elif status in {"pending", "interrupted"}:
                    pending += 1
        summary = DownloadSummary(**counts)
        metadata["stats"] = {**summary.as_dict(), "pending": pending}
        metadata["complete"] = counts["failed"] == 0 and pending == 0
        metadata["updated_at"] = utc_now()
        return summary

    async def download_ship(self, ship: Ship) -> DownloadSummary:
        ship_dir = self.layout.ship_dir(ship.name)
        ship_dir.mkdir(parents=True, exist_ok=True)
        metadata_path = self.layout.metadata_path(ship.name)
        previous = self.metadata_store.load(metadata_path)
        metadata, prepared = self._prepare_metadata(ship, previous)
        self.metadata_store.write(metadata_path, metadata)
        metadata_lock = asyncio.Lock()

        async def persist() -> None:
            async with metadata_lock:
                self._refresh_metadata_status(metadata)
                await asyncio.to_thread(
                    self.metadata_store.write, metadata_path, metadata
                )

        async def process(item: PreparedVoice) -> None:
            self.reporter.info(f"[下载] {item.voice_set_name}/{item.destination.name}")
            result = await self.audio_downloader.download(
                item.voice.audio_url or "", item.destination, force=item.force
            )
            if result.status in {"success", "skipped"}:
                try:
                    await asyncio.to_thread(
                        atomic_write_text, item.text_path, item.voice.text
                    )
                except OSError as exc:
                    item.record.update(
                        download_status="failed", error=f"TXT 写入失败：{exc}"
                    )
                    self.reporter.error(f"[失败] {item.text_path.name}：{exc}")
                else:
                    item.record.update(
                        download_status=result.status,
                        error=None,
                        size=result.size,
                    )
                    verb = "完成" if result.status == "success" else "跳过"
                    self.reporter.info(f"[{verb}] {item.destination.name}")
            else:
                item.record.update(download_status="failed", error=result.error)
                self.reporter.error(
                    f"[失败] {item.destination.name}：{result.error or '未知错误'}"
                )
            await persist()

        tasks = [asyncio.create_task(process(item)) for item in prepared]
        try:
            if tasks:
                await asyncio.gather(*tasks)
        except asyncio.CancelledError:
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            for item in prepared:
                if item.record["download_status"] == "pending":
                    item.record["download_status"] = "interrupted"
            await persist()
            raise

        summary = self._refresh_metadata_status(metadata)
        self.metadata_store.write(metadata_path, metadata)
        failures = []
        for voice_set_name, records in metadata["voice_sets"].items():
            for record in records:
                if record["download_status"] == "failed":
                    failures.append(
                        {
                            "stage": "audio",
                            "voice_set": voice_set_name,
                            "category": record["category"],
                            "text": record["text"],
                            "url": record["source_url"],
                            "error": record["error"],
                        }
                    )
        self.failed_store.replace_ship_failures(ship.name, failures)
        return summary

    def is_ship_complete(self, ship_name: str) -> bool:
        metadata_path = self.layout.metadata_path(ship_name)
        metadata = self.metadata_store.load(metadata_path)
        if metadata is None or metadata.get("complete") is not True:
            return False
        ship_dir = self.layout.ship_dir(ship_name)
        sets = metadata.get("voice_sets")
        if not isinstance(sets, dict) or not sets:
            return False
        found_record = False
        for records in sets.values():
            if not isinstance(records, list) or not records:
                return False
            for record in records:
                found_record = True
                if not isinstance(record, dict) or record.get("source_url") is None:
                    continue
                mp3 = record.get("mp3")
                txt = record.get("txt")
                text = record.get("text")
                if not isinstance(mp3, str) or not isinstance(txt, str) or not isinstance(text, str):
                    return False
                mp3_path = safe_relative_path(ship_dir, mp3, ".mp3")
                txt_path = safe_relative_path(ship_dir, txt, ".txt")
                if mp3_path is None or txt_path is None or not is_valid_mp3(mp3_path):
                    return False
                try:
                    if txt_path.read_text(encoding="utf-8") != text:
                        return False
                except (OSError, UnicodeError):
                    return False
        return found_record
