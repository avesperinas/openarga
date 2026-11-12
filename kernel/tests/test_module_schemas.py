from __future__ import annotations

from pathlib import Path

import pytest
from rendered_module import TEMPLATE, render
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from kernel import schemas
from kernel.db import engine
from kernel.manifests import load_all
from kernel.modules import sync
from kernel.provision import role_for

TEMPLATE_MANIFEST = TEMPLATE / "manifest.yaml"

REPO = Path(__file__).resolve().parents[2]
MODULES = REPO / "modules"
MODULE = "probe"
TABLE = f"{MODULE}.{MODULE}_readings"
ROLE = role_for(MODULE)


async def run_as(role: str, statement: str):
    async with engine().begin() as connection:
        await connection.execute(text(f'set local role "{role}"'))
        result = await connection.execute(text(statement))
        return result.all() if result.returns_rows else []


async def _forget(module: str, role: str) -> None:
    async with engine().begin() as connection:
        await connection.execute(text(f"drop schema if exists {module} cascade"))
        for statement in (
            "delete from kernel.module_migrations where module = :m",
            "delete from kernel.modules where id = :m",
        ):
            await connection.execute(text(statement), {"m": module})
        await connection.execute(
            text(
                "do $$ begin "
                f"if exists (select 1 from pg_roles where rolname = '{role}') "
                f"then execute 'drop owned by {role}'; execute 'drop role {role}'; "
                "end if; end $$"
            )
        )


@pytest.fixture
async def registered(database_url: str, tmp_path):
    render(tmp_path, MODULE)
    await _forget(MODULE, ROLE)
    async with engine().begin() as connection:
        await sync(connection, load_all(tmp_path), tmp_path)
    yield tmp_path
    await _forget(MODULE, ROLE)
    await engine().dispose()


@pytest.fixture
async def repo_modules(database_url: str):
    async with engine().begin() as connection:
        await sync(connection, load_all(MODULES), MODULES)
    yield
    async with engine().begin() as connection:
        for manifest in load_all(MODULES):
            await connection.execute(
                text("delete from kernel.modules where id = :id"), {"id": manifest.id}
            )
    await engine().dispose()


async def test_the_module_list_says_which_credentials_each_module_asks_for(repo_modules) -> None:
    from httpx import ASGITransport, AsyncClient

    from kernel.main import app

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://kernel") as client:
        listed = {row["id"]: row for row in (await client.get("/modules")).json()}

    assert listed["library"]["credentials"] == []
    assert listed["training"]["credentials"] == []


async def test_registering_a_module_leaves_its_schema_and_role_in_place(registered) -> None:
    async with engine().connect() as connection:
        schema = await connection.scalar(
            text("select 1 from information_schema.schemata where schema_name = :name"),
            {"name": MODULE},
        )
        role = await connection.scalar(
            text("select 1 from pg_roles where rolname = :name"), {"name": ROLE}
        )

    assert schema, "el módulo quedó registrado sin schema: registrar no significaba nada"
    assert role


async def test_its_tables_exist_and_belong_to_the_module_role(registered) -> None:
    async with engine().connect() as connection:
        owner = await connection.scalar(
            text("select tableowner from pg_tables where schemaname = :s and tablename = :t"),
            {"s": MODULE, "t": f"{MODULE}_readings"},
        )

    assert owner == ROLE


async def test_the_module_role_can_use_its_own_table(registered) -> None:
    await run_as(
        ROLE,
        f"insert into {TABLE} (ts, label, value) values (now(), 'prueba', 1)",
    )

    rows = await run_as(ROLE, f"select label from {TABLE}")

    assert [row.label for row in rows] == ["prueba"]


async def test_having_its_own_tables_does_not_open_the_kernel_log(registered) -> None:
    with pytest.raises(DBAPIError) as failure:
        await run_as(ROLE, "select * from kernel.events")

    assert "permission denied" in str(failure.value)


async def test_registering_twice_changes_nothing(registered) -> None:
    async with engine().begin() as connection:
        await sync(connection, load_all(registered), registered)

    rows = await run_as(ROLE, f"select count(*) as total from {TABLE}")

    assert rows[0].total == 0


async def test_sql_that_needs_kernel_privileges_fails_instead_of_passing(registered) -> None:
    async with engine().begin() as connection:
        await connection.execute(text(f'set local role "{ROLE}"'))
        with pytest.raises(DBAPIError) as failure:
            await connection.execute(text("create table kernel.colada (id int)"))

    assert "permission denied" in str(failure.value)


def test_a_schema_file_with_only_comments_is_not_a_statement() -> None:
    assert not schemas.has_statements("-- solo un comentario\n\n-- y otro\n")
    assert schemas.has_statements("-- un comentario\ncreate table x (id int);\n")


def test_the_files_are_applied_in_name_order(tmp_path) -> None:
    target = render(tmp_path, MODULE)
    for name in ("0010_despues.sql", "0002_antes.sql"):
        (target / "schema" / name).write_text("select 1;\n", encoding="utf-8")
    assert [path.name for path in schemas.schema_files(tmp_path, MODULE)] == [
        "0001_init.sql",
        "0002_antes.sql",
        "0010_despues.sql",
    ]


