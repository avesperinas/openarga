import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text

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


async def decisions() -> list[tuple[str, str, str]]:
    async with engine().connect() as connection:
        rows = (
            await connection.execute(
                text(
                    "select decision, method, decided_by from kernel.entity_decisions "
                    "order by decided_at, id"
                )
            )
        ).all()
    return [(row.decision, row.method, row.decided_by) for row in rows]


async def test_an_automatic_merge_says_why(api) -> None:
    await seed.load()

    outcome = await resolve()

    absorbed = (await api.get(f"/entities/{outcome.merged[0].candidate}")).json()
    provenance = absorbed["merged_via"]
    assert provenance["decided_by"] == "resolver"
    assert provenance["method"] == "rule"
    assert provenance["rule"] in {"same_name_other_store", "same_store_number"}
    assert provenance["confidence"] >= 0.8
    assert provenance["evidence"]


async def test_a_manual_merge_says_who(api) -> None:
    await seed.load()
    queue = {item["raw_alias"]: item for item in (await api.get("/resolution-queue")).json()}
    survivor = queue[seed.SPELLINGS[0]]["candidate"]["id"]

    await api.post(
        f"/resolution-queue/{queue[seed.LONERS[0]]['id']}/merge", json={"into": survivor}
    )

    assert ("merged", "manual", "person") in await decisions()


async def test_undoing_puts_the_events_back_where_they_were(api) -> None:
    await seed.load()
    outcome = await resolve()
    absorbed, survivor = outcome.merged[0].candidate, outcome.merged[0].target
    before = (await api.get("/events", params={"entity_id": absorbed})).json()["events"]

    undone = await api.post(f"/entities/{absorbed}/unmerge")

    assert undone.status_code == 200, undone.text
    assert undone.json()["status"] == "candidate"
    assert undone.json()["merged_into"] is None
    assert undone.json()["merged_via"] is None

    after = (await api.get("/events", params={"entity_id": absorbed})).json()["events"]
    assert [item["id"] for item in after] == [item["id"] for item in before]

    survivors_events = (await api.get("/events", params={"entity_id": survivor})).json()["events"]
    assert len(survivors_events) < 6


async def test_the_next_pass_does_not_redo_what_was_undone(api) -> None:
    await seed.load()
    outcome = await resolve()
    absorbed = outcome.merged[0].candidate
    await api.post(f"/entities/{absorbed}/unmerge")

    second = await resolve()

    assert [decision.candidate for decision in second.merged] == []
    refused = {item.entity: item.reason for item in second.abstained}
    assert refused.get(absorbed) == "descartado antes"


async def test_undoing_is_written_down_as_a_rejection(api) -> None:
    await seed.load()
    outcome = await resolve()
    await api.post(f"/entities/{outcome.merged[0].candidate}/unmerge")

    assert ("rejected", "undo", "person") in await decisions()


async def test_undoing_something_that_is_not_merged_is_refused(api) -> None:
    await seed.load()
    loner = next(
        item["candidate"]["id"]
        for item in (await api.get("/resolution-queue")).json()
        if item["raw_alias"] == seed.LONERS[0]
    )

    response = await api.post(f"/entities/{loner}/unmerge")

    assert response.status_code == 409
    assert "not merged" in response.json()["detail"]


async def test_the_log_is_append_only(api) -> None:
    await seed.load()
    outcome = await resolve()
    absorbed, survivor = outcome.merged[0].candidate, outcome.merged[0].target
    await api.post(f"/entities/{absorbed}/unmerge")

    async with engine().begin() as connection:
        from kernel.entities import merge_entities

        await merge_entities(
            connection,
            absorbed,
            survivor,
            method="manual",
            decided_by="person",
            evidence="me he arrepentido",
        )

    assert [row[0] for row in await decisions()] == ["merged", "merged", "rejected", "merged"]
