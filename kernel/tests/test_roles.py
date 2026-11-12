from __future__ import annotations

import asyncio
import os
import secrets
import subprocess
import sys
from pathlib import Path

import pytest
from rendered_module import render
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import create_async_engine

from kernel.roles import login_for, scram_verifier, verifies

REPO = Path(__file__).resolve().parents[2]
TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL", "postgresql+asyncpg://openarga:changeme@localhost:5433/openarga"
)
MODULE = "rolesprobe"
MODULE_ROLE = f"mod_{MODULE}"
MODULE_READER = f"mod_{MODULE}_read"
MODULE_LOGIN = login_for(MODULE)
KERNEL_USER = "rolesprobe_kernel"
KERNEL_PASSWORD = secrets.token_urlsafe(24)
MODULE_PASSWORD = secrets.token_urlsafe(24)


def url_for(database: str, user: str | None = None, password: str | None = None) -> str:
    url = make_url(TEST_DATABASE_URL).set(database=database)
    if user is not None:
        url = url.set(username=user, password=password)
    return url.render_as_string(hide_password=False)


async def _admin(statements: list[str]) -> None:
    engine = create_async_engine(url_for("postgres"), isolation_level="AUTOCOMMIT")
    try:
        async with engine.connect() as connection:
            for statement in statements:
                await connection.execute(text(statement))
    finally:
        await engine.dispose()


async def _query(url: str, statement: str, role: str | None = None) -> list:
    engine = create_async_engine(url)
    try:
        async with engine.begin() as connection:
            if role:
                await connection.execute(text(f'set local role "{role}"'))
            result = await connection.execute(text(statement))
            return result.all() if result.returns_rows else []
    finally:
        await engine.dispose()


def query(url: str, statement: str, role: str | None = None) -> list:
    return asyncio.run(_query(url, statement, role))


def run(command: str, env: dict[str, str], *arguments: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-m", command, *arguments],
        env={**os.environ, **env},
        capture_output=True,
        text=True,
        timeout=120,
    )


def drop_roles() -> list[str]:
    roles = (MODULE_LOGIN, MODULE_READER, MODULE_ROLE, KERNEL_USER, "arga_auth", "arga_backup")
    return [f'drop role if exists "{role}"' for role in roles]


@pytest.fixture
def modules(tmp_path: Path) -> Path:
    target = render(tmp_path, MODULE)
    for sql in (target / "schema").glob("*.sql"):
        sql.unlink()
    (target / "schema" / "0001_init.sql").write_text(
        f"create table if not exists {MODULE}.{MODULE}_items (id int primary key);",
        encoding="utf-8",
    )
    return tmp_path


@pytest.fixture
def database():
    name = f"roles_{secrets.token_hex(4)}"
    asyncio.run(_admin([*drop_roles(), f'create database "{name}"']))
    yield name
    asyncio.run(_admin([f'drop database if exists "{name}" with (force)', *drop_roles()]))


def roles_env(database: str, modules: Path) -> dict[str, str]:
    return {
        "ADMIN_DATABASE_URL": url_for(database),
        "KERNEL_DB_USER": KERNEL_USER,
        "KERNEL_DB_PASSWORD": KERNEL_PASSWORD,
        f"{MODULE.upper()}_DB_PASSWORD": MODULE_PASSWORD,
        "MODULES_PATH": str(modules),
    }


def kernel_env(database: str, modules: Path, as_superuser: bool = False) -> dict[str, str]:
    url = url_for(database) if as_superuser else url_for(database, KERNEL_USER, KERNEL_PASSWORD)
    return {"DATABASE_URL": url, "MODULES_PATH": str(modules)}


def start_kernel(database: str, modules: Path, as_superuser: bool = False) -> None:
    env = kernel_env(database, modules, as_superuser)
    for command in ("kernel.migrate", "kernel.modules"):
        result = run(command, env)
        assert result.returncode == 0, f"{command}: {result.stderr}"


