from __future__ import annotations

from uuid import UUID

import pytest
from sqlalchemy import text

from arga_tenancy import as_user

ANA = UUID("0a0a0a0a-0000-4000-8000-00000000a0a0")
LUIS = UUID("0b0b0b0b-0000-4000-8000-00000000b0b0")
CASA = UUID("0c0c0c0c-0000-4000-8000-00000000c0c0")
WRITE = "mod_planner"
READ = "mod_planner_read"


async def as_role(engine, role: str, person: UUID | None, statement: str, spaces=(), **params):
    with as_user(person, tuple(spaces)):
        async with engine.begin() as connection:
            await connection.execute(text(f'set local role "{role}"'))
            result = await connection.execute(text(statement), params)
            return result.all() if result.returns_rows else result.rowcount


LAYER = (
    "insert into planner.planner_calendar (name, tone, space_id) "
    "values (:name, 3, cast(:space as uuid)) returning id"
)
EVENT = (
    "insert into planner.planner_event (calendar_id, title, start_at, end_at, tz, space_id) "
    "values (:calendar, :title, now(), now() + interval '1 hour', 'Europe/Madrid', "
    "cast(:space as uuid))"
)


@pytest.fixture
async def two_people(schema):
    for person, name in ((ANA, "Ana"), (LUIS, "Luis")):
        [(layer,)] = await as_role(schema, WRITE, person, LAYER, name=name, space=None)
        await as_role(
            schema, WRITE, person, EVENT, calendar=layer, title=f"Cita de {name}", space=None
        )
    [(home,)] = await as_role(schema, WRITE, ANA, LAYER, name="Casa", space=CASA, spaces=[CASA])
    await as_role(
        schema, WRITE, ANA, EVENT, calendar=home, title="Cena en casa", space=CASA, spaces=[CASA]
    )
    return schema


@pytest.mark.parametrize("role", [WRITE, READ])
async def test_each_one_reads_only_their_own(two_people, role: str) -> None:
    ana = await as_role(two_people, role, ANA, "select title from planner.planner_event")
    luis = await as_role(two_people, role, LUIS, "select title from planner.planner_event")

    assert sorted(row.title for row in ana) == ["Cena en casa", "Cita de Ana"]
    assert [row.title for row in luis] == ["Cita de Luis"]


async def test_a_shared_layer_is_seen_by_the_members_of_its_space(two_people) -> None:
    luis = await as_role(
        two_people,
        READ,
        LUIS,
        "select title from planner.planner_event order by title",
        spaces=[CASA],
    )

    assert [row.title for row in luis] == ["Cena en casa", "Cita de Luis"]


async def test_nobody_changes_what_is_not_theirs(two_people) -> None:
    changed = await as_role(
        two_people,
        WRITE,
        LUIS,
        "update planner.planner_event set title = 'mine' where title = 'Ana''s appointment'",
    )

    assert changed == 0


@pytest.mark.parametrize("role", [WRITE, READ])
async def test_without_a_person_nothing_is_seen(two_people, role: str) -> None:
    assert await as_role(two_people, role, None, "select title from planner.planner_event") == []


async def test_the_reader_cannot_write(two_people) -> None:
    from sqlalchemy.exc import DBAPIError

    with pytest.raises(DBAPIError):
        await as_role(two_people, READ, ANA, "update planner.planner_event set title = 'x'")


async def test_the_app_only_shows_the_person_who_asks(api, two_people) -> None:
    from arga_tenancy import USER_HEADER

    found = (
        await api.get("/search", params={"q": "Cita"}, headers={USER_HEADER: str(LUIS)})
    ).json()

    assert [o["title"] for o in found] == ["Cita de Luis"]
