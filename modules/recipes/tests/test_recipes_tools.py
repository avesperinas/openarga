from __future__ import annotations

from pathlib import Path

import httpx
import pytest
import yaml

MANIFEST = Path(__file__).resolve().parents[1] / "manifest.yaml"
READ = {"x-arga-scopes": "recipes:read"}
WRITE = {"x-arga-scopes": "recipes:read recipes:write"}


async def add_food(api, name: str, category: str, macros: dict, **measures) -> str:
    response = await api.post(
        "/foods/manual", json={"name": name, "category_id": category, "macros": macros, **measures}
    )
    return response.json()["id"]


@pytest.fixture
async def pantry(api) -> dict[str, str]:
    return {
        "leek": await add_food(
            api, "Leek", "vegetable", {"kcal": 61, "protein": 1.5, "fat": 0.3, "carbs": 14.15}
        ),
        "potato": await add_food(
            api, "Potato", "vegetable", {"kcal": 77, "protein": 2, "fat": 0.1, "carbs": 17.5}
        ),
    }


def call(api, name: str, arguments: dict, headers: dict = READ):
    return api.post(f"/tools/{name}", json=arguments, headers=headers)


def receta(**overrides) -> dict:
    body = {
        "name": "Leek soup",
        "servings": 4,
        "tags": ["winter"],
        "ingredients": [
            {"name": "Leek", "quantity": 400, "unit": "g"},
            {"name": "Potato", "quantity": 600, "unit": "g"},
        ],
        "steps": [
            {"action": "chop", "text": "Chop the leek", "minutes": 5, "equipment": "board"},
            {
                "action": "simmer",
                "text": "Cocer a fuego lento",
                "minutes": 30,
                "attended": False,
                "equipment": "hob",
                "after": [1],
            },
        ],
    }
    body.update(overrides)
    return body


async def test_the_listed_tools_are_the_ones_the_manifest_declares(api) -> None:
    manifest = yaml.safe_load(MANIFEST.read_text())
    served = (await api.get("/tools")).json()

    assert {tool["name"] for tool in served} == {tool["name"] for tool in manifest["tools"]}
    assert {tool["name"] for tool in served} == {
        "find_recipes",
        "get_recipe",
        "find_foods",
        "list_categories",
        "list_tags",
        "list_nutrients",
        "search_food_sources",
        "import_food",
        "add_manual_food",
        "correct_food",
        "set_food_alias",
        "replace_food",
        "create_recipe",
        "update_recipe",
        "delete_recipe",
        "archive_recipe",
        "unarchive_recipe",
        "share_recipe",
    }
    assert all("properties" in tool["input_schema"] for tool in served)


async def test_what_changes_something_of_yours_carries_the_write_scope(api) -> None:
    manifest = yaml.safe_load(MANIFEST.read_text())

    writing = {t["name"] for t in manifest["tools"] if t["scope"] == "recipes:write"}

    assert writing == {
        "search_food_sources",
        "import_food",
        "add_manual_food",
        "correct_food",
        "set_food_alias",
        "replace_food",
        "create_recipe",
        "update_recipe",
        "delete_recipe",
        "archive_recipe",
        "unarchive_recipe",
        "share_recipe",
    }


async def test_without_a_scope_of_this_module_nothing_runs(api, pantry) -> None:
    assert (await call(api, "find_recipes", {}, headers={})).status_code == 403
    assert (
        await call(api, "find_recipes", {}, headers={"x-arga-scopes": "training:read"})
    ).status_code == 403


async def test_writing_with_only_the_read_scope_is_refused_by_postgres(api, pantry) -> None:
    response = await call(api, "create_recipe", receta(), headers=READ)

    assert response.status_code == 403
    assert "mod_recipes_read" in response.json()["detail"]


async def test_a_recipe_is_written_from_a_dictated_one(api, pantry) -> None:
    response = await call(api, "create_recipe", receta(), headers=WRITE)

    assert response.status_code == 200, response.text
    saved = response.json()["content"]["saved"]
    assert saved["name"] == "Leek soup"
    assert saved["version"] == 1
    assert saved["total_minutes"] == 35
    assert saved["active_minutes"] == 5
    assert saved["unresolved_ingredients"] == []


