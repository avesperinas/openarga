from __future__ import annotations

from uuid import UUID

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from arga_tenancy import as_user

ANA = UUID("0a0a0a0a-0000-4000-8000-00000000a0a0")
LUIS = UUID("0b0b0b0b-0000-4000-8000-00000000b0b0")
WRITE = "mod_recipes"
READ = "mod_recipes_read"


async def as_role(engine, role: str, person: UUID | None, statement: str, **params):
    with as_user(person):
        async with engine.begin() as connection:
            await connection.execute(text(f'set local role "{role}"'))
            result = await connection.execute(text(statement), params)
            return result.all() if result.returns_rows else result.rowcount


@pytest.fixture
async def two_cooks(schema):
    for person, recipe, food in ((ANA, "Leek soup", "Leek"), (LUIS, "Marmitako", "Bonito")):
        await as_role(
            schema,
            WRITE,
            person,
            "insert into recipes.recipes_recipe (name, servings) values (:name, 4)",
            name=recipe,
        )
        await as_role(
            schema,
            WRITE,
            person,
            "insert into recipes.recipes_food "
            "(name, source, source_ref, category_id, kcal_100g, protein_100g, fat_100g, carbs_100g)"
            " values (:name, 'manual', null, 'vegetable', 30, 1.5, 0.3, 6)",
            name=food,
        )
    return schema


@pytest.mark.parametrize("role", [WRITE, READ])
async def test_each_cook_reads_only_their_own_recipes(two_cooks, role: str) -> None:
    ana = await as_role(two_cooks, role, ANA, "select name from recipes.recipes_recipe")
    luis = await as_role(two_cooks, role, LUIS, "select name from recipes.recipes_recipe")

    assert [row.name for row in ana] == ["Leek soup"]
    assert [row.name for row in luis] == ["Marmitako"]


@pytest.mark.parametrize("role", [WRITE, READ])
async def test_without_a_person_nothing_is_seen(two_cooks, role: str) -> None:
    rows = await as_role(two_cooks, role, None, "select name from recipes.recipes_recipe")

    assert rows == []


async def test_the_catalogue_shows_what_is_everyones_and_what_is_yours(two_cooks) -> None:
    categories = await as_role(
        two_cooks, READ, LUIS, "select id from recipes.recipes_food_category"
    )
    foods = await as_role(two_cooks, READ, LUIS, "select name from recipes.recipes_food")

    assert len(categories) == 13
    assert [row.name for row in foods] == ["Bonito"]


async def test_importing_a_food_in_someone_elses_name_is_refused_by_postgres(two_cooks) -> None:
    with pytest.raises(DBAPIError) as refused:
        await as_role(
            two_cooks,
            WRITE,
            ANA,
            "insert into recipes.recipes_food "
            "(name, source, category_id, kcal_100g, protein_100g, fat_100g, carbs_100g, user_id) "
            "values ('Txistorra', 'manual', 'protein', 400, 20, 35, 1, :other)",
            other=LUIS,
        )

    assert "row-level security" in str(refused.value).lower()


async def test_changing_someone_elses_recipe_changes_nothing(two_cooks) -> None:
    touched = await as_role(
        two_cooks,
        WRITE,
        ANA,
        "update recipes.recipes_recipe set servings = 12 where name = 'Marmitako'",
    )
    intact = await as_role(
        two_cooks,
        READ,
        LUIS,
        "select servings from recipes.recipes_recipe where name = 'Marmitako'",
    )

    assert touched == 0
    assert [row.servings for row in intact] == [4]


async def test_the_reader_role_cannot_write(two_cooks) -> None:
    with pytest.raises(DBAPIError) as refused:
        await as_role(
            two_cooks,
            READ,
            ANA,
            "insert into recipes.recipes_recipe (name, servings) values ('Ajoarriero', 2)",
        )

    assert "permission denied" in str(refused.value).lower()


async def test_the_module_cannot_write_events_itself(two_cooks) -> None:
    with pytest.raises(DBAPIError) as refused:
        await as_role(
            two_cooks,
            WRITE,
            ANA,
            "insert into kernel.events (module, source, type, payload) "
            "values ('recipes', 'app', 'recipes.recipe_saved', '{}'::jsonb)",
        )

    assert "permission denied" in str(refused.value).lower()
