from __future__ import annotations

import pytest

from arga_widgets import validate
from vitals.widgets import KINDS

WRITE = {"x-arga-scopes": "vitals:write"}


@pytest.mark.parametrize("widget", sorted(KINDS))
async def test_with_nothing_each_widget_is_empty_and_says_why(api, widget: str) -> None:
    found = (await api.get(f"/widgets/{widget}")).json()

    assert found["state"] == "empty"
    assert found["body"]["detail"]


async def test_the_ldl_card_compares_with_the_previous_checkup(api) -> None:
    for day, value in (("2025-06-11", 118), ("2026-09-02", 151)):
        created = await api.post("/checkups", json={"day": day})
        await api.post(
            f"/checkups/{created.json()['id']}/results",
            json={"analyte": "ldl", "value": value, "unit": "mg/dL", "ref_high": 130},
        )

    found = (await api.get("/widgets/ldl")).json()

    assert found["state"] == "ready"
    validate("kpi-delta", found["body"])
    assert found["body"]["value"] == 151
    assert found["body"]["previous"] == 118
    assert found["body"]["good_when"] == "down"
    assert "fuera" in found["body"]["detail"]


async def test_the_weight_card_knows_which_way_is_good(api) -> None:
    await api.put("/goals", json={"weight_max_kg": 76})
    await api.post("/weight", json={"kg": 80, "day": "2026-08-01"})
    await api.post("/weight", json={"kg": 78, "day": "2026-08-31"})

    found = (await api.get("/widgets/weight")).json()

    assert found["state"] == "ready"
    assert found["body"]["previous"] == 80
    assert found["body"]["good_when"] == "down"


async def test_the_way_asked_for_wins_over_the_band(api) -> None:
    await api.put("/goals", json={"weight_max_kg": 76, "weight_direction": "up"})
    await api.post("/weight", json={"kg": 80, "day": "2026-08-01"})
    await api.post("/weight", json={"kg": 78, "day": "2026-08-31"})

    found = (await api.get("/widgets/weight")).json()

    assert found["body"]["good_when"] == "up"


async def test_a_widget_it_does_not_have_is_a_404(api) -> None:
    assert (await api.get("/widgets/inventado")).status_code == 404


async def test_the_weight_card_shows_the_last_weighing_when_weighing_is_rare(api) -> None:
    await api.post("/weight", json={"kg": 76.5, "day": "2026-08-08"})
    await api.post("/weight", json={"kg": 76.9, "day": "2026-09-09"})
    await api.post("/weight", json={"kg": 76.6, "day": "2026-09-24"})

    found = (await api.get("/widgets/weight")).json()

    assert found["state"] == "ready"
    validate("kpi-delta", found["body"])
    assert found["body"]["value"] == 76.6
    assert found["body"]["previous"] == 76.5
    assert found["body"]["since"] == "desde el 08/08/2026"
    assert found["body"]["detail"] == "pesada del 24/09"


async def test_the_weight_card_averages_the_last_week_of_weighings(api) -> None:
    await api.post("/weight", json={"kg": 77, "day": "2026-09-20"})
    await api.post("/weight", json={"kg": 76, "day": "2026-09-24"})

    found = (await api.get("/widgets/weight")).json()

    assert found["state"] == "ready"
    assert found["body"]["value"] == 76.5
    assert found["body"]["previous"] == 77
    assert found["body"]["detail"] == "media de 2 pesadas hasta el 24/09"


async def test_a_single_weighing_is_enough_for_the_weight_card(api) -> None:
    await api.post("/weight", json={"kg": 76.6, "day": "2026-09-24"})

    found = (await api.get("/widgets/weight")).json()

    assert found["state"] == "ready"
    assert found["body"]["previous"] == 76.6
    assert found["body"]["since"] == "sin pesadas anteriores"


def _day(text_: str, count: int):
    from datetime import date

    from vitals import steps

    return steps.StepsDay(day=date.fromisoformat(text_), steps=count)


