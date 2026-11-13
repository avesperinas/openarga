from __future__ import annotations

import pytest
from test_recipes_tools import WRITE, add_food, call, receta

from recipes import foods

MACROS = {"kcal": 89, "protein": 1.1, "fat": 0.3, "carbs": 22.8}


@pytest.fixture
async def fruits(api) -> None:
    for name in (
        "Pl\u00e1tano shake",
        "Pl\u00e1tano",
        "Chocolate with pl\u00e1tano",
        "Platanito fried",
    ):
        await add_food(api, name, "fruit", MACROS)


async def test_the_pantry_finds_without_accents_and_what_starts_the_same_first(api, fruits) -> None:
    found = (await api.get("/foods", params={"query": "platano"})).json()

    assert [one["name"] for one in found] == [
        "Pl\u00e1tano",
        "Pl\u00e1tano shake",
        "Chocolate with pl\u00e1tano",
    ]
    started = (await api.get("/foods", params={"query": "PLAT"})).json()
    assert [one["name"] for one in started][:2] == ["Platanito fried", "Pl\u00e1tano"]


async def test_claude_finds_foods_and_recipes_the_same_way(api, fruits) -> None:
    await add_food(api, "Leek", "vegetable", MACROS)
    await add_food(api, "Potato", "vegetable", MACROS)
    for name in ("Cream of l\u00e9ntils", "L\u00e9ntils stew", "Salad of l\u00e9ntils"):
        await call(api, "create_recipe", receta(name=name), headers=WRITE)

    pantry = (await call(api, "find_foods", {"query": "platano"})).json()["content"]
    book = (await call(api, "find_recipes", {"query": "lentils"})).json()["content"]
    by_ingredient = (await call(api, "find_recipes", {"ingredient": "L\u00c9EK"})).json()["content"]

    assert [one["name"] for one in pantry["foods"]][0] == "Pl\u00e1tano"
    assert [one["name"] for one in book["recipes"]] == [
        "L\u00e9ntils stew",
        "Cream of l\u00e9ntils",
        "Salad of l\u00e9ntils",
    ]
    assert len(by_ingredient["recipes"]) == 3


def test_closeness_is_the_same_scale_as_the_database() -> None:
    assert foods.fold("\u00d1oquis of PUMPKIN, sm\u00e0ll") == "noquis of pumpkin, small"
    assert foods.closeness("platano", "Pl\u00e1tano") == 0
    assert foods.closeness("plat", "Pl\u00e1tano") == 1
    assert foods.closeness("plat", "Shake with pl\u00e1tano") == 2
    assert foods.closeness("tano", "Shake with pl\u00e1tano") == 3
    assert foods.closeness("kiwi", "Pl\u00e1tano") is None


async def test_percent_and_underscore_are_searched_as_they_are(api) -> None:
    for name in ("Chocolate 85% cacao", "Chocolate 85 cacao", "Sauce a_b", "Sauce axb"):
        await add_food(api, name, "other", MACROS)

    percent = (await api.get("/foods", params={"query": "85%"})).json()
    underscore = (await api.get("/foods", params={"query": "a_b"})).json()

    assert [one["name"] for one in percent] == ["Chocolate 85% cacao"]
    assert [one["name"] for one in underscore] == ["Sauce a_b"]
