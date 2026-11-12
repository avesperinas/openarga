from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import text

from goals.common import today

METER = "probe_meter"


@pytest.fixture
async def meter(schema):
    async with schema.begin() as connection:
        await connection.execute(text("delete from kernel.events where module = :m"), {"m": METER})
        await connection.execute(
            text(
                "insert into kernel.modules (id, version, enabled, manifest) "
                "values (:m, '0.1.0', true, cast(:manifest as jsonb)) "
                "on conflict (id) do update set manifest = excluded.manifest"
            ),
            {
                "m": METER,
                "manifest": json.dumps(
                    {"id": METER, "publishes": [{"type": f"{METER}.metric", "contract": "metric"}]}
                ),
            },
        )
    yield schema
    async with schema.begin() as connection:
        await connection.execute(text("delete from kernel.events where module = :m"), {"m": METER})
        await connection.execute(text("delete from kernel.modules where id = :m"), {"m": METER})


async def publish(engine, key: str, kind: str, unit: str, days_ago: int, value: float, n=0):
    day = today() - timedelta(days=days_ago)
    point = {"key": key, "label": key.split(".")[1].capitalize(), "unit": unit, "kind": kind}
    async with engine.begin() as connection:
        await connection.execute(
            text(
                "insert into kernel.events (ts, module, source, type, payload, dedup_hash) "
                "values (:ts, :m, 'app', :type, cast(:payload as jsonb), :dedup)"
            ),
            {
                "ts": datetime.now(UTC) - timedelta(days=days_ago) + timedelta(minutes=n),
                "m": METER,
                "type": f"{METER}.metric",
                "payload": json.dumps(
                    {"metric": {**point, "day": day.isoformat(), "value": value}}
                ),
                "dedup": f"{key}@{day}:{value}:{n}",
            },
        )


async def test_the_available_figures_come_from_the_log_with_their_last_value(meter, api) -> None:
    await publish(meter, f"{METER}.steps", "amount", "steps", 1, 9000)
    await publish(meter, f"{METER}.steps", "amount", "steps", 0, 3000)
    await publish(meter, f"{METER}.steps", "amount", "steps", 0, 6500, n=5)
    listed = {one["key"]: one for one in (await api.get("/metrics")).json()}
    assert listed[f"{METER}.steps"]["last_value"] == 6500
    assert listed[f"{METER}.steps"]["kind"] == "amount"


async def test_a_steps_goal_is_met_by_itself(meter, api) -> None:
    for days_ago in range(1, 4):
        await publish(meter, f"{METER}.steps", "amount", "steps", days_ago, 8500)
    await publish(meter, f"{METER}.steps", "amount", "steps", 0, 4000)
    goal = (
        await api.post(
            "/goals",
            json={
                "title": "8.000 pasos",
                "kind": "periodic",
                "period": "day",
                "target": 8000,
                "metric_key": f"{METER}.steps",
                "start_on": (today() - timedelta(days=10)).isoformat(),
            },
        )
    ).json()
    assert goal["metric"]["unit"] == "steps"
    assert goal["streak"] == 3 and goal["today_met"] is False
    await publish(meter, f"{METER}.steps", "amount", "steps", 0, 8100, n=30)
    again = (await api.get(f"/goals/{goal['id']}")).json()["goal"]
    assert again["today_met"] is True and again["streak"] == 4


async def test_a_net_worth_goal_moves_with_its_pace_and_projection(meter, api) -> None:
    for days_ago, value in ((20, 50000), (10, 51000), (0, 52000)):
        await publish(meter, f"{METER}.net_worth", "level", "EUR", days_ago, value)
    goal = (
        await api.post(
            "/goals",
            json={
                "title": "60.000 € de patrimonio",
                "kind": "dated",
                "target": 60000,
                "metric_key": f"{METER}.net_worth",
                "start_on": (today() - timedelta(days=20)).isoformat(),
                "due_on": (today() + timedelta(days=80)).isoformat(),
            },
        )
    ).json()
    assert goal["start_value"] == 50000 and goal["current"] == 52000
    assert goal["pace"] == "on_track"
    assert round(goal["projection"]) == 60000 and goal["projection_reached"] is True


