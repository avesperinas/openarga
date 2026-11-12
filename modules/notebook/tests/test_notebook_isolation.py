from __future__ import annotations

from uuid import UUID

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from arga_tenancy import as_user

ANA = UUID("0a0a0a0a-0000-4000-8000-00000000a0a0")
LUIS = UUID("0b0b0b0b-0000-4000-8000-00000000b0b0")
WRITE = "mod_notebook"
READ = "mod_notebook_read"
TABLES = [
    "notebook_folder",
    "notebook_note",
    "notebook_revision",
    "notebook_link",
    "notebook_tag",
    "notebook_outbox",
    "notebook_file",
    "notebook_export",
    "notebook_exported",
]


async def as_role(engine, role: str, person: UUID | None, statement: str, **params):
    with as_user(person):
        async with engine.begin() as connection:
            await connection.execute(text(f'set local role "{role}"'))
            result = await connection.execute(text(statement), params)
            return result.all() if result.returns_rows else result.rowcount


async def write_as(engine, person: UUID, title: str, content: str) -> None:
    from notebook import files, notes

    with as_user(person):
        async with engine.begin() as connection:
            await connection.execute(text(f'set local role "{WRITE}"'))
            created = await notes.create(connection, "Carpeta", title, "primera", "app")
            await notes.write(connection, created.id, content, None, "tool")
            await files.save(connection, "foto.png", str(person).encode())
            await connection.execute(
                text("insert into notebook.notebook_export (outcome) values ('ok')")
            )
            await connection.execute(
                text(
                    "insert into notebook.notebook_exported (path, sha256) "
                    "values ('a.md', repeat('a', 64))"
                )
            )


@pytest.fixture
async def two_people(schema):
    await write_as(schema, ANA, "Plan", "El de Ana #ana [[Otro]]")
    await write_as(schema, LUIS, "Plan", "El de Luis #luis [[Otro]]")
    return schema


@pytest.mark.parametrize("role", [WRITE, READ])
@pytest.mark.parametrize("table", TABLES)
async def test_each_one_sees_only_their_own_rows(two_people, role: str, table: str) -> None:
    ana = await as_role(two_people, role, ANA, f"select user_id from notebook.{table}")
    luis = await as_role(two_people, role, LUIS, f"select user_id from notebook.{table}")

    assert ana and {row.user_id for row in ana} == {ANA}
    assert luis and {row.user_id for row in luis} == {LUIS}


@pytest.mark.parametrize("role", [WRITE, READ])
async def test_without_a_person_nothing_is_seen(two_people, role: str) -> None:
    assert await as_role(two_people, role, None, "select id from notebook.notebook_note") == []


async def test_a_link_never_resolves_to_someone_elses_note(two_people) -> None:
    ana_plan = await as_role(two_people, READ, ANA, "select id from notebook.notebook_note")
    resolved = await as_role(
        two_people, READ, LUIS, "select notebook.resolve('plan', null, '') as id"
    )
    by_ana = await as_role(two_people, READ, ANA, "select notebook.resolve('plan', null, '') as id")

    assert resolved[0].id != ana_plan[0].id
    assert by_ana[0].id == ana_plan[0].id


async def test_writing_in_someone_elses_name_is_refused_by_postgres(two_people) -> None:
    with pytest.raises(DBAPIError) as refused:
        await as_role(
            two_people,
            WRITE,
            ANA,
            "insert into notebook.notebook_note (title, title_key, user_id) values ('x', 'x', :other)",
            other=LUIS,
        )

    assert "row-level security" in str(refused.value).lower()


async def test_the_reader_role_cannot_write(two_people) -> None:
    with pytest.raises(DBAPIError) as refused:
        await as_role(
            two_people, READ, ANA, "update notebook.notebook_note set content = 'cambiado'"
        )

    assert "permission denied" in str(refused.value).lower()


async def test_the_module_cannot_write_events_itself(two_people) -> None:
    with pytest.raises(DBAPIError) as refused:
        await as_role(
            two_people,
            WRITE,
            ANA,
            "insert into kernel.events (module, source, type, payload) "
            "values ('notebook', 'app', 'notebook.note_changed', '{}'::jsonb)",
        )

    assert "permission denied" in str(refused.value).lower()


async def test_a_title_is_unique_per_folder_only_for_its_owner(two_people) -> None:
    with pytest.raises(DBAPIError) as refused:
        await as_role(
            two_people,
            WRITE,
            ANA,
            "insert into notebook.notebook_note (folder, folder_key, title, title_key) "
            "values ('Carpeta', 'carpeta', 'PLAN', 'plan')",
        )

    assert "notebook_note_one_per_place" in str(refused.value)
