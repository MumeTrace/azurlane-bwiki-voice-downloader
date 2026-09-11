import asyncio
from pathlib import Path

import httpx
import pytest

from downloader.audio import AudioDownloader, is_valid_mp3
from downloader.resume import PartialMetadata, save_partial_metadata


MP3 = b"\xff\xfb\x90\x64" + (b"audio-data" * 100)


def run(coro):
    return asyncio.run(coro)


def test_existing_valid_mp3_is_skipped_without_request(tmp_path: Path) -> None:
    destination = tmp_path / "voice.mp3"
    destination.write_bytes(MP3)

    def handler(_request: httpx.Request) -> httpx.Response:
        raise AssertionError("不应发起网络请求")

    async def scenario() -> None:
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(handler)
        ) as client:
            downloader = AudioDownloader(client=client)
            result = await downloader.download("https://example.test/voice.mp3", destination)
            assert result.status == "skipped"
            assert result.size == len(MP3)

    run(scenario())


def test_range_resume_requires_matching_content_range(tmp_path: Path) -> None:
    destination = tmp_path / "voice.mp3"
    part = tmp_path / "voice.mp3.part"
    split = 137
    part.write_bytes(MP3[:split])
    save_partial_metadata(
        part, PartialMetadata(url="https://example.test/voice.mp3", etag='"v1"')
    )

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["Range"] == f"bytes={split}-"
        assert request.headers["If-Range"] == '"v1"'
        return httpx.Response(
            206,
            headers={
                "Content-Type": "audio/mpeg",
                "Content-Range": f"bytes {split}-{len(MP3)-1}/{len(MP3)}",
                "ETag": '"v1"',
            },
            content=MP3[split:],
        )

    async def scenario() -> None:
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(handler)
        ) as client:
            downloader = AudioDownloader(client=client, max_attempts=1)
            result = await downloader.download("https://example.test/voice.mp3", destination)
            assert result.status == "success"
            assert destination.read_bytes() == MP3
            assert not part.exists()

    run(scenario())


def test_server_ignoring_range_restarts_instead_of_appending(tmp_path: Path) -> None:
    destination = tmp_path / "voice.mp3"
    part = tmp_path / "voice.mp3.part"
    part.write_bytes(b"obsolete partial")

    def handler(request: httpx.Request) -> httpx.Response:
        assert "Range" in request.headers
        return httpx.Response(
            200,
            headers={"Content-Type": "audio/mpeg", "Content-Length": str(len(MP3))},
            content=MP3,
        )

    async def scenario() -> None:
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(handler)
        ) as client:
            downloader = AudioDownloader(client=client, max_attempts=1)
            result = await downloader.download("https://example.test/voice.mp3", destination)
            assert result.status == "success"
            assert destination.read_bytes() == MP3
            assert is_valid_mp3(destination)

    run(scenario())


def test_permanent_404_is_recorded_without_fake_file(tmp_path: Path) -> None:
    destination = tmp_path / "missing.mp3"

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, content=b"not found")

    async def scenario() -> None:
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(handler)
        ) as client:
            downloader = AudioDownloader(client=client, max_attempts=4)
            result = await downloader.download("https://example.test/missing.mp3", destination)
            assert result.status == "failed"
            assert "HTTP 404" in (result.error or "")
            assert not destination.exists()

    run(scenario())


def test_cancellation_keeps_partial_file_for_next_run(tmp_path: Path) -> None:
    destination = tmp_path / "voice.mp3"
    started = asyncio.Event()
    never = asyncio.Event()

    class PausingStream(httpx.AsyncByteStream):
        async def __aiter__(self):
            yield MP3[:137]
            started.set()
            await never.wait()
            yield MP3[137:]

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            headers={"Content-Type": "audio/mpeg", "Content-Length": str(len(MP3))},
            stream=PausingStream(),
        )

    async def scenario() -> None:
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(handler)
        ) as client:
            downloader = AudioDownloader(client=client, max_attempts=1)
            task = asyncio.create_task(
                downloader.download("https://example.test/voice.mp3", destination)
            )
            await started.wait()
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
            part = tmp_path / "voice.mp3.part"
            assert part.exists()
            assert part.stat().st_size == 137
            assert (tmp_path / "voice.mp3.part.meta.json").exists()
            assert not destination.exists()

    run(scenario())
