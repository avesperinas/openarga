from __future__ import annotations

from datetime import date, timedelta
from uuid import UUID

from goals_people import PERSON
from sqlalchemy import text

from arga_tenancy import as_user
from goals.common import today
from goals.progress import monday

ANA = UUID("0a0a0a0a-0000-4000-8000-00000000a0a1")
LUIS = UUID("0b0b0b0b-0000-4000-8000-00000000b0b1")
SPACE = UUID("5a5a5a5a-0000-4000-8000-00000000c0c1")


def day(offset: int) -> str:
    return (today() + timedelta(days=offset)).isoformat()


async def categories(api) -> dict[str, str]:
    return {one["name"]: one["id"] for one in (await api.get("/categories")).json()}


async def new_goal(api, **body) -> dict:
    response = await api.post("/goals", json=body)
    assert response.status_code == 201, response.text
    return response.json()


async def test_reading_five_days_a_week_is_marked_and_shows_its_streak(api) -> None:
    mine = await categories(api)
    start = monday(today()) - timedelta(days=14)
    goal = await new_goal(
        api,
        title="Leer 20 minutos",
        kind="periodic",
        period="day",
        days_per_week=5,
        category_id=mine["Aprender"],
        start_on=start.isoformat(),
    )
    assert goal["category"] == "Aprender" and goal["streak_unit"] == "weeks"

    for week in (1, 2):
        first = monday(today()) - timedelta(days=7 * week)
        for offset in range(5):
            marked = await api.post(
                f"/goals/{goal['id']}/checks",
                json={"day": (first + timedelta(days=offset)).isoformat(), "done": True},
            )
            assert marked.status_code == 200, marked.text

    today_marked = (await api.post(f"/goals/{goal['id']}/checks", json={"done": True})).json()
    assert today_marked["today_met"] is True and today_marked["today_manual"] is True
    assert today_marked["streak"] == 2
    assert today_marked["constancy"] == 1.0

    undone = (await api.delete(f"/goals/{goal['id']}/checks/{day(0)}")).json()
    assert undone["today_met"] is False

    listed = (await api.get("/goals")).json()
    assert [one["title"] for one in listed] == ["Leer 20 minutos"]
    assert (await api.get("/categories")).json()[5]["goals"] == 1


async def test_a_dated_goal_that_ended_yesterday_is_missed_in_the_history(api) -> None:
    goal = await new_goal(
        api,
        title="Correr 10 km en 50 minutos",
        kind="dated",
        direction="at_most",
        start_value=58,
        target=50,
        start_on=day(-60),
        due_on=day(-1),
    )
    assert (await api.get("/goals")).json() == []
    closed = (await api.get("/goals?state=closed")).json()
    assert [(one["title"], one["status"], one["closed_on"]) for one in closed] == [
        ("Correr 10 km en 50 minutos", "missed", day(-1))
    ]
    assert closed[0]["id"] == goal["id"]

    kinds = await _outbox(api)
    assert [payload["what"] for payload in kinds] == ["created", "missed"]


async def _outbox(api) -> list[dict]:
    from goals.db import engine

    async with engine().begin() as connection:
        rows = await connection.execute(
            text("select payload from goals.goals_outbox where type = 'goals.goal' order by id")
        )
        return [row.payload for row in rows]


async def test_a_manual_value_that_reaches_the_target_closes_it(api) -> None:
    goal = await new_goal(
        api,
        title="Ahorrar 3.000 €",
        kind="dated",
        start_value=0,
        target=3000,
        start_on=day(-30),
        due_on=day(60),
    )
    halfway = (await api.post(f"/goals/{goal['id']}/checks", json={"value": 1500})).json()
    assert halfway["current"] == 1500 and halfway["pace"] == "ahead"
    assert halfway["status"] == "active"

    done = (await api.post(f"/goals/{goal['id']}/checks", json={"value": 3100})).json()
    assert done["status"] == "achieved" and done["closed_value"] == 3100


async def test_a_milestone_is_ticked_done_and_can_be_reopened(api) -> None:
    goal = await new_goal(
        api, title="El B2 de alemán", kind="dated", start_on=day(-10), due_on=day(200)
    )
    assert goal["reached"] is False
    done = (await api.post(f"/goals/{goal['id']}/checks", json={"done": True})).json()
    assert done["status"] == "achieved"
    back = (await api.post(f"/goals/{goal['id']}/reopen")).json()
    assert back["status"] == "active"
    gone = await api.post(f"/goals/{goal['id']}/close", json={"outcome": "abandoned"})
    assert gone.json()["status"] == "abandoned"


