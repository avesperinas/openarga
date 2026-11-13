from __future__ import annotations

import pytest

READ = {"x-arga-scopes": "recipes:read"}
WRITE = {"x-arga-scopes": "recipes:read recipes:write"}

CHICKEN = "Chicken, broiler or fryers, breast, skinless, boneless, meat only, raw"
LEEK = "Leeks, (bulb and lower leaf-portion), raw"


async def imported(api, name: str, ref: str, **extra) -> dict:
    response = await api.post(
        "/foods",
        json={
            "source": "usda",
            "source_ref": ref,
            "name": name,
            "category_id": "protein",
            "macros": {"kcal": 120, "protein": 22.5, "fat": 2.62, "carbs": 0},
            **extra,
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def call(api, name: str, arguments: dict, headers: dict = WRITE):
    return api.post(f"/tools/{name}", json=arguments, headers=headers)


async def test_the_alias_is_yours_and_the_source_name_stays(api) -> None:
    food = await imported(api, CHICKEN, "171077")

    named = await api.put(f"/foods/{food['id']}/alias", json={"alias": "  Chicken breast "})

    assert named.status_code == 200, named.text
    assert named.json()["alias"] == "Chicken breast"
    assert named.json()["name"] == CHICKEN
    assert named.json()["source"] == "usda"


async def test_the_alias_is_given_when_importing(api) -> None:
    food = await imported(api, CHICKEN, "171077", alias="Chicken breast")

    assert food["alias"] == "Chicken breast"
    assert food["name"] == CHICKEN


async def test_the_pantry_is_searched_and_ordered_by_what_you_call_it(api) -> None:
    await imported(api, CHICKEN, "171077", alias="Hen")
    await imported(api, LEEK, "11246", alias="Baby garlic")

    everything = (await api.get("/foods")).json()
    found = (await api.get("/foods", params={"query": "hen"})).json()

    assert [food["alias"] for food in everything] == ["Baby garlic", "Hen"]
    assert [food["name"] for food in found] == [CHICKEN]


async def test_emptying_the_alias_takes_it_off(api) -> None:
    food = await imported(api, CHICKEN, "171077", alias="Chicken")

    cleared = await api.put(f"/foods/{food['id']}/alias", json={"alias": "   "})

    assert cleared.json()["alias"] is None


async def test_one_alias_names_one_food(api) -> None:
    await imported(api, CHICKEN, "171077", alias="Chicken")
    other = await imported(api, LEEK, "11246")

    clash = await api.put(f"/foods/{other['id']}/alias", json={"alias": "chicken"})

    assert clash.status_code == 409
    assert CHICKEN in clash.json()["detail"]


async def test_a_food_that_is_not_there_is_a_404(api) -> None:
    missing = await api.put(
        "/foods/00000000-0000-4000-8000-000000000000/alias", json={"alias": "Chicken"}
    )

    assert missing.status_code == 404


async def test_the_recipe_reads_with_your_names(api) -> None:
    food = await imported(api, CHICKEN, "171077", alias="Chicken breast")
    recipe = await api.post(
        "/recipes",
        json={
            "name": "Grilled chicken",
            "servings": 2,
            "ingredients": [{"food_id": food["id"], "quantity": 300, "unit": "g"}],
            "steps": [
                {
                    "action": "grill",
                    "text": "Grilled",
                    "minutes": 10,
                    "equipment": "hob",
                    "ingredients": [1],
                }
            ],
        },
    )
    assert recipe.status_code == 201, recipe.text

    body = recipe.json()
    assert body["groups"][0]["ingredients"][0]["name"] == "Chicken breast"
    assert body["kitchen"]["steps"][0]["ingredients"] == ["Chicken breast"]
    assert body["kitchen"]["grid"]["rows"][0]["name"] == "Chicken breast"


async def test_a_dictated_recipe_finds_the_food_by_its_alias(api) -> None:
    await imported(api, CHICKEN, "171077", alias="Chicken breast")

    saved = (
        await call(
            api,
            "create_recipe",
            {
                "name": "Grilled chicken",
                "servings": 2,
                "ingredients": [{"name": "chicken breast", "quantity": 300, "unit": "g"}],
            },
        )
    ).json()["content"]["saved"]

    assert saved["unresolved_ingredients"] == []
    assert saved["per_serving"]["kcal"] == pytest.approx(180)


async def test_recipes_are_found_by_the_alias_of_an_ingredient(api) -> None:
    food = await imported(api, CHICKEN, "171077", alias="Chicken breast")
    await api.post(
        "/recipes",
        json={
            "name": "Grilled chicken",
            "servings": 2,
            "ingredients": [{"food_id": food["id"], "quantity": 300, "unit": "g"}],
        },
    )

    found = (await call(api, "find_recipes", {"ingredient": "breast"}, headers=READ)).json()

    assert [one["name"] for one in found["content"]["recipes"]] == ["Grilled chicken"]


async def test_the_model_names_a_food_and_the_pantry_shows_it(api) -> None:
    food = await imported(api, CHICKEN, "171077")

    named = (
        await call(api, "set_food_alias", {"food_id": food["id"], "alias": "Chicken breast"})
    ).json()["content"]["food"]
    found = (await call(api, "find_foods", {"query": "breast"}, headers=READ)).json()

    assert named["alias"] == "Chicken breast"
    assert named["name"] == CHICKEN
    assert [one["alias"] for one in found["content"]["foods"]] == ["Chicken breast"]


async def test_a_taken_alias_is_said_to_the_model_and_nothing_changes(api) -> None:
    await imported(api, CHICKEN, "171077", alias="Chicken")
    other = await imported(api, LEEK, "11246")

    answer = (
        await call(api, "set_food_alias", {"food_id": other["id"], "alias": "Chicken"})
    ).json()["content"]

    assert answer["food"] is None
    assert "is already the alias" in answer["note"]


async def test_naming_a_food_with_only_the_read_scope_is_refused_by_postgres(api) -> None:
    food = await imported(api, CHICKEN, "171077")

    refused = await call(api, "set_food_alias", {"food_id": food["id"], "alias": "Chicken"}, READ)

    assert refused.status_code == 403
    assert "mod_recipes_read" in refused.json()["detail"]
