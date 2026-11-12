from __future__ import annotations

from uuid import UUID

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from arga_tenancy import as_user

ANA = UUID("0a0a0a0a-0000-4000-8000-00000000a0a0")
LUIS = UUID("0b0b0b0b-0000-4000-8000-00000000b0b0")
WRITE = "mod_travel"
READ = "mod_travel_read"


async def as_role(engine, role: str, person: UUID | None, statement: str, **params):
    with as_user(person):
        async with engine.begin() as connection:
            await connection.execute(text(f'set local role "{role}"'))
            result = await connection.execute(text(statement), params)
            return result.all() if result.returns_rows else result.rowcount


INSERT = (
    "insert into travel.travel_trip (title, starts_on, ends_on) "
    "values (:title, date '2025-01-01', date '2025-01-03')"
)


@pytest.fixture
async def two_travellers(schema):
    await as_role(schema, WRITE, ANA, INSERT, title="Roma")
    await as_role(schema, WRITE, LUIS, INSERT, title="Oporto")
    return schema


@pytest.mark.parametrize("role", [WRITE, READ])
async def test_each_one_reads_only_their_own(two_travellers, role: str) -> None:
    ana = await as_role(two_travellers, role, ANA, "select title from travel.travel_trip")
    luis = await as_role(two_travellers, role, LUIS, "select title from travel.travel_trip")

    assert [row.title for row in ana] == ["Roma"]
    assert [row.title for row in luis] == ["Oporto"]


@pytest.mark.parametrize("role", [WRITE, READ])
async def test_without_a_person_nothing_is_seen(two_travellers, role: str) -> None:
    assert await as_role(two_travellers, role, None, "select title from travel.travel_trip") == []


async def test_writing_in_someone_elses_name_is_refused_by_postgres(two_travellers) -> None:
    with pytest.raises(DBAPIError) as refused:
        await as_role(
            two_travellers,
            WRITE,
            ANA,
            "insert into travel.travel_place (name, user_id) values ('Lyon', :other)",
            other=LUIS,
        )

    assert "row-level security" in str(refused.value).lower()


async def test_someone_elses_trip_cannot_be_hung_from(two_travellers) -> None:
    [luis_trip] = await as_role(two_travellers, WRITE, LUIS, "select id from travel.travel_trip")
    changed = await as_role(
        two_travellers,
        WRITE,
        ANA,
        "update travel.travel_trip set title = 'Mío' where id = :id",
        id=luis_trip.id,
    )

    assert changed == 0


async def test_the_reader_role_cannot_write(two_travellers) -> None:
    with pytest.raises(DBAPIError) as refused:
        await as_role(two_travellers, READ, ANA, INSERT, title="Viena")

    assert "permission denied" in str(refused.value).lower()


async def test_the_module_cannot_write_events_itself(two_travellers) -> None:
    with pytest.raises(DBAPIError) as refused:
        await as_role(
            two_travellers,
            WRITE,
            ANA,
            "insert into kernel.events (module, source, type, payload) "
            "values ('travel', 'app', 'travel.trip', '{}'::jsonb)",
        )

    assert "permission denied" in str(refused.value).lower()
