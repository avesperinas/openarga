from __future__ import annotations

from uuid import UUID

import pytest
from sqlalchemy import text


async def log(api, *items, said=None, eaten_at=None):
    body = {"items": list(items)}
    if said:
        body["said"] = said
    if eaten_at:
        body["eaten_at"] = eaten_at
    return await api.post("/entries", json=body)


async def test_a_pantry_food_in_grams_shows_in_the_day_with_its_macros(api, world) -> None:
    rice = await world.manual_food(
        "Arroz cocido", {"kcal": 130, "protein": 2.7, "fat": 0.3, "carbs": 28}
    )

    response = await log(api, {"food_id": rice, "quantity": 200, "unit": "g"})

    assert response.status_code == 201, response.text
    day = (await api.get("/day")).json()
    [entry] = day["entries"]
    [item] = entry["items"]
    assert (item["name"], item["grams"], item["estimated"]) == ("Arroz cocido", 200, False)
    assert day["nutrients"]["kcal"] == 260
    assert day["nutrients"]["protein"] == pytest.approx(5.4)
    assert day["nutrients"]["carbs"] == 56


async def test_correcting_the_food_later_does_not_change_what_was_eaten(api, world) -> None:
    rice = await world.manual_food(
        "Arroz cocido", {"kcal": 130, "protein": 2.7, "fat": 0.3, "carbs": 28}
    )
    await log(api, {"food_id": rice, "quantity": 100, "unit": "g"})

    corrected = await world.recipes.put(
        f"/foods/{rice}/nutrition",
        json={"macros": {"kcal": 300, "protein": 50, "fat": 50, "carbs": 50}},
    )
    assert corrected.status_code == 200, corrected.text

    day = (await api.get("/day")).json()
    assert day["nutrients"]["kcal"] == 130
    await log(api, {"food_id": rice, "quantity": 100, "unit": "g"})
    assert (await api.get("/day")).json()["nutrients"]["kcal"] == 430


async def test_micros_come_from_the_pantry_multiplied_by_the_grams(api, world) -> None:
    lentils = await world.imported("lentils", alias="lentejas")

    await log(api, {"food_id": lentils["id"], "quantity": 80, "unit": "g", "estimated": True})

    day = (await api.get("/day")).json()
    assert day["nutrients"]["iron"] == pytest.approx(5.2)
    assert day["nutrients"]["folate"] == pytest.approx(383.2)
    assert "vitamin_d" not in day["nutrients"]
    assert day["entries"][0]["items"][0]["estimated"] is True


async def test_nobody_can_send_a_nutrient_with_a_line(api, world) -> None:
    rice = await world.manual_food("Arroz", {"kcal": 130, "protein": 2.7, "fat": 0.3, "carbs": 28})

    response = await log(
        api, {"food_id": rice, "quantity": 100, "unit": "g", "nutrients": {"iron": 50}}
    )

    assert response.status_code == 422


async def test_units_need_the_weight_of_one_and_say_so(api, world) -> None:
    egg = await world.manual_food(
        "Huevo", {"kcal": 143, "protein": 12.6, "fat": 9.5, "carbs": 0.7}, grams_per_unit=60
    )
    bread = await world.manual_food("Pan", {"kcal": 266, "protein": 7.6, "fat": 3.3, "carbs": 50.6})

    ok = await log(api, {"food_id": egg, "quantity": 2, "unit": "unit"})
    assert ok.json()["items"][0]["grams"] == 120
    refused = await log(api, {"food_id": bread, "quantity": 1, "unit": "unit"})
    assert refused.status_code == 409
    assert "gramos" in refused.json()["detail"]


async def test_a_house_portion_counts_its_grams_and_says_which(api, world) -> None:
    ham = await world.manual_food(
        "Jamón",
        {"kcal": 250, "protein": 30, "fat": 14, "carbs": 0},
        grams_per_unit=100,
        portions=[{"name": "Loncha", "grams": 15}],
    )

    logged = await log(api, {"food_id": ham, "quantity": 3, "unit": "unit", "portion": "loncha"})

    assert logged.status_code == 201, logged.text
    [item] = logged.json()["items"]
    assert (item["name"], item["grams"], item["portion"]) == ("Jamón", 45, "loncha")
    unknown = await log(api, {"food_id": ham, "quantity": 1, "unit": "unit", "portion": "taco"})
    assert unknown.status_code == 409
    assert "loncha" in unknown.json()["detail"]


