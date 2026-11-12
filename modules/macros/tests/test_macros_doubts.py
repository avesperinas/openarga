from __future__ import annotations

WRITE = {"x-arga-scopes": "macros:write"}
APPLE = {"kcal": 52, "protein": 0.3, "fat": 0.2, "carbs": 14}
PEAR = {"kcal": 57, "protein": 0.4, "fat": 0.1, "carbs": 15}


async def claude(api, *items) -> dict:
    response = await api.post("/tools/log_intake", json={"items": list(items)}, headers=WRITE)
    assert response.status_code == 200, response.text
    return response.json()["content"]["logged"]


async def test_the_first_time_is_asked_and_the_second_is_not(api, world) -> None:
    apple = await world.manual_food("Manzana", APPLE)

    first = await claude(api, {"food_id": apple, "quantity": 180, "unit": "g"})
    assert first["items"][0]["doubt"] == "first"
    second = await claude(api, {"food_id": apple, "quantity": 150, "unit": "g"})
    assert "doubt" not in second["items"][0]

    unsure = await claude(api, {"food_id": apple, "quantity": 150, "unit": "g", "unsure": True})
    assert unsure["items"][0]["doubt"] == "unsure"


async def test_what_you_log_in_the_app_is_never_asked(api, world) -> None:
    apple = await world.manual_food("Manzana", APPLE)
    logged = await api.post(
        "/entries", json={"items": [{"food_id": apple, "quantity": 180, "unit": "g"}]}
    )
    assert logged.json()["items"][0]["doubt"] is None


async def test_the_tick_and_a_swap_clear_the_doubt_and_keep_the_numbers(api, world) -> None:
    apple = await world.manual_food("Manzana", APPLE)
    pear = await world.manual_food("Pera", PEAR)
    logged = await claude(
        api,
        {"food_id": apple, "quantity": 180, "unit": "g"},
        {"food_id": pear, "quantity": 100, "unit": "g", "unsure": True},
    )
    first, second = (one["item_id"] for one in logged["items"])

    sure = await api.post(f"/items/{first}/sure")
    assert sure.status_code == 200, sure.text
    [kept, still] = sure.json()["items"]
    assert (kept["doubt"], kept["nutrients"]["kcal"]) == (None, 93.6)
    assert still["doubt"] == "unsure"

    swapped = await api.patch(
        f"/entries/{logged['entry_id']}", json={"swap": [{"item_id": second, "food_id": apple}]}
    )
    assert swapped.json()["items"][1]["doubt"] is None
    assert (await api.post("/items/00000000-0000-4000-8000-000000000000/sure")).status_code == 404
