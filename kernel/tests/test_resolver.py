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


async def pass_over_everything() -> resolver.Outcome:
    async with engine().begin() as connection:
        return await resolver.run(connection)


async def entity_of(api, alias: str) -> str:
    queue = (await api.get("/resolution-queue")).json()
    return next(item["candidate"]["id"] for item in queue if item["raw_alias"] == alias)


async def test_the_pass_unites_the_three_spellings_without_being_asked(api) -> None:
    await seed.load()

    outcome = await pass_over_everything()

    assert len(outcome.merged) == 2
    survivor = (await api.get(f"/entities/{outcome.merged[0].target}")).json()
    assert sorted(alias["alias"] for alias in survivor["aliases"]) == sorted(seed.SPELLINGS)

    events = (await api.get("/events", params={"entity_id": survivor["id"]})).json()["events"]
    assert len(events) == 6


async def test_a_second_pass_changes_nothing(api) -> None:
    await seed.load()
    await pass_over_everything()

    second = await pass_over_everything()

    assert second.merged == []
    assert second.changed is False


async def test_what_it_cannot_resolve_it_leaves_alone(api) -> None:
    await seed.load()

    outcome = await pass_over_everything()

    abstained = {item.name for item in outcome.abstained}
    assert set(seed.LONERS) <= abstained
    for alias in seed.LONERS:
        entity = (await api.get(f"/entities/{await entity_of(api, alias)}")).json()
        assert entity["status"] == "candidate"
        assert entity["merged"] == []


async def test_a_shared_word_is_not_enough_to_merge(api) -> None:
    for index, alias in enumerate(["CLINICA DENTAL SAUCE", "BAR EL SAUCE"]):
        await api.post(
            "/events",
            json={
                "ts": "2026-09-11T10:00:00+00:00",
                "module": "finance",
                "source": seed.SOURCE,
                "type": "finance.transaction",
                "entity": {"alias": alias, "kind": seed.KIND},
                "payload": {"amount": -9.0},
                "dedup_hash": f"{seed.SOURCE}:sauce:{index}",
            },
        )

    outcome = await pass_over_everything()

    assert outcome.merged == []
    assert {item.name for item in outcome.abstained} == {"CLINICA DENTAL SAUCE", "BAR EL SAUCE"}


async def test_the_pass_does_not_confirm_anything(api) -> None:
    await seed.load()

    outcome = await pass_over_everything()

    survivor = (await api.get(f"/entities/{outcome.merged[0].target}")).json()
    assert survivor["status"] == "candidate"


async def test_ingestion_still_resolves_only_by_exact_alias(api) -> None:
    await seed.load()
    await pass_over_everything()

    ingested = await api.post(
        "/events",
        json={
            "ts": "2026-09-12T10:00:00+00:00",
            "module": "finance",
            "source": seed.SOURCE,
            "type": "finance.transaction",
            "entity": {"alias": "ALBA MARKET 999", "kind": seed.KIND},
            "payload": {"amount": -5.0},
            "dedup_hash": f"{seed.SOURCE}:later",
        },
    )

    assert ingested.json()["queued"] is True
    entity = (await api.get(f"/entities/{ingested.json()['entity_id']}")).json()
    assert entity["status"] == "candidate"
    assert entity["merged_into"] is None

    outcome = await pass_over_everything()
    assert [decision.candidate_name for decision in outcome.merged] == ["ALBA MARKET 999"]


async def test_the_endpoint_reports_what_the_pass_decided(api) -> None:
    await seed.load()

    response = await api.post("/resolution/run")

    assert response.status_code == 200
    body = response.json()
    assert body["threshold"] == 0.8
    assert len(body["merged"]) == 2
    assert {item["rule"] for item in body["merged"]} == {
        "same_name_other_store",
        "same_store_number",
    }
    assert {item["entity"] for item in body["abstained"]} >= set(seed.LONERS)


async def test_a_merged_entity_keeps_matching_through_its_family(api) -> None:
    await seed.load()
    await pass_over_everything()

    async with engine().connect() as connection:
        merged = await connection.scalar(
            text(
                "select count(*) from kernel.entities "
                "where status = 'merged' and module = 'finance'"
            )
        )

    assert merged == 2