async def test_reaching_the_figure_closes_it(meter, api) -> None:
    await publish(meter, f"{METER}.degree", "level", "count", 5, 0)
    goal = (
        await api.post(
            "/goals",
            json={
                "title": "Aprobar el máster",
                "kind": "dated",
                "target": 1,
                "metric_key": f"{METER}.degree",
                "due_on": (today() + timedelta(days=200)).isoformat(),
            },
        )
    ).json()
    assert goal["status"] == "active"
    await publish(meter, f"{METER}.degree", "level", "count", 0, 1)
    closed = (await api.get("/goals?state=closed")).json()
    assert [(one["title"], one["status"]) for one in closed] == [("Aprobar el máster", "achieved")]


async def test_kpis_publishes_its_own_figure_when_a_task_is_ticked(api) -> None:
    from goals.db import engine

    categories = {one["name"]: one["id"] for one in (await api.get("/categories")).json()}
    task = (
        await api.post("/tasks", json={"category_id": categories["Casa"], "title": "Regar"})
    ).json()
    await api.post(f"/tasks/{task['id']}/done")
    await api.post(f"/tasks/{task['id']}/undo")
    async with engine().begin() as connection:
        rows = await connection.execute(
            text("select payload from goals.goals_outbox where type = 'goals.metric' order by id")
        )
        points = [row.payload["metric"] for row in rows]
    assert [(one["key"], one["value"]) for one in points] == [
        ("goals.tasks_done", 1),
        ("goals.tasks_done", 0),
    ]


async def test_the_history_of_the_figure_is_queued_once(api) -> None:
    from goals import figures
    from goals.db import engine

    categories = {one["name"]: one["id"] for one in (await api.get("/categories")).json()}
    for title in ("Uno", "Dos"):
        task = (
            await api.post("/tasks", json={"category_id": categories["Casa"], "title": title})
        ).json()
        await api.post(f"/tasks/{task['id']}/done")
    for _ in range(2):
        async with engine().begin() as connection:
            await connection.execute(text('set local role "mod_goals"'))
            await figures.backfill(connection)
    async with engine().begin() as connection:
        history = (
            await connection.execute(
                text("select payload from goals.goals_outbox where dedup_hash like :tail"),
                {"tail": "%:history"},
            )
        ).all()
    assert [row.payload["metric"]["value"] for row in history] == [2]


async def test_a_mark_goal_only_counts_what_is_lifted_after_it_starts(meter, api) -> None:
    await publish(meter, f"{METER}.bench", "peak", "kg", 900, 140)
    await publish(meter, f"{METER}.bench", "peak", "kg", 1, 110)
    goal = (
        await api.post(
            "/goals",
            json={
                "title": "Press banca 130",
                "kind": "dated",
                "target": 130,
                "metric_key": f"{METER}.bench",
                "due_on": (today() + timedelta(days=90)).isoformat(),
            },
        )
    ).json()
    assert goal["status"] == "active" and goal["start_value"] == 140
    assert goal["metric"]["kind"] == "level"
    await publish(meter, f"{METER}.bench", "peak", "kg", 0, 132.5)
    closed = (await api.get("/goals?state=closed")).json()
    assert [(one["title"], one["status"]) for one in closed] == [("Press banca 130", "achieved")]


async def _tool(api, name: str, arguments: dict) -> dict:
    response = await api.post(
        f"/tools/{name}", json=arguments, headers={"x-arga-scopes": "goals:write"}
    )
    assert response.status_code == 200, response.text
    return response.json()["content"]