@pytest.fixture
async def evolving(database_url: str, tmp_path):
    from kernel.manifests import load_all as load

    module = "migraprobe"
    target = tmp_path / module
    (target / "schema").mkdir(parents=True)
    (target / "manifest.yaml").write_text(
        (TEMPLATE_MANIFEST.read_text(encoding="utf-8"))
        .replace("__MODULE_ID__", module)
        .replace("__MODULE_NAME__", module.title()),
        encoding="utf-8",
    )
    (target / "schema" / "0001_init.sql").write_text(
        f"create table {module}.{module}_items (id int primary key);"
    )
    (target / "schema" / "0002_label.sql").write_text(
        f"alter table {module}.{module}_items add column label text;"
    )

    async def cleanup() -> None:
        async with engine().begin() as connection:
            await connection.execute(text(f"drop schema if exists {module} cascade"))
            for statement in (
                "delete from kernel.module_migrations where module = :m",
                "delete from kernel.modules where id = :m",
            ):
                await connection.execute(text(statement), {"m": module})

    await cleanup()
    yield module, tmp_path, [m for m in load(tmp_path) if m.id == module]
    await cleanup()
    await engine().dispose()


async def test_a_migration_that_cannot_repeat_is_applied_once(evolving) -> None:
    module, root, manifests = evolving

    for _ in range(3):
        async with engine().begin() as connection:
            await sync(connection, manifests, root)

    async with engine().connect() as connection:
        recorded = (
            (
                await connection.execute(
                    text(
                        "select filename from kernel.module_migrations where module = :m order by 1"
                    ),
                    {"m": module},
                )
            )
            .scalars()
            .all()
        )
        column = await connection.scalar(
            text(
                "select 1 from information_schema.columns "
                "where table_schema = :m and table_name = :t and column_name = 'label'"
            ),
            {"m": module, "t": f"{module}_items"},
        )

    assert recorded == ["0001_init.sql", "0002_label.sql"]
    assert column


async def test_a_new_file_is_applied_on_the_next_start(evolving) -> None:
    module, root, manifests = evolving
    (root / module / "schema" / "0002_label.sql").rename(root / "aparte.sql")
    async with engine().begin() as connection:
        await sync(connection, manifests, root)

    (root / "aparte.sql").rename(root / module / "schema" / "0002_label.sql")
    async with engine().begin() as connection:
        applied = await schemas.apply(connection, schemas.from_disk(root, module), module)

    assert applied == ["0002_label.sql"]


async def test_an_applied_file_that_changes_stops_the_start(evolving) -> None:
    module, root, manifests = evolving
    async with engine().begin() as connection:
        await sync(connection, manifests, root)

    path = root / module / "schema" / "0001_init.sql"
    path.write_text(path.read_text() + "\n-- retocado")

    with pytest.raises(schemas.ChangedMigration, match="0001_init.sql"):
        async with engine().begin() as connection:
            await sync(connection, manifests, root)


@pytest.fixture
async def catalogued(database_url: str, tmp_path):
    from kernel.manifests import load_all as load

    module = "catprobe"
    target = tmp_path / module
    (target / "schema").mkdir(parents=True)
    (target / "manifest.yaml").write_text(
        (TEMPLATE_MANIFEST.read_text(encoding="utf-8"))
        .replace("__MODULE_ID__", module)
        .replace("__MODULE_NAME__", module.title()),
        encoding="utf-8",
    )
    (target / "schema" / "0001_init.sql").write_text(
        f"""
        create table {module}.{module}_kind (
            id text primary key,
            user_id uuid default nullif(current_setting('arga.user_id', true), '')::uuid
        );
        comment on table {module}.{module}_kind is 'arga:catalog';
        insert into {module}.{module}_kind (id) values ('primero');
        """
    )

    async def cleanup() -> None:
        async with engine().begin() as connection:
            await connection.execute(text(f"drop schema if exists {module} cascade"))
            for statement in (
                "delete from kernel.module_migrations where module = :m",
                "delete from kernel.modules where id = :m",
            ):
                await connection.execute(text(statement), {"m": module})

    await cleanup()
    yield module, tmp_path, [m for m in load(tmp_path) if m.id == module]
    await cleanup()
    await engine().dispose()


async def test_a_deployed_module_can_seed_its_catalog_in_a_new_file(catalogued) -> None:
    from arga_tenancy import as_user
    from kernel.provision import role_for as role_of

    module, root, manifests = catalogued
    with as_user(None):
        async with engine().begin() as connection:
            await sync(connection, manifests, root)
    (root / module / "schema" / "0002_mas.sql").write_text(
        f"insert into {module}.{module}_kind (id) values ('segundo');"
    )

    with as_user(None):
        async with engine().begin() as connection:
            await sync(connection, manifests, root)

    someone = "0c0c0c0c-0000-4000-8000-00000000c0c0"
    with as_user(someone):
        async with engine().begin() as connection:
            await connection.execute(text(f'set local role "{role_of(module)}"'))
            seen = (
                (
                    await connection.execute(
                        text(f"select id from {module}.{module}_kind order by 1")
                    )
                )
                .scalars()
                .all()
            )
    async with engine().connect() as connection:
        forced = await connection.scalar(
            text(
                "select relforcerowsecurity from pg_catalog.pg_class "
                "where oid = cast(:t as regclass)"
            ),
            {"t": f"{module}.{module}_kind"},
        )

    assert seen == ["primero", "segundo"]
    assert forced