async def test_one_package_from_outside_counts_its_label_and_works_in_a_menu(api, world) -> None:
    assert (await api.get("/search", params={"q": "galletas"})).status_code == 200
    logged = await log(
        api,
        {
            "source": "off",
            "source_ref": "8400000000017",
            "quantity": 1,
            "unit": "unit",
            "portion": "envase",
        },
    )
    assert logged.status_code == 201, logged.text
    [item] = logged.json()["items"]
    assert (item["name"], item["grams"], item["portion"]) == ("Galletas de marca", 200, "envase")
    assert item["nutrients"]["kcal"] == pytest.approx(960)

    two = await log(
        api,
        {"food_id": item["food_id"], "quantity": 2, "unit": "unit", "portion": "ración"},
    )
    assert two.json()["items"][0]["grams"] == 60

    menu = await api.post("/templates/from-entry/" + logged.json()["id"], json={"name": "Galletas"})
    assert menu.status_code == 201, menu.text
    assert menu.json()["items"][0]["portion"] == "envase"
    again = await api.post(f"/templates/{menu.json()['id']}/log", json={})
    assert again.json()["items"][0]["portion"] == "envase"
    assert again.json()["items"][0]["grams"] == 200


async def test_a_whole_piece_counts_only_what_is_eaten(api, world) -> None:
    tuna = await world.manual_food(
        "Bonito", {"kcal": 140, "protein": 24, "fat": 5, "carbs": 0}, edible_fraction=0.82
    )

    logged = await log(api, {"food_id": tuna, "quantity": 730, "unit": "g", "as_purchased": True})

    [item] = logged.json()["items"]
    assert (item["quantity"], item["grams"]) == (730, pytest.approx(598.6))
    day = (await api.get("/day")).json()
    assert day["nutrients"]["kcal"] == pytest.approx(838.0, abs=0.1)


async def test_a_supplement_is_logged_in_its_units(api, world) -> None:
    capsule = await world.manual_food(
        "Omega 3",
        {"kcal": 9, "protein": 0, "fat": 1, "carbs": 0},
        category_id="supplement",
        per_unit="cápsula",
        nutrients={"omega3_epa": 0.33, "vitamin_d": 5},
    )

    logged = await log(api, {"food_id": capsule, "quantity": 2, "unit": "unit"})
    in_grams = await log(api, {"food_id": capsule, "quantity": 2, "unit": "g"})

    assert logged.status_code == 201, logged.text
    [item] = logged.json()["items"]
    assert item["grams"] is None
    day = (await api.get("/day")).json()
    assert day["nutrients"]["kcal"] == 18
    assert day["nutrients"]["vitamin_d"] == 10
    assert in_grams.status_code == 409
    assert "cápsula" in in_grams.json()["detail"]

    changed = await api.patch(
        f"/entries/{logged.json()['id']}",
        json={"change": [{"item_id": item["id"], "quantity": 3, "unit": "unit"}]},
    )
    assert changed.status_code == 200, changed.text
    day = (await api.get("/day")).json()
    assert day["nutrients"]["vitamin_d"] == 15


async def test_replacing_a_food_in_recipes_recalculates_what_was_eaten(api, world) -> None:
    wrong = await world.manual_food(
        "Leche equivocada", {"kcal": 40, "protein": 3, "fat": 1, "carbs": 5}
    )
    right = await world.manual_food(
        "Leche entera", {"kcal": 64, "protein": 3.2, "fat": 3.6, "carbs": 4.7}
    )
    first = await log(api, {"food_id": wrong, "quantity": 250, "unit": "g"})
    said = await log(api, {"food_id": wrong, "name": "mi leche", "quantity": 100, "unit": "g"})
    assert first.status_code == said.status_code == 201

    body = {"old_food_id": wrong, "new_food_id": right}
    scopes = {"x-arga-scopes": "recipes:read recipes:write"}
    done = (await world.recipes.post("/tools/replace_food", json=body, headers=scopes)).json()

    macros = done["content"]["replaced"]["macros"]
    assert (macros["done"], macros["items"], macros["entries"]) == (True, 2, 2)
    day = (await api.get("/day")).json()
    assert day["nutrients"]["kcal"] == 224
    names = sorted(item["name"] for entry in day["entries"] for item in entry["items"])
    assert names == ["Leche entera", "mi leche"]
    again = (await world.recipes.post("/tools/replace_food", json=body, headers=scopes)).json()
    assert again["content"]["replaced"]["macros"]["items"] == 0


