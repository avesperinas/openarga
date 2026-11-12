from __future__ import annotations

from uuid import UUID, uuid4

import pytest
from goals_people import OTHER, PERSON
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from arga_tenancy import as_user
from goals.main import app

ANA = UUID("0a0a0a0a-0000-4000-8000-00000000a0a0")
LUIS = UUID("0b0b0b0b-0000-4000-8000-00000000b0b0")
WRITE = "mod_goals"
READ = "mod_goals_read"
OUTSIDER = UUID("00000000-0000-4000-8000-00000000c0c0")


async def as_role(engine, role: str, person: UUID | None, statement: str, **params):
    with as_user(person):
        async with engine.begin() as connection:
            await connection.execute(text(f'set local role "{role}"'))
            result = await connection.execute(text(statement), params)
            return result.all() if result.returns_rows else result.rowcount


CATEGORY = "insert into goals.goals_category (name, hue) values (:name, 1)"
TASK = (
    "insert into goals.goals_task (category_id, title) select id, :title from goals.goals_category"
)


@pytest.fixture
async def two_people(schema):
    await as_role(schema, WRITE, ANA, CATEGORY, name="De Ana")
    await as_role(schema, WRITE, ANA, TASK, title="Tarea de Ana")
    await as_role(schema, WRITE, LUIS, CATEGORY, name="De Luis")
    await as_role(schema, WRITE, LUIS, TASK, title="Tarea de Luis")
    return schema


@pytest.mark.parametrize("role", [WRITE, READ])
async def test_each_one_reads_only_their_own(two_people, role: str) -> None:
    ana = await as_role(two_people, role, ANA, "select title from goals.goals_task")
    luis = await as_role(two_people, role, LUIS, "select name from goals.goals_category")
    assert [row.title for row in ana] == ["Tarea de Ana"]
    assert [row.name for row in luis] == ["De Luis"]


@pytest.mark.parametrize("role", [WRITE, READ])
async def test_without_a_person_nothing_is_seen(two_people, role: str) -> None:
    assert await as_role(two_people, role, None, "select title from goals.goals_task") == []


async def test_writing_in_someone_elses_name_is_refused_by_postgres(two_people) -> None:
    with pytest.raises(DBAPIError) as refused:
        await as_role(
            two_people,
            WRITE,
            ANA,
            "insert into goals.goals_category (name, hue, user_id) values ('X', 1, :other)",
            other=LUIS,
        )
    assert "row-level security" in str(refused.value).lower()


async def test_nobody_puts_a_row_in_a_space_they_are_not_in(two_people) -> None:
    with pytest.raises(DBAPIError) as refused:
        await as_role(
            two_people,
            WRITE,
            ANA,
            "insert into goals.goals_category (name, hue, space_id) values ('X', 1, :space)",
            space=uuid4(),
        )
    assert "row-level security" in str(refused.value).lower()


async def test_the_reader_role_cannot_write(two_people) -> None:
    with pytest.raises(DBAPIError) as refused:
        await as_role(two_people, READ, ANA, CATEGORY, name="Otra")
    assert "permission denied" in str(refused.value).lower()


async def test_the_module_cannot_write_events_itself(two_people) -> None:
    with pytest.raises(DBAPIError) as refused:
        await as_role(
            two_people,
            WRITE,
            ANA,
            "insert into kernel.events (module, source, type, payload) "
            "values ('goals', 'app', 'goals.task', '{}'::jsonb)",
        )
    assert "permission denied" in str(refused.value).lower()


async def test_an_hour_needs_its_day_in_the_schema_too(two_people) -> None:
    with pytest.raises(DBAPIError) as refused:
        await as_role(
            two_people,
            WRITE,
            ANA,
            "insert into goals.goals_task (category_id, title, due_time) "
            "select id, 'X', '10:00' from goals.goals_category",
        )
    assert "goals_task_time_needs_day" in str(refused.value)


AS_OUTSIDER = {"x-arga-user": str(OUTSIDER)}


