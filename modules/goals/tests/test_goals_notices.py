from __future__ import annotations

from datetime import timedelta

from sqlalchemy import text
from test_goals_goals import categories, new_goal

from goals import notices
from goals.common import today


def sunday():
    return today() + timedelta(days=6 - today().weekday())


async def build(schema) -> list[dict]:
    async with schema.begin() as connection:
        await connection.execute(text('set local role "mod_goals"'))
        return await notices.build(connection)


async def test_on_sunday_the_goals_that_do_not_make_it_are_said(api, schema, monkeypatch) -> None:
    mine = await categories(api)
    await new_goal(
        api,
        title="Leer 20 minutos",
        kind="periodic",
        period="day",
        days_per_week=7,
        category_id=mine["Aprender"],
        start_on=(today() - timedelta(days=today().weekday())).isoformat(),
    )
    monkeypatch.setattr(notices, "today", sunday)

    [one] = await build(schema)

    year, week, _ = sunday().isocalendar()
    assert one["kind"] == "goals_at_risk"
    assert one["key"] == f"week:{year}-W{week:02d}"
    assert one["title"] == "«Leer 20 minutos» no llega esta semana"
    assert one["body"].startswith("Leer 20 minutos: 0 de 7")
    assert one["at"].startswith(f"{sunday().isoformat()}T18:00")


async def test_any_other_day_says_nothing(api, schema, monkeypatch) -> None:
    monkeypatch.setattr(notices, "today", lambda: sunday() - timedelta(days=1))

    assert await build(schema) == []
