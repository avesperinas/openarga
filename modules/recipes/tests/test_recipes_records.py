from __future__ import annotations

from sqlalchemy import text
from test_recipes_recipes import leek_soup, pantry  # noqa: F401 - the pantry is a fixture

import arga_contracts as contracts
from recipes import records
from recipes.db import engine


async def built() -> dict[str, dict]:
    async with engine().begin() as connection:
        await connection.execute(text('set local role "mod_recipes"'))
        found = await records.build(connection)
    for one in found:
        assert one == contracts.record(**one)
    return {one["id"]: one for one in found}


async def test_each_recipe_is_a_card_and_the_pantry_another(api, pantry) -> None:  # noqa: F811
    recipe = (await api.post("/recipes", json=leek_soup(pantry))).json()

    found = await built()

    card = found[f"recipe:{recipe['id']}"]
    assert card["title"] == "Leek soup" and card["folder"] == "Recipes"
    assert card["href"] == f"/recipes/recipe/{recipe['id']}"
    props = card["properties"]
    assert props["servings"] == 4 and props["version"] == 1
    assert props["tags"] == ["pot", "winter"]
    assert props["kcal_serving"] == round(recipe["nutrition"]["per_serving"]["kcal"])
    assert "- Leek: 400 g · sliced" in card["body"]
    assert "- Cod: 200 g (optional)" in card["body"]
    assert "## Per serving" in card["body"]

    shelf = found["pantry"]
    assert shelf["properties"] == {"foods": 4}
    assert "| Olive oil | 884 | 0 | 0 | 100 | manual |" in shelf["body"]