async def test_a_recipe_goes_in_servings_and_keeps_its_version(api, world) -> None:
    lentils = await world.imported("lentils", alias="lentejas")
    recipe = (
        await world.recipes.post(
            "/recipes",
            json={
                "name": "Lentejas estofadas",
                "servings": 4,
                "ingredients": [{"food_id": lentils["id"], "quantity": 400, "unit": "g"}],
            },
        )
    ).json()

    entry = (
        await log(
            api, {"kind": "recipe", "recipe_id": recipe["id"], "quantity": 2, "unit": "serving"}
        )
    ).json()

    [item] = entry["items"]
    assert (item["name"], item["quantity"], item["grams"]) == ("Lentejas estofadas", 2, 200)
    assert entry["nutrients"]["kcal"] == pytest.approx(704)
    assert entry["nutrients"]["iron"] == pytest.approx(13)


async def test_by_eye_and_water(api, world) -> None:
    entry = (
        await log(
            api,
            {
                "kind": "quick",
                "name": "Pintxo",
                "quantity": 400,
                "unit": "kcal",
                "quick": {"protein": 20},
            },
            {"kind": "water", "quantity": 500, "unit": "ml"},
        )
    ).json()

    quick, water = entry["items"]
    assert quick["estimated"] is True
    assert quick["nutrients"] == {"kcal": 400, "protein": 20}
    assert water["nutrients"] == {}
    day = (await api.get("/day")).json()
    assert day["drinks"]["water_l"] == 0.5
    assert "iron" not in day["nutrients"]


async def test_something_from_outside_is_imported_into_the_pantry_as_it_is_logged(
    api, world
) -> None:
    found = (await api.get("/search", params={"q": "galletas"})).json()
    [cookies] = found["candidates"]

    entry = (
        await log(
            api,
            {
                "source": cookies["source"],
                "source_ref": cookies["source_ref"],
                "quantity": 30,
                "unit": "g",
            },
        )
    ).json()

    assert entry["nutrients"]["kcal"] == 144
    assert entry["nutrients"]["sodium"] == pytest.approx(270)
    [kept] = (await world.recipes.get("/foods", params={"query": "galletas"})).json()
    assert kept["id"] == entry["items"][0]["food_id"]


async def test_changing_the_quantity_recalculates_from_what_was_kept_even_offline(
    api, world
) -> None:
    lentils = await world.imported("lentils", alias="lentejas")
    entry = (await log(api, {"food_id": lentils["id"], "quantity": 100, "unit": "g"})).json()
    world.recipes_down()

    changed = await api.patch(
        f"/entries/{entry['id']}",
        json={"change": [{"item_id": entry["items"][0]["id"], "quantity": 50}]},
    )

    assert changed.status_code == 200, changed.text
    assert changed.json()["nutrients"]["iron"] == pytest.approx(3.25)
    assert changed.json()["items"][0]["grams"] == 50


async def test_with_recipes_down_nothing_new_is_logged_and_it_says_so(api, world) -> None:
    rice = await world.manual_food("Arroz", {"kcal": 130, "protein": 2.7, "fat": 0.3, "carbs": 28})
    entry = (await log(api, {"food_id": rice, "quantity": 100, "unit": "g"})).json()
    world.recipes_down()

    refused = await log(api, {"food_id": rice, "quantity": 100, "unit": "g"})
    assert refused.status_code == 503
    assert "Recipes no contesta" in refused.json()["detail"]
    assert "Error" not in refused.json()["detail"]
    assert "Timeout" not in refused.json()["detail"]
    assert (await api.get("/search", params={"q": "arroz"})).status_code == 503

    assert (await api.get("/day")).json()["nutrients"]["kcal"] == 130
    assert (await api.delete(f"/entries/{entry['id']}")).status_code == 204
    assert (await api.get("/day")).json()["entries"] == []


async def test_a_line_is_duplicated_and_deleted_and_the_last_takes_its_entry(api, world) -> None:
    coffee = await world.manual_food("Café", {"kcal": 1, "protein": 0.1, "fat": 0, "carbs": 0})
    entry = (await log(api, {"food_id": coffee, "quantity": 200, "unit": "ml"})).json()
    item = entry["items"][0]["id"]

    twice = (await api.post(f"/items/{item}/duplicate")).json()
    assert len(twice["items"]) == 2
    left = (await api.delete(f"/items/{item}")).json()
    assert len(left["entry"]["items"]) == 1
    gone = (await api.delete(f"/items/{twice['items'][1]['id']}")).json()
    assert gone["entry"] is None
    assert (await api.get("/day")).json()["entries"] == []


