import asyncio

import httpx
import pytest

import bwiki.client as client_module
from bwiki.client import BWikiClient, BWikiRequestError


def test_retryable_page_status_uses_bounded_retry(monkeypatch) -> None:
    attempts = 0
    delays: list[float] = []

    def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            return httpx.Response(503)
        return httpx.Response(200, text="ok")

    async def fake_sleep(delay: float) -> None:
        delays.append(delay)

    monkeypatch.setattr(client_module.asyncio, "sleep", fake_sleep)

    async def scenario() -> None:
        async with BWikiClient(
            max_attempts=2, transport=httpx.MockTransport(handler)
        ) as client:
            text, _ = await client.get_text("https://example.test/page")
            assert text == "ok"

    asyncio.run(scenario())
    assert attempts == 2
    assert delays == [1.0]


def test_non_retryable_page_status_fails_immediately() -> None:
    attempts = 0

    def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        return httpx.Response(404)

    async def scenario() -> None:
        async with BWikiClient(
            max_attempts=4, transport=httpx.MockTransport(handler)
        ) as client:
            with pytest.raises(BWikiRequestError, match="404"):
                await client.get_text("https://example.test/missing")

    asyncio.run(scenario())
    assert attempts == 1