async def test_an_ingredient_the_pantry_does_not_have_is_left_to_resolve(api, pantry) -> None:
    body = receta()
    body["ingredients"].append({"name": "Grandma's sofrito", "quantity": 1, "unit": "unit"})

    saved = (await call(api, "create_recipe", body, headers=WRITE)).json()["content"]["saved"]

    assert saved["unresolved_ingredients"] == ["Grandma's sofrito"]
    assert "1 of 3" in saved["macros_note"]


async def test_editing_writes_a_new_version_and_keeps_the_old(api, pantry) -> None:
    created = (await call(api, "create_recipe", receta(), headers=WRITE)).json()["content"]["saved"]
    lighter = receta(servings=6)
    lighter["recipe_id"] = created["recipe_id"]

    updated = (await call(api, "update_recipe", lighter, headers=WRITE)).json()["content"]["saved"]

    assert updated["version"] == 2
    assert updated["servings"] == 6
    found = (await call(api, "get_recipe", {"recipe_id": created["recipe_id"]})).json()["content"]
    assert found["recipe"]["versions"] == 2


async def test_a_recipe_can_be_asked_for_other_people(api, pantry) -> None:
    created = (await call(api, "create_recipe", receta(), headers=WRITE)).json()["content"]["saved"]

    for_two = (
        await call(api, "get_recipe", {"recipe_id": created["recipe_id"], "servings": 2})
    ).json()["content"]["recipe"]

    assert for_two["servings"] == 4
    assert for_two["requested_servings"] == 2
    assert for_two["groups"][0]["ingredients"][0]["quantity"] == 200


async def test_a_recipe_comes_with_its_kitchen_diagram(api, pantry) -> None:
    created = (await call(api, "create_recipe", receta(), headers=WRITE)).json()["content"]["saved"]

    recipe = (await call(api, "get_recipe", {"recipe_id": created["recipe_id"]})).json()["content"][
        "recipe"
    ]

    kitchen = recipe["kitchen"]
    assert [(one["start"], one["end"]) for one in kitchen["steps"]] == [(0, 5), (5, 35)]
    assert kitchen["total_minutes"] == 35


async def test_recipes_are_searched_by_what_you_actually_ask(api, pantry) -> None:
    await call(api, "create_recipe", receta(), headers=WRITE)
    long = receta(
        name="Stew",
        tags=["sunday"],
        ingredients=[{"name": "Potato", "quantity": 800, "unit": "g"}],
    )
    long["steps"] = [
        {
            "action": "simmer",
            "text": "Simmer",
            "minutes": 180,
            "attended": False,
            "equipment": "hob",
        }
    ]
    await call(api, "create_recipe", long, headers=WRITE)

    by_name = (await call(api, "find_recipes", {"query": "leek s"})).json()["content"]
    by_tag = (await call(api, "find_recipes", {"tag": "sunday"})).json()["content"]
    by_time = (await call(api, "find_recipes", {"max_minutes": 60})).json()["content"]
    by_work = (await call(api, "find_recipes", {"max_active_minutes": 10})).json()["content"]
    by_ingredient = (await call(api, "find_recipes", {"ingredient": "leek"})).json()["content"]

    assert [r["name"] for r in by_name["recipes"]] == ["Leek soup"]
    assert [r["name"] for r in by_tag["recipes"]] == ["Stew"]
    assert [r["name"] for r in by_time["recipes"]] == ["Leek soup"]
    assert sorted(r["name"] for r in by_work["recipes"]) == ["Leek soup", "Stew"]
    assert [r["name"] for r in by_ingredient["recipes"]] == ["Leek soup"]
    assert by_name["recipes_in_book"] == 2


async def test_the_pantry_is_what_the_model_looks_at_before_writing(api, pantry) -> None:
    found = (await call(api, "find_foods", {"query": "lee"})).json()["content"]

    assert [food["name"] for food in found["foods"]] == ["Leek"]
    assert found["foods"][0]["per_100g"]["kcal"] == 61


async def test_a_recipe_that_is_not_yours_is_said_and_not_invented(api, pantry) -> None:
    response = await call(api, "get_recipe", {"recipe_id": "00000000-0000-4000-8000-000000000000"})

    assert response.status_code == 200
    assert response.json()["content"]["recipe"] is None
    assert "is not in your recipe book" in response.json()["content"]["note"]


