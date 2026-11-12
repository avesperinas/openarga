import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text

from kernel.db import engine
from kernel.main import app

SOURCE = "resolution-test"
MODULE = "finance"

MERCADONA = "MERCADONA SA 4412"
MERCADONA_OTRA = "MERCADONA 4412 VALENCIA"
GASOLINERA = "REPSOL E.S. 0912"


OWN_ENTITIES = "select entity_id from kernel.entity_aliases where source = :source"


async def _clear() -> None:
    async with engine().begin() as connection:
        await connection.execute(
            text("delete from kernel.events where source = :source"), {"source": SOURCE}
        )
        await connection.execute(
            text(f"update kernel.entities set merged_into = null where id in ({OWN_ENTITIES})"),
            {"source": SOURCE},
        )
        await connection.execute(
            text(f"delete from kernel.entities where id in ({OWN_ENTITIES})"), {"source": SOURCE}
        )


@pytest.fixture
async def api(database_url: str):
    await _clear()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://kernel") as client:
        yield client
    await _clear()
    await engine().dispose()


def event(alias: str, dedup: str, kind: str = "shop", amount: float = -12.4) -> dict:
    return {
        "ts": "2026-09-11T10:00:00+00:00",
        "module": MODULE,
        "source": SOURCE,
        "type": "finance.transaction",
        "entity": {"alias": alias, "kind": kind},
        "payload": {"amount": amount},
        "dedup_hash": dedup,
    }


async def ingest(api, alias: str, dedup: str, **kwargs) -> dict:
    response = await api.post("/events", json=event(alias, dedup, **kwargs))
    assert response.status_code == 200, response.text
    return response.json()


async def pending(api) -> list[dict]:
    response = await api.get("/resolution-queue")
    assert response.status_code == 200, response.text
    return response.json()


async def test_an_unknown_alias_creates_a_candidate_and_queues_it(api) -> None:
    ingested = await ingest(api, MERCADONA, "tx:1")

    assert ingested["queued"] is True
    assert ingested["entity_id"] is not None

    queue = await pending(api)
    assert len(queue) == 1
    assert queue[0]["raw_alias"] == MERCADONA
    assert queue[0]["source"] == SOURCE
    assert queue[0]["candidate"]["status"] == "candidate"
    assert queue[0]["candidate"]["id"] == ingested["entity_id"]


async def test_the_same_alias_resolves_without_queuing_again(api) -> None:
    first = await ingest(api, MERCADONA, "tx:1")
    second = await ingest(api, MERCADONA, "tx:2")

    assert second["queued"] is False
    assert second["entity_id"] == first["entity_id"]
    assert len(await pending(api)) == 1


async def test_a_different_alias_of_the_same_shop_creates_a_second_candidate(api) -> None:
    first = await ingest(api, MERCADONA, "tx:1")
    second = await ingest(api, MERCADONA_OTRA, "tx:2")

    assert first["entity_id"] != second["entity_id"]
    assert len(await pending(api)) == 2


async def test_the_queue_suggests_the_candidate_that_looks_alike(api) -> None:
    await ingest(api, MERCADONA, "tx:1")
    await ingest(api, MERCADONA_OTRA, "tx:2")
    await ingest(api, GASOLINERA, "tx:3")

    queue = {item["raw_alias"]: item for item in await pending(api)}

    suggested = [item["name"] for item in queue[MERCADONA_OTRA]["suggestions"]]
    assert suggested == [MERCADONA]
    assert queue[GASOLINERA]["suggestions"] == []


async def test_merging_leaves_both_events_on_the_same_entity(api) -> None:
    first = await ingest(api, MERCADONA, "tx:1")
    second = await ingest(api, MERCADONA_OTRA, "tx:2")

    queue = {item["raw_alias"]: item for item in await pending(api)}
    merged = await api.post(
        f"/resolution-queue/{queue[MERCADONA_OTRA]['id']}/merge",
        json={"into": first["entity_id"]},
    )

    assert merged.status_code == 200, merged.text
    survivor = merged.json()
    assert survivor["id"] == first["entity_id"]
    assert survivor["status"] == "confirmed"
    assert second["entity_id"] in survivor["merged"]

    assert sorted(alias["alias"] for alias in survivor["aliases"]) == sorted(
        [MERCADONA, MERCADONA_OTRA]
    )

    listed = (await api.get("/events", params={"entity_id": first["entity_id"]})).json()["events"]
    assert sorted(item["id"] for item in listed) == sorted([first["id"], second["id"]])


async def test_merging_does_not_rewrite_the_events(api) -> None:
    first = await ingest(api, MERCADONA, "tx:1")
    second = await ingest(api, MERCADONA_OTRA, "tx:2")

    queue = {item["raw_alias"]: item for item in await pending(api)}
    await api.post(
        f"/resolution-queue/{queue[MERCADONA_OTRA]['id']}/merge",
        json={"into": first["entity_id"]},
    )

    async with engine().connect() as connection:
        stored = await connection.scalar(
            text("select cast(entity_id as text) from kernel.events where id = cast(:id as uuid)"),
            {"id": second["id"]},
        )

    assert stored == second["entity_id"]