def assert_module_is_isolated(database: str) -> None:
    as_module = url_for(database, MODULE_LOGIN, MODULE_PASSWORD)

    query(as_module, f"insert into {MODULE}.{MODULE}_items values (1) on conflict do nothing")
    assert query(as_module, f"select count(*) from {MODULE}.events") == [(0,)]

    for statement in ("select 1 from kernel.events limit 1", "create table kernel.colada (id int)"):
        with pytest.raises(DBAPIError, match="permission denied"):
            query(as_module, statement)

    items = f"{MODULE}.{MODULE}_items"
    assert query(as_module, f"select count(*) from {items}", role=MODULE_READER) == [(1,)]
    assert query(as_module, f"select count(*) from {MODULE}.events", role=MODULE_READER) == [(0,)]
    with pytest.raises(DBAPIError, match="permission denied"):
        query(as_module, f"insert into {items} values (2)", role=MODULE_READER)


def test_a_fresh_database_migrates_and_provisions_without_a_superuser(database, modules) -> None:
    result = run("kernel.roles", roles_env(database, modules))
    assert result.returncode == 0, result.stderr

    start_kernel(database, modules)

    as_kernel = url_for(database, KERNEL_USER, KERNEL_PASSWORD)
    assert query(
        as_kernel,
        "select rolsuper, rolcreaterole, rolcreatedb, rolbypassrls from pg_roles "
        "where rolname = current_user",
    ) == [(False, True, False, False)]
    assert query(as_kernel, f"select tableowner from pg_tables where schemaname = '{MODULE}'") == [
        (MODULE_ROLE,)
    ]
    assert_module_is_isolated(database)


def test_an_existing_database_changes_hands_and_keeps_working(database, modules) -> None:
    start_kernel(database, modules, as_superuser=True)

    result = run("kernel.roles", roles_env(database, modules))
    assert result.returncode == 0, result.stderr
    start_kernel(database, modules)

    as_kernel = url_for(database, KERNEL_USER, KERNEL_PASSWORD)
    owners = query(
        as_kernel,
        "select distinct pg_get_userbyid(c.relowner) from pg_class c "
        "join pg_namespace n on n.oid = c.relnamespace "
        "where n.nspname = 'kernel' and c.relkind in ('r', 'v', 'S', 'p')",
    )
    assert owners == [(KERNEL_USER,)]
    assert query(
        as_kernel, "select tableowner from pg_tables where tablename = 'alembic_version'"
    ) == [(KERNEL_USER,)]
    assert query(
        as_kernel,
        "select 1 from pg_namespace where nspname = 'kernel' and "
        f"pg_get_userbyid(nspowner) = '{KERNEL_USER}'",
    ) == [(1,)]
    assert_module_is_isolated(database)


def test_the_kernel_does_not_read_a_module_without_putting_on_its_role(database, modules) -> None:
    run("kernel.roles", roles_env(database, modules))
    start_kernel(database, modules)
    as_kernel = url_for(database, KERNEL_USER, KERNEL_PASSWORD)

    with pytest.raises(DBAPIError, match="permission denied"):
        query(as_kernel, f"select * from {MODULE}.{MODULE}_items")
    assert query(as_kernel, f"select count(*) from {MODULE}.{MODULE}_items", role=MODULE_ROLE) == [
        (0,)
    ]


def test_running_it_again_changes_nothing(database, modules) -> None:
    env = roles_env(database, modules)
    run("kernel.roles", env)
    start_kernel(database, modules)

    again = run("kernel.roles", env)

    assert again.returncode == 0, again.stderr
    assert f"sin cambios  {KERNEL_USER}" in again.stdout
    assert f"sin cambios  {MODULE_LOGIN}" in again.stdout
    assert "contraseña" not in again.stdout and "creado" not in again.stdout
    start_kernel(database, modules)


def test_the_superuser_can_still_start_the_kernel_after_the_handover(database, modules) -> None:
    run("kernel.roles", roles_env(database, modules))
    start_kernel(database, modules)

    start_kernel(database, modules, as_superuser=True)
    assert_module_is_isolated(database)


def test_a_changed_password_is_rewritten(database, modules) -> None:
    env = roles_env(database, modules)
    run("kernel.roles", env)

    rotated = secrets.token_urlsafe(24)
    result = run("kernel.roles", {**env, f"{MODULE.upper()}_DB_PASSWORD": rotated})

    assert f"contraseña   {MODULE_LOGIN}" in result.stdout
    assert query(url_for(database, MODULE_LOGIN, rotated), "select 1") == [(1,)]


