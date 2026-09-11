import asyncio

from bwiki.ship_index import ShipIndex


class FakeClient:
    def __init__(self) -> None:
        self.calls = 0

    async def get_json(self, _url, params=None):
        self.calls += 1
        if self.calls == 1:
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
        assert client.calls == 2
        assert (await index.find_exact(" 欧根亲王 ")).name == "欧根亲王"
        assert [ship.name for ship in await index.suggest("欧根")] == [
            "欧根亲王",
            "小欧根",
        ]
        assert "%E6%AC%A7%E6%A0%B9" in ships[0].page_url

    asyncio.run(scenario())