async def test_merging_empties_the_queue_on_both_sides(api) -> None:
    first = await ingest(api, MERCADONA, "tx:1")
    second_queue = {item["raw_alias"]: item for item in await pending(api)}
    await ingest(api, MERCADONA_OTRA, "tx:2")

    queue = {item["raw_alias"]: item for item in await pending(api)}
    await api.post(
        f"/resolution-queue/{queue[MERCADONA_OTRA]['id']}/merge",
        json={"into": first["entity_id"]},
    )

    assert second_queue[MERCADONA]["candidate"]["status"] == "candidate"
    assert await pending(api) == []


async def test_a_third_spelling_can_be_merged_into_the_same_survivor(api) -> None:
    first = await ingest(api, MERCADONA, "tx:1")
    await ingest(api, MERCADONA_OTRA, "tx:2")
    await ingest(api, "MERCADONA SA", "tx:3")

    for item in await pending(api):
        if item["candidate"]["id"] == first["entity_id"]:
            continue
        response = await api.post(
            f"/resolution-queue/{item['id']}/merge", json={"into": first["entity_id"]}
        )
        assert response.status_code == 200, response.text

    entity = (await api.get(f"/entities/{first['entity_id']}")).json()

    assert len(entity["aliases"]) == 3
    assert len(entity["merged"]) == 2
    assert await pending(api) == []


async def test_confirming_marks_the_candidate_as_a_thing_of_its_own(api) -> None:
    ingested = await ingest(api, GASOLINERA, "tx:1")
    item = (await pending(api))[0]

    confirmed = await api.post(f"/resolution-queue/{item['id']}/confirm")

    assert confirmed.status_code == 200, confirmed.text
    assert confirmed.json()["status"] == "confirmed"
    assert confirmed.json()["id"] == ingested["entity_id"]
    assert await pending(api) == []


async def test_a_resolved_item_cannot_be_resolved_twice(api) -> None:
    await ingest(api, GASOLINERA, "tx:1")
    item = (await pending(api))[0]
    await api.post(f"/resolution-queue/{item['id']}/confirm")

    again = await api.post(f"/resolution-queue/{item['id']}/confirm")

    assert again.status_code == 409
    assert "already resolved" in again.json()["detail"]


async def test_an_entity_cannot_be_merged_into_itself(api) -> None:
    ingested = await ingest(api, MERCADONA, "tx:1")
    item = (await pending(api))[0]

    response = await api.post(
        f"/resolution-queue/{item['id']}/merge", json={"into": ingested["entity_id"]}
    )

    assert response.status_code == 422
    assert "into itself" in response.json()["detail"]


async def test_merging_into_a_merged_entity_follows_the_chain(api) -> None:
    first = await ingest(api, MERCADONA, "tx:1")
    second = await ingest(api, MERCADONA_OTRA, "tx:2")

    queue = {item["raw_alias"]: item for item in await pending(api)}
    await api.post(
        f"/resolution-queue/{queue[MERCADONA_OTRA]['id']}/merge", json={"into": first["entity_id"]}
    )

    third = await ingest(api, "MERCADONA SA", "tx:3")
    item = (await pending(api))[0]
    response = await api.post(
        f"/resolution-queue/{item['id']}/merge", json={"into": second["entity_id"]}
    )

    assert response.status_code == 200, response.text
    assert response.json()["id"] == first["entity_id"]
    assert third["entity_id"] in response.json()["merged"]


async def test_a_merge_across_kinds_is_refused(api) -> None:
    shop = await ingest(api, MERCADONA, "tx:1")
    await ingest(api, "Sentadilla", "tx:2", kind="exercise")

    queue = {item["raw_alias"]: item for item in await pending(api)}
    response = await api.post(
        f"/resolution-queue/{queue['Sentadilla']['id']}/merge", json={"into": shop["entity_id"]}
    )

    assert response.status_code == 422
    assert "cannot merge" in response.json()["detail"]


async def test_an_event_cannot_declare_an_entity_twice(api) -> None:
    body = event(MERCADONA, "tx:1") | {"entity_id": "5f7d4a7e-0b3f-4f6e-9a62-0f2f6a1f9c11"}

    response = await api.post("/events", json=body)

    assert response.status_code == 422
    assert "entity_id" in response.json()["detail"]


async def test_an_event_without_an_entity_is_still_ingested(api) -> None:
    body = event(MERCADONA, "tx:1")
    del body["entity"]

    response = await api.post("/events", json=body)

    assert response.status_code == 200
    assert response.json()["entity_id"] is None
    assert response.json()["queued"] is False
    assert await pending(api) == []


async def test_an_unknown_entity_is_404(api) -> None:
    missing = "5f7d4a7e-0b3f-4f6e-9a62-0f2f6a1f9c11"

    assert (await api.get(f"/entities/{missing}")).status_code == 404
