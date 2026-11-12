from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from arga_testing import fresh_modules
from arga_testing import manifests as repo_manifests
from kernel import sealed
from kernel.db import engine

REPO = Path(__file__).resolve().parents[2]
MODULES = REPO / "modules"

EXPOSED = text("""
    select n.nspname || '.' || c.relname as name,
           case when acl.grantee = 0 then 'PUBLIC' else pg_get_userbyid(acl.grantee) end as grantee
    from pg_catalog.pg_class c
    join pg_catalog.pg_namespace n on n.oid = c.relnamespace
    join pg_catalog.pg_attribute a on a.attrelid = c.oid and a.attname = 'ciphertext'
     and not a.attisdropped
    cross join lateral aclexplode(coalesce(a.attacl, c.relacl)) acl
    where n.nspname = any(:schemas)
      and (acl.grantee = 0 or pg_get_userbyid(acl.grantee) <> 'mod_' || n.nspname)
    order by 1, 2
""")


@pytest.fixture
async def registered(database_url: str):
    manifests = repo_manifests(MODULES)
    async with engine().begin() as connection:
        await fresh_modules(connection, *(m.id for m in manifests))
    yield [m.id for m in manifests]
    async with engine().begin() as connection:
        for manifest in manifests:
            await connection.execute(
                text("delete from kernel.modules where id = :id"), {"id": manifest.id}
            )
    await engine().dispose()


async def as_role(role: str, statement: str):
    async with engine().begin() as connection:
        await connection.execute(text(f'set local role "{role}"'))
        return (await connection.execute(text(statement))).all()


async def secret_tables(modules: list[str]) -> list[str]:
    found = []
    async with engine().connect() as connection:
        for module in modules:
            found.extend(await sealed.secret_tables(connection, module))
    return found


async def test_the_repo_has_secret_tables_and_they_are_recognised(registered) -> None:
    assert set(await secret_tables(registered)) >= {
        "hub.hub_credential",
    }


async def test_nobody_but_the_owner_can_read_the_secret(registered) -> None:
    async with engine().connect() as connection:
        exposed = (await connection.execute(EXPOSED, {"schemas": registered})).all()

    assert exposed == []


@pytest.mark.parametrize("module", ["hub"])
async def test_the_read_role_cannot_read_a_credential_even_encrypted(registered, module) -> None:
    with pytest.raises(DBAPIError, match="permission denied"):
        await as_role(f"mod_{module}_read", f"select ciphertext from {module}.{module}_credential")


@pytest.mark.parametrize("module", ["hub"])
async def test_the_module_itself_still_can(registered, module) -> None:
    assert (
        await as_role(f"mod_{module}", f"select ciphertext from {module}.{module}_credential") == []
    )


@pytest.mark.parametrize("module", ["hub"])
async def test_the_read_role_still_sees_which_credentials_there_are(registered, module) -> None:
    assert (
        await as_role(f"mod_{module}_read", f"select key from {module}.{module}_credential") == []
    )


async def test_the_read_role_still_reads_everything_else(registered) -> None:
    assert await as_role("mod_money_read", "select id from money.money_v1_account") == []


async def test_a_permission_opened_by_hand_is_closed_at_the_next_boot(
    registered, database_url
) -> None:
    async with engine().begin() as connection:
        await connection.execute(text("grant select on hub.hub_credential to mod_hub_read"))
        await connection.execute(text("grant select on hub.hub_credential to public"))

    closed = await sealed.seal_everything(database_url)

    assert "hub.hub_credential" in closed["hub"]

    with pytest.raises(DBAPIError, match="permission denied"):
        await as_role("mod_hub_read", "select ciphertext from hub.hub_credential")
    async with engine().connect() as connection:
        assert (await connection.execute(EXPOSED, {"schemas": registered})).all() == []