async def test_a_goal_set_up_later_starts_where_the_figure_was_on_its_first_day(meter, api) -> None:
    for days_ago, value in ((100, 18000), (70, 21000), (0, 30000)):
        await publish(meter, f"{METER}.net_worth", "level", "EUR", days_ago, value)
    start_on = (today() - timedelta(days=99)).isoformat()
    due_on = (today() + timedelta(days=60)).isoformat()
    shape = {"kind": "dated", "target": 35000, "start_on": start_on, "due_on": due_on}

    refused = await _tool(
        api,
        "create_goal",
        {"title": "Patrimonio", "metric_key": f"{METER}.net_worth", "start_value": 30000, **shape},
    )
    assert "Quita start_value" in refused["error"]

    created = await _tool(
        api, "create_goal", {"title": "Patrimonio", "metric_key": f"{METER}.net_worth", **shape}
    )
    assert created["start"] == 18000

    refused = await _tool(api, "update_goal", {"goal_id": created["goal_id"], "start_value": 30000})
    assert "Quita start_value" in refused["error"]
    by_hand = await _tool(api, "create_goal", {"title": "A mano", "start_value": 30000, **shape})
    tied = await _tool(
        api,
        "update_goal",
        {"goal_id": by_hand["goal_id"], "metric_key": f"{METER}.net_worth", "start_value": None},
    )
    assert tied["start"] == 18000


async def test_moving_the_first_day_moves_the_start(meter, api) -> None:
    for days_ago, value in ((40, 100), (20, 110), (0, 120)):
        await publish(meter, f"{METER}.weight", "level", "kg", days_ago, value)
    goal = (
        await api.post(
            "/goals",
            json={
                "title": "Peso",
                "kind": "dated",
                "direction": "at_most",
                "target": 90,
                "metric_key": f"{METER}.weight",
                "start_on": (today() - timedelta(days=20)).isoformat(),
                "due_on": (today() + timedelta(days=60)).isoformat(),
            },
        )
    ).json()
    assert goal["start_value"] == 110
    moved = (
        await api.put(
            f"/goals/{goal['id']}",
            json={"start_on": (today() - timedelta(days=40)).isoformat()},
        )
    ).json()
    assert moved["start_value"] == 100 and moved["start"] == 100


async def test_a_start_that_has_not_come_is_not_today(meter, api) -> None:
    await publish(meter, f"{METER}.net_worth", "level", "EUR", 0, 30000)
    goal = (
        await api.post(
            "/goals",
            json={
                "title": "Patrimonio el año que viene",
                "kind": "dated",
                "target": 60000,
                "metric_key": f"{METER}.net_worth",
                "start_on": (today() + timedelta(days=30)).isoformat(),
                "due_on": (today() + timedelta(days=400)).isoformat(),
            },
        )
    ).json()
    assert goal["start_value"] is None


async def test_a_figure_that_starts_after_the_goal_does_not_lend_today(meter, api) -> None:
    for days_ago, value in ((5, 100), (0, 120)):
        await publish(meter, f"{METER}.weight", "level", "kg", days_ago, value)
    goal = (
        await api.post(
            "/goals",
            json={
                "title": "Peso",
                "kind": "dated",
                "direction": "at_most",
                "target": 90,
                "metric_key": f"{METER}.weight",
                "start_on": (today() - timedelta(days=30)).isoformat(),
                "due_on": (today() + timedelta(days=60)).isoformat(),
            },
        )
    ).json()
    assert goal["start_value"] is None and goal["start"] == 100


async def test_every_goal_figure_comes_in_one_query(meter, api, monkeypatch) -> None:
    from goals import metrics

    figures = ("steps", "sleep", "water", "net_worth")
    for name in figures:
        key = f"{METER}.{name}"
        await publish(meter, key, "amount", "count", 40, 1)
        await publish(meter, key, "amount", "count", 0, 5)
        made = await api.post(
            "/goals",
            json={
                "title": name,
                "kind": "periodic",
                "period": "day",
                "target": 3,
                "metric_key": key,
                "start_on": (today() - timedelta(days=10)).isoformat(),
            },
        )
        assert made.status_code == 201, made.text

    asked: list[str] = []
    real = metrics.series_many

    async def counted(connection, since_by_key):
        if since_by_key:
            asked.append(",".join(sorted(since_by_key)))
        return await real(connection, since_by_key)

    async def one_by_one(*_args, **_kwargs):
        raise AssertionError("una consulta por cifra")

    monkeypatch.setattr(metrics, "series_many", counted)
    monkeypatch.setattr(metrics, "series", one_by_one)
    listed = (await api.get("/goals")).json()

    assert len(asked) == 1 and asked[0].count(",") == len(figures) - 1
    assert all(goal["today_met"] for goal in listed if goal["title"] in figures)