async def test_the_shape_is_explained_when_wrong(api) -> None:
    periodic_with_date = await api.post(
        "/goals", json={"title": "Algo", "kind": "periodic", "period": "day", "due_on": day(3)}
    )
    assert periodic_with_date.status_code == 409
    dated_without_date = await api.post("/goals", json={"title": "Algo", "kind": "dated"})
    assert "fecha límite" in dated_without_date.json()["detail"]
    weekly_without_total = await api.post(
        "/goals", json={"title": "Algo", "kind": "periodic", "period": "week"}
    )
    assert weekly_without_total.status_code == 409
    unknown_metric = await api.post(
        "/goals",
        json={
            "title": "Pasos",
            "kind": "periodic",
            "period": "day",
            "target": 8000,
            "metric_key": "nadie.steps",
        },
    )
    assert unknown_metric.status_code == 404


async def test_edit_order_feature_and_delete(api) -> None:
    first = await new_goal(api, title="Meditar", kind="periodic", period="day")
    second = await new_goal(
        api, title="Gimnasio", kind="periodic", period="day", days_per_week=3, featured=True
    )
    assert first["days_per_week"] == 7

    changed = await api.put(
        f"/goals/{first['id']}", json={"title": "Meditar 10 minutos", "featured": True}
    )
    assert changed.json()["featured"] is True
    goals = {one["title"]: one for one in (await api.get("/goals")).json()}
    assert goals["Gimnasio"]["featured"] is False

    ordered = await api.post("/goals/order", json={"ids": [second["id"], first["id"]]})
    assert [one["title"] for one in ordered.json()] == ["Gimnasio", "Meditar 10 minutos"]

    assert (await api.delete(f"/goals/{first['id']}")).status_code == 204
    assert (await api.get(f"/goals/{first['id']}")).status_code == 404


async def test_the_detail_has_one_point_per_day_for_a_periodic(api) -> None:
    goal = await new_goal(api, title="Beber agua", kind="periodic", period="day", start_on=day(-3))
    await api.post(
        f"/goals/{goal['id']}/checks", json={"day": day(-2), "done": True, "note": "2 l"}
    )
    found = (await api.get(f"/goals/{goal['id']}")).json()
    assert [(point["day"], point["met"]) for point in found["history"]] == [
        (day(-3), False),
        (day(-2), True),
        (day(-1), False),
        (day(0), False),
    ]
    assert found["history"][1]["note"] == "2 l"


async def test_deleting_a_category_leaves_its_goals_without_one(api) -> None:
    mine = await categories(api)
    goal = await new_goal(
        api, title="Estirar", kind="periodic", period="day", category_id=mine["Deporte"]
    )
    assert (await api.delete(f"/categories/{mine['Deporte']}")).status_code == 204
    found = (await api.get(f"/goals/{goal['id']}")).json()["goal"]
    assert found["category_id"] is None and found["title"] == "Estirar"


async def test_someone_who_used_goals_before_gets_the_goal_categories_once(schema, api) -> None:
    with as_user(PERSON):
        async with schema.begin() as connection:
            await connection.execute(text('set local role "mod_goals"'))
            await connection.execute(text("insert into goals.goals_person default values"))
            await connection.execute(
                text("insert into goals.goals_category (name, hue) values ('Salud', 2)")
            )
    names = list(await categories(api))
    assert names == ["Salud", "Dinero", "Aprender", "Deporte"]
    for category_id in (await categories(api)).values():
        await api.delete(f"/categories/{category_id}")
    assert await categories(api) == {}


