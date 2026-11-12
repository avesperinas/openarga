from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import text

from arga_testing import fresh_modules
from arga_testing import manifests as repo_manifests
from kernel.db import engine

REPO = Path(__file__).resolve().parents[2]
MODULES = REPO / "modules"
CLASSES = {"arga:person", "arga:catalog", "arga:shared", "arga:system"}
OWNED = {"arga:person", "arga:catalog", "arga:shared"}

TABLES = text("""
    select n.nspname as schema, c.relname as name, obj_description(c.oid, 'pg_class') as class_,
           c.relrowsecurity as rls, c.relforcerowsecurity as forced,
           exists (select 1 from pg_policy p where p.polrelid = c.oid and p.polname = 'arga_owner')
             as has_policy,
           (select format_type(a.atttypid, a.atttypmod) from pg_attribute a
             where a.attrelid = c.oid and a.attname = 'user_id' and not a.attisdropped)
             as user_type,
           (select pg_get_expr(d.adbin, d.adrelid) from pg_attribute a
             join pg_attrdef d on d.adrelid = a.attrelid and d.adnum = a.attnum
             where a.attrelid = c.oid and a.attname = 'user_id') as user_default,
           (select format_type(a.atttypid, a.atttypmod) from pg_attribute a
             where a.attrelid = c.oid and a.attname = 'space_id' and not a.attisdropped)
             as space_type
    from pg_class c
    join pg_namespace n on n.oid = c.relnamespace
    where c.relkind in ('r', 'p')
      and n.nspname = any(:schemas)
    order by 1, 2
""")


@pytest.fixture
async def every_table(database_url: str):
    manifests = repo_manifests(MODULES)
    async with engine().begin() as connection:
        await fresh_modules(connection, *(m.id for m in manifests))
    async with engine().connect() as connection:
        rows = (
            await connection.execute(
                TABLES, {"schemas": ["kernel", "public", *(m.id for m in manifests)]}
            )
        ).all()
    yield rows, {m.id for m in manifests}
    async with engine().begin() as connection:
        for manifest in manifests:
            await connection.execute(
                text("delete from kernel.modules where id = :id"), {"id": manifest.id}
            )
    await engine().dispose()


async def test_every_table_says_whose_it_is(every_table) -> None:
    rows, modules = every_table

    unclassified = [f"{row.schema}.{row.name}" for row in rows if row.class_ not in CLASSES]

    assert {row.schema for row in rows} >= {"kernel", *modules}, "no se registraron los módulos"
    assert not unclassified, (
        f"estas tablas no dicen de qué clase son: {unclassified}. Cada tabla lleva "
        f"`comment on table ... is 'arga:person'` (o `arga:catalog`, `arga:shared`, "
        f"`arga:system`). Ver ADR-0028 y ADR-0038."
    )


async def test_what_belongs_to_someone_carries_its_owner(every_table) -> None:
    rows, _ = every_table

    without_owner = [
        f"{row.schema}.{row.name}"
        for row in rows
        if row.class_ in OWNED
        and not (
            row.user_type == "uuid"
            and row.user_default is not None
            and "arga.user_id" in row.user_default
        )
    ]

    assert not without_owner, (
        f"estas tablas son de alguien y no llevan `user_id uuid default` el GUC: {without_owner}"
    )


def without_space(rows) -> list[str]:
    return [
        f"{row.schema}.{row.name}"
        for row in rows
        if row.class_ == "arga:shared" and row.space_type != "uuid"
    ]


async def test_what_belongs_to_a_space_says_which_space(every_table) -> None:
    rows, _ = every_table

    assert not without_space(rows), (
        f"estas tablas son de un espacio y no llevan `space_id uuid`: {without_space(rows)}. "
        f"Ver ADR-0038."
    )


async def test_a_shared_table_that_forgets_its_space_is_caught(database_url: str) -> None:
    async with engine().begin() as connection:
        await connection.execute(text("drop schema if exists olvido cascade"))
        await connection.execute(text("create schema olvido"))
        await connection.execute(
            text(
                "create table olvido.olvido_cosa (id int, "
                "user_id uuid default nullif(current_setting('arga.user_id', true), '')::uuid)"
            )
        )
        await connection.execute(text("comment on table olvido.olvido_cosa is 'arga:shared'"))
    try:
        async with engine().connect() as connection:
            rows = (await connection.execute(TABLES, {"schemas": ["olvido"]})).all()
    finally:
        async with engine().begin() as connection:
            await connection.execute(text("drop schema olvido cascade"))
        await engine().dispose()

    assert without_space(rows) == ["olvido.olvido_cosa"]


async def test_postgres_separates_what_belongs_to_someone(every_table) -> None:
    rows, _ = every_table

    open_tables = [
        f"{row.schema}.{row.name}"
        for row in rows
        if row.class_ in OWNED and not (row.rls and row.forced and row.has_policy)
    ]
    system_with_rls = [
        f"{row.schema}.{row.name}" for row in rows if row.class_ == "arga:system" and row.rls
    ]

    assert not open_tables, f"sin RLS forzada con su política: {open_tables}"
    assert not system_with_rls, f"del sistema y con RLS: {system_with_rls}"


async def test_the_system_has_no_owner(every_table) -> None:
    rows, _ = every_table

    system = {f"{row.schema}.{row.name}" for row in rows if row.class_ == "arga:system"}

    assert system == {
        "kernel.modules",
        "kernel.module_migrations",
        "kernel.users",
        "kernel.spaces",
        "kernel.space_members",
        "kernel.space_invites",
        "public.alembic_version",
        "training.training_muscle",
        "travel.travel_tile",
    }
