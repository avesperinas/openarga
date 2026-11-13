from __future__ import annotations

import json
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import text

import arga_contracts as contracts
from macros.common import today

MADRID = ZoneInfo("Europe/Madrid")
WRITE = {"x-arga-scopes": "macros:read macros:write"}
READ = {"x-arga-scopes": "macros:read"}

INSERT = text(
    "insert into kernel.events (ts, module, source, type, payload, dedup_hash, user_id)"
    " values (now(), :module, 'test', :type, cast(:payload as jsonb), :dedup, :user)"
)


@pytest.fixture
async def publishers(schema, world):
    from arga_tenancy import current_user
    from arga_testing import fresh_modules

    async with schema.begin() as connection:
        await connection.execute(text("delete from kernel.events where source = 'test'"))
        await fresh_modules(
            connection, "training", "vitals", "macros", fresh=["training", "vitals"]
        )
    person = str(current_user.get())

    async def publish(module: str, kind: str, payload: dict, dedup: str) -> None:
        async with schema.begin() as connection:
            await connection.execute(
                INSERT,
                {
                    "module": module,
                    "type": kind,
                    "payload": json.dumps(payload),
                    "dedup": f"{dedup}:{person}",
                    "user": person,
                },
            )

    yield publish
    async with schema.begin() as connection:
        await connection.execute(text("delete from kernel.events where source = 'test'"))
        await connection.execute(
            text("delete from kernel.modules where id in ('training', 'vitals')")
        )


def call(api, name: str, arguments: dict, headers: dict = WRITE):
    return api.post(f"/tools/{name}", json=arguments, headers=headers)


async def goals_of(api) -> dict[str, dict]:
    found = (await call(api, "get_goals", {}, READ)).json()["content"]
    return {one["nutrient"]: one for one in found["goals"]}


async def eat(api, world, kcal: float, saturated: float = 0) -> None:
    grams = kcal / 5
    food = await world.manual_food(
        f"Meal of {kcal}",
        {"kcal": 500, "protein": 0, "fat": 10, "carbs": 0},
        nutrients={"saturated_fat": round(saturated / grams * 100, 4)},
    )
    logged = await api.post(
        "/entries", json={"items": [{"food_id": food, "quantity": grams, "unit": "g"}]}
    )
    assert logged.status_code == 201, logged.text


async def test_without_goals_of_yours_the_efsa_ones_apply(api, world, publishers) -> None:
    await publishers(
        "vitals",
        "vitals.weight",
        {"body_weight": contracts.body_weight(id="w1", day=today(), kg=80)},
        "weight",
    )

    found = await goals_of(api)

    assert (found["fat"]["unit"], found["fat"]["min"], found["fat"]["max"]) == ("kcal_pct", 20, 35)
    assert (found["sodium"]["max"], found["sodium"]["source"]) == (2000, "efsa")
    assert found["protein"]["min"] == pytest.approx(66.4)
    assert "kcal" not in found


async def test_a_range_says_low_ok_and_high(api, world) -> None:
    await call(api, "set_goal", {"nutrient": "kcal", "min": 1900, "max": 2100})
    await eat(api, world, 1500)

    day = (await call(api, "get_day", {}, READ)).json()["content"]
    kcal = next(one for one in day["goals"] if one["nutrient"] == "kcal")
    assert (kcal["status"], kcal["goal"], kcal["source"]) == (
        "low",
        {"min": 1900, "max": 2100, "unit": "amount"},
        "own",
    )
    assert day["target"]["kcal"] == 2000

    await eat(api, world, 700)
    day = (await call(api, "get_day", {}, READ)).json()["content"]
    assert next(one for one in day["goals"] if one["nutrient"] == "kcal")["status"] == "high"


