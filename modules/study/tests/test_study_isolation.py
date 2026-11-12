from __future__ import annotations

from uuid import UUID

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from arga_tenancy import USER_HEADER, as_user
from study.main import app

ANA = UUID("0a0a0a0a-0000-4000-8000-00000000a0a0")
LUIS = UUID("0b0b0b0b-0000-4000-8000-00000000b0b0")
WRITE = "mod_study"
READ = "mod_study_read"


async def as_role(engine, role: str, person: UUID | None, statement: str, **params):
    with as_user(person):
        async with engine.begin() as connection:
            await connection.execute(text(f'set local role "{role}"'))
            result = await connection.execute(text(statement), params)
            return result.all() if result.returns_rows else result.rowcount


COURSE = "insert into study.study_course (name) values (:name) returning id"


@pytest.fixture
async def two_students(schema):
    await as_role(schema, WRITE, ANA, COURSE, name="El máster de Ana")
    await as_role(schema, WRITE, LUIS, COURSE, name="El curso de Luis")
    return schema


@pytest.mark.parametrize("role", [WRITE, READ])
async def test_each_one_reads_only_their_own(two_students, role: str) -> None:
    ana = await as_role(two_students, role, ANA, "select name from study.study_course")
    luis = await as_role(two_students, role, LUIS, "select name from study.study_course")

    assert [row.name for row in ana] == ["El máster de Ana"]
    assert [row.name for row in luis] == ["El curso de Luis"]


@pytest.mark.parametrize("role", [WRITE, READ])
async def test_without_a_person_nothing_is_seen(two_students, role: str) -> None:
    assert await as_role(two_students, role, None, "select name from study.study_course") == []


async def test_writing_in_someone_elses_name_is_refused_by_postgres(two_students) -> None:
    with pytest.raises(DBAPIError) as refused:
        await as_role(
            two_students,
            WRITE,
            ANA,
            "insert into study.study_course (name, user_id) values ('Ajeno', :other)",
            other=LUIS,
        )

    assert "row-level security" in str(refused.value).lower()


async def test_the_reader_role_cannot_write(two_students) -> None:
    with pytest.raises(DBAPIError) as refused:
        await as_role(two_students, READ, ANA, COURSE, name="Otro")

    assert "permission denied" in str(refused.value).lower()


async def test_the_module_cannot_write_events_itself(two_students) -> None:
    with pytest.raises(DBAPIError) as refused:
        await as_role(
            two_students,
            WRITE,
            ANA,
            "insert into kernel.events (module, source, type, payload) "
            "values ('study', 'app', 'study.course', '{}'::jsonb)",
        )

    assert "permission denied" in str(refused.value).lower()


async def test_someone_elses_course_cannot_be_used_through_the_api(two_students, notebook) -> None:
    luis_course = (await as_role(two_students, WRITE, LUIS, "select id from study.study_course"))[
        0
    ].id
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://study") as api:
        headers = {USER_HEADER: str(ANA)}
        seen = await api.get(f"/courses/{luis_course}", headers=headers)
        subject = await api.post(
            f"/courses/{luis_course}/subjects", json={"name": "Colada"}, headers=headers
        )
        note = await api.post(
            "/notes", json={"course_id": str(luis_course), "body": "hola"}, headers=headers
        )

    assert (seen.status_code, subject.status_code, note.status_code) == (404, 404, 404)
    subjects = await as_role(two_students, WRITE, LUIS, "select name from study.study_subject")
    assert subjects == []


async def test_the_note_index_only_shows_your_own_notes(two_students) -> None:
    for person in (ANA, LUIS):
        await as_role(
            two_students,
            WRITE,
            person,
            "insert into study.study_note (course_id, title) "
            "select id, 'Derivadas' from study.study_course",
        )

    found = await as_role(
        two_students,
        READ,
        ANA,
        "select count(*) as n from study.study_note where title = 'Derivadas'",
    )

    assert found[0].n == 1
