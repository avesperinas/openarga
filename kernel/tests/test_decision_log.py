import pytest
from httpx import ASGITransport, AsyncClient

from kernel import resolver, seed
from kernel.db import engine
from kernel.main import app


@pytest.fixture
async def api(database_url: str):
    await seed.clear()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://kernel") as client:
        yield client
    await seed.clear()
    await engine().dispose()


async def resolve() -> resolver.Outcome:
    async with engine().begin() as connection:
        return await resolver.run(connection)


async def test_every_alias_says_how_it_got_here(api) -> None:
    await seed.load()
    outcome = await resolve()

    entity = (await api.get(f"/entities/{outcome.merged[0].target}")).json()

    aliases = {item["alias"]: item for item in entity["aliases"]}
    assert sorted(aliases) == sorted(seed.SPELLINGS)

    assert aliases[seed.SPELLINGS[0]]["via"] is None

    for alias in seed.SPELLINGS[1:]:
        via = aliases[alias]["via"]
        assert via is not None, alias
        assert via["decided_by"] == "resolver"
        assert via["rule"] in {"same_name_other_store", "same_store_number"}
        assert via["confidence"] >= 0.8
        assert via["decided_at"]


async def test_the_log_lists_what_was_decided(api) -> None:
    await seed.load()
    await resolve()

    decisions = (await api.get("/resolutions")).json()

    assert len(decisions) == 2
    assert {item["decision"] for item in decisions} == {"merged"}
    assert {item["decided_by"] for item in decisions} == {"resolver"}
    assert all(item["loser_name"] and item["winner_name"] for item in decisions)


async def test_the_log_can_be_read_for_one_entity(api) -> None:
    await seed.load()
    outcome = await resolve()
    absorbed = outcome.merged[0].candidate

    decisions = (await api.get("/resolutions", params={"entity_id": absorbed})).json()

    assert [item["loser_id"] for item in decisions] == [absorbed]


async def test_a_rejection_is_in_the_log_too(api) -> None:
    await seed.load()
    outcome = await resolve()
    await api.post(f"/entities/{outcome.merged[0].candidate}/unmerge")

    decisions = (await api.get("/resolutions")).json()

    assert decisions[0]["decision"] == "rejected"
    assert decisions[0]["method"] == "undo"
    assert decisions[0]["decided_by"] == "person"


async def test_the_queue_still_answers_the_same(api) -> None:
    await seed.load()

    pending = (await api.get("/resolution-queue")).json()

    assert len(pending) == len(seed.SPELLINGS) + len(seed.LONERS)
    assert all(item["candidate"]["status"] == "candidate" for item in pending)


async def test_nothing_is_pending_after_the_pass_except_what_it_could_not_resolve(api) -> None:
    await seed.load()
    await resolve()

    pending = (await api.get("/resolution-queue")).json()

    assert {item["raw_alias"] for item in pending} == set(seed.LONERS)
