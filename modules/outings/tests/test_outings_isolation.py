from __future__ import annotations

from uuid import UUID

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from arga_tenancy import as_user

ANA = UUID("0a0a0a0a-0000-4000-8000-00000000a0a0")
LUIS = UUID("0b0b0b0b-0000-4000-8000-00000000b0b0")
WRITE = "mod_outings"
READ = "mod_outings_read"


async def as_role(engine, role: str, person: UUID | None, statement: str, **params):
    with as_user(person):
        async with engine.begin() as connection:
            await connection.execute(text(f'set local role "{role}"'))
            result = await connection.execute(text(statement), params)
            return result.all() if result.returns_rows else result.rowcount


NOTED = "insert into outings.outings_wish (kind, name) values ('plan', :name)"


@pytest.fixture
async def two_people(schema):
    await as_role(schema, WRITE, ANA, NOTED, name="La de Ana")
    await as_role(schema, WRITE, LUIS, NOTED, name="La de Luis")
    return schema


@pytest.mark.parametrize("role", [WRITE, READ])
async def test_each_one_reads_only_their_own(two_people, role: str) -> None:
    ana = await as_role(two_people, role, ANA, "select name from outings.outings_wish")
    luis = await as_role(two_people, role, LUIS, "select name from outings.outings_wish")

    assert [row.name for row in ana] == ["La de Ana"]
    assert [row.name for row in luis] == ["La de Luis"]


@pytest.mark.parametrize("role", [WRITE, READ])
async def test_without_a_person_nothing_is_seen(two_people, role: str) -> None:
    rows = await as_role(two_people, role, None, "select name from outings.outings_wish")

    assert rows == []


async def test_someone_elses_photo_cannot_be_hung_on_my_wish(two_people) -> None:
    with pytest.raises(DBAPIError) as refused:
        await as_role(
            two_people,
            WRITE,
            ANA,
            "insert into outings.outings_photo (wish_id, content, content_type, thumb, user_id) "
            "select id, '\\x00'::bytea, 'image/jpeg', '\\x00'::bytea, :other "
            "from outings.outings_wish",
            other=LUIS,
        )

    assert "row-level security" in str(refused.value).lower()


async def test_writing_in_someone_elses_name_is_refused_by_postgres(two_people) -> None:
    with pytest.raises(DBAPIError) as refused:
        await as_role(
            two_people,
            WRITE,
            ANA,
            "insert into outings.outings_wish (kind, name, user_id) values ('plan', 'Ajena', :o)",
            o=LUIS,
        )

    assert "row-level security" in str(refused.value).lower()


async def test_the_reader_role_cannot_write(two_people) -> None:
    with pytest.raises(DBAPIError) as refused:
        await as_role(two_people, READ, ANA, NOTED, name="Otra")

    assert "permission denied" in str(refused.value).lower()


async def test_the_module_cannot_write_events_itself(two_people) -> None:
    with pytest.raises(DBAPIError) as refused:
        await as_role(
            two_people,
            WRITE,
            ANA,
            "insert into kernel.events (module, source, type, payload) "
            "values ('outings', 'app', 'outings.record', '{}'::jsonb)",
        )

    assert "permission denied" in str(refused.value).lower()
