from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from macros.common import MADRID, today

READ = {"x-arga-scopes": "macros:read"}
WRITE = {"x-arga-scopes": "macros:read macros:write"}


def at(hour: int, minute: int = 0, days_ago: int = 0) -> str:
    moment = datetime.combine(today() - timedelta(days=days_ago), datetime.min.time(), MADRID)
    return (moment + timedelta(hours=hour, minutes=minute)).isoformat()


async def log(api, food: str, grams: float, when: str) -> None:
    response = await api.post(
        "/entries",
        json={"eaten_at": when, "items": [{"food_id": food, "quantity": grams, "unit": "g"}]},
    )
    assert response.status_code == 201, response.text


async def test_micros_come_grouped_and_what_is_unknown_is_not_zero(api, world) -> None:
    salmon = await world.manual_food(
        "Salmón",
        {"kcal": 200, "protein": 20, "fat": 13, "carbs": 0},
        nutrients={"omega3_epa": 0.8, "omega3_dha": 1.2, "water": 64},
    )
    bread = await world.manual_food("Pan", {"kcal": 250, "protein": 8, "fat": 3, "carbs": 50})
    await log(api, salmon, 100, at(14))
    await log(api, bread, 100, at(14))
    water = await api.post(
        "/entries", json={"items": [{"kind": "water", "quantity": 500, "unit": "ml"}]}
    )
    assert water.status_code == 201

    day = (await api.get("/day")).json()

    groups = {group["key"]: {one["key"]: one for one in group["items"]} for group in day["groups"]}
    epa_dha = groups["fats"]["omega3_epa_dha"]
    assert epa_dha["value"] == pytest.approx(2.0)
    assert epa_dha["coverage"] == pytest.approx(200 / 450, abs=0.001)
    assert epa_dha["partial"] is True
    assert groups["other"]["water"]["value"] == pytest.approx(564)
    assert groups["vitamins"]["vitamin_d"]["value"] is None
    assert groups["sugars"]["added_sugars"]["value"] is None


async def test_who_adds_a_nutrient_is_said_by_name_and_share(api, world) -> None:
    milk = await world.manual_food(
        "Leche", {"kcal": 64, "protein": 3.2, "fat": 3.6, "carbs": 4.7}, nutrients={"sugars": 4.7}
    )
    apple = await world.manual_food(
        "Manzana", {"kcal": 52, "protein": 0.3, "fat": 0.2, "carbs": 14}, nutrients={"sugars": 10}
    )
    for hour in (8, 11, 17):
        await log(api, milk, 250, at(hour))
    await log(api, apple, 150, at(13))

    found = (await api.post("/tools/get_day", json={"nutrient": "sugars"}, headers=READ)).json()[
        "content"
    ]["contributors"]

    assert [(one["name"], one["times"]) for one in found["items"]] == [("Leche", 3), ("Manzana", 1)]
    assert found["total"] == pytest.approx(3 * 11.75 + 15)
    assert found["items"][0]["share"] == pytest.approx(70.1, abs=0.1)
    unknown = (
        await api.post("/tools/get_day", json={"nutrient": "vitamina_x"}, headers=READ)
    ).json()["content"]
    assert unknown["contributors"] is None


async def test_caffeine_says_how_much_is_left_and_the_last_dose(api, world) -> None:
    coffee = await world.manual_food(
        "Café", {"kcal": 2, "protein": 0.1, "fat": 0, "carbs": 0}, nutrients={"caffeine": 40}
    )
    await log(api, coffee, 200, at(8, days_ago=1))
    await log(api, coffee, 200, at(13, days_ago=1))
    yesterday = (today() - timedelta(days=1)).isoformat()

    day = (await api.get("/day", params={"day": yesterday})).json()

    caffeine = day["caffeine"]
    assert caffeine["total_mg"] == 160
    assert caffeine["last_at"].startswith(f"{yesterday}T13:00")
    expected = 80 * 0.5 ** (16 / 5) + 80 * 0.5 ** (11 / 5)
    assert caffeine["now_mg"] == pytest.approx(expected, abs=0.2)
    curve = [point["mg"] for point in caffeine["curve"]]
    assert curve[0] == 80 and max(curve) == pytest.approx(80 + 80 * 0.5 ** (5 / 5), abs=0.2)
    assert curve[-1] < curve[-2]


async def test_the_week_says_how_each_goal_went_each_day(api, world) -> None:
    await api.post(
        "/tools/set_goal",
        json={
            "nutrient": "kcal",
            "min": 1900,
            "max": 2100,
            "valid_from": (today() - timedelta(days=6)).isoformat(),
        },
        headers=WRITE,
    )
    rice = await world.manual_food("Arroz", {"kcal": 400, "protein": 8, "fat": 1, "carbs": 88})
    await log(api, rice, 500, at(14, days_ago=1))
    await log(api, rice, 600, at(14))

    week = (await api.get("/week")).json()

    rows = {row["nutrient"]: row["states"] for row in week["compliance"]}
    assert rows["kcal"][-2:] == ["ok", "high"]
    assert rows["kcal"][0] == "none"
    average = next(one for one in week["goals"] if one["nutrient"] == "kcal")
    assert average["value"] == pytest.approx(2200) and average["status"] == "high"


async def test_the_new_widgets_say_how_goals_go(api, world) -> None:
    await api.post(
        "/tools/set_goal", json={"nutrient": "kcal", "min": 1900, "max": 2100}, headers=WRITE
    )
    rice = await world.manual_food("Arroz", {"kcal": 400, "protein": 8, "fat": 1, "carbs": 88})
    await log(api, rice, 500, at(9))

    goals = (await api.get("/widgets/goals_today")).json()
    compliance = (await api.get("/widgets/compliance")).json()

    assert goals["state"] == "ready"
    kcal = next(row for row in goals["body"]["rows"] if row["label"] == "Energía")
    assert (kcal["value"], kcal["tone"]) == ("2.000 kcal", "positive")
    assert compliance["state"] == "ready"
    assert len(compliance["body"]["values"]) == 28
