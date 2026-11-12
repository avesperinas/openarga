from __future__ import annotations

from uuid import uuid4

import pytest
from sqlalchemy import text

from arga_tenancy import as_user
from kernel import rls
from kernel.backfill import AmbiguousOwner, backfill_module
from kernel.db import engine
from kernel.provision import provision

MODULE = "rellenotest"


async def reset_people(*subjects: str) -> list:
    async with engine().begin() as connection:
        await connection.execute(text("delete from kernel.users"))
        ids = []
        for subject in subjects:
            ids.append(
                await connection.scalar(
                    text("insert into kernel.users (subject) values (:s) returning id"),
                    {"s": subject},
                )
            )
        return ids


@pytest.fixture
async def module(database_url: str):
    async with engine().begin() as connection:
        await connection.execute(text(f"drop schema if exists {MODULE} cascade"))
    await provision(MODULE)
    with as_user(None):
        async with engine().begin() as connection:
            await connection.execute(text(f'set local role "mod_{MODULE}"'))
            for table, kind in (
                ("cosas", "arga:person"),
                ("catalogo", "arga:catalog"),
                ("anatomia", "arga:system"),
            ):
                await connection.execute(
                    text(
                        f"create table {MODULE}.{MODULE}_{table} (n int, user_id uuid default "
                        f"nullif(current_setting('arga.user_id', true), '')::uuid)"
                    )
                )
                await connection.execute(
                    text(f"comment on table {MODULE}.{MODULE}_{table} is '{kind}'")
                )
                await connection.execute(
                    text(f"insert into {MODULE}.{MODULE}_{table} (n) values (1), (2)")
                )
            await connection.execute(
                text(
                    f"create function {MODULE}.refuse() returns trigger language plpgsql as "
                    "$$ begin raise exception 'publicado, no se modifica'; end $$"
                )
            )
            await connection.execute(
                text(
                    f"create trigger immutable before update on {MODULE}.{MODULE}_cosas "
                    f"for each row execute function {MODULE}.refuse()"
                )
            )
        async with engine().begin() as connection:
            await rls.enforce(connection, MODULE)
    yield
    async with engine().begin() as connection:
        await connection.execute(text(f"drop schema if exists {MODULE} cascade"))
        await connection.execute(text("delete from kernel.users"))
    await engine().dispose()


async def owners(table: str) -> list:
    async with engine().connect() as connection:
        return (
            (
                await connection.execute(
                    text(f"select user_id from {MODULE}.{MODULE}_{table} order by n")
                )
            )
            .scalars()
            .all()
        )


async def run() -> dict[str, int]:
    async with engine().begin() as connection:
        return await backfill_module(connection, MODULE)


async def test_with_one_person_everything_of_someone_becomes_theirs(module) -> None:
    (owner,) = await reset_people("persona-sintetica")

    moved = await run()

    assert moved == {f"{MODULE}.{MODULE}_cosas": 2}
    assert await owners("cosas") == [owner, owner]
    assert await owners("catalogo") == [None, None]
    assert await owners("anatomia") == [None, None]


async def test_what_the_module_protects_with_a_trigger_still_gets_its_owner_and_stays_protected(
    module,
) -> None:
    (owner,) = await reset_people("persona-sintetica")

    await run()

    assert await owners("cosas") == [owner, owner]
    with as_user(None), pytest.raises(Exception, match="publicado"):
        async with engine().begin() as connection:
            await connection.execute(text(f"update {MODULE}.{MODULE}_cosas set n = n + 10"))


async def test_a_second_pass_changes_nothing(module) -> None:
    await reset_people("persona-sintetica")
    await run()

    assert await run() == {}


async def test_without_anyone_nothing_is_given_and_nothing_breaks(module) -> None:
    await reset_people()

    assert await run() == {}
    assert await owners("cosas") == [None, None]


async def test_with_several_people_it_refuses_to_guess(module) -> None:
    await reset_people("una", "otra")

    with pytest.raises(AmbiguousOwner, match="varias personas"):
        await run()
    assert await owners("cosas") == [None, None]


async def test_with_several_people_the_catalogue_of_everyone_does_not_stop_the_boot(module) -> None:
    await reset_people("una", "otra")
    async with engine().begin() as connection:
        await connection.execute(text(f"delete from {MODULE}.{MODULE}_cosas"))

    assert await run() == {}
    assert await owners("catalogo") == [None, None]


async def test_a_module_that_does_not_exist_yet_is_nothing_to_do(database_url) -> None:
    async with engine().begin() as connection:
        assert await backfill_module(connection, f"nadie_{uuid4().hex[:8]}") == {}
    await engine().dispose()


async def test_the_owner_is_given_through_the_policy_that_is_already_watching(module) -> None:
    (owner,) = await reset_people("persona-sintetica")

    moved = await run()

    assert moved == {f"{MODULE}.{MODULE}_cosas": 2}
    assert await owners("cosas") == [owner, owner]


async def test_the_tables_are_left_forced_again(module) -> None:
    await reset_people("persona-sintetica")

    await run()

    async with engine().connect() as connection:
        forced = (
            (
                await connection.execute(
                    text(
                        "select relforcerowsecurity from pg_catalog.pg_class c "
                        "join pg_catalog.pg_namespace n on n.oid = c.relnamespace "
                        "where n.nspname = :schema and c.relkind = 'r' "
                        "and obj_description(c.oid, 'pg_class') = any(:classes)"
                    ),
                    {"schema": MODULE, "classes": ["arga:person", "arga:catalog"]},
                )
            )
            .scalars()
            .all()
        )
    assert forced == [True, True]
