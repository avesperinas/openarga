from __future__ import annotations

from datetime import UTC, date, datetime

from insights_world import insight, weekly
from sqlalchemy import text

from arga_contracts import records as fichas
from insights import records
from insights.db import engine

WRITE = {"x-arga-scopes": "insights:read insights:write"}


async def publish(api, arguments: dict) -> str:
    response = await api.post("/tools/publish_insight", json=arguments, headers=WRITE)
    assert response.status_code == 200, response.text
    return response.json()["content"]["published"]["insight_id"]


async def queued(schema) -> list[dict]:
    async with engine().begin() as connection:
        await connection.execute(text('set local role "mod_insights"'))
        await fichas.publish(connection, "insights", await records.build(connection))
    async with schema.connect() as connection:
        rows = await connection.execute(
            text(
                "select payload from insights.insights_outbox where type = 'insights.record' order by id"
            )
        )
        return [row.payload["record"] for row in rows]


def test_the_summary_is_of_its_week_and_one_on_monday_is_of_the_one_before() -> None:
    sunday = datetime(2026, 10, 25, 17, tzinfo=UTC)
    monday = datetime(2026, 10, 26, 9, tzinfo=UTC)
    wednesday = datetime(2026, 10, 28, 9, tzinfo=UTC)

    assert records.week_of(sunday) == date(2026, 10, 19)
    assert records.week_of(monday) == date(2026, 10, 19)
    assert records.week_of(wednesday) == date(2026, 10, 26)
    assert records.week_key(date(2026, 10, 19)) == "2026-W43"


async def test_the_weekly_summary_is_published_as_a_record_and_an_alert_is_not(api, schema) -> None:
    await publish(api, insight())
    summary = await publish(api, weekly(3))

    (found,) = await queued(schema)

    monday = records.week_of(datetime.now(UTC))
    key = records.week_key(monday)
    assert found["id"] == f"semana-{key}"
    assert found["kind"] == "Resumen de la semana"
    assert found["folder"] == "Semanas"
    assert found["href"] == f"/insights/consejo/{summary}"
    assert found["properties"] == {"semana": key, "propuestas": 3}
    assert "## Propuestas para la semana que viene" in found["body"]
    assert "\n3. " in found["body"]


async def test_a_second_summary_of_the_same_week_replaces_the_first(api, schema) -> None:
    await publish(api, weekly(3))
    await queued(schema)
    second = await publish(api, weekly(4))

    published = await queued(schema)

    assert len(published) == 2
    assert published[0]["id"] == published[1]["id"]
    assert published[1]["href"] == f"/insights/consejo/{second}"
    assert published[1]["properties"]["propuestas"] == 4
