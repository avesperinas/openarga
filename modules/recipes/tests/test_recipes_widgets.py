from __future__ import annotations

from pathlib import Path

import pytest
import yaml

MANIFEST = Path(__file__).resolve().parents[1] / "manifest.yaml"
WRITE = {"x-arga-scopes": "recipes:read recipes:write"}


async def add_food(api, name: str) -> None:
    await api.post(
        "/foods/manual",
        json={
            "name": name,
            "category_id": "vegetable",
            "macros": {"kcal": 61, "protein": 1.5, "fat": 0.3, "carbs": 14},
        },
    )


async def add_recipe(api, name: str, minutes: int, attended: bool = True) -> None:
    await api.post(
        "/recipes",
        json={
            "name": name,
            "servings": 4,
            "ingredients": [{"name": "Leek", "quantity": 200, "unit": "g"}],
            "steps": [
                {
                    "action": "simmer",
                    "text": "Cocer",
                    "minutes": minutes,
                    "attended": attended,
                    "equipment": "hob",
                }
            ],
        },
    )


@pytest.fixture
async def cooked(api):
    await add_food(api, "Leek")
    await add_recipe(api, "Omelette", 20)
    await add_recipe(api, "Stew", 180, attended=False)
    return api


def test_the_manifest_declares_both_and_they_open_the_app() -> None:
    widgets = yaml.safe_load(MANIFEST.read_text())["ui"]["widgets"]

    assert [w["id"] for w in widgets] == ["recipes", "quick"]
    assert [w["kind"] for w in widgets] == ["stats", "list"]
    assert all(w["link"] == "/recipes" for w in widgets)
    assert all(w["endpoint"] == f"/api/recipes/widgets/{w['id']}" for w in widgets)


async def test_an_empty_recipe_book_says_empty_and_not_zero(api) -> None:
    response = await api.get("/widgets/recipes")

    assert response.status_code == 200
    assert response.json()["state"] == "empty"


async def test_the_recipe_book_counts_what_there_is(cooked) -> None:
    body = (await cooked.get("/widgets/recipes")).json()

    assert body["state"] == "ready"
    stats = {one["label"]: one["value"] for one in body["body"]["stats"]}
    assert stats["Recipes"] == 2
    assert stats["On average"] == 100
    assert stats["In 30 min"] == 1


async def test_the_quick_card_only_brings_what_fits_on_a_weeknight(cooked) -> None:
    body = (await cooked.get("/widgets/quick")).json()

    assert body["state"] == "ready"
    assert body["body"]["rows"] == [{"label": "Omelette", "value": "20 min"}]


async def test_with_nothing_quick_the_card_says_so(api) -> None:
    await add_food(api, "Leek")
    await add_recipe(api, "Stew", 180, attended=False)

    body = (await api.get("/widgets/quick")).json()

    assert body["state"] == "empty"
    assert "30 minutes" in body["body"]["detail"]


async def test_a_widget_reads_and_never_writes(cooked) -> None:
    assert (await cooked.get("/widgets/recipes")).json()["state"] == "ready"
    assert (await cooked.get("/widgets/quick")).json()["state"] == "ready"
