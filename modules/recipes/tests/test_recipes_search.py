from __future__ import annotations

import pytest
from test_recipes_tools import WRITE, add_food, call, receta

from recipes import foods

MACROS = {"kcal": 89, "protein": 1.1, "fat": 0.3, "carbs": 22.8}


@pytest.fixture
async def fruits(api) -> None:
    for name in ("Batido de plátano", "Plátano", "Chocolate con plátano", "Platanito frito"):
        await add_food(api, name, "fruit", MACROS)


async def test_the_pantry_finds_without_accents_and_what_starts_the_same_first(api, fruits) -> None:
    found = (await api.get("/foods", params={"query": "platano"})).json()

    assert [one["name"] for one in found] == [
        "Plátano",
        "Batido de plátano",
        "Chocolate con plátano",
    ]
    started = (await api.get("/foods", params={"query": "PLAT"})).json()
    assert [one["name"] for one in started][:2] == ["Platanito frito", "Plátano"]


async def test_claude_finds_foods_and_recipes_the_same_way(api, fruits) -> None:
    await add_food(api, "Puerro", "vegetable", MACROS)
    await add_food(api, "Patata", "vegetable", MACROS)
    for name in ("Crema de lentejas", "Lentejas estofadas", "Ensalada de lentejas"):
        await call(api, "create_recipe", receta(name=name), headers=WRITE)

    pantry = (await call(api, "find_foods", {"query": "platano"})).json()["content"]
    book = (await call(api, "find_recipes", {"query": "lentéjas"})).json()["content"]
    by_ingredient = (await call(api, "find_recipes", {"ingredient": "PÚERRO"})).json()["content"]

    assert [one["name"] for one in pantry["foods"]][0] == "Plátano"
    assert [one["name"] for one in book["recipes"]] == [
        "Lentejas estofadas",
        "Crema de lentejas",
        "Ensalada de lentejas",
    ]
    assert len(by_ingredient["recipes"]) == 3


def test_closeness_is_the_same_scale_as_the_database() -> None:
    assert foods.fold("Ñoquis de CALABAZA, pequeños") == "noquis de calabaza, pequenos"
    assert foods.closeness("platano", "Plátano") == 0
    assert foods.closeness("plat", "Plátano") == 1
    assert foods.closeness("plat", "Batido de plátano") == 2
    assert foods.closeness("tano", "Batido de plátano") == 3
    assert foods.closeness("kiwi", "Plátano") is None


async def test_percent_and_underscore_are_searched_as_they_are(api) -> None:
    for name in ("Chocolate 85% cacao", "Chocolate 85 cacao", "Salsa a_b", "Salsa axb"):
        await add_food(api, name, "other", MACROS)

    percent = (await api.get("/foods", params={"query": "85%"})).json()
    underscore = (await api.get("/foods", params={"query": "a_b"})).json()

    assert [one["name"] for one in percent] == ["Chocolate 85% cacao"]
    assert [one["name"] for one in underscore] == ["Salsa a_b"]
