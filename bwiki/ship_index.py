"""Dynamic complete ship index from MediaWiki's Category:舰娘 API."""

from __future__ import annotations

import difflib
import unicodedata
from urllib.parse import quote

from .client import BWikiClient, BWikiRequestError
from .models import ShipReference


API_URL = "https://wiki.biligame.com/blhx/api.php"
SHIP_BASE_URL = "https://wiki.biligame.com/blhx/"


class ShipIndexError(RuntimeError):
    """The complete category index could not be parsed safely."""


def _normalized(value: str) -> str:
    return unicodedata.normalize("NFC", value).strip().casefold()


class ShipIndex:
    def __init__(self, client: BWikiClient) -> None:
        self.client = client
        self._cache: tuple[ShipReference, ...] | None = None

    async def fetch_all(self, *, refresh: bool = False) -> tuple[ShipReference, ...]:
        if self._cache is not None and not refresh:
            return self._cache

        continuation: str | None = None
        ships: list[ShipReference] = []
        seen_page_ids: set[int] = set()
        while True:
            params = {
                "action": "query",
                "format": "json",
                "formatversion": "2",
                "list": "categorymembers",
                "cmtitle": "Category:舰娘",
                "cmnamespace": "0",
                "cmlimit": "max",
            }
            if continuation:
                params["cmcontinue"] = continuation
            try:
                payload = await self.client.get_json(API_URL, params=params)
                members = payload["query"]["categorymembers"]
            except (BWikiRequestError, KeyError, TypeError) as exc:
                raise ShipIndexError(f"舰娘分类 API 结构异常：{exc}") from exc
            if not isinstance(members, list):
                raise ShipIndexError("舰娘分类 API 的 categorymembers 不是数组")

            for member in members:
                if not isinstance(member, dict):
                    continue
                title = member.get("title")
                page_id = member.get("pageid")
                if not isinstance(title, str) or not isinstance(page_id, int):
                    continue
                if page_id in seen_page_ids:
                    continue
                seen_page_ids.add(page_id)
                ships.append(
                    ShipReference(
                        name=title,
                        page_id=page_id,
                        page_url=SHIP_BASE_URL + quote(title, safe=""),
                    )
                )

            continue_data = payload.get("continue")
            if not isinstance(continue_data, dict):
                break
            raw_continue = continue_data.get("cmcontinue")
            if not isinstance(raw_continue, str) or not raw_continue:
                break
            continuation = raw_continue

        if not ships:
            raise ShipIndexError("舰娘分类 API 返回了空列表")
        self._cache = tuple(ships)
        return self._cache

    async def find_exact(self, name: str) -> ShipReference | None:
        wanted = _normalized(name)
        for ship in await self.fetch_all():
            if _normalized(ship.name) == wanted:
                return ship
        return None

    async def suggest(self, name: str, limit: int = 5) -> tuple[ShipReference, ...]:
        ships = await self.fetch_all()
        wanted = _normalized(name)
        scored: list[tuple[float, ShipReference]] = []
        for ship in ships:
            candidate = _normalized(ship.name)
            score = difflib.SequenceMatcher(a=wanted, b=candidate).ratio()
            if wanted and candidate.startswith(wanted):
                score += 2.0
            elif wanted and wanted in candidate:
                score += 1.0
            elif candidate and candidate in wanted:
                score += 0.5
            if score >= 0.45:
                scored.append((score, ship))
        scored.sort(key=lambda item: (-item[0], item[1].name))
        return tuple(ship for _, ship in scored[:limit])
