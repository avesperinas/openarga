from __future__ import annotations

from uuid import UUID

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from arga_tenancy import as_user

ANA = UUID("0a0a0a0a-0000-4000-8000-00000000a0a0")
LUIS = UUID("0b0b0b0b-0000-4000-8000-00000000b0b0")
CASA = UUID("0c0c0c0c-0000-4000-8000-00000000c0c0")
WRITE = "mod_shopping"
READ = "mod_shopping_read"


async def as_role(engine, role: str, person: UUID | None, statement: str, spaces=(), **params):
    with as_user(person, tuple(spaces)):
        async with engine.begin() as connection:
            await connection.execute(text(f'set local role "{role}"'))
            result = await connection.execute(text(statement), params)
            return result.all() if result.returns_rows else result.rowcount


INSERT = (
    "insert into shopping.shopping_product (name, key, category_id, space_id) "
    "values (:name, lower(:name), 'dairy', cast(:space as uuid))"
)


@pytest.fixture
async def two_shoppers(schema):
    await as_role(schema, WRITE, ANA, INSERT, name="Milk", space=None)
    await as_role(schema, WRITE, LUIS, INSERT, name="Kefir", space=None)
    await as_role(schema, WRITE, ANA, INSERT, name="Eggs", space=CASA, spaces=[CASA])
    return schema


@pytest.mark.parametrize("role", [WRITE, READ])
async def test_each_one_reads_only_their_own(two_shoppers, role: str) -> None:
    ana = await as_role(two_shoppers, role, ANA, "select name from shopping.shopping_product")
    luis = await as_role(two_shoppers, role, LUIS, "select name from shopping.shopping_product")

    assert sorted(row.name for row in ana) == ["Eggs", "Milk"]
    assert [row.name for row in luis] == ["Kefir"]


async def test_what_belongs_to_a_home_is_seen_by_its_members(two_shoppers) -> None:
    luis = await as_role(
        two_shoppers,
        READ,
        LUIS,
        "select name from shopping.shopping_product order by name",
        spaces=[CASA],
    )

    assert [row.name for row in luis] == ["Eggs", "Kefir"]


@pytest.mark.parametrize("role", [WRITE, READ])
async def test_without_a_person_nothing_is_seen(two_shoppers, role: str) -> None:
    rows = await as_role(two_shoppers, role, None, "select name from shopping.shopping_product")

    assert rows == []


async def test_the_sections_are_everyones(two_shoppers) -> None:
    sections = await as_role(two_shoppers, READ, LUIS, "select id from shopping.shopping_category")

    assert len(sections) == 13


async def test_writing_in_someone_elses_name_is_refused_by_postgres(two_shoppers) -> None:
    with pytest.raises(DBAPIError) as refused:
        await as_role(
            two_shoppers,
            WRITE,
            ANA,
            "insert into shopping.shopping_product (name, key, category_id, user_id) "
            "values ('Bread', 'bread', 'bakery', :other)",
            other=LUIS,
        )

    assert "row-level security" in str(refused.value).lower()


async def test_the_reader_role_cannot_write(two_shoppers) -> None:
    with pytest.raises(DBAPIError) as refused:
        await as_role(two_shoppers, READ, ANA, INSERT, name="Bread", space=None)

    assert "permission denied" in str(refused.value).lower()


async def test_the_module_cannot_write_events_itself(two_shoppers) -> None:
    with pytest.raises(DBAPIError) as refused:
        await as_role(
            two_shoppers,
            WRITE,
            ANA,
            "insert into kernel.events (module, source, type, payload) "
            "values ('shopping', 'app', 'shopping.trip_finished', '{}'::jsonb)",
        )

    assert "permission denied" in str(refused.value).lower()


async def test_a_product_is_on_the_list_once_even_if_two_things_add_it(two_shoppers) -> None:
    add = (
        "insert into shopping.shopping_item (product_id) "
        "select id from shopping.shopping_product where name = 'Milk'"
    )
    await as_role(two_shoppers, WRITE, ANA, add)

    with pytest.raises(DBAPIError) as refused:
        await as_role(two_shoppers, WRITE, ANA, add)

    assert "shopping_item_open_once" in str(refused.value)
