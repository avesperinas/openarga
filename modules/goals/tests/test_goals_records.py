from __future__ import annotations

from datetime import date

from sqlalchemy import text
from test_goals_goals import categories, day, new_goal

import arga_contracts as contracts
from arga_tenancy import current_user
from goals import records
from goals.common import today
from goals.db import engine


async def built() -> dict[str, dict]:
    async with engine().begin() as connection:
        await connection.execute(text('set local role "mod_goals"'))
        found = await records.build(connection)
    for one in found:
        assert one == contracts.record(**one)
    return {one["id"]: one for one in found}


async def test_goals_what_is_pending_and_what_was_done_each_day(api) -> None:
    mine = await categories(api)
    goal = await new_goal(
        api,
        title="Leer 20 minutos",
        kind="periodic",
        period="day",
        days_per_week=5,
        category_id=mine["Aprender"],
        start_on=day(-3),
    )
    await api.post(f"/goals/{goal['id']}/checks", json={"day": day(-1), "done": True})
    pending = (
        await api.post(
            "/tasks", json={"category_id": mine["Casa"], "title": "Regar", "due_on": day(2)}
        )
    ).json()
    done = (await api.post("/tasks", json={"category_id": mine["Casa"], "title": "Tender"})).json()
    await api.post(f"/tasks/{done['id']}/done")

    found = await built()

    ficha = found[f"goal:{goal['id']}"]
    assert ficha["title"] == "Leer 20 minutos" and ficha["folder"] == "Metas"
    assert ficha["href"] == f"/goals/meta/{goal['id']}"
    assert ficha["properties"]["estado"] == "activa"
    assert ficha["properties"]["clase"] == "periódica"
    assert ficha["properties"]["categoria"] == "Aprender"
    assert ficha["body"].startswith("5 días a la semana")
    assert f"| {day(-1)} |  | sí |" in ficha["body"]

    todo = found["pending"]
    assert f"- [ ] Regar · {day(2)}" in todo["body"]
    assert todo["properties"]["pendientes"] >= 1
    assert pending["id"]

    today_ = found[f"day:{today().isoformat()}"]
    assert today_["properties"] == {"tareas_hechas": 1}
    assert today_["body"] == "- [x] Tender · Casa"


async def test_the_worker_rebuilds_them_on_every_pass_not_only_the_first(
    schema, monkeypatch
) -> None:
    from types import SimpleNamespace

    import httpx

    from goals import publisher

    person = current_user.get()
    rebuilt = []

    async def refresh(client, engine, app, build, every, user):
        rebuilt.append((app, user))

    async def users(client):
        return [person]

    async def pending(connection, client):
        return {"published": 0, "pending": 0}

    from arga_module import publisher as kit

    monkeypatch.setattr(publisher, "fichas", SimpleNamespace(refresh=refresh))
    monkeypatch.setattr(kit, "users", users)
    monkeypatch.setattr(publisher.PUBLISHER, "publish_pending", pending)
    async with httpx.AsyncClient() as client:
        await publisher.run_once(client)
        await publisher.run_once(client)

    assert rebuilt == [("goals", person), ("goals", person)]


def test_a_goal_behind_says_so_and_what_was_expected() -> None:
    from goals import goals as goals_

    base = {name: None for name in goals_.Goal.model_fields}
    one = goals_.Goal.model_construct(
        **{
            **base,
            "id": "g1",
            "title": "Colesterol por debajo de 200",
            "kind": "dated",
            "status": "active",
            "start_on": date(2026, 1, 1),
            "due_on": date(2026, 12, 31),
            "target": 200.0,
            "current": 255.0,
            "expected": 221.4567,
            "pace": "behind",
            "week": [],
            "featured": False,
            "position": 0,
            "today_manual": False,
        }
    )

    found = records.goal(goals_.GoalDetail.model_construct(goal=one, history=[]))

    assert found["properties"]["ritmo"] == "por detrás"
    assert found["properties"]["esperado"] == 221.46
    assert found["properties"]["actual"] == 255.0
