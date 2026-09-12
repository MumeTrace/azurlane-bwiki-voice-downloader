"""Resumable MP3 downloads with local validation and bounded concurrency."""

from __future__ import annotations

import asyncio
import os
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import httpx

from storage.metadata import atomic_write_text
from utils.retry import RETRYABLE_HTTP_STATUS, exponential_delay, retry_after_seconds

from .resume import (
    PartialMetadata,
    load_partial_metadata,
    parse_content_range,
    parse_unsatisfied_total,
    partial_metadata_path,
    save_partial_metadata,
)


DownloadStatus = Literal["success", "skipped", "failed"]


@dataclass(frozen=True, slots=True)
class AudioDownloadResult:
    status: DownloadStatus
    size: int = 0
    error: str | None = None


class RetriableAudioError(RuntimeError):
    def __init__(self, message: str, retry_after: float | None = None) -> None:
        super().__init__(message)
        self.retry_after = retry_after


class PermanentAudioError(RuntimeError):
    pass


def is_valid_mp3(path: Path) -> bool:
    try:
        size = path.stat().st_size
        if size <= 4:
            return False
        with path.open("rb") as handle:
            head = handle.read(min(size, 8192))
    except OSError:
        return False
    lowered = head[:256].lstrip().lower()
    if lowered.startswith((b"<!doctype html", b"<html", b"{", b"[")):
        return False
    if head.startswith(b"ID3"):
        return True
    return any(
        head[index] == 0xFF and head[index + 1] & 0xE0 == 0xE0
        for index in range(len(head) - 1)
    )


async def _open_file(path: Path, mode: str):
    return await asyncio.to_thread(path.open, mode)


async def _close_file(handle) -> None:
    await asyncio.to_thread(handle.close)


async def _flush_file(handle) -> None:
    await asyncio.to_thread(handle.flush)
    await asyncio.to_thread(os.fsync, handle.fileno())


async def _response_chunks(response: httpx.Response):
    # Mock/custom transports may supply an already-buffered response even when
    # requested through ``stream``.  Real network responses stay unconsumed and
    # are written transport-chunk by transport-chunk.
    if response.is_stream_consumed:
        if response.content:
            yield response.content
        return
    async for chunk in response.aiter_raw():
        yield chunk


