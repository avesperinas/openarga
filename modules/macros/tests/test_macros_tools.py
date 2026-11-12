from __future__ import annotations

import pytest

from macros import tools

WRITE = {"x-arga-scopes": "macros:write"}
READ = {"x-arga-scopes": "macros:read"}


async def call(api, name: str, arguments: dict, headers=WRITE) -> dict:
    response = await api.post(f"/tools/{name}", json=arguments, headers=headers)
    assert response.status_code == 200, response.text
    return response.json()["content"]


def test_every_tool_of_the_manifest_is_served() -> None:
    from pathlib import Path

    import yaml

    manifest = yaml.safe_load((Path(__file__).parents[1] / "manifest.yaml").read_text())
    assert {tool["name"] for tool in manifest["tools"]} == set(tools.TOOLS)


async def test_a_coffee_with_milk_two_servings_of_lentils_and_a_beer(api, world) -> None:
    await world.imported("coffee", alias="café")
    await world.imported("milk", alias="leche")
    lentils = await world.imported("lentils", alias="lentejas")
    recipe = (
        await world.recipes.post(
            "/recipes",
            json={
                "name": "Lentejas",
                "servings": 4,
                "ingredients": [{"food_id": lentils["id"], "quantity": 400, "unit": "g"}],
            },
        )
    ).json()

    coffee = (await call(api, "find_food", {"query": "café"}, READ))["pantry"][0]
    milk = (await call(api, "find_food", {"query": "leche"}, READ))["pantry"][0]
    stew = (await call(api, "find_food", {"query": "lentejas"}, READ))["recipes"][0]
    beer = (await call(api, "find_food", {"query": "beer"}, READ))["outside"][0]
    assert stew["recipe_id"] == recipe["id"]

    logged = await call(
        api,
        "log_intake",
        {
            "said": "un café con leche, dos raciones de lentejas y un botellín",
            "items": [
                {"food_id": coffee["food_id"], "quantity": 150, "unit": "ml", "estimated": True},
                {"food_id": milk["food_id"], "quantity": 100, "unit": "ml", "estimated": True},
                {
                    "kind": "recipe",
                    "recipe_id": stew["recipe_id"],
                    "quantity": 2,
                    "unit": "serving",
                },
                {
                    "source": beer["source"],
                    "source_ref": beer["source_ref"],
                    "quantity": 250,
                    "unit": "ml",
                    "estimated": True,
                },
            ],
        },
    )

    assert [item["estimated"] for item in logged["logged"]["items"]] == [True, True, False, True]
    day = await call(api, "get_day", {}, READ)
    assert day["drinks"]["caffeine_mg"] == 60
    assert day["drinks"]["alcohol_g"] == pytest.approx(9.8, abs=0.1)
    assert day["drinks"]["alcohol_units"] == pytest.approx(1.0, abs=0.1)
    assert day["totals"]["calcium"] == 120
    assert day["entries"][0]["said"].startswith("un café con leche")


async def test_the_model_cannot_write_a_figure(api, world) -> None:
    rice = await world.manual_food("Arroz", {"kcal": 130, "protein": 2.7, "fat": 0.3, "carbs": 28})

    response = await api.post(
        "/tools/log_intake",
        json={"items": [{"food_id": rice, "quantity": 100, "unit": "g", "iron": 40}]},
        headers=WRITE,
    )

    assert response.status_code == 422


async def test_reading_scope_does_not_log(api, world) -> None:
    rice = await world.manual_food("Arroz", {"kcal": 130, "protein": 2.7, "fat": 0.3, "carbs": 28})

    response = await api.post(
        "/tools/log_intake",
        json={"items": [{"food_id": rice, "quantity": 100, "unit": "g"}]},
        headers=READ,
    )

    assert response.status_code == 403


async def test_update_and_delete_by_ids(api, world) -> None:
    rice = await world.manual_food("Arroz", {"kcal": 130, "protein": 2.7, "fat": 0.3, "carbs": 28})
    logged = (
        await call(
            api,
            "log_intake",
            {
                "items": [
                    {"food_id": rice, "quantity": 100, "unit": "g"},
                    {"kind": "water", "quantity": 300, "unit": "ml"},
                ]
            },
        )
    )["logged"]
    rice_line, water_line = logged["items"]

    updated = await call(
        api,
        "update_intake",
        {
            "entry_id": logged["entry_id"],
            "change": [{"item_id": rice_line["item_id"], "quantity": 150}],
        },
    )
    assert updated["updated"]["items"][0]["kcal"] == 195
    await call(api, "delete_intake", {"item_id": water_line["item_id"]})
    assert (await call(api, "get_day", {}, READ))["drinks"]["water_l"] == 0
    await call(api, "delete_intake", {"entry_id": logged["entry_id"]})
    assert (await call(api, "get_day", {}, READ))["entries"] == []


async def test_errors_come_back_as_words_the_model_can_read(api, world) -> None:
    answer = await call(api, "delete_intake", {"entry_id": "00000000-0000-4000-8000-000000000000"})
    assert "no" in answer["error"] or "entrada" in answer["error"]
    world.recipes_down()
    down = await call(api, "find_food", {"query": "café"}, READ)
    assert "Recipes no contesta" in down["error"]


async def test_set_target_and_the_day_says_what_is_left(api, world) -> None:
    rice = await world.manual_food("Arroz", {"kcal": 130, "protein": 2.7, "fat": 0.3, "carbs": 28})
    await call(api, "set_target", {"kcal": 2000, "protein": 140})
    await call(api, "log_intake", {"items": [{"food_id": rice, "quantity": 100, "unit": "g"}]})

    day = await call(api, "get_day", {}, READ)

    assert day["target"]["kcal"] == 2000
    assert day["remaining"] == {"kcal": 1870, "protein": 137.3}
