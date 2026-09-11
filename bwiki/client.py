"""Asynchronous, rate-limited BWiki page client with bounded retries."""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Mapping
from typing import Any

import httpx

from utils.retry import RETRYABLE_HTTP_STATUS, exponential_delay, retry_after_seconds


DEFAULT_USER_AGENT = (
    "azurlane-bwiki-voice-downloader/1.0 "
    "(local archival tool; conservative concurrency)"
)


class BWikiRequestError(RuntimeError):
    """A BWiki request failed after the configured retry policy."""


class BWikiClient:
    def __init__(
        self,
        *,
        page_concurrency: int = 4,
        max_attempts: int = 4,
        timeout: float = 30.0,
        on_retry: Callable[[str], None] | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.max_attempts = max_attempts
        self.on_retry = on_retry
        self._semaphore = asyncio.Semaphore(page_concurrency)
        self._client = httpx.AsyncClient(
            follow_redirects=True,
            timeout=httpx.Timeout(timeout),
            headers={"User-Agent": DEFAULT_USER_AGENT},
            transport=transport,
        )

    async def __aenter__(self) -> BWikiClient:
        return self

    async def __aexit__(self, *_: object) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        await self._client.aclose()

    async def _request(
        self, url: str, params: Mapping[str, str] | None = None
    ) -> httpx.Response:
        last_error: Exception | None = None
        for attempt in range(1, self.max_attempts + 1):
            try:
                async with self._semaphore:
                    response = await self._client.get(url, params=params)
                if response.status_code not in RETRYABLE_HTTP_STATUS:
                    response.raise_for_status()
                    return response
                delay = exponential_delay(attempt)
                retry_after = retry_after_seconds(response.headers.get("Retry-After"))
                if retry_after is not None:
                    delay = max(delay, min(retry_after, 60.0))
                last_error = BWikiRequestError(
                    f"HTTP {response.status_code}: {response.url}"
                )
            except httpx.RequestError as exc:
                delay = exponential_delay(attempt)
                last_error = exc
            except httpx.HTTPStatusError as exc:
                raise BWikiRequestError(str(exc)) from exc

            if attempt < self.max_attempts:
                if self.on_retry:
                    self.on_retry(
                        f"[重试] 页面请求第 {attempt + 1}/{self.max_attempts} 次，"
                        f"{delay:g} 秒后继续：{url}"
                    )
                await asyncio.sleep(delay)

        raise BWikiRequestError(f"请求最终失败：{url}；{last_error}") from last_error

    async def get_text(self, url: str) -> tuple[str, str]:
        response = await self._request(url)
        return response.text, str(response.url)

    async def get_json(
        self, url: str, params: Mapping[str, str] | None = None
    ) -> dict[str, Any]:
        response = await self._request(url, params=params)
        try:
            payload = response.json()
        except ValueError as exc:
            raise BWikiRequestError(f"响应不是合法 JSON：{response.url}") from exc
        if not isinstance(payload, dict):
            raise BWikiRequestError(f"JSON 顶层不是对象：{response.url}")
        return payload
