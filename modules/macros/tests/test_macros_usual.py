from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from macros.common import today

MADRID = ZoneInfo("Europe/Madrid")

WRITE = {"x-arga-scopes": "macros:write"}
READ = {"x-arga-scopes": "macros:read"}
YOGURT = {"kcal": 61, "protein": 3.5, "fat": 3.3, "carbs": 4.7}
NUTS = {"kcal": 654, "protein": 15, "fat": 65, "carbs": 14}
APPLE = {"kcal": 52, "protein": 0.3, "fat": 0.2, "carbs": 14}


async def at(api, day, hhmm, *items):
    response = await api.post(
        "/entries", json={"eaten_at": f"{day.isoformat()}T{hhmm}:00", "items": list(items)}
    )
    assert response.status_code == 201, response.text
    return response.json()


async def call(api, name, arguments, headers=WRITE):
    response = await api.post(f"/tools/{name}", json=arguments, headers=headers)
    assert response.status_code == 200, response.text
    return response.json()["content"]


async def snacks(api, world):
    yogurt = await world.manual_food("Yogur natural", YOGURT)
    nuts = await world.manual_food("Nueces", NUTS)
    apple = await world.manual_food("Manzana", APPLE)
    for back in (1, 2, 4):
        day = today() - timedelta(days=back)
        await at(
            api,
            day,
            "18:00",
            {"food_id": yogurt, "quantity": 125, "unit": "g"},
            {"food_id": nuts, "quantity": 20 + back, "unit": "g"},
        )
    await at(
        api, today() - timedelta(days=2), "13:30", {"food_id": apple, "quantity": 180, "unit": "g"}
    )
    return yogurt, nuts, apple


async def test_the_usual_of_a_meal(api, world) -> None:
    yogurt, nuts, apple = await snacks(api, world)

    found = (await api.get("/usual/snack")).json()

    assert [one["name"] for one in found["yesterday"]] == ["Yogur natural", "Nueces"]
    assert found["usual"]["times"] == 3
    assert found["usual"]["label"] == "Yogur natural + Nueces"
    assert [(one["name"], one["quantity"], one["times"]) for one in found["items"]] == [
        ("Nueces", 21, 3),
        ("Yogur natural", 125, 3),
    ]
    assert [one["name"] for one in found["recent"]] == ["Manzana"]


async def test_like_yesterday_and_the_usual_are_one_tap_even_with_recipes_down(api, world) -> None:
    await snacks(api, world)
    found = (await api.get("/usual/snack")).json()
    world.recipes_down()

    copied = await api.post(
        "/items/repeat", json={"item_ids": found["usual"]["item_ids"], "meal": "snack"}
    )
    assert copied.status_code == 201, copied.text
    entry = copied.json()
    assert (entry["meal"], entry["day"]) == ("snack", today().isoformat())
    assert entry["nutrients"]["kcal"] == pytest.approx(61 * 1.25 + 6.54 * 21)

    assert (await api.delete(f"/entries/{entry['id']}")).status_code == 204


def test_the_meal_of_now_is_the_default() -> None:
    from macros import meals

    assert meals.meal_of(datetime(2026, 10, 20, 18, 5, tzinfo=MADRID)) == "snack"


async def test_a_menu_is_logged_into_the_chosen_meal(api, world) -> None:
    apple = await world.manual_food("Manzana", APPLE)
    menu = await api.post(
        "/templates",
        json={"name": "Fruta", "items": [{"food_id": apple, "quantity": 180, "unit": "g"}]},
    )
    assert menu.status_code == 201, menu.text
    yesterday = today() - timedelta(days=1)
    logged = await api.post(
        f"/templates/{menu.json()['id']}/log",
        json={"meal": "morning", "eaten_at": f"{yesterday.isoformat()}T00:00:00"},
    )
    assert logged.status_code == 201, logged.text
    assert (logged.json()["meal"], logged.json()["day"]) == ("morning", yesterday.isoformat())


async def test_the_desktop_shortcut_opens_the_sheet_to_log(api, schema) -> None:
    found = (await api.get("/widgets/log")).json()
    assert found["state"] == "ready"
    [action] = found["body"]["actions"]
    assert action["href"] == "/macros/log"
    assert action["label"].startswith("Log ")
