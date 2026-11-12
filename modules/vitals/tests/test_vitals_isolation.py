from __future__ import annotations

from uuid import UUID

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from arga_tenancy import as_user

ANA = UUID("0a0a0a0a-0000-4000-8000-00000000a0a0")
LUIS = UUID("0b0b0b0b-0000-4000-8000-00000000b0b0")
WRITE = "mod_vitals"
READ = "mod_vitals_read"


async def as_role(engine, role: str, person: UUID | None, statement: str, **params):
    with as_user(person):
        async with engine.begin() as connection:
            await connection.execute(text(f'set local role "{role}"'))
            result = await connection.execute(text(statement), params)
            return result.all() if result.returns_rows else result.rowcount


INSERT = "insert into vitals.vitals_weight (day, kg) values ('2026-09-01', :kg)"


@pytest.fixture
async def two_people(schema):
    await as_role(schema, WRITE, ANA, INSERT, kg=61.5)
    await as_role(schema, WRITE, LUIS, INSERT, kg=82.0)
    await as_role(
        schema, WRITE, ANA, "insert into vitals.vitals_goal (steps_per_day) values (9000)"
    )
    return schema


@pytest.mark.parametrize("role", [WRITE, READ])
async def test_each_one_reads_only_their_own(two_people, role: str) -> None:
    ana = await as_role(two_people, role, ANA, "select kg from vitals.vitals_weight")
    luis = await as_role(two_people, role, LUIS, "select kg from vitals.vitals_weight")

    assert [float(row.kg) for row in ana] == [61.5]
    assert [float(row.kg) for row in luis] == [82.0]


async def test_a_goal_is_only_its_owners(two_people) -> None:
    luis = await as_role(two_people, READ, LUIS, "select steps_per_day from vitals.vitals_goal")

    assert luis == []


@pytest.mark.parametrize("role", [WRITE, READ])
async def test_without_a_person_nothing_is_seen(two_people, role: str) -> None:
    rows = await as_role(two_people, role, None, "select kg from vitals.vitals_weight")

    assert rows == []


async def test_the_same_weight_the_same_day_is_two_rows_for_two_people(two_people) -> None:
    await as_role(two_people, WRITE, LUIS, INSERT, kg=61.5)

    luis = await as_role(two_people, READ, LUIS, "select kg from vitals.vitals_weight order by kg")
    assert [float(row.kg) for row in luis] == [61.5, 82.0]


async def test_writing_in_someone_elses_name_is_refused_by_postgres(two_people) -> None:
    with pytest.raises(DBAPIError) as refused:
        await as_role(
            two_people,
            WRITE,
            ANA,
            "insert into vitals.vitals_weight (day, kg, user_id) values ('2026-09-02', 70, :other)",
            other=LUIS,
        )

    assert "row-level security" in str(refused.value).lower()


async def test_the_reader_role_cannot_write(two_people) -> None:
    with pytest.raises(DBAPIError) as refused:
        await as_role(two_people, READ, ANA, INSERT, kg=60)

    assert "permission denied" in str(refused.value).lower()


async def test_the_module_cannot_write_events_itself(two_people) -> None:
    with pytest.raises(DBAPIError) as refused:
        await as_role(
            two_people,
            WRITE,
            ANA,
            "insert into kernel.events (module, source, type, payload) "
            "values ('vitals', 'app', 'vitals.weight', '{}'::jsonb)",
        )

    assert "permission denied" in str(refused.value).lower()