def with_space(space: str, who: UUID) -> dict[str, str]:
    return {"x-arga-user": str(who), "x-arga-spaces": space}


@pytest.fixture
async def couple(api, schema):
    from kernel import db as kernel_db
    from kernel.main import app as kernel_app

    tag = f"goals-shared-{uuid4()}"
    async with schema.begin() as connection:
        for who in (PERSON, OTHER, OUTSIDER):
            await connection.execute(
                text(
                    "insert into kernel.users (id, subject) values (:id, :s) "
                    "on conflict (id) do nothing"
                ),
                {"id": who, "s": f"{tag}-{who}"},
            )
    kernel = AsyncClient(transport=ASGITransport(app=kernel_app), base_url="http://kernel")
    app.state.client = kernel
    try:
        created = await api.post("/spaces", json={"name": "Casa de Goals"})
        assert created.status_code == 201, created.text
        space = created.json()["id"]
        code = (await api.post(f"/spaces/{space}/invites")).json()["code"]
        joined = await api.post(
            "/spaces/join", json={"code": code}, headers={"x-arga-user": str(OTHER)}
        )
        assert joined.status_code == 200, joined.text
        yield space
    finally:
        await kernel.aclose()
        async with schema.begin() as connection:
            await connection.execute(text("delete from kernel.spaces where name = 'Casa de Goals'"))
            await connection.execute(
                text("delete from kernel.users where subject like :s"), {"s": f"{tag}-%"}
            )
        await kernel_db.engine().dispose()
        kernel_db.engine.cache_clear()


async def test_a_shared_category_is_seen_and_tended_by_its_members_only(api, couple) -> None:
    space = couple
    home = next(one for one in (await api.get("/categories")).json() if one["name"] == "Casa")
    before = (
        await api.post("/tasks", json={"category_id": home["id"], "title": "Llamar al fontanero"})
    ).json()

    shared = await api.put(f"/categories/{home['id']}/space", json={"space_id": space})
    assert shared.status_code == 200, shared.text
    assert shared.json()["space_id"] == space

    mine = with_space(space, PERSON)
    after = (
        await api.post(
            "/tasks",
            json={"category_id": home["id"], "title": "Pagar la derrama"},
            headers=mine,
        )
    ).json()
    assert (
        after["space_id"] == space
        and (await api.get(f"/tasks/{before['id']}", headers=mine)).json()["space_id"] == space
    )

    theirs = (await api.get("/tasks", headers=with_space(space, OTHER))).json()
    assert {one["title"] for one in theirs} == {"Llamar al fontanero", "Pagar la derrama"}
    done = await api.post(f"/tasks/{before['id']}/done", headers=with_space(space, OTHER))
    assert done.status_code == 200, done.text
    seen = (await api.get(f"/tasks/{before['id']}", headers=with_space(space, PERSON))).json()
    assert seen["status"] == "done" and seen["done_by_me"] is False

    assert (await api.get(f"/tasks/{after['id']}", headers=AS_OUTSIDER)).status_code == 404
    assert (await api.get("/tasks", headers=AS_OUTSIDER)).json() == []


async def test_back_to_being_only_yours(api, couple) -> None:
    space = couple
    work = next(one for one in (await api.get("/categories")).json() if one["name"] == "Trabajo")
    task = (await api.post("/tasks", json={"category_id": work["id"], "title": "Informe"})).json()
    await api.put(f"/categories/{work['id']}/space", json={"space_id": space})
    back = await api.put(f"/categories/{work['id']}/space", json={"space_id": None})
    assert back.json()["space_id"] is None
    gone = await api.get(f"/tasks/{task['id']}", headers=with_space(space, OTHER))
    assert gone.status_code == 404


async def test_a_space_you_are_not_in_is_refused(api, couple) -> None:
    work = next(one for one in (await api.get("/categories")).json() if one["name"] == "Trabajo")
    refused = await api.put(f"/categories/{work['id']}/space", json={"space_id": str(uuid4())})
    assert refused.status_code == 404
