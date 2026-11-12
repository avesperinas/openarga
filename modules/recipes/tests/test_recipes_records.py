from __future__ import annotations

from sqlalchemy import text
from test_recipes_recipes import pantry, porrusalda  # noqa: F401 - la despensa es un fixture

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


async def test_each_recipe_is_a_ficha_and_the_pantry_another(api, pantry) -> None:  # noqa: F811
    recipe = (await api.post("/recipes", json=porrusalda(pantry))).json()

    found = await built()

    ficha = found[f"recipe:{recipe['id']}"]
    assert ficha["title"] == "Porrusalda" and ficha["folder"] == "Recetas"
    assert ficha["href"] == f"/recipes/receta/{recipe['id']}"
    props = ficha["properties"]
    assert props["raciones"] == 4 and props["version"] == 1
    assert props["etiquetas"] == ["invierno", "olla"]
    assert props["kcal_racion"] == round(recipe["nutrition"]["per_serving"]["kcal"])
    assert "- Puerro: 400 g · en rodajas" in ficha["body"]
    assert "- Bacalao: 200 g (opcional)" in ficha["body"]
    assert "## Por ración" in ficha["body"]

    shelf = found["pantry"]
    assert shelf["properties"] == {"alimentos": 4}
    assert "| Aceite de oliva | 884 | 0 | 0 | 100 | manual |" in shelf["body"]
