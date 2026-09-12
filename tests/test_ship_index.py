import asyncio

from bwiki.ship_index import ShipIndex


class FakeClient:
    def __init__(self) -> None:
        self.category_calls = 0
        self.search_calls = 0

    async def get_json(self, _url, params=None):
        if params.get("list") == "search":
            self.search_calls += 1
            return {
                "query": {
                    "search": [
                        {"title": "欧根亲王"},
                        {"title": "小欧根"},
                    ]
                }
            }
        self.category_calls += 1
        if self.category_calls == 1:
            assert "cmcontinue" not in params
            return {
                "query": {
                    "categorymembers": [
                        {"pageid": 1, "title": "欧根亲王"},
                        {"pageid": 2, "title": "小欧根"},
                    ]
                },
                "continue": {"cmcontinue": "next-token", "continue": "-||"},
            }
        assert params["cmcontinue"] == "next-token"
        return {
            "query": {
                "categorymembers": [{"pageid": 3, "title": "标枪"}]
            }
        }


def test_index_paginates_and_supports_explicit_fuzzy_choice() -> None:
    async def scenario() -> None:
        client = FakeClient()
        index = ShipIndex(client)  # type: ignore[arg-type]
        ships = await index.fetch_all()
        assert [ship.name for ship in ships] == ["欧根亲王", "小欧根", "标枪"]
        assert client.category_calls == 2
        assert (await index.find_exact(" 欧根亲王 ")).name == "欧根亲王"
        assert [ship.name for ship in await index.suggest("欧根")] == [
            "欧根亲王",
            "小欧根",
        ]
        assert client.search_calls == 1
        assert "%E6%AC%A7%E6%A0%B9" in ships[0].page_url

    asyncio.run(scenario())


class FakeAliasClient:
    async def get_json(self, _url, params=None):
        if params.get("list") == "categorymembers":
            return {
                "query": {
                    "categorymembers": [
                        {"pageid": 1, "title": "欧根亲王"},
                        {"pageid": 2, "title": "曾克海军上将"},
                        {"pageid": 3, "title": "泽西"},
                    ]
                }
            }
        if "titles" in params:
            if params["titles"] == "萨沃伊亲王":
                return {
                    "query": {
                        "redirects": [
                            {"from": "萨沃伊亲王", "to": "欧根亲王"}
                        ],
                        "pages": [
                            {"pageid": 1, "ns": 0, "title": "欧根亲王"}
                        ],
                    }
                }
            return {
                "query": {
                    "pages": [{"ns": 0, "title": params["titles"], "missing": True}]
                }
            }
        if params.get("list") == "search":
            return {
                "query": {
                    "search": [
                        {"title": "战列巡洋舰「泽特」前来报到！"},
                        {"title": "曾克海军上将"},
                        {"title": "泽西"},
                    ]
                }
            }
        raise AssertionError(f"unexpected params: {params}")


def test_index_resolves_redirects_and_filters_search_to_ship_category() -> None:
    async def scenario() -> None:
        index = ShipIndex(FakeAliasClient())  # type: ignore[arg-type]

        redirected = await index.find_exact("萨沃伊亲王")
        assert redirected is not None
        assert redirected.name == "欧根亲王"

        assert await index.find_exact("泽特") is None
        assert [ship.name for ship in await index.suggest("泽特")] == [
            "曾克海军上将",
            "泽西",
        ]

    asyncio.run(scenario())
