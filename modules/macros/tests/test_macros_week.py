from __future__ import annotations

import json
from datetime import timedelta

import pytest
from sqlalchemy import text

from arga_widgets import validate
from macros.common import now, today


async def log(api, food_id: str, grams: float, days_ago: int = 0) -> dict:
    moment = (now() - timedelta(days=days_ago)).replace(microsecond=0).isoformat()
    response = await api.post(
        "/entries",
        json={"eaten_at": moment, "items": [{"food_id": food_id, "quantity": grams, "unit": "g"}]},
    )
    assert response.status_code == 201, response.text
    return response.json()


async def test_a_branded_product_without_micros_dims_vitamin_d_and_sodium_goes_red(
    api, world
) -> None:
    milk = await world.imported("milk", alias="semi milk")
    found = (await api.get("/search", params={"q": "biscuits"})).json()
    [cookies] = found["candidates"]
    await log(api, milk["id"], 250)
    for days_ago in range(3):
        await api.post(
            "/entries",
            json={
                "eaten_at": (now() - timedelta(days=days_ago)).replace(microsecond=0).isoformat(),
                "items": [
                    {
                        "source": cookies["source"],
                        "source_ref": cookies["source_ref"],
                        "quantity": 300,
                    }
                ],
            },
        )

    week = (await api.get("/week")).json()
    micros = {micro["key"]: micro for micro in week["micros"]}

    assert micros["vitamin_d"]["partial"] is True
    assert "Branded biscuits" in micros["vitamin_d"]["missing"]
    assert micros["vitamin_d"]["coverage"] < 0.8
    assert micros["sodium"]["status"] == "high"
    assert micros["sodium"]["partial"] is False
    assert week["days_logged"] == 3
    assert week["profile"]["from_health"] is False


async def test_references_follow_the_health_profile_and_your_own(api, world, schema) -> None:
    from arga_tenancy import current_user

    person = current_user.get()
    async with schema.begin() as connection:
        await connection.execute(
            text(
                "insert into kernel.events (ts, module, source, type, payload, dedup_hash, user_id)"
                " values (now(), 'hub', 'test', 'health.profile', cast(:p as jsonb),"
                " :d, :u)"
            ),
            {
                "p": json.dumps({"sex": "female", "birth_date": "1994-05-01"}),
                "d": f"macros-test-profile:{person}",
                "u": str(person),
            },
        )
    try:
        found = (await api.get("/references")).json()
        refs = {one["nutrient"]: one for one in found["references"]}
        assert found["profile"]["sex"] == "female"
        assert refs["iron"]["value"] == 16

        assert (
            await api.put("/references/caffeine", json={"kind": "max", "value": 200})
        ).status_code == 204
        refs = {one["nutrient"]: one for one in (await api.get("/references")).json()["references"]}
        assert (refs["caffeine"]["value"], refs["caffeine"]["own"]) == (200, True)
        assert (await api.delete("/references/caffeine")).status_code == 204
        assert (
            await api.put("/references/unobtainium", json={"kind": "max", "value": 1})
        ).status_code == 409
    finally:
        async with schema.begin() as connection:
            await connection.execute(
                text("delete from kernel.events where source = 'test' and type = 'health.profile'")
            )


async def test_days_over_and_under_the_target(api, world) -> None:
    rice = await world.manual_food("Arroz", {"kcal": 100, "protein": 2, "fat": 0, "carbs": 20})
    await api.put(
        "/target", json={"kcal": 2000, "valid_from": (today() - timedelta(days=7)).isoformat()}
    )
    await log(api, rice, 2500, days_ago=2)
    await log(api, rice, 1000, days_ago=1)
    await log(api, rice, 2050)

    marks = {
        mark["day"]: mark["against_target"] for mark in (await api.get("/week")).json()["days"]
    }

    assert marks[(today() - timedelta(days=2)).isoformat()] == "over"
    assert marks[(today() - timedelta(days=1)).isoformat()] == "under"
    assert marks[today().isoformat()] == "on"
    assert marks[(today() - timedelta(days=3)).isoformat()] == "none"


async def metric_points(schema) -> list[dict]:
    async with schema.connect() as connection:
        rows = (
            await connection.execute(
                text(
                    "select payload from macros.macros_outbox"
                    " where type = 'macros.metric' order by id"
                )
            )
        ).all()
    return [row.payload["metric"] for row in rows]