async def test_a_share_of_the_kcal_is_measured_against_what_was_eaten(api, world) -> None:
    await call(api, "set_goal", {"nutrient": "saturated_fat", "max": 7, "unit": "kcal_pct"})
    await call(api, "set_goal", {"nutrient": "kcal", "min": 2000, "max": 2000})
    await eat(api, world, 2000, saturated=18)

    day = (await call(api, "get_day", {}, READ)).json()["content"]
    saturated = next(one for one in day["goals"] if one["nutrient"] == "saturated_fat")
    assert (saturated["status"], saturated["share_of_kcal"]) == ("high", 8.1)
    found = (await api.get("/day")).json()
    drawn = next(one for one in found["goals"] if one["nutrient"] == "saturated_fat")
    assert drawn["high"] == pytest.approx(15.6)


async def test_a_share_needs_something_that_has_kcal(api, world) -> None:
    refused = await call(api, "set_goal", {"nutrient": "caffeine", "max": 5, "unit": "kcal_pct"})

    assert refused.status_code == 422
    assert "has no kcal" in refused.text


async def test_training_days_have_their_own_and_a_workout_makes_one(api, world, publishers) -> None:
    await call(api, "set_goal", {"nutrient": "carbs", "min": 200, "max": 250})
    await call(
        api, "set_goal", {"nutrient": "carbs", "min": 300, "max": 350, "profile": "training"}
    )

    rest = await goals_of(api)
    start = datetime.combine(today(), datetime.min.time(), MADRID) + timedelta(hours=10)
    workout = contracts.workout(
        id="s1",
        kind="strength",
        name="Pull",
        start=start,
        end=start + timedelta(hours=1),
        tz="Europe/Madrid",
    )
    await publishers("training", "training.workout", {"workout": workout}, "workout")
    trained = (await call(api, "get_goals", {}, READ)).json()["content"]

    assert (rest["carbs"]["min"], rest["carbs"]["profile"]) == (200, "any")
    assert trained["day_kind"]["kind"] == "training"
    assert trained["day_kind"]["source"] == "workout"
    assert trained["day_kind"]["workouts"] == ["Pull"]
    by_key = {one["nutrient"]: one for one in trained["goals"]}
    assert (by_key["carbs"]["min"], by_key["carbs"]["profile"]) == (300, "training")

    marked = (await call(api, "set_day_kind", {"kind": "rest"})).json()["content"]["day_kind"]
    assert (marked["kind"], marked["source"]) == ("rest", "manual")
    assert (await goals_of(api))["carbs"]["min"] == 200
    back = (await call(api, "set_day_kind", {"kind": None})).json()["content"]["day_kind"]
    assert back["source"] == "workout"


async def test_no_goal_is_a_choice_and_reset_brings_the_efsa_back(api, world) -> None:
    await call(api, "set_goal", {"nutrient": "sodium"})
    assert "sodium" not in await goals_of(api)

    await call(api, "set_goal", {"nutrient": "sodium", "reset": True})
    assert (await goals_of(api))["sodium"]["source"] == "efsa"


async def test_a_goal_from_tomorrow_leaves_today_alone(api, world) -> None:
    tomorrow = (today() + timedelta(days=1)).isoformat()
    await call(api, "set_goal", {"nutrient": "fiber", "min": 40, "valid_from": tomorrow})

    assert (await goals_of(api))["fiber"]["min"] == 25
    later = (await call(api, "get_goals", {"day": tomorrow}, READ)).json()["content"]["goals"]
    assert next(one for one in later if one["nutrient"] == "fiber")["min"] == 40


async def test_the_old_shortcut_and_references_become_ranges(api, world) -> None:
    await call(api, "set_target", {"kcal": 2000, "protein": 150})
    await api.put("/references/caffeine", json={"kind": "max", "value": 200})

    found = await goals_of(api)

    assert (found["kcal"]["min"], found["kcal"]["max"]) == (1800, 2200)
    assert (found["protein"]["min"], found["protein"]["max"]) == (150, None)
    assert (found["caffeine"]["max"], found["caffeine"]["source"]) == (200, "own")
    refs = {one["nutrient"]: one for one in (await api.get("/references")).json()["references"]}
    assert refs["caffeine"]["value"] == 200