class AudioDownloader:
    def __init__(
        self,
        *,
        concurrency: int = 8,
        max_attempts: int = 4,
        timeout: float = 60.0,
        on_retry: Callable[[str], None] | None = None,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.max_attempts = max_attempts
        self.on_retry = on_retry
        self._semaphore = asyncio.Semaphore(concurrency)
        self._owns_client = client is None
        self._client = client or httpx.AsyncClient(
            follow_redirects=True,
            timeout=httpx.Timeout(timeout, connect=30.0),
            headers={
                "User-Agent": (
                    "azurlane-bwiki-voice-downloader/2.0 "
                    "(local archival tool; conservative concurrency)"
                )
            },
        )

    async def __aenter__(self) -> AudioDownloader:
        return self

    async def __aexit__(self, *_: object) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    async def download(
        self, url: str, destination: Path, *, force: bool = False
    ) -> AudioDownloadResult:
        destination.parent.mkdir(parents=True, exist_ok=True)
        if not force and await asyncio.to_thread(is_valid_mp3, destination):
            return AudioDownloadResult(
                status="skipped", size=destination.stat().st_size
            )

        async with self._semaphore:
            last_error: Exception | None = None
            for attempt in range(1, self.max_attempts + 1):
                try:
                    size = await self._download_once(url, destination)
                    return AudioDownloadResult(status="success", size=size)
                except asyncio.CancelledError:
                    raise
                except PermanentAudioError as exc:
                    return AudioDownloadResult(status="failed", error=str(exc))
                except (RetriableAudioError, httpx.RequestError, OSError) as exc:
                    last_error = exc
                    if attempt >= self.max_attempts:
                        break
                    delay = exponential_delay(attempt)
                    if isinstance(exc, RetriableAudioError) and exc.retry_after is not None:
                        delay = max(delay, min(exc.retry_after, 60.0))
                    if self.on_retry:
                        self.on_retry(
                            f"[重试] {destination.name} 第 {attempt + 1}/"
                            f"{self.max_attempts} 次，{delay:g} 秒后继续"
                        )
                    await asyncio.sleep(delay)
            return AudioDownloadResult(
                status="failed", error=f"{type(last_error).__name__}: {last_error}"
            )

    async def _download_once(self, url: str, destination: Path) -> int:
        part_path = destination.with_name(f"{destination.name}.part")
        part_meta_path = partial_metadata_path(part_path)
        existing_meta = load_partial_metadata(part_path)
        part_size = part_path.stat().st_size if part_path.exists() else 0

        if part_size and existing_meta is not None and existing_meta.url != url:
            await asyncio.to_thread(atomic_write_text, part_path, "")
            part_size = 0
            existing_meta = None

        headers: dict[str, str] = {}
        if part_size:
            headers["Range"] = f"bytes={part_size}-"
            validator = None
            if existing_meta is not None:
                validator = existing_meta.etag or existing_meta.last_modified
            if validator:
                headers["If-Range"] = validator

        async with self._client.stream("GET", url, headers=headers) as response:
            if response.status_code in RETRYABLE_HTTP_STATUS:
                raise RetriableAudioError(
                    f"HTTP {response.status_code}",
                    retry_after=retry_after_seconds(response.headers.get("Retry-After")),
                )
            if response.status_code == 416:
                total = parse_unsatisfied_total(response.headers.get("Content-Range"))
                if (
                    total is not None
                    and total == part_size
                    and await asyncio.to_thread(is_valid_mp3, part_path)
                ):
                    await asyncio.to_thread(part_path.replace, destination)
                    if part_meta_path.exists():
                        await asyncio.to_thread(part_meta_path.unlink)
                    return total
                await asyncio.to_thread(atomic_write_text, part_path, "")
                if part_meta_path.exists():
                    await asyncio.to_thread(part_meta_path.unlink)
                raise RetriableAudioError("服务器拒绝当前 Range，已准备从头重试")
            if response.status_code >= 400:
                raise PermanentAudioError(f"HTTP {response.status_code}: {url}")

            content_type = response.headers.get("Content-Type", "").lower()
            if content_type and not (
                content_type.startswith("audio/")
                or "octet-stream" in content_type
                or "binary" in content_type
            ):
                raise PermanentAudioError(
                    f"响应 Content-Type 不是音频：{content_type or '缺失'}"
                )

            mode = "wb"
            starting_size = 0
            expected_total: int | None = None
            if response.status_code == 206:
                content_range = parse_content_range(response.headers.get("Content-Range"))
                if content_range is None:
                    raise RetriableAudioError("206 响应缺少合法 Content-Range")
                start, _, expected_total = content_range
                if start != part_size:
                    raise RetriableAudioError(
                        f"Range 起点不匹配：请求 {part_size}，响应 {start}"
                    )
                mode = "ab" if part_size else "wb"
                starting_size = part_size
            elif response.status_code == 200:
                raw_length = response.headers.get("Content-Length")
                if raw_length and raw_length.isdigit():
                    expected_total = int(raw_length)

            await asyncio.to_thread(
                save_partial_metadata,
                part_path,
                PartialMetadata(
                    url=url,
                    etag=response.headers.get("ETag"),
                    last_modified=response.headers.get("Last-Modified"),
                ),
            )

            handle = await _open_file(part_path, mode)
            received = 0
            try:
                # Do not aggregate into a large application buffer: writing each
                # transport chunk preserves more progress when Ctrl+C arrives.
                async for chunk in _response_chunks(response):
                    if not chunk:
                        continue
                    await asyncio.to_thread(handle.write, chunk)
                    received += len(chunk)
                await _flush_file(handle)
            finally:
                await _close_file(handle)

        actual_size = part_path.stat().st_size
        if expected_total is not None and actual_size != expected_total:
            raise RetriableAudioError(
                f"文件长度不完整：期望 {expected_total}，实际 {actual_size}"
            )
        if actual_size != starting_size + received:
            raise RetriableAudioError("写入后的文件长度与响应数据量不一致")
        if not await asyncio.to_thread(is_valid_mp3, part_path):
            raise RetriableAudioError("下载内容未通过 MP3 文件头检查")

        await asyncio.to_thread(part_path.replace, destination)
        if part_meta_path.exists():
            await asyncio.to_thread(part_meta_path.unlink)
        return destination.stat().st_size