async def test_each_day_publishes_its_figures_and_only_what_changed(api, world, schema) -> None:
    lentils = await world.imported("lentils", alias="dry lentils")
    entry = await log(api, lentils["id"], 100)

    first = {point["key"]: point for point in await metric_points(schema)}
    assert first["macros.protein"]["value"] == pytest.approx(24.6)
    assert first["macros.protein"]["kind"] == "amount"
    assert first["macros.iron"]["unit"] == "mg"
    assert "macros.vitamin_d" not in first

    rice = await world.manual_food("Arroz", {"kcal": 130, "protein": 0, "fat": 0, "carbs": 28})
    await log(api, rice, 100)
    second = (await metric_points(schema))[len(first) :]
    assert {point["key"] for point in second} == {"macros.kcal", "macros.carbs"}

    await api.delete(f"/entries/{entry['id']}")
    last = {point["key"]: point for point in await metric_points(schema)}
    assert last["macros.iron"]["value"] == 0
    assert last["macros.kcal"]["value"] == 130


async def test_the_widgets_answer_their_kind(api, world) -> None:
    empty = (await api.get("/widgets/today")).json()
    assert empty["state"] == "empty"
    rice = await world.manual_food("Arroz", {"kcal": 130, "protein": 2.7, "fat": 0.3, "carbs": 28})
    await log(api, rice, 200)
    no_target = (await api.get("/widgets/today")).json()
    unknown = (await api.get("/widgets/week_short")).json()
    assert (unknown["state"], unknown["body"]["detail"]) == (
        "empty",
        "What you logged has no micronutrients",
    )
    milk = await world.imported("milk", alias="semi milk")
    await log(api, milk["id"], 200)
    assert "goal" in no_target["body"]["detail"]

    await api.put("/target", json={"kcal": 2000, "protein": 140})
    ring = (await api.get("/widgets/today")).json()
    stats = (await api.get("/widgets/macros_today")).json()
    week = (await api.get("/widgets/week_short")).json()

    assert (ring["state"], ring["body"]["value"], ring["body"]["target"]) == ("ready", 360, 2000)
    assert [one["label"] for one in stats["body"]["stats"]] == ["Protein", "Carbs", "Fat"]
    assert week["state"] == "ready"
    rows = {row["label"]: row for row in week["body"]["rows"]}
    assert rows["Vitamin D"]["value"] == "16 % · data missing"
    for kind, answer in (("ring", ring), ("stats", stats), ("list", week)):
        validate(kind, answer["body"], answer["state"])


async def test_the_week_counts_only_complete_days_when_there_are_enough(api, world) -> None:
    milk = await world.imported("milk", alias="semi milk")
    for days_ago in (1, 2, 3):
        await log(api, milk["id"], 500, days_ago=days_ago)
        day = (today() - timedelta(days=days_ago)).isoformat()
        assert (await api.put(f"/day-complete/{day}", json={"complete": True})).status_code == 200
    await log(api, milk["id"], 50)

    week = (await api.get("/week")).json()
    assert week["counted"] == {"days": 3, "complete": True}
    every = (await api.get("/week", params={"only_complete": False})).json()
    assert every["counted"]["complete"] is False
    assert every["days_logged"] == 4
    assert week["averages"]["kcal"] > every["averages"]["kcal"]


async def test_with_few_complete_days_the_week_counts_what_has_something(api, world) -> None:
    milk = await world.imported("milk", alias="semi milk")
    await log(api, milk["id"], 500, days_ago=1)
    await log(api, milk["id"], 500, days_ago=2)
    week = (await api.get("/week")).json()
    assert week["counted"] == {"days": 2, "complete": False}


async def test_the_trend_has_each_day_and_a_share_per_week(api, world) -> None:
    milk = await world.imported("milk", alias="semi milk")
    for days_ago in (1, 2, 3):
        await log(api, milk["id"], 500, days_ago=days_ago)
        day = (today() - timedelta(days=days_ago)).isoformat()
        await api.put(f"/day-complete/{day}", json={"complete": True})
    trend = (await api.get("/week/trend", params={"weeks": 2})).json()
    assert len(trend["days"]) == 14
    assert len(trend["weeks"]) == 2
    assert trend["days"][-1]["day"] == today().isoformat()
    assert [one["complete"] for one in trend["days"][-4:]] == [True, True, True, False]
    calcium = trend["nutrients"]["calcium"]
    assert calcium[0] is None
    assert calcium[1] is not None and calcium[1] > 0


async def test_suggestions_come_from_what_you_eat_more_than_once(api, world) -> None:
    milk = await world.imported("milk", alias="semi milk")
    for days_ago in (1, 2, 3):
        await log(api, milk["id"], 150, days_ago=days_ago)
        day = (today() - timedelta(days=days_ago)).isoformat()
        await api.put(f"/day-complete/{day}", json={"complete": True})
    found = (await api.get("/week/suggestions")).json()
    assert found["window"]["days"] == 3
    for nutrient in found["nutrients"]:
        assert nutrient["share"] < 0.9
        for food in nutrient["foods"]:
            assert food["times"] >= 2
            assert food["share_of_reference"] >= 0.1
    contributors = await api.get("/week/contributors/calcium")
    assert contributors.status_code == 200, contributors.text
    assert (await api.get("/week/contributors/nope")).status_code == 404
