from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text

from kernel.db import engine
from kernel.main import app

SOURCE = "events-test"
MODULE = "finance"

BASE_EVENT = {
    "ts": "2026-09-11T10:00:00+00:00",
    "module": MODULE,
    "source": SOURCE,
    "type": "finance.transaction",
    "payload": {"amount": -12.4, "merchant": "MERCADONA SA 4412"},
}


async def _clear() -> None:
    async with engine().begin() as connection:
        await connection.execute(
            text("delete from kernel.events where source = :source"), {"source": SOURCE}
        )


@pytest.fixture
async def api(database_url: str):
    await _clear()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://kernel") as client:
        yield client
    await _clear()
    await engine().dispose()


async def count_events() -> int:
    async with engine().connect() as connection:
        return await connection.scalar(
            text("select count(*) from kernel.events where source = :source"), {"source": SOURCE}
        )


def event(**overrides) -> dict:
    return BASE_EVENT | overrides


async def test_the_same_event_twice_leaves_one_row_and_answers_200_both_times(api) -> None:
    first = await api.post("/events", json=event(dedup_hash="bbva:tx:8891"))
    second = await api.post("/events", json=event(dedup_hash="bbva:tx:8891"))

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["created"] is True
    assert second.json()["created"] is False
    assert first.json()["id"] == second.json()["id"]
    assert await count_events() == 1


async def test_the_kernel_derives_a_dedup_hash_when_the_connector_omits_it(api) -> None:
    first = await api.post("/events", json=event())
    second = await api.post("/events", json=event())

    assert first.json()["dedup_hash"].startswith("auto:")
    assert first.json()["id"] == second.json()["id"]
    assert await count_events() == 1


async def test_the_derived_hash_ignores_the_timezone_of_the_same_instant(api) -> None:
    utc = await api.post("/events", json=event(ts="2026-09-11T10:00:00+00:00"))
    madrid = await api.post("/events", json=event(ts="2026-09-11T12:00:00+02:00"))

    assert utc.json()["id"] == madrid.json()["id"]
    assert await count_events() == 1


async def test_reingesting_does_not_rewrite_the_row(api) -> None:
    first = await api.post("/events", json=event(dedup_hash="bbva:tx:8891"))
    again = await api.post(
        "/events", json=event(dedup_hash="bbva:tx:8891", payload={"amount": -99.9})
    )

    assert again.json()["created"] is False
    stored = (await api.get("/events", params={"module": MODULE})).json()["events"]
    assert [item["id"] for item in stored] == [first.json()["id"]]
    assert stored[0]["payload"] == BASE_EVENT["payload"]


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("ts", "2026-09-11T10:00:00"),
        ("ts", "ayer"),
        ("module", "Finance"),
        ("module", "finance-1"),
        ("source", "Fuente Rara"),
        ("type", "transaction"),
        ("type", "Finance.Transaction"),
        ("payload", "no soy un objeto"),
        ("entity_id", "no-soy-un-uuid"),
    ],
)
async def test_ingestion_rejects_a_malformed_event(api, field: str, value) -> None:
    response = await api.post("/events", json=event(**{field: value}))

    assert response.status_code == 422
    assert await count_events() == 0


@pytest.fixture
async def entity(api):
    async with engine().begin() as connection:
        entity_id = await connection.scalar(
            text(
                "insert into kernel.entities (kind, module, name) "
                "values ('merchant', :module, 'Mercadona') returning id"
            ),
            {"module": MODULE},
        )
    yield entity_id
    async with engine().begin() as connection:
        await connection.execute(
            text("delete from kernel.events where entity_id = :id"), {"id": entity_id}
        )
        await connection.execute(
            text("delete from kernel.entities where id = :id"), {"id": entity_id}
        )


async def test_listing_filters_by_entity(api, entity) -> None:
    with_entity = await api.post("/events", json=event(entity_id=str(entity)))
    await api.post("/events", json=event(dedup_hash="sin-entidad"))

    listed = (await api.get("/events", params={"entity_id": str(entity)})).json()["events"]

    assert [item["id"] for item in listed] == [with_entity.json()["id"]]


async def seed(api, count: int, **overrides) -> list[str]:
    start = datetime(2026, 9, 11, 10, 0, tzinfo=UTC)
    ids = []
    for index in range(count):
        response = await api.post(
            "/events",
            json=event(ts=(start + timedelta(minutes=index)).isoformat(), **overrides),
        )
        ids.append(response.json()["id"])
    return list(reversed(ids))