def test_the_steps_card_falls_back_to_the_last_day_and_says_which() -> None:
    from datetime import date

    from vitals.widgets import last_steps

    today = date(2026, 9, 28)
    days = [_day("2026-09-24", 9000), _day("2026-09-27", 6400)]

    assert last_steps(days, today) == (days[1], "de ayer")
    assert last_steps(days[:1], today) == (days[0], "del jueves 24")
    assert last_steps([_day("2026-09-12", 5000)], today)[1] == "del 12 de septiembre"
    assert last_steps([*days, _day("2026-09-28", 1200)], today)[1] is None
    assert last_steps([], today) is None
    assert last_steps([_day("2026-09-29", 300), days[1]], today) == (days[1], "de ayer")


async def test_the_steps_card_shows_the_last_day_when_today_has_none(api, schema, person) -> None:
    import json
    from datetime import datetime, timedelta

    from sqlalchemy import text

    from vitals import steps

    await api.put("/goals", json={"steps_per_day": 8000})
    yesterday = steps.today() - timedelta(days=1)
    async with schema.begin() as connection:
        await connection.execute(
            text("""
                insert into kernel.events
                    (ts, ingested_at, module, source, type, payload, dedup_hash, user_id)
                values (:ts, now(), 'hub', 'apple_health', 'health.steps',
                        cast(:payload as jsonb), :dedup, :user)
            """),
            {
                "ts": datetime.fromisoformat(f"{yesterday}T20:00:00+00:00"),
                "payload": json.dumps({"date": yesterday.isoformat(), "steps": 6400}),
                "dedup": f"widget-steps:{yesterday}",
                "user": person,
            },
        )
    try:
        found = (await api.get("/widgets/steps_today")).json()
    finally:
        async with schema.begin() as connection:
            await connection.execute(
                text("delete from kernel.events where dedup_hash like 'widget-steps:%'")
            )

    assert found["state"] == "ready"
    validate("ring", found["body"])
    assert found["body"]["value"] == 6400
    assert found["body"]["target"] == 8000
    assert found["body"]["label"] == "de ayer"
    assert "unit" not in found["body"]


async def test_the_week_card_has_seven_days_ending_today(api, schema, person) -> None:
    import json
    from datetime import datetime, timedelta

    from sqlalchemy import text

    from vitals import steps

    await api.put("/goals", json={"steps_per_day": 8000})
    today = steps.today()
    counts = {today - timedelta(days=1): 9000, today - timedelta(days=3): 5000}
    async with schema.begin() as connection:
        for day, count in counts.items():
            await connection.execute(
                text("""
                    insert into kernel.events
                        (ts, ingested_at, module, source, type, payload, dedup_hash, user_id)
                    values (:ts, now(), 'hub', 'apple_health', 'health.steps',
                            cast(:payload as jsonb), :dedup, :user)
                """),
                {
                    "ts": datetime.fromisoformat(f"{day}T20:00:00+00:00"),
                    "payload": json.dumps({"date": day.isoformat(), "steps": count}),
                    "dedup": f"widget-week:{day}",
                    "user": person,
                },
            )
    try:
        found = (await api.get("/widgets/steps_week")).json()
    finally:
        async with schema.begin() as connection:
            await connection.execute(
                text("delete from kernel.events where dedup_hash like 'widget-week:%'")
            )

    assert found["state"] == "ready"
    validate(KINDS["steps_week"], found["body"])
    assert found["body"]["series"] == [0, 0, 0, 5000, 0, 9000, 0]
    assert found["body"]["highlight"] == 6
    assert found["body"]["labels"][-1] == "LMXJVSD"[today.weekday()]
    assert found["body"]["value"] == 7000
    assert found["body"]["detail"] == "media diaria · objetivo cumplido 1 de 7"


async def test_the_weight_card_draws_the_last_three_months(api) -> None:
    for day, kg in (("2026-05-01", 82), ("2026-07-10", 80), ("2026-08-20", 79), ("2026-09-20", 78)):
        await api.post("/weight", json={"kg": kg, "day": day})

    body = (await api.get("/widgets/weight")).json()["body"]

    assert len(body["series"]) >= 2
    assert body["series"][-1] == body["value"]
    assert max(body["series"]) < 82