async def test_the_usual_and_yesterday_come_back_with_one_tap(api, world) -> None:
    coffee = await world.manual_food("Café", {"kcal": 1, "protein": 0.1, "fat": 0, "carbs": 0})
    from macros.common import now
    from macros.meals import meal_of

    moment = now()
    for days in (1, 2, 3):
        earlier = (
            moment.replace(microsecond=0) - __import__("datetime").timedelta(days=days)
        ).isoformat()
        await log(api, {"food_id": coffee, "quantity": 200, "unit": "ml"}, eaten_at=earlier)

    usual = (await api.get(f"/usual/{meal_of(moment)}")).json()
    assert (usual["usual"]["label"], usual["usual"]["times"]) == ("Café", 3)
    assert len(usual["yesterday"]) == 1
    yesterday = (moment - __import__("datetime").timedelta(days=1)).date().isoformat()
    [entry] = (await api.get("/day", params={"day": yesterday})).json()["entries"]
    again = await api.post(f"/entries/{entry['id']}/repeat")
    assert again.status_code == 201
    assert len((await api.get("/day")).json()["entries"]) == 1


async def test_what_one_person_eats_the_other_never_sees(api, world, schema) -> None:
    from arga_tenancy import current_user

    other = "00000000-0000-4000-8000-00000000b0b0"

    rice = await world.manual_food("Arroz", {"kcal": 130, "protein": 2.7, "fat": 0.3, "carbs": 28})
    await log(api, {"food_id": rice, "quantity": 100, "unit": "g"})

    token = current_user.set(UUID(other))
    try:
        assert (await api.get("/day")).json()["entries"] == []
    finally:
        current_user.reset(token)
    async with schema.connect() as connection:
        await connection.execute(text("set role mod_macros"))
        await connection.execute(text(f"set arga.user_id = '{other}'"))
        assert await connection.scalar(text("select count(*) from macros.macros_item")) == 0


async def test_a_dish_without_recipe_keeps_its_name_and_can_be_renamed_or_undone(
    api, world
) -> None:
    oats = await world.manual_food("Avena", {"kcal": 380, "protein": 13, "fat": 7, "carbs": 60})
    egg = await world.manual_food("Huevo", {"kcal": 140, "protein": 12, "fat": 10, "carbs": 1})
    created = await api.post(
        "/entries",
        json={
            "items": [
                {"food_id": oats, "quantity": 50, "dish": "Tortita de avena"},
                {"food_id": egg, "quantity": 60, "dish": "Tortita de avena"},
            ]
        },
    )
    assert created.status_code == 201, created.text
    entry = created.json()
    assert [item["dish"] for item in entry["items"]] == ["Tortita de avena", "Tortita de avena"]

    again = (await api.post(f"/entries/{entry['id']}/repeat")).json()
    assert [item["dish"] for item in again["items"]] == ["Tortita de avena", "Tortita de avena"]

    renamed = await api.put(
        f"/entries/{entry['id']}/dish", json={"from": "Tortita de avena", "to": "Tortita"}
    )
    assert renamed.status_code == 200, renamed.text
    assert {item["dish"] for item in renamed.json()["items"]} == {"Tortita"}
    undone = (
        await api.put(f"/entries/{entry['id']}/dish", json={"from": "Tortita", "to": None})
    ).json()
    assert {item["dish"] for item in undone["items"]} == {None}
    assert (await api.put(f"/entries/{entry['id']}/dish", json={"from": "Nada"})).status_code == 404


async def test_a_dish_is_saved_as_a_recipe_only_when_asked(api, world) -> None:
    oats = await world.manual_food("Avena", {"kcal": 380, "protein": 13, "fat": 7, "carbs": 60})
    milk = await world.manual_food("Leche", {"kcal": 46, "protein": 3.4, "fat": 1.6, "carbs": 4.8})
    entry = (
        await api.post(
            "/entries",
            json={
                "items": [
                    {"food_id": oats, "quantity": 40, "dish": "Gachas"},
                    {"food_id": milk, "quantity": 200, "unit": "ml", "dish": "Gachas"},
                    {
                        "kind": "quick",
                        "name": "Canela",
                        "quantity": 5,
                        "unit": "kcal",
                        "dish": "Gachas",
                    },
                ]
            },
        )
    ).json()
    before = (await world.recipes.get("/recipes")).json()
    assert all(one["name"] != "Gachas" for one in before)

    saved = await api.post(f"/entries/{entry['id']}/dish/recipe", json={"dish": "Gachas"})
    assert saved.status_code == 200, saved.text
    assert saved.json()["skipped"] == 1
    after = (await world.recipes.get("/recipes")).json()
    assert any(one["name"] == "Gachas" for one in after)
    again = (await api.get(f"/entries/{entry['id']}")).json()
    assert [item["kind"] for item in again["items"]] == ["food", "food", "quick"]
