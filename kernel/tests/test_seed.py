import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text

from kernel import seed
from kernel.db import engine
from kernel.main import app


@pytest.fixture
async def api(database_url: str):
    await seed.clear()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://kernel") as client:
        yield client
    await seed.clear()
    await engine().dispose()


async def count_events() -> int:
    async with engine().connect() as connection:
        return await connection.scalar(
            text("select count(*) from kernel.events where source = :source"),
            {"source": seed.SOURCE},
        )


async def test_the_seed_leaves_the_queue_with_something_to_decide(api) -> None:
    sent, created = await seed.load()

    queue = (await api.get("/resolution-queue")).json()

    assert (sent, created) == (8, 8)
    assert len(queue) == len(seed.SPELLINGS) + len(seed.LONERS)
    assert sorted(item["raw_alias"] for item in queue) == sorted(seed.SPELLINGS + seed.LONERS)


async def test_similarity_catches_the_easy_pair(api) -> None:
    await seed.load()

    queue = {item["raw_alias"]: item for item in (await api.get("/resolution-queue")).json()}
    easy = [alias for alias in seed.SPELLINGS if alias != seed.UNMATCHED_SPELLING]

    for alias in easy:
        suggested = {item["name"] for item in queue[alias]["suggestions"]}
        assert suggested == set(easy) - {alias}, alias


async def test_similarity_misses_the_spelling_that_matters(api) -> None:
    await seed.load()

    queue = {item["raw_alias"]: item for item in (await api.get("/resolution-queue")).json()}

    assert queue[seed.UNMATCHED_SPELLING]["suggestions"] == []
    for alias in seed.SPELLINGS:
        suggested = {item["name"] for item in queue[alias]["suggestions"]}
        assert seed.UNMATCHED_SPELLING not in suggested


async def test_the_loners_match_nothing(api) -> None:
    await seed.load()

    queue = {item["raw_alias"]: item for item in (await api.get("/resolution-queue")).json()}

    for alias in seed.LONERS:
        assert queue[alias]["suggestions"] == []


async def test_loading_twice_does_not_duplicate(api) -> None:
    await seed.load()
    sent, created = await seed.load()

    assert (sent, created) == (8, 0)
    assert await count_events() == 8


async def test_the_whole_thing_can_be_merged_into_one_shop(api) -> None:
    await seed.load()
    queue = {item["raw_alias"]: item for item in (await api.get("/resolution-queue")).json()}
    survivor = queue[seed.SPELLINGS[0]]["candidate"]["id"]

    for alias in seed.SPELLINGS[1:]:
        response = await api.post(
            f"/resolution-queue/{queue[alias]['id']}/merge", json={"into": survivor}
        )
        assert response.status_code == 200, response.text

    entity = (await api.get(f"/entities/{survivor}")).json()
    events = (await api.get("/events", params={"entity_id": survivor})).json()["events"]

    assert sorted(alias["alias"] for alias in entity["aliases"]) == sorted(seed.SPELLINGS)
    assert entity["status"] == "confirmed"
    assert len(events) == 6
    assert len((await api.get("/resolution-queue")).json()) == len(seed.LONERS)


async def test_clearing_leaves_nothing_behind(api) -> None:
    await seed.load()

    await seed.clear()

    assert await count_events() == 0
    assert (await api.get("/resolution-queue")).json() == []


def test_the_seed_invents_its_names() -> None:
    assert all(alias.isupper() for alias in seed.SPELLINGS + seed.LONERS)
    assert "ALBA" in seed.SPELLINGS[0]


def test_the_command_rejects_anything_it_does_not_understand(capsys) -> None:
    assert seed.main(["--wipe"]) == 2
    assert "uso: python -m kernel.seed" in capsys.readouterr().err


async def test_the_matcher_sees_the_seed_the_way_it_should(api) -> None:
    await seed.load()
    queue = {item["raw_alias"]: item for item in (await api.get("/resolution-queue")).json()}

    for alias in seed.SPELLINGS:
        entity = queue[alias]["candidate"]["id"]
        matches = (await api.get(f"/entities/{entity}/matches")).json()
        mergeable = [item["name"] for item in matches["candidates"] if item["would_merge"]]
        assert mergeable, f"{alias} debería tener con qué fusionarse"
        assert set(mergeable) <= set(seed.SPELLINGS) - {alias}

    for alias in seed.LONERS:
        matches = (await api.get(f"/entities/{queue[alias]['candidate']['id']}/matches")).json()
        assert [item for item in matches["candidates"] if item["would_merge"]] == []