def test_a_module_without_a_password_is_named_and_skipped(database, modules) -> None:
    env = roles_env(database, modules)
    del env[f"{MODULE.upper()}_DB_PASSWORD"]

    result = run("kernel.roles", env)

    assert result.returncode == 0, result.stderr
    assert f"falta {MODULE.upper()}_DB_PASSWORD" in result.stdout


@pytest.mark.parametrize("missing", ["ADMIN_DATABASE_URL", "KERNEL_DB_PASSWORD"])
def test_it_refuses_to_run_without_what_it_needs(database, modules, missing: str) -> None:
    env = roles_env(database, modules)
    env[missing] = ""

    result = run("kernel.roles", env)

    assert result.returncode == 1
    assert missing in result.stderr


def test_it_refuses_a_connection_that_is_not_a_superuser(database, modules) -> None:
    run("kernel.roles", roles_env(database, modules))

    result = run(
        "kernel.roles",
        {
            **roles_env(database, modules),
            "ADMIN_DATABASE_URL": url_for(database, KERNEL_USER, KERNEL_PASSWORD),
        },
    )

    assert result.returncode == 1
    assert "superusuario" in result.stderr


def test_the_verifier_checks_against_its_own_salt() -> None:
    stored = scram_verifier("correct horse")

    assert verifies("correct horse", stored)
    assert not verifies("wrong horse", stored)
    assert not verifies("correct horse", None)
    assert not verifies("correct horse", "md5abc")


def test_the_authorization_server_gets_its_schema_and_nothing_else(database, modules) -> None:
    password = secrets.token_urlsafe(24)
    run("kernel.roles", {**roles_env(database, modules), "AUTH_DB_PASSWORD": password})
    start_kernel(database, modules)
    as_auth = url_for(database, "arga_auth", password)

    query(as_auth, "create table auth.probe (id int)")
    for statement in (
        "select 1 from kernel.events limit 1",
        f"select 1 from {MODULE}.{MODULE}_items limit 1",
    ):
        with pytest.raises(DBAPIError, match="permission denied"):
            query(as_auth, statement)


def test_the_backup_login_reads_everything_and_changes_nothing(database, modules) -> None:
    password = secrets.token_urlsafe(24)
    result = run("kernel.roles", {**roles_env(database, modules), "BACKUP_DB_PASSWORD": password})
    assert result.returncode == 0, result.stderr
    start_kernel(database, modules)
    items = f"{MODULE}.{MODULE}_items"
    admin = url_for(database)
    query(admin, f"insert into {items} values (1)")
    query(admin, f"alter table {items} enable row level security")
    query(admin, f"alter table {items} force row level security")
    query(admin, f"create policy nobody on {items} using (false)")
    as_module = url_for(database, MODULE_LOGIN, MODULE_PASSWORD)
    assert query(as_module, f"select count(*) from {items}") == [(0,)]

    as_backup = url_for(database, "arga_backup", password)
    assert query(as_backup, f"select count(*) from {items}") == [(1,)]
    assert query(as_backup, "select count(*) from alembic_version") == [(1,)]
    for statement in (
        f"insert into {items} values (2)",
        f"delete from {items}",
        "delete from alembic_version",
        "create table kernel.colada (id int)",
        "create table public.colada (id int)",
    ):
        with pytest.raises(DBAPIError, match="permission denied"):
            query(as_backup, statement)

    again = run("kernel.roles", {**roles_env(database, modules), "BACKUP_DB_PASSWORD": password})
    assert "sin cambios  arga_backup" in again.stdout


def test_infra_declares_the_modules_by_giving_each_a_password() -> None:
    from kernel.roles import declared_modules

    found = declared_modules(
        {
            "TRAINING_DB_PASSWORD": "x",
            "LIBRARY_DB_PASSWORD": "y",
            "KERNEL_DB_PASSWORD": "no",
            "AUTH_DB_PASSWORD": "no",
            "BACKUP_DB_PASSWORD": "no",
            "POSTGRES_PASSWORD": "no",
            "DEMO_DB_PASSWORD": "",
            "OTRA_COSA": "no",
        }
    )

    assert found == {"training": "x", "library": "y"}
