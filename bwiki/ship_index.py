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
        self._resolved_names: dict[str, ShipReference | None] = {}

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
        ships = await self.fetch_all()
        for ship in ships:
            if _normalized(ship.name) == wanted:
                return ship

        if wanted in self._resolved_names:
            return self._resolved_names[wanted]

        by_name = {_normalized(ship.name): ship for ship in ships}
        params = {
            "action": "query",
            "format": "json",
            "formatversion": "2",
            "redirects": "1",
            "titles": name.strip(),
        }
        try:
            payload = await self.client.get_json(API_URL, params=params)
            pages = payload["query"]["pages"]
        except (BWikiRequestError, KeyError, TypeError):
            self._resolved_names[wanted] = None
            return None

        if not isinstance(pages, list):
            self._resolved_names[wanted] = None
            return None
        for page in pages:
            if not isinstance(page, dict) or page.get("missing") is True:
                continue
            title = page.get("title")
            if isinstance(title, str):
                resolved = by_name.get(_normalized(title))
                if resolved is not None:
                    self._resolved_names[wanted] = resolved
                    return resolved

        self._resolved_names[wanted] = None
        return None

    async def _search_category_members(
        self, name: str, ships: tuple[ShipReference, ...], limit: int
    ) -> tuple[ShipReference, ...]:
        params = {
            "action": "query",
            "format": "json",
            "formatversion": "2",
            "list": "search",
            "srnamespace": "0",
            "srlimit": str(max(20, limit * 4)),
            "srsearch": name.strip(),
        }
        try:
            payload = await self.client.get_json(API_URL, params=params)
            results = payload["query"]["search"]
        except (BWikiRequestError, KeyError, TypeError):
            return ()
        if not isinstance(results, list):
            return ()

        by_name = {_normalized(ship.name): ship for ship in ships}
        matches: list[ShipReference] = []
        seen: set[int | str] = set()
        for result in results:
            if not isinstance(result, dict):
                continue
            title = result.get("title")
            if not isinstance(title, str):
                continue
            ship = by_name.get(_normalized(title))
            if ship is None:
                continue
            identity: int | str = ship.page_id if ship.page_id is not None else ship.name
            if identity in seen:
                continue
            seen.add(identity)
            matches.append(ship)
            if len(matches) >= limit:
                break
        return tuple(matches)

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
        local_matches = tuple(ship for _, ship in scored[:limit])
        search_matches = await self._search_category_members(name, ships, limit)

        combined: list[ShipReference] = []
        seen: set[int | str] = set()
        for ship in (*search_matches, *local_matches):
            identity: int | str = ship.page_id if ship.page_id is not None else ship.name
            if identity in seen:
                continue
            seen.add(identity)
            combined.append(ship)
            if len(combined) >= limit:
                break
        return tuple(combined)