async def test_listing_filters_by_module_type_and_time_range(api) -> None:
    await seed(api, 1, module="finance", type="finance.transaction")
    await seed(api, 1, module="health", type="health.weight", payload={"kg": 71.2})

    by_module = (await api.get("/events", params={"module": "health"})).json()["events"]
    assert [item["module"] for item in by_module] == ["health"]

    by_type = (await api.get("/events", params={"type": "finance.transaction"})).json()["events"]
    assert [item["type"] for item in by_type] == ["finance.transaction"]

    inside = await api.get(
        "/events",
        params={
            "module": MODULE,
            "since": "2026-09-11T09:00:00+00:00",
            "until": "2026-09-11T11:00:00+00:00",
        },
    )
    assert len(inside.json()["events"]) == 1

    outside = await api.get(
        "/events", params={"module": MODULE, "since": "2026-09-11T11:00:00+00:00"}
    )
    assert outside.json()["events"] == []


async def test_the_time_range_is_half_open(api) -> None:
    await seed(api, 1)

    excluded = await api.get(
        "/events", params={"module": MODULE, "until": "2026-09-11T10:00:00+00:00"}
    )
    included = await api.get(
        "/events", params={"module": MODULE, "since": "2026-09-11T10:00:00+00:00"}
    )

    assert excluded.json()["events"] == []
    assert len(included.json()["events"]) == 1


async def test_the_cursor_walks_every_event_once(api) -> None:
    expected = await seed(api, 7)

    seen: list[str] = []
    cursor = None
    pages = 0
    while True:
        params: dict = {"limit": 3, "module": MODULE}
        if cursor:
            params["cursor"] = cursor
        page = (await api.get("/events", params=params)).json()
        seen.extend(item["id"] for item in page["events"])
        pages += 1
        cursor = page["next_cursor"]
        if cursor is None:
            break

    assert seen == expected
    assert len(seen) == len(set(seen))
    assert pages == 3


async def test_the_last_page_has_no_cursor(api) -> None:
    await seed(api, 2)

    page = (await api.get("/events", params={"limit": 50, "module": MODULE})).json()

    assert len(page["events"]) == 2
    assert page["next_cursor"] is None


async def test_a_broken_cursor_is_rejected(api) -> None:
    response = await api.get("/events", params={"cursor": "no-es-un-cursor"})

    assert response.status_code == 422
    assert response.json()["detail"] == "invalid cursor"


async def test_the_limit_is_capped(api) -> None:
    assert (await api.get("/events", params={"limit": 5000})).status_code == 422
    assert (await api.get("/events", params={"limit": 0})).status_code == 422


async def test_an_answer_says_how_much_of_it_was_postgres(api) -> None:
    response = await api.get("/events", params={"module": MODULE})

    db, app_part = response.headers["server-timing"].split(", ")
    queries = int(db.split('desc="')[1].split(" ")[0])
    assert queries >= 1
    assert float(db.split("dur=")[1].split(";")[0]) > 0
    assert app_part.startswith("app;dur=")


async def test_a_batch_ingests_in_order_and_says_which_were_new(api) -> None:
    await api.post("/events", json=event(dedup_hash="lote:1"))

    response = await api.post(
        "/events/batch",
        json={
            "events": [
                event(dedup_hash="lote:1"),
                event(dedup_hash="lote:2"),
                event(dedup_hash="lote:2"),
                event(ts="2026-09-12T10:00:00+00:00"),
            ]
        },
    )

    assert response.status_code == 200
    results = response.json()["results"]
    assert [one["created"] for one in results] == [False, True, False, True]
    assert results[1]["id"] == results[2]["id"]
    assert results[3]["dedup_hash"].startswith("auto:")
    assert await count_events() == 3


async def test_a_batch_with_one_bad_event_ingests_none(api) -> None:
    good = event(dedup_hash="lote:bueno")
    both = event(
        dedup_hash="lote:malo", entity_id=str(uuid4()), entity={"kind": "merchant", "alias": "x"}
    )

    assert (await api.post("/events/batch", json={"events": [good, both]})).status_code == 422
    assert (
        await api.post("/events/batch", json={"events": [good, event(type="transaction")]})
    ).status_code == 422
    assert await count_events() == 0


async def test_a_batch_has_a_size(api) -> None:
    assert (await api.post("/events/batch", json={"events": []})).status_code == 422
    too_many = [event(dedup_hash=f"lote:{n}") for n in range(501)]
    assert (await api.post("/events/batch", json={"events": too_many})).status_code == 422
    assert await count_events() == 0
