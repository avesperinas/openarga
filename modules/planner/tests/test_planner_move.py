from __future__ import annotations

import secrets
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text

from planner import apps

MODULES = Path(__file__).resolve().parents[2]
TOKEN = secrets.token_hex(16)
DAY = "2026-10-06"


@pytest.fixture
def migrated(database_url: str) -> None:
    from kernel import db as kernel_db
    from kernel import migrate

    kernel_db.engine.cache_clear()
    migrate.upgrade()


@pytest.fixture
async def kernel(migrated, schema, monkeypatch):
    from arga_testing import fresh_modules
    from kernel import capabilities
    from kernel import db as kernel_db
    from kernel.main import app as kernel_app
    from training import db as training_db
    from training.main import app as training_app

    monkeypatch.setenv("MODULE_REGISTRATION_TOKEN", TOKEN)
    monkeypatch.setenv("KERNEL_URL", "http://kernel")
    clean = text("delete from kernel.events where module in ('training', 'planner')")
    async with schema.begin() as connection:
        await connection.execute(clean)
        await fresh_modules(connection, "planner", "training", fresh=["training"])
    monkeypatch.setattr(capabilities, "module_transport", lambda: ASGITransport(app=training_app))
    monkeypatch.setattr(apps, "kernel_transport", lambda: ASGITransport(app=kernel_app))
    training_db.engine.cache_clear()
    async with AsyncClient(transport=ASGITransport(app=kernel_app), base_url="http://kernel") as c:
        yield c
    await training_db.engine().dispose()
    training_db.engine.cache_clear()
    async with schema.begin() as connection:
        await connection.execute(clean)
        await connection.execute(text("delete from kernel.modules where id = 'training'"))
    await kernel_db.engine().dispose()


@pytest.fixture
async def training(kernel):
    from training.main import app as training_app

    async with AsyncClient(
        transport=ASGITransport(app=training_app), base_url="http://training"
    ) as c:
        yield c


async def flush(kernel) -> int:
    from training import db as training_db
    from training import publisher

    async with training_db.engine().begin() as connection:
        await connection.execute(text('set local role "mod_training"'))
        return (await publisher.publish_pending(connection, kernel))["published"]


async def padel(training, kernel) -> str:
    kind = (await training.post("/activity-types", json={"name": "Padel"})).json()
    logged = (
        await training.post(
            "/activities", json={"activity_type_id": kind["id"], "day": DAY, "start_time": "18:30"}
        )
    ).json()
    await flush(kernel)
    return logged["id"]


async def shown(api) -> list[dict]:
    await api.get("/calendars")
    return (
        await api.get(
            "/occurrences",
            params={"from": "2026-10-05T00:00:00+02:00", "to": "2026-10-09T00:00:00+02:00"},
        )
    ).json()


async def test_a_padel_moves_in_the_calendar_and_in_training(api, kernel, training) -> None:
    activity = await padel(training, kernel)
    [layer] = [one for one in (await api.get("/calendars")).json() if one["origin"] == "app"]
    [found] = await shown(api)
    assert layer["movable"] is True

    moved = await api.post(
        f"/app-events/{found['id'].removeprefix('app:')}/move",
        json={"start": "2026-10-07T19:30:00+02:00", "end": "2026-10-07T20:30:00+02:00"},
    )

    assert moved.status_code == 200, moved.text
    assert moved.json()["start"] == "2026-10-07T19:30:00+02:00"
    assert [one["start"] for one in await shown(api)] == ["2026-10-07T19:30:00+02:00"]
    assert await flush(kernel) >= 1
    assert [one["start"] for one in await shown(api)] == ["2026-10-07T19:30:00+02:00"]
    listed = (
        await training.get("/activities", params={"since": DAY, "until": "2026-10-08"})
    ).json()
    assert [(one["id"], one["day"], one["start_time"]) for one in listed] == [
        (activity, "2026-10-07", "19:30:00")
    ]


async def test_back_to_where_it_was_also_arrives(api, kernel, training) -> None:
    await padel(training, kernel)
    [found] = await shown(api)
    target = f"/app-events/{found['id'].removeprefix('app:')}/move"

    await api.post(
        target, json={"start": "2026-10-07T19:30:00+02:00", "end": "2026-10-07T20:30:00+02:00"}
    )
    await flush(kernel)
    await api.post(target, json={"start": found["start"], "end": found["end"]})
    await flush(kernel)

    [again] = await shown(api)
    assert (again["start"], again["end"]) == (found["start"], found["end"])


async def test_what_the_app_refuses_comes_back_with_its_reason(api, kernel, training) -> None:
    await padel(training, kernel)
    [found] = await shown(api)

    refused = await api.post(
        f"/app-events/{found['id'].removeprefix('app:')}/move",
        json={"start": DAY, "end": "2026-10-07", "all_day": True},
    )

    assert refused.status_code == 409
    assert "hora" in refused.json()["detail"]
    [same] = await shown(api)
    assert same["start"] == found["start"]