async def test_bad_arguments_are_a_422_and_an_unknown_tool_a_404(api, pantry) -> None:
    assert (await call(api, "find_recipes", {"limit": 0})).status_code == 422
    assert (await call(api, "does_not_exist", {})).status_code == 404


USDA_LEEK = {
    "foods": [
        {
            "fdcId": 11246,
            "description": "Leeks, raw",
            "foodCategory": "Vegetables and Vegetable Products",
            "foodNutrients": [
                {"nutrientId": 1008, "value": 61},
                {"nutrientId": 1003, "value": 1.5},
                {"nutrientId": 1004, "value": 0.3},
                {"nutrientId": 1005, "value": 14.15},
            ],
        }
    ]
}


@pytest.fixture
async def sources(api, hub):
    await hub.with_usda()

    def handler(request: httpx.Request) -> httpx.Response:
        if "nal.usda.gov" in request.url.host:
            return httpx.Response(200, json=USDA_LEEK)
        return httpx.Response(200, json={"hits": []})

    hub.answer(handler)
    return api


async def test_the_categories_are_read_before_saving_a_food(api) -> None:
    found = (await call(api, "list_categories", {})).json()["content"]["categories"]

    assert len(found) == 13
    assert "supplement" in {one["category_id"] for one in found}
    assert "vegetable" in {one["category_id"] for one in found}
    assert all(one["emoji"] for one in found)


async def test_the_tags_that_already_exist_are_read(api, pantry) -> None:
    await call(api, "create_recipe", receta(), headers=WRITE)

    found = (await call(api, "list_tags", {})).json()["content"]["tags"]

    assert [tag["name"] for tag in found] == ["winter"]


async def test_spending_your_usda_quota_needs_the_write_scope(sources) -> None:
    refused = await call(sources, "search_food_sources", {"query": "leek"}, headers=READ)

    assert refused.status_code == 403
    assert "recipes:write" in refused.json()["detail"]
    assert "candidates" not in refused.text


async def test_a_food_is_searched_outside_and_imported_with_the_macros_it_came_with(
    sources,
) -> None:
    found = (await call(sources, "search_food_sources", {"query": "leek"}, headers=WRITE)).json()[
        "content"
    ]
    candidate = found["candidates"][0]

    saved = (
        await call(
            sources,
            "import_food",
            {
                "source": candidate["source"],
                "source_ref": candidate["source_ref"],
                "name": "Leek",
                "category_id": candidate["category_hint"],
                "macros": candidate["macros"],
            },
            headers=WRITE,
        )
    ).json()["content"]["food"]

    assert candidate["category_hint"] == "vegetable"
    assert saved["per_100g"]["kcal"] == 61
    assert saved["source"] == "usda"
    assert saved["corrected"] is False
    pantry = (await call(sources, "find_foods", {"query": "leek"})).json()["content"]
    assert [food["name"] for food in pantry["foods"]] == ["Leek"]


async def test_pure_oil_is_saved_whole(api) -> None:
    body = {
        "source": "usda",
        "source_ref": "173577",
        "name": "Fish oil, salmon",
        "category_id": "fat",
        "alias": "salmon oil",
        "macros": {"kcal": 902, "protein": 0, "fat": 100, "carbs": 0},
    }

    saved = (await call(api, "import_food", body, headers=WRITE)).json()["content"]["food"]

    assert saved["per_100g"]["kcal"] == 902
    found = (await call(api, "find_foods", {"query": "salmon"})).json()["content"]["foods"]
    assert [food["per_100g"]["kcal"] for food in found] == [902]


async def test_importing_the_same_thing_twice_does_not_make_two_foods(sources) -> None:
    body = {
        "source": "usda",
        "source_ref": "11246",
        "name": "Leek",
        "category_id": "vegetable",
        "macros": {"kcal": 61, "protein": 1.5, "fat": 0.3, "carbs": 14.15},
    }

    first = (await call(sources, "import_food", body, headers=WRITE)).json()["content"]["food"]
    again = (await call(sources, "import_food", body, headers=WRITE)).json()["content"]["food"]

    assert first["food_id"] == again["food_id"]


