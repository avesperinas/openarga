from __future__ import annotations

from uuid import UUID

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from arga_tenancy import as_user

ANA = UUID("0a0a0a0a-0000-4000-8000-00000000a0a0")
LUIS = UUID("0b0b0b0b-0000-4000-8000-00000000b0b0")
WRITE = "mod_library"
READ = "mod_library_read"


async def as_role(engine, role: str, person: UUID | None, statement: str, **params):
    with as_user(person):
        async with engine.begin() as connection:
            await connection.execute(text(f'set local role "{role}"'))
            result = await connection.execute(text(statement), params)
            return result.all() if result.returns_rows else result.rowcount


TYPED = "insert into library.library_manual_edition (title) values (:title)"
FETCHED = (
    "insert into library.library_edition (title, source, source_ref, user_id) "
    "values (:title, 'openlibrary', :ref, cast(:owner as uuid))"
)


@pytest.fixture
async def two_readers(schema):
    await as_role(schema, WRITE, ANA, TYPED, title="El de Ana")
    await as_role(schema, WRITE, LUIS, TYPED, title="El de Luis")
    return schema


@pytest.mark.parametrize("role", [WRITE, READ])
async def test_each_one_reads_only_their_own(two_readers, role: str) -> None:
    ana = await as_role(two_readers, role, ANA, "select title from library.library_manual_edition")
    luis = await as_role(
        two_readers, role, LUIS, "select title from library.library_manual_edition"
    )

    assert [row.title for row in ana] == ["El de Ana"]
    assert [row.title for row in luis] == ["El de Luis"]


@pytest.mark.parametrize("role", [WRITE, READ])
async def test_without_a_person_nothing_is_seen(two_readers, role: str) -> None:
    rows = await as_role(
        two_readers, role, None, "select title from library.library_manual_edition"
    )

    assert rows == []


async def test_an_edition_fetched_by_someone_is_theirs(two_readers) -> None:
    await as_role(two_readers, WRITE, ANA, FETCHED, title="Traído por Ana", ref="OL1M", owner=ANA)

    luis = await as_role(two_readers, READ, LUIS, "select title from library.library_edition")
    ana = await as_role(two_readers, READ, ANA, "select title from library.library_edition")

    assert luis == []
    assert [row.title for row in ana] == ["Traído por Ana"]


async def test_writing_in_someone_elses_name_is_refused_by_postgres(two_readers) -> None:
    with pytest.raises(DBAPIError) as refused:
        await as_role(
            two_readers,
            WRITE,
            ANA,
            "insert into library.library_manual_edition (title, user_id) values ('Ajeno', :other)",
            other=LUIS,
        )

    assert "row-level security" in str(refused.value).lower()


async def test_the_reader_role_cannot_write(two_readers) -> None:
    with pytest.raises(DBAPIError) as refused:
        await as_role(two_readers, READ, ANA, TYPED, title="Otro")

    assert "permission denied" in str(refused.value).lower()


async def test_the_module_cannot_write_events_itself(two_readers) -> None:
    with pytest.raises(DBAPIError) as refused:
        await as_role(
            two_readers,
            WRITE,
            ANA,
            "insert into kernel.events (module, source, type, payload) "
            "values ('library', 'app', 'library.reading_finished', '{}'::jsonb)",
        )

    assert "permission denied" in str(refused.value).lower()


async def test_a_reading_cannot_say_read_without_its_dates(two_readers) -> None:
    with pytest.raises(DBAPIError) as refused:
        await as_role(
            two_readers,
            WRITE,
            ANA,
            "insert into library.library_reading (manual_edition_id, status) "
            "select id, 'read' from library.library_manual_edition",
        )

    assert "library_reading_read_has_both" in str(refused.value)
