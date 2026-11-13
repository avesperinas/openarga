from __future__ import annotations

from datetime import datetime, time
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import text

from macros.common import today

MADRID = ZoneInfo("Europe/Madrid")

READ = {"x-arga-scopes": "macros:read"}
WRITE = {"x-arga-scopes": "macros:read macros:write"}


def tool(api, name: str, body: dict, headers: dict = WRITE):
    return api.post(f"/tools/{name}", json=body, headers=headers)


async def test_planned_does_not_count_until_it_is_confirmed(api, world, schema) -> None:
    rice = await world.manual_food("Arroz", {"kcal": 130, "protein": 2.7, "fat": 0.3, "carbs": 28})
    dinner = datetime.combine(today(), time(21), MADRID).isoformat()

    planned = (
        await tool(
            api,
            "log_intake",
            {"eaten_at": dinner, "planned": True, "items": [{"food_id": rice, "quantity": 200}]},
        )
    ).json()["content"]["logged"]
    day = (await tool(api, "get_day", {}, READ)).json()["content"]

    assert day["totals"] == {} and day["entries"] == []
    assert [one["entry_id"] for one in day["planned"]] == [planned["entry_id"]]
    async with schema.connect() as connection:
        queued = await connection.scalar(
            text("select count(*) from macros.macros_outbox where type = 'macros.intake'")
        )
    assert queued == 0

    confirmed = await tool(api, "confirm_intake", {"entry_id": planned["entry_id"]})
    day = (await tool(api, "get_day", {}, READ)).json()["content"]

    assert confirmed.status_code == 200, confirmed.text
    assert day["totals"]["kcal"] == 260 and day["planned"] == []
    again = await api.post(f"/entries/{planned['entry_id']}/confirm", json={})
    assert again.status_code == 409

    undone = await api.post(f"/entries/{planned['entry_id']}/unconfirm")
    day = (await tool(api, "get_day", {}, READ)).json()["content"]
    assert undone.status_code == 200, undone.text
    assert undone.json()["status"] == "planned"
    assert day["totals"] == {} and len(day["planned"]) == 1
    assert (await api.post(f"/entries/{planned['entry_id']}/unconfirm")).status_code == 409


async def test_a_template_is_logged_in_one_step_by_its_name(api, world) -> None:
    capsule = await world.manual_food(
        "Omega 3",
        {"kcal": 9, "protein": 0, "fat": 1, "carbs": 0},
        category_id="supplement",
        per_unit="capsule",
        nutrients={"vitamin_d": 5},
    )
    saved = await tool(
        api,
        "save_template",
        {
            "name": "Morning supplements",
            "items": [{"food_id": capsule, "quantity": 2, "unit": "unit"}],
        },
    )
    assert saved.status_code == 200, saved.text

    logged = (await tool(api, "log_template", {"template": "morning supplements"})).json()

    assert logged["content"]["totals"]["kcal"] == 18
    listed = (await tool(api, "get_usual", {}, READ)).json()["content"]["menus"]
    assert [one["name"] for one in listed] == ["Morning supplements"]
    missing = (await tool(api, "log_template", {"template": "cena"})).json()["content"]
    assert "Morning supplements" in missing["error"]


async def test_a_daily_template_shows_up_planned_once_a_day(api, world) -> None:
    from macros import templates
    from macros.main import app, as_app

    coffee = await world.manual_food("Coffee", {"kcal": 2, "protein": 0.1, "fat": 0, "carbs": 0})
    entry = (
        await api.post("/entries", json={"items": [{"food_id": coffee, "quantity": 200}]})
    ).json()
    made = await api.post(
        f"/templates/from-entry/{entry['id']}", json={"name": "Coffee", "daily_at": "08:00"}
    )
    assert made.status_code == 201, made.text

    async with as_app() as connection:
        first = await templates.materialise(connection, app.state.client)
    async with as_app() as connection:
        second = await templates.materialise(connection, app.state.client)

    assert (first, second) == (1, 0)
    [planned] = (await api.get("/day")).json()["planned"]
    moment = datetime.fromisoformat(planned["eaten_at"]).astimezone(MADRID)
    assert (moment.date(), moment.time()) == (today(), time(8))


async def test_a_newer_recipe_version_is_offered_and_recalculated(api, world) -> None:
    lentils = await world.imported("lentils", alias="dry lentils")
    body = {
        "name": "Stewed lentils",
        "servings": 4,
        "ingredients": [{"food_id": lentils["id"], "quantity": 400, "unit": "g"}],
    }
    recipe = (await world.recipes.post("/recipes", json=body)).json()
    await api.post(
        "/entries",
        json={
            "items": [
                {"kind": "recipe", "recipe_id": recipe["id"], "quantity": 1, "unit": "serving"}
            ]
        },
    )
    before = (await api.get("/day")).json()["nutrients"]["kcal"]
    body["ingredients"][0]["quantity"] = 800
    updated = await world.recipes.put(f"/recipes/{recipe['id']}", json=body)
    assert updated.status_code == 200, updated.text

    offered = (await tool(api, "get_outdated_recipes", {}, READ)).json()["content"]["recipes"]
    done = (await tool(api, "recalculate_recipe_intakes", {"recipe_id": recipe["id"]})).json()[
        "content"
    ]["recalculated"]

    assert [(one["name"], one["items"]) for one in offered] == [("Stewed lentils", 1)]
    assert done["items"] == 1
    assert (await api.get("/day")).json()["nutrients"]["kcal"] == pytest.approx(before * 2)
    assert (await tool(api, "get_outdated_recipes", {}, READ)).json()["content"]["recipes"] == []
