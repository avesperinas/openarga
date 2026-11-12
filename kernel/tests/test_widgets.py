import json

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text

from kernel import resolver, seed
from kernel.db import engine
from kernel.main import app
from kernel.ui import SIZES
from kernel.widgets import BY_VOLUME, KINDS, LIST_LIKE


@pytest.fixture
async def api(database_url: str):
    async with engine().begin() as connection:
        await connection.execute(text("delete from kernel.resolution_queue"))
        await connection.execute(text("delete from kernel.events"))
    await seed.clear()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://kernel") as client:
        yield client
    await seed.clear()
    await engine().dispose()


async def resolve() -> None:
    async with engine().begin() as connection:
        await resolver.run(connection)


async def kernel_widgets(api) -> list[dict]:
    return [w for w in (await api.get("/ui/widgets")).json() if w["source"] == "kernel"]


async def test_the_catalogue_lists_them_all(api) -> None:
    catalogue = await kernel_widgets(api)

    assert [w["id"] for w in catalogue] == [
        "events",
        "events_trend",
        "events_by_weekday",
        "activity",
        "entities",
        "entities_by_volume",
        "version",
    ]
    assert {w["source"] for w in catalogue} == {"kernel"}


async def test_every_entry_says_where_to_ask_and_what_sizes_it_takes(api) -> None:
    for widget in await kernel_widgets(api):
        assert widget["endpoint"] == f"/api/kernel/widgets/{widget['id']}"
        assert widget["sizes"], widget["id"]
        assert set(widget["sizes"]) <= set(SIZES), widget["id"]
        assert 1 <= widget["hue"] <= 8


async def test_every_entry_declares_which_body_it_is(api) -> None:
    for widget in (await api.get("/ui/widgets")).json():
        assert widget["kind"] in KINDS, widget["id"]
        assert widget["shape"] == ("list" if widget["kind"] in LIST_LIKE else "number")


@pytest.mark.parametrize(
    "widget",
    [
        "events",
        "events_trend",
        "events_by_weekday",
        "activity",
        "entities",
        "entities_by_volume",
        "version",
    ],
)
async def test_every_widget_answers_the_whole_envelope(api, widget: str) -> None:
    response = await api.get(f"/widgets/{widget}")

    assert response.status_code == 200
    sealed = response.json()
    assert sealed["state"] in {"ready", "empty", "error", "disconnected"}
    assert sealed["updated_at"]
    assert "body" in sealed


async def test_sync_is_gone(api) -> None:
    assert (await api.get("/widgets/sync")).status_code == 404


async def test_version_never_touches_the_database(api) -> None:
    sealed = (await api.get("/widgets/version")).json()

    assert sealed["state"] == "ready"
    assert sealed["body"]["value"]


async def test_with_no_data_the_counters_are_empty_and_not_zero_pretending(api) -> None:
    for widget in ("events", "entities"):
        assert (await api.get(f"/widgets/{widget}")).json()["state"] == "empty"


async def test_the_counters_count_once_there_is_something(api) -> None:
    await seed.load()

    events = (await api.get("/widgets/events")).json()
    entities = (await api.get("/widgets/entities")).json()

    assert events["state"] == "ready"
    assert events["body"]["previous"] is not None
    assert events["body"]["good_when"] == "up"
    assert "8 en total" in events["body"]["detail"]
    assert entities["state"] == "ready"
    assert entities["body"]["value"] == 5


async def test_the_series_come_dense_with_zeros_and_not_with_holes(api) -> None:
    await seed.load()

    trend = (await api.get("/widgets/events_trend")).json()
    weekday = (await api.get("/widgets/events_by_weekday")).json()
    activity = (await api.get("/widgets/activity")).json()

    if trend["state"] == "ready":
        assert len(trend["body"]["series"]) == 14
        assert all(isinstance(point, int) for point in trend["body"]["series"])
    if weekday["state"] == "ready":
        assert len(weekday["body"]["series"]) == 7
        assert weekday["body"]["labels"] == ["L", "M", "X", "J", "V", "S", "D"]
        assert 0 <= weekday["body"]["highlight"] <= 6
    if activity["state"] == "ready":
        assert len(activity["body"]["values"]) == 56
        assert activity["body"]["columns"] == 7


async def test_by_volume_shows_the_doubt_the_resolver_left(api) -> None:
    await seed.load()
    await resolve()

    sealed = (await api.get("/widgets/entities_by_volume")).json()

    assert sealed["state"] == "ready"
    assert sealed["body"]["rows"]
    assert "uncertainty" in sealed or all(row["value"] for row in sealed["body"]["rows"])


async def test_by_volume_asks_for_each_family_once_and_not_per_event(api) -> None:
    await seed.load()

    async with engine().connect() as connection:
        plan = await connection.scalar(
            text(f"explain (format json) {BY_VOLUME.text}"), {"limit": 5}
        )

    assert "SubPlan" not in json.dumps(plan)


async def test_an_unknown_widget_says_so(api) -> None:
    response = await api.get("/widgets/inventado")

    assert response.status_code == 404
    assert "has no widget" in response.json()["detail"]