async def test_a_source_that_is_down_is_said_and_does_not_look_like_an_empty_shelf(
    api, hub
) -> None:
    await hub.with_usda()

    def down(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("no network", request=request)

    hub.answer(down)

    found = (await call(api, "search_food_sources", {"query": "leek"}, headers=WRITE)).json()[
        "content"
    ]

    assert found["candidates"] == []
    assert {one["source"] for one in found["failed"]} == {"usda", "off"}


USDA_FISH_OIL = {
    "foods": [
        {
            "fdcId": 173577,
            "description": "Fish oil, salmon",
            "foodCategory": "Fats and Oils",
            "foodNutrients": [
                {"nutrientId": 1008, "value": 902},
                {"nutrientId": 1003, "value": 0},
                {"nutrientId": 1004, "value": 100},
                {"nutrientId": 1005, "value": 0},
            ],
        }
    ]
}
OFF_BAD_SALT = {
    "hits": [
        {
            "code": "0000000000024",
            "product_name": "Synthetic coffee with the salt misplaced",
            "nutriments": {
                "energy-kcal_100g": 40,
                "proteins_100g": 1,
                "fat_100g": 1,
                "carbohydrates_100g": 7,
                "salt_100g": 3210,
            },
        },
        {
            "code": "0000000000031",
            "product_name": "Synthetic coffee",
            "nutriments": {
                "energy-kcal_100g": 2,
                "proteins_100g": 0.1,
                "fat_100g": 0,
                "carbohydrates_100g": 0,
            },
        },
    ]
}


async def test_one_impossible_candidate_does_not_sink_the_search(api, hub) -> None:
    await hub.with_usda()

    def handler(request: httpx.Request) -> httpx.Response:
        if "nal.usda.gov" in request.url.host:
            return httpx.Response(200, json=USDA_FISH_OIL)
        return httpx.Response(200, json=OFF_BAD_SALT)

    hub.answer(handler)

    response = await call(api, "search_food_sources", {"query": "fish oil"}, headers=WRITE)

    assert response.status_code == 200
    found = response.json()["content"]
    assert [(one["name"], one["macros"]["kcal"]) for one in found["candidates"]] == [
        ("Fish oil, salmon", 902),
        ("Synthetic coffee", 2),
    ]
    assert found["failed"] == []
    [discarded] = found["discarded"]
    assert discarded["name"] == "Synthetic coffee with the salt misplaced"
    assert "sal" in discarded["reason"]


async def test_a_source_that_fails_now_and_then_is_asked_again(api, hub) -> None:
    await hub.with_usda()
    asked: list[str] = []

    def flaky(request: httpx.Request) -> httpx.Response:
        if "nal.usda.gov" not in request.url.host:
            return httpx.Response(200, json={"hits": []})
        asked.append(request.url.path)
        if len(asked) == 1:
            return httpx.Response(500)
        return httpx.Response(200, json=USDA_LEEK)

    hub.answer(flaky)

    found = (await call(api, "search_food_sources", {"query": "leek"}, headers=WRITE)).json()[
        "content"
    ]

    assert len(asked) == 2
    assert found["failed"] == []
    assert [one["source_ref"] for one in found["candidates"]] == ["11246"]


async def test_the_same_search_twice_asks_the_source_once(api, hub) -> None:
    await hub.with_usda()
    asked: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        asked.append(request.url.host)
        if "nal.usda.gov" in request.url.host:
            return httpx.Response(200, json=USDA_LEEK)
        return httpx.Response(200, json={"hits": []})

    hub.answer(handler)

    first = (await call(api, "search_food_sources", {"query": "leek"}, headers=WRITE)).json()
    again = (await call(api, "search_food_sources", {"query": " Leek "}, headers=WRITE)).json()

    assert first["content"]["candidates"] == again["content"]["candidates"]
    assert len(asked) == 2


async def test_steps_say_their_closed_values_and_count_from_one(api) -> None:
    served = {tool["name"]: tool for tool in (await api.get("/tools")).json()}
    step = served["create_recipe"]["input_schema"]["$defs"]["StepIn"]["properties"]

    assert "toast" in step["action"]["enum"]
    assert "air_fryer" in step["equipment"]["enum"]
    assert "from 1" in step["after"]["description"]
    assert "from 1" in step["ingredients"]["description"]


async def test_the_air_fryer_has_its_own_lane_and_toasting_is_a_step(api, pantry) -> None:
    body = receta(
        name="Air-fried potatoes",
        steps=[
            {"action": "chop", "text": "Cortar", "minutes": 5, "equipment": "board"},
            {
                "action": "fry",
                "text": "Fry without oil",
                "minutes": 20,
                "attended": False,
                "equipment": "air_fryer",
                "after": [1],
                "ingredients": [2],
            },
            {"action": "toast", "text": "Toast the bread", "minutes": 3, "equipment": "oven"},
        ],
    )

    created = (await call(api, "create_recipe", body, headers=WRITE)).json()["content"]["saved"]
    recipe = (await call(api, "get_recipe", {"recipe_id": created["recipe_id"]})).json()["content"][
        "recipe"
    ]

    assert recipe["kitchen"]["lanes"] == ["oven", "air_fryer", "board"]
    assert [one["action"] for one in recipe["kitchen"]["steps"]] == ["chop", "fry", "toast"]


async def test_what_no_source_has_is_typed_and_stays_marked_as_typed(api) -> None:
    saved = (
        await call(
            api,
            "add_manual_food",
            {
                "name": "Grandma's sofrito",
                "category_id": "other",
                "macros": {"kcal": 120, "protein": 1.2, "fat": 10, "carbs": 6},
                "grams_per_unit": 200,
            },
            headers=WRITE,
        )
    ).json()["content"]["food"]

    assert saved["source"] == "manual"
    assert saved["grams_per_unit"] == 200


async def test_a_category_that_does_not_exist_is_said_instead_of_guessed(api) -> None:
    answer = (
        await call(
            api,
            "add_manual_food",
            {
                "name": "Something",
                "category_id": "does-not-exist",
                "macros": {"kcal": 10, "protein": 1, "fat": 1, "carbs": 1},
            },
            headers=WRITE,
        )
    ).json()["content"]

    assert answer["food"] is None
    assert "list_categories" in answer["note"]


async def test_macros_can_be_corrected_and_the_food_says_so(api, pantry) -> None:
    corrected = (
        await call(
            api,
            "correct_food",
            {
                "food_id": pantry["leek"],
                "macros": {"kcal": 55, "protein": 1.5, "fat": 0.3, "carbs": 12},
            },
            headers=WRITE,
        )
    ).json()["content"]["food"]

    assert corrected["per_100g"]["kcal"] == 55
    assert corrected["corrected"] is True


async def test_a_dictated_recipe_can_be_finished_without_opening_the_app(sources) -> None:
    candidate = (
        await call(sources, "search_food_sources", {"query": "leek"}, headers=WRITE)
    ).json()["content"]["candidates"][0]
    await call(
        sources,
        "import_food",
        {
            "source": candidate["source"],
            "source_ref": candidate["source_ref"],
            "name": "Leek",
            "category_id": "vegetable",
            "macros": candidate["macros"],
        },
        headers=WRITE,
    )

    saved = (
        await call(
            sources,
            "create_recipe",
            {
                "name": "Steamed leeks",
                "servings": 2,
                "ingredients": [{"name": "Leek", "quantity": 400, "unit": "g"}],
            },
            headers=WRITE,
        )
    ).json()["content"]["saved"]

    assert saved["unresolved_ingredients"] == []
    assert saved["macros_note"] is None
    assert saved["per_serving"]["kcal"] == 122


async def test_a_recipe_is_deleted_only_when_its_name_is_said_out_loud(api, pantry) -> None:
    created = (await call(api, "create_recipe", receta(), headers=WRITE)).json()["content"]["saved"]

    wrong = (
        await call(
            api,
            "delete_recipe",
            {"recipe_id": created["recipe_id"], "name": "Stew"},
            headers=WRITE,
        )
    ).json()["content"]

    assert wrong["deleted"] is None
    assert "Leek soup" in wrong["note"]
    assert (await call(api, "find_recipes", {})).json()["content"]["recipes_in_book"] == 1

    right = (
        await call(
            api,
            "delete_recipe",
            {"recipe_id": created["recipe_id"], "name": "leek soup "},
            headers=WRITE,
        )
    ).json()["content"]

    assert right["deleted"]["name"] == "Leek soup"
    assert (await call(api, "find_recipes", {})).json()["content"]["recipes_in_book"] == 0