async def test_a_goal_in_a_shared_category_is_only_its_owners(schema) -> None:
    async def run(person: UUID, statement: str, **params):
        with as_user(person, spaces=(SPACE,)):
            async with schema.begin() as connection:
                await connection.execute(text('set local role "mod_goals"'))
                result = await connection.execute(text(statement), params)
                return result.all() if result.returns_rows else None

    await run(
        ANA,
        "insert into goals.goals_category (name, hue, space_id) values ('Casa', 2, :s)",
        s=SPACE,
    )
    shared = (await run(LUIS, "select id from goals.goals_category"))[0].id
    await run(
        ANA,
        "insert into goals.goals_goal "
        "(category_id, title, kind, period, days_per_week, start_on) "
        "values (:c, 'Ordenar cada día', 'periodic', 'day', 7, current_date)",
        c=shared,
    )
    assert [row.title for row in await run(ANA, "select title from goals.goals_goal")] == [
        "Ordenar cada día"
    ]
    assert await run(LUIS, "select title from goals.goals_goal") == []
    goal_id = (await run(ANA, "select id from goals.goals_goal"))[0].id
    await run(
        LUIS,
        "insert into goals.goals_goal_check (goal_id, day, done) values (:g, current_date, true)",
        g=goal_id,
    )
    assert await run(ANA, "select 1 from goals.goals_goal_check") == []


async def test_the_old_date(api) -> None:
    goal = await new_goal(
        api, title="Leer 12 libros", kind="dated", target=12, start_on=day(-5), due_on=day(100)
    )
    future = await api.post(f"/goals/{goal['id']}/checks", json={"day": day(1), "value": 1})
    assert future.status_code == 409
    before = await api.post(
        f"/goals/{goal['id']}/checks", json={"day": date(2000, 1, 1).isoformat(), "value": 1}
    )
    assert before.status_code == 409


async def test_goals_of_today_are_ticked_from_the_desktop(api) -> None:
    empty = (await api.get("/widgets/goals_today")).json()
    assert empty["state"] == "empty"
    goal = await new_goal(api, title="Meditar", kind="periodic", period="day")

    card = (await api.get("/widgets/goals_today")).json()
    assert card["body"]["checkable"] is True
    assert [(one["title"], one["done"]) for one in card["body"]["tasks"]] == [("Meditar", False)]

    ticked = await api.post("/widgets/goals_today/act", json={"verb": "complete", "id": goal["id"]})
    assert ticked.json()["body"]["tasks"][0]["done"] is True
    assert (await api.get(f"/goals/{goal['id']}")).json()["goal"]["today_met"] is True

    back = await api.post("/widgets/goals_today/act", json={"verb": "reopen", "id": goal["id"]})
    assert back.json()["body"]["tasks"][0]["done"] is False
    refused = await api.post("/widgets/goal/act", json={"verb": "complete", "id": goal["id"]})
    assert refused.status_code == 404


async def test_dated_goals_and_the_featured_one_on_the_desktop(api) -> None:
    goal = await new_goal(
        api,
        title="Ahorrar 3.000 €",
        kind="dated",
        start_value=0,
        target=3000,
        start_on=day(-30),
        due_on=day(30),
        featured=True,
    )
    await api.post(f"/goals/{goal['id']}/checks", json={"value": 900})
    listed = (await api.get("/widgets/goals")).json()
    assert listed["body"]["rows"] == [
        {"label": "Ahorrar 3.000 €", "value": "900 · por detrás", "tone": "negative"}
    ]
    shown = (await api.get("/widgets/goal")).json()
    assert shown["state"] == "ready"
    assert shown["body"]["value"] == 900 and shown["body"]["target"] == 3000
    assert shown["body"]["expected"] == 1500


async def test_a_goal_from_before_kpis_lands_closed_in_the_history(api) -> None:
    created = await api.post(
        "/goals/past",
        json={
            "title": "Media maratón por debajo de 1:50",
            "start_on": "2024-01-01",
            "due_on": "2024-12-31",
            "outcome": "achieved",
            "closed_on": "2024-10-20",
            "target": 110,
            "closed_value": 108,
            "direction": "at_most",
            "note": "De los objetivos de 2024.",
        },
    )
    assert created.status_code == 201, created.text
    goal = created.json()
    assert (goal["status"], goal["closed_on"], goal["closed_value"]) == (
        "achieved",
        "2024-10-20",
        108,
    )

    active = (await api.get("/goals")).json()
    closed = (await api.get("/goals", params={"state": "closed"})).json()
    assert goal["id"] not in [one["id"] for one in active]
    assert goal["id"] in [one["id"] for one in closed]

    future = await api.post(
        "/goals/past",
        json={
            "title": "Aún no ha pasado",
            "start_on": "2026-01-01",
            "due_on": "2999-12-31",
            "outcome": "missed",
        },
    )
    assert future.status_code == 409
    assert "sigue abierta" in future.json()["detail"]
