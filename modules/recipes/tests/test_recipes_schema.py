from __future__ import annotations

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

WRITE = "mod_recipes"


async def run(engine, statement: str, **params):
    async with engine.begin() as connection:
        await connection.execute(text(f'set local role "{WRITE}"'))
        result = await connection.execute(text(statement), params)
        return result.all() if result.returns_rows else result.rowcount


@pytest.fixture
async def draft(schema):
    (recipe,) = await run(
        schema,
        "insert into recipes.recipes_recipe (name, servings) values ('Porrusalda', 4) returning id",
    )
    (version,) = await run(
        schema,
        "insert into recipes.recipes_recipe_version (recipe_id, number, source, servings) "
        "values (:recipe, 1, 'app', 4) returning id",
        recipe=recipe.id,
    )
    (food,) = await run(
        schema,
        "insert into recipes.recipes_food "
        "(name, source, source_ref, category_id, kcal_100g, protein_100g, fat_100g, carbs_100g) "
        "values ('Puerro', 'usda', '11246', 'vegetable', 61, 1.5, 0.3, 14.2) returning id",
    )
    return schema, recipe.id, version.id, food.id


async def seal(engine, version_id) -> None:
    await run(
        engine,
        "update recipes.recipes_recipe_version set sealed_at = now() where id = :v",
        v=version_id,
    )


async def add_ingredient(engine, version_id, food_id, position: int = 1):
    return await run(
        engine,
        "insert into recipes.recipes_recipe_ingredient "
        "(version_id, position, food_id, quantity, unit) "
        "values (:v, :p, :f, 200, 'g')",
        v=version_id,
        p=position,
        f=food_id,
    )


async def test_a_draft_takes_ingredients(draft) -> None:
    engine, _, version, food = draft

    assert await add_ingredient(engine, version, food) == 1


async def test_a_sealed_version_is_never_rewritten(draft) -> None:
    engine, _, version, food = draft
    await add_ingredient(engine, version, food)
    await seal(engine, version)

    with pytest.raises(DBAPIError) as refused:
        await run(
            engine,
            "update recipes.recipes_recipe_version set note = 'menos sal' where id = :v",
            v=version,
        )

    assert "sealed" in str(refused.value)


async def test_a_sealed_version_takes_no_more_ingredients(draft) -> None:
    engine, _, version, food = draft
    await seal(engine, version)

    with pytest.raises(DBAPIError) as refused:
        await add_ingredient(engine, version, food)

    assert "sealed" in str(refused.value)


async def test_an_ingredient_of_a_sealed_version_is_not_removed(draft) -> None:
    engine, _, version, food = draft
    await add_ingredient(engine, version, food)
    await seal(engine, version)

    with pytest.raises(DBAPIError) as refused:
        await run(
            engine,
            "delete from recipes.recipes_recipe_ingredient where version_id = :v",
            v=version,
        )

    assert "sealed" in str(refused.value)


async def test_only_one_version_can_be_open_at_a_time(draft) -> None:
    engine, recipe, _, _ = draft

    with pytest.raises(DBAPIError) as refused:
        await run(
            engine,
            "insert into recipes.recipes_recipe_version "
            "(recipe_id, number, source, servings) values (:r, 2, 'tool', 4)",
            r=recipe,
        )

    assert "recipes_version_one_draft" in str(refused.value)


async def test_an_ingredient_is_a_food_or_a_name_to_resolve_but_never_both(draft) -> None:
    engine, _, version, food = draft

    with pytest.raises(DBAPIError):
        await run(
            engine,
            "insert into recipes.recipes_recipe_ingredient "
            "(version_id, position, food_id, unresolved_name, quantity, unit) "
            "values (:v, 1, :f, 'puerro del huerto', 200, 'g')",
            v=version,
            f=food,
        )

    with pytest.raises(DBAPIError):
        await run(
            engine,
            "insert into recipes.recipes_recipe_ingredient "
            "(version_id, position, quantity, unit) values (:v, 2, 200, 'g')",
            v=version,
        )

    assert (
        await run(
            engine,
            "insert into recipes.recipes_recipe_ingredient "
            "(version_id, position, unresolved_name, quantity, unit) "
            "values (:v, 3, 'sofrito de casa', 1, 'unit')",
            v=version,
        )
        == 1
    )


async def test_the_outbox_does_not_publish_the_same_thing_twice(schema) -> None:
    encolar = (
        "insert into recipes.recipes_outbox (type, payload, dedup_hash) "
        "values ('recipes.recipe_saved', '{\"recipe\": \"x\"}'::jsonb, 'receta:x:v1')"
    )
    assert await run(schema, encolar) == 1

    with pytest.raises(DBAPIError) as refused:
        await run(schema, encolar)

    assert "recipes_outbox" in str(refused.value)


async def test_a_food_is_imported_once_per_source(schema) -> None:
    importar = (
        "insert into recipes.recipes_food "
        "(name, source, source_ref, category_id, kcal_100g, protein_100g, fat_100g, carbs_100g) "
        "values ('Puerro', 'usda', '11246', 'vegetable', 61, 1.5, 0.3, 14.2)"
    )
    assert await run(schema, importar) == 1

    with pytest.raises(DBAPIError) as refused:
        await run(schema, importar)

    assert "recipes_food_once_per_source" in str(refused.value)


async def test_deleting_the_recipe_takes_its_versions_but_a_loose_one_stays(draft) -> None:
    engine, recipe, version, food = draft
    await add_ingredient(engine, version, food)
    await seal(engine, version)

    with pytest.raises(DBAPIError) as refused:
        await run(
            engine,
            "delete from recipes.recipes_recipe_version where id = :v",
            v=version,
        )
    assert "sealed" in str(refused.value)

    assert await run(engine, "delete from recipes.recipes_recipe where id = :r", r=recipe) == 1
    assert (
        await run(
            engine,
            "select count(*) as n from recipes.recipes_recipe_version where recipe_id = :r",
            r=recipe,
        )
    )[0].n == 0
