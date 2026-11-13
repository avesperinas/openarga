from __future__ import annotations

import json

import pytest
from sqlalchemy import text


async def add_food(api, name: str, category: str, macros: dict, **measures) -> str:
    response = await api.post(
        "/foods/manual", json={"name": name, "category_id": category, "macros": macros, **measures}
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


@pytest.fixture
async def pantry(api) -> dict[str, str]:
    return {
        "leek": await add_food(
            api,
            "Leek",
            "vegetable",
            {"kcal": 61, "protein": 1.5, "fat": 0.3, "carbs": 14.15},
            grams_per_unit=90,
        ),
        "potato": await add_food(
            api,
            "Potato",
            "vegetable",
            {"kcal": 77, "protein": 2, "fat": 0.1, "carbs": 17.5},
        ),
        "oil": await add_food(
            api,
            "Olive oil",
            "fat",
            {"kcal": 884, "protein": 0, "fat": 100, "carbs": 0},
            density_g_ml=0.92,
        ),
        "cod": await add_food(
            api,
            "Cod",
            "fish",
            {"kcal": 82, "protein": 18, "fat": 0.7, "carbs": 0},
        ),
    }


def leek_soup(pantry: dict[str, str], **overrides) -> dict:
    body = {
        "name": "Leek soup",
        "servings": 4,
        "tags": ["winter", "pot"],
        "ingredients": [
            {"food_id": pantry["leek"], "quantity": 400, "unit": "g", "note": "sliced"},
            {"food_id": pantry["potato"], "quantity": 600, "unit": "g"},
            {"food_id": pantry["oil"], "quantity": 30, "unit": "ml"},
            {"food_id": pantry["cod"], "quantity": 200, "unit": "g", "optional": True},
        ],
    }
    body.update(overrides)
    return body


async def test_a_recipe_is_created_with_its_first_version_sealed(api, pantry) -> None:
    response = await api.post("/recipes", json=leek_soup(pantry))

    assert response.status_code == 201, response.text
    recipe = response.json()
    assert recipe["name"] == "Leek soup"
    assert recipe["version"] == 1
    assert recipe["versions"] == 1
    assert recipe["source"] == "app"
    assert [tag["name"] for tag in recipe["tags"]] == ["pot", "winter"]


async def test_the_ingredients_come_grouped_by_category_with_their_emoji(api, pantry) -> None:
    recipe = (await api.post("/recipes", json=leek_soup(pantry))).json()

    groups = {group["category_id"]: group for group in recipe["groups"]}
    assert list(groups) == ["vegetable", "fish", "fat"]
    assert groups["vegetable"]["emoji"] == "🥬"
    assert [i["name"] for i in groups["vegetable"]["ingredients"]] == ["Leek", "Potato"]
    assert groups["vegetable"]["ingredients"][0]["note"] == "sliced"
    assert groups["fish"]["ingredients"][0]["optional"] is True


async def test_the_macros_are_added_up_in_grams(api, pantry) -> None:
    recipe = (await api.post("/recipes", json=leek_soup(pantry))).json()

    total = recipe["nutrition"]["total"]
    assert total["kcal"] == pytest.approx(1114, abs=2)
    assert recipe["nutrition"]["counted"] == 4
    assert recipe["nutrition"]["ingredients"] == 4
    assert recipe["nutrition"]["uncertainty"] is None
    assert recipe["nutrition"]["per_serving"]["kcal"] == pytest.approx(total["kcal"] / 4, abs=0.2)


async def test_asking_for_more_people_scales_the_quantities(api, pantry) -> None:
    created = (await api.post("/recipes", json=leek_soup(pantry))).json()

    for_six = (await api.get(f"/recipes/{created['id']}", params={"servings": 6})).json()

    assert for_six["servings"] == 4
    assert for_six["requested_servings"] == 6
    puerro = for_six["groups"][0]["ingredients"][0]
    assert puerro["quantity"] == 600
    assert for_six["nutrition"]["total"]["kcal"] == pytest.approx(
        created["nutrition"]["total"]["kcal"] * 1.5, abs=1
    )
    assert for_six["nutrition"]["per_serving"]["kcal"] == pytest.approx(
        created["nutrition"]["per_serving"]["kcal"], abs=1
    )


async def test_an_ingredient_that_cannot_be_converted_is_counted_and_said(api, pantry) -> None:
    body = leek_soup(pantry)
    body["ingredients"].append({"name": "Grandma's sofrito", "quantity": 1, "unit": "unit"})

    recipe = (await api.post("/recipes", json=body)).json()

    assert recipe["nutrition"]["counted"] == 4
    assert recipe["nutrition"]["ingredients"] == 5
    assert "missing" in recipe["nutrition"]["uncertainty"]
    assert "Grandma's sofrito" in recipe["nutrition"]["uncertainty"]
    unresolved = [
        i for group in recipe["groups"] for i in group["ingredients"] if i["food_id"] is None
    ]
    assert [i["name"] for i in unresolved] == ["Grandma's sofrito"]
    assert unresolved[0]["grams"] is None


async def test_an_ingredient_by_name_finds_what_is_already_in_the_pantry(api, pantry) -> None:
    body = {
        "name": "Just leeks",
        "servings": 2,
        "ingredients": [{"name": "leek", "quantity": 200, "unit": "g"}],
    }

    recipe = (await api.post("/recipes", json=body)).json()

    assert recipe["nutrition"]["counted"] == 1
    assert recipe["groups"][0]["ingredients"][0]["food_id"] == pantry["leek"]


async def test_editing_writes_the_next_version_and_keeps_the_old_one(api, pantry) -> None:
    created = (await api.post("/recipes", json=leek_soup(pantry))).json()
    lighter = leek_soup(pantry)
    lighter["ingredients"][2]["quantity"] = 10
    lighter["note"] = "less oil"

    updated = await api.put(f"/recipes/{created['id']}", json=lighter)

    assert updated.status_code == 200, updated.text
    body = updated.json()
    assert body["version"] == 2
    assert body["versions"] == 2
    assert body["note"] == "less oil"
    assert body["nutrition"]["total"]["kcal"] < created["nutrition"]["total"]["kcal"]


async def test_the_previous_version_is_still_there_untouched(api, pantry, schema) -> None:
    created = (await api.post("/recipes", json=leek_soup(pantry))).json()
    await api.put(f"/recipes/{created['id']}", json=leek_soup(pantry, name="Light leek soup"))

    async with schema.begin() as connection:
        await connection.execute(text('set local role "mod_recipes"'))
        rows = (
            await connection.execute(
                text(
                    "select number, sealed_at is not null as sealed from "
                    "recipes.recipes_recipe_version where recipe_id = cast(:id as uuid) "
                    "order by number"
                ),
                {"id": created["id"]},
            )
        ).all()

    assert [(row.number, row.sealed) for row in rows] == [(1, True), (2, True)]


async def test_every_saved_version_is_queued_for_the_log(api, pantry, schema) -> None:
    created = (await api.post("/recipes", json=leek_soup(pantry))).json()
    await api.put(f"/recipes/{created['id']}", json=leek_soup(pantry))

    async with schema.begin() as connection:
        await connection.execute(text('set local role "mod_recipes"'))
        rows = (
            await connection.execute(
                text(
                    "select type, payload, dedup_hash, published_at from "
                    "recipes.recipes_outbox order by id"
                )
            )
        ).all()

    assert [row.type for row in rows] == ["recipes.recipe_saved"] * 2
    assert [row.dedup_hash for row in rows] == [
        f"recipe:{created['id']}:v1",
        f"recipe:{created['id']}:v2",
    ]
    assert all(row.published_at is None for row in rows)
    payload = rows[0].payload if isinstance(rows[0].payload, dict) else json.loads(rows[0].payload)
    assert payload["name"] == "Leek soup"
    assert payload["ingredients"] == 4


async def test_a_recipe_without_ingredients_is_refused(api) -> None:
    response = await api.post("/recipes", json={"name": "Aire", "servings": 2, "ingredients": []})

    assert response.status_code == 422


async def test_an_ingredient_is_a_food_or_a_name_never_both(api, pantry) -> None:
    response = await api.post(
        "/recipes",
        json={
            "name": "Confusa",
            "servings": 2,
            "ingredients": [
                {"food_id": pantry["leek"], "name": "leek", "quantity": 100, "unit": "g"}
            ],
        },
    )

    assert response.status_code == 422


async def test_a_food_that_does_not_exist_is_a_404(api) -> None:
    response = await api.post(
        "/recipes",
        json={
            "name": "Fantasma",
            "servings": 2,
            "ingredients": [
                {
                    "food_id": "00000000-0000-4000-8000-000000000000",
                    "quantity": 100,
                    "unit": "g",
                }
            ],
        },
    )

    assert response.status_code == 404


async def test_two_recipes_cannot_share_a_name(api, pantry) -> None:
    await api.post("/recipes", json=leek_soup(pantry))

    again = await api.post("/recipes", json=leek_soup(pantry))

    assert again.status_code == 409


async def test_the_recipe_book_lists_what_has_been_saved(api, pantry) -> None:
    await api.post("/recipes", json=leek_soup(pantry))

    listed = (await api.get("/recipes")).json()

    assert [recipe["name"] for recipe in listed] == ["Leek soup"]
    assert listed[0]["servings"] == 4
    assert sorted(listed[0]["tags"]) == ["pot", "winter"]


async def test_deleting_takes_its_versions_with_it(api, pantry) -> None:
    created = (await api.post("/recipes", json=leek_soup(pantry))).json()

    gone = await api.delete(f"/recipes/{created['id']}")

    assert gone.status_code == 204
    assert (await api.get(f"/recipes/{created['id']}")).status_code == 404
    assert (await api.get("/recipes")).json() == []


def con_pasos(pantry: dict[str, str]) -> dict:
    body = leek_soup(pantry)
    body["steps"] = [
        {
            "action": "chop",
            "text": "Slice the leek",
            "minutes": 5,
            "equipment": "board",
            "ingredients": [1],
        },
        {
            "action": "peel",
            "text": "Break the potatoes",
            "minutes": 5,
            "equipment": "board",
            "ingredients": [2],
        },
        {
            "action": "saute",
            "text": "Soften the leek in the oil",
            "minutes": 10,
            "equipment": "hob",
            "after": [1],
            "ingredients": [3],
        },
        {
            "action": "simmer",
            "text": "Cocer a fuego lento",
            "minutes": 30,
            "attended": False,
            "equipment": "hob",
            "after": [2, 3],
        },
    ]
    return body


async def test_a_recipe_carries_its_kitchen_diagram(api, pantry) -> None:
    recipe = (await api.post("/recipes", json=con_pasos(pantry))).json()

    kitchen = recipe["kitchen"]
    assert [(one["start"], one["end"]) for one in kitchen["steps"]] == [
        (0, 5),
        (5, 10),
        (10, 20),
        (20, 50),
    ]
    assert kitchen["total_minutes"] == 50
    assert kitchen["active_minutes"] == 20
    assert kitchen["lanes"] == ["hob", "board"]


async def test_each_step_says_what_goes_in_it(api, pantry) -> None:
    recipe = (await api.post("/recipes", json=con_pasos(pantry))).json()

    steps = {one["position"]: one for one in recipe["kitchen"]["steps"]}
    assert steps[1]["ingredients"] == ["Leek"]
    assert steps[3]["ingredients"] == ["Olive oil"]
    assert steps[4]["ingredients"] == []


async def test_an_unattended_step_lets_the_cook_carry_on(api, pantry) -> None:
    body = leek_soup(pantry)
    body["steps"] = [
        {
            "action": "bake",
            "text": "In the oven",
            "minutes": 40,
            "attended": False,
            "equipment": "oven",
        },
        {"action": "chop", "text": "Chop the salad", "minutes": 10, "equipment": "board"},
    ]

    kitchen = (await api.post("/recipes", json=body)).json()["kitchen"]

    assert [one["start"] for one in kitchen["steps"]] == [0, 0]
    assert kitchen["total_minutes"] == 40
    assert kitchen["active_minutes"] == 10


async def test_a_step_that_depends_on_a_later_one_is_refused_with_its_reason(api, pantry) -> None:
    body = leek_soup(pantry)
    body["steps"] = [
        {"action": "chop", "text": "Chop", "minutes": 5, "after": [2]},
        {"action": "mix", "text": "Mix", "minutes": 5},
    ]

    response = await api.post("/recipes", json=body)

    assert response.status_code == 422
    assert "earlier ones" in response.text


async def test_a_step_cannot_use_an_ingredient_that_is_not_there(api, pantry) -> None:
    body = leek_soup(pantry)
    body["steps"] = [{"action": "chop", "text": "Chop", "minutes": 5, "ingredients": [99]}]

    response = await api.post("/recipes", json=body)

    assert response.status_code == 422
    assert "there are only" in response.text


async def test_an_unknown_verb_is_refused(api, pantry) -> None:
    body = leek_soup(pantry)
    body["steps"] = [{"action": "flambear", "text": "Flambear", "minutes": 2}]

    assert (await api.post("/recipes", json=body)).status_code == 422


async def test_two_things_on_the_same_hob_are_said_not_forbidden(api, pantry) -> None:
    body = leek_soup(pantry)
    body["steps"] = [
        {"action": "simmer", "text": "Caldo", "minutes": 40, "attended": False, "equipment": "hob"},
        {"action": "fry", "text": "Sofrito", "minutes": 15, "equipment": "hob"},
    ]

    kitchen = (await api.post("/recipes", json=body)).json()["kitchen"]

    assert kitchen["overlaps"] == [{"equipment": "hob", "positions": [1, 2]}]


async def test_a_recipe_without_steps_has_an_empty_diagram_and_not_an_error(api, pantry) -> None:
    recipe = (await api.post("/recipes", json=leek_soup(pantry))).json()

    assert recipe["kitchen"]["steps"] == []
    assert recipe["kitchen"]["total_minutes"] == 0


async def test_editing_rewrites_the_steps_into_the_new_version(api, pantry) -> None:
    created = (await api.post("/recipes", json=con_pasos(pantry))).json()
    faster = con_pasos(pantry)
    faster["steps"][3]["minutes"] = 20

    updated = (await api.put(f"/recipes/{created['id']}", json=faster)).json()

    assert updated["version"] == 2
    assert updated["kitchen"]["total_minutes"] == 40
    assert created["kitchen"]["total_minutes"] == 50


async def test_the_recipe_comes_with_its_grid_drawn(api, pantry) -> None:
    recipe = (await api.post("/recipes", json=con_pasos(pantry))).json()

    made = recipe["kitchen"]["grid"]
    assert [row["name"] for row in made["rows"]] == [
        "Leek",
        "Olive oil",
        "Potato",
        "Cod",
    ]
    assert [(c["position"], c["column"], c["row"], c["span"]) for c in made["cells"]] == [
        (1, 1, 1, 1),
        (2, 1, 3, 1),
        (3, 2, 1, 2),
        (4, 3, 1, 3),
    ]
    assert made["columns"] == 3
    assert made["notes"] == ["goes into no step: Cod"]


async def test_a_step_says_what_it_depends_on_so_editing_does_not_lose_it(api, pantry) -> None:
    recipe = (await api.post("/recipes", json=con_pasos(pantry))).json()

    steps = {one["position"]: one for one in recipe["kitchen"]["steps"]}
    assert steps[3]["after"] == [1]
    assert steps[3]["uses"] == [3]
    assert steps[4]["after"] == [2, 3]
    assert steps[4]["uses"] == []


async def test_an_archived_recipe_leaves_the_book_and_the_search_but_still_opens(
    api, pantry
) -> None:
    recipe = (await api.post("/recipes", json=leek_soup(pantry))).json()
    assert (await api.post(f"/recipes/{recipe['id']}/archive")).status_code == 204

    book = (await api.get("/recipes")).json()
    assert all(one["id"] != recipe["id"] for one in book)
    archived = (await api.get("/recipes", params={"archived": True})).json()
    assert [one["id"] for one in archived] == [recipe["id"]]
    assert archived[0]["archived"] is True
    opened = (await api.get(f"/recipes/{recipe['id']}")).json()
    assert opened["archived"] is True

    assert (await api.post(f"/recipes/{recipe['id']}/unarchive")).status_code == 204
    assert any(one["id"] == recipe["id"] for one in (await api.get("/recipes")).json())
    assert (
        await api.post("/recipes/00000000-0000-0000-0000-000000000000/archive")
    ).status_code == 404
