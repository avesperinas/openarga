from __future__ import annotations

import pytest

APPLE = {"kcal": 52, "protein": 0.3, "fat": 0.2, "carbs": 14}
PEAR = {"kcal": 57, "protein": 0.4, "fat": 0.1, "carbs": 15}


async def logged(api, *items) -> dict:
    response = await api.post("/entries", json={"items": list(items)})
    assert response.status_code == 201, response.text
    return response.json()


async def test_changing_the_food_keeps_the_quantity(api, world) -> None:
    apple = await world.manual_food("Manzana", APPLE)
    pear = await world.manual_food("Pera", PEAR)
    entry = await logged(api, {"food_id": apple, "quantity": 180, "unit": "g", "estimated": True})
    item = entry["items"][0]["id"]

    changed = await api.patch(
        f"/entries/{entry['id']}", json={"swap": [{"item_id": item, "food_id": pear}]}
    )

    assert changed.status_code == 200, changed.text
    [line] = changed.json()["items"]
    assert (line["id"], line["name"], line["food_id"]) == (item, "Pera", pear)
    assert (line["quantity"], line["unit"], line["grams"]) == (180, "g", 180)
    assert line["estimated"] is True
    assert line["nutrients"]["kcal"] == pytest.approx(57 * 1.8)


async def test_a_swap_needs_one_new_thing(api, world) -> None:
    apple = await world.manual_food("Manzana", APPLE)
    entry = await logged(api, {"food_id": apple, "quantity": 100, "unit": "g"})
    refused = await api.patch(
        f"/entries/{entry['id']}", json={"swap": [{"item_id": entry["items"][0]["id"]}]}
    )
    assert refused.status_code == 422


async def test_correcting_the_quantity_yourself_drops_the_estimate(api, world) -> None:
    apple = await world.manual_food("Manzana", APPLE)
    entry = await logged(api, {"food_id": apple, "quantity": 150, "unit": "g", "estimated": True})
    item = entry["items"][0]["id"]
    changed = await api.patch(
        f"/entries/{entry['id']}",
        json={"change": [{"item_id": item, "quantity": 200, "estimated": False}]},
    )
    [line] = changed.json()["items"]
    assert (line["quantity"], line["estimated"]) == (200, False)
    assert line["nutrients"]["kcal"] == pytest.approx(104)


async def test_the_house_measures_of_a_line(api, world) -> None:
    yogurt = await world.manual_food(
        "Yogur natural",
        {"kcal": 61, "protein": 3.5, "fat": 3.3, "carbs": 4.7},
        portions=[{"name": "Envase", "grams": 125}, {"name": "Cucharada", "grams": 15}],
    )
    entry = await logged(api, {"food_id": yogurt, "quantity": 125, "unit": "g"})
    found = await api.get(f"/items/{entry['items'][0]['id']}/measures")
    assert found.status_code == 200, found.text
    assert found.json()["measures"] == [
        {"name": "cucharada", "grams": 15},
        {"name": "envase", "grams": 125},
    ]
