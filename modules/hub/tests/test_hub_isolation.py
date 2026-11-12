from __future__ import annotations

from uuid import UUID

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from arga_crypto import Undecipherable
from arga_tenancy import as_user
from hub import credentials

ANA = UUID("0a0a0a0a-0000-4000-8000-00000000a0a0")
EVA = UUID("0e0e0e0e-0000-4000-8000-00000000e0e0")
WRITE = "mod_hub"
READ = "mod_hub_read"


async def as_role(engine, role: str, person: UUID | None, statement: str, **params):
    with as_user(person):
        async with engine.begin() as connection:
            await connection.execute(text(f'set local role "{role}"'))
            result = await connection.execute(text(statement), params)
            return result.all() if result.returns_rows else result.rowcount


CONNECT = "insert into hub.hub_connection (provider, label) values (:provider, :label) returning id"


@pytest.fixture
async def two_people(schema):
    ana = (await as_role(schema, WRITE, ANA, CONNECT, provider="bitvavo", label="Bitvavo"))[0].id
    eva = (await as_role(schema, WRITE, EVA, CONNECT, provider="claude", label="Claude"))[0].id
    for person, connection in ((ANA, ana), (EVA, eva)):
        await as_role(
            schema,
            WRITE,
            person,
            "insert into hub.hub_run (connection_id, capability, operation, "
            "outcome) values (:c, 'sync', 'balances', 'ok')",
            c=connection,
        )
    return schema, ana, eva


@pytest.mark.parametrize("role", [WRITE, READ])
async def test_each_person_sees_only_their_connections_and_runs(two_people, role: str) -> None:
    schema, _, _ = two_people

    ana = await as_role(schema, role, ANA, "select label from hub.hub_connection")
    eva_runs = await as_role(schema, role, EVA, "select 1 from hub.hub_run")

    assert [row.label for row in ana] == ["Bitvavo"]
    assert len(eva_runs) == 1


@pytest.mark.parametrize("role", [WRITE, READ])
async def test_without_a_person_nothing_is_seen(two_people, role: str) -> None:
    schema, _, _ = two_people

    assert await as_role(schema, role, None, "select * from hub.hub_connection") == []


async def test_the_read_role_cannot_write(two_people) -> None:
    schema, _, _ = two_people

    with pytest.raises(DBAPIError, match="permission denied"):
        await as_role(schema, READ, ANA, CONNECT, provider="bitvavo", label="Otra")


async def test_the_read_role_sees_that_a_credential_exists_but_not_the_secret(two_people) -> None:
    schema, ana, _ = two_people
    with as_user(ANA):
        async with schema.begin() as connection:
            await connection.execute(text(f'set local role "{WRITE}"'))
            await credentials.store(connection, "bitvavo", ana, "api_key", "clave-de-prueba-1234")

    keys = await as_role(schema, READ, ANA, "select key from hub.hub_credential")
    with pytest.raises(DBAPIError, match="permission denied"):
        await as_role(schema, READ, ANA, "select ciphertext from hub.hub_credential")

    assert [row.key for row in keys] == ["api_key"]


async def test_the_module_role_cannot_reach_the_kernel_log(two_people) -> None:
    schema, _, _ = two_people

    with pytest.raises(DBAPIError, match="permission denied"):
        await as_role(schema, WRITE, ANA, "select * from kernel.events")


async def test_the_value_goes_in_encrypted_and_opens_only_for_its_person(two_people) -> None:
    schema, ana, _ = two_people
    with as_user(ANA):
        async with schema.begin() as connection:
            await connection.execute(text(f'set local role "{WRITE}"'))
            await credentials.store(connection, "bitvavo", ana, "api_key", "clave-de-prueba-1234")
            raw = await connection.scalar(text("select ciphertext from hub.hub_credential"))
            opened = await credentials.use(connection, "bitvavo", ana, "api_key")
            listed = await credentials.status(connection, ana, ("api_key", "api_secret"))

    assert b"clave-de-prueba" not in bytes(raw)
    assert opened == "clave-de-prueba-1234"
    assert [(s.key, s.configured, s.hint) for s in listed] == [
        ("api_key", True, "…1234"),
        ("api_secret", False, None),
    ]


def test_a_secret_sealed_for_one_provider_does_not_open_with_another() -> None:
    sealed = credentials.vault("enable_banking").seal(ANA, "c:key", "secreto-de-prueba")

    with pytest.raises(Undecipherable):
        credentials.vault("claude").open(ANA, "c:key", sealed)


def test_a_secret_copied_to_another_connection_or_person_does_not_open() -> None:
    box = credentials.vault("bitvavo")
    sealed = box.seal(ANA, "una:api_key", "secreto-de-prueba")

    with pytest.raises(Undecipherable):
        box.open(ANA, "otra:api_key", sealed)
    with pytest.raises(Undecipherable):
        box.open(EVA, "una:api_key", sealed)


def test_what_was_sealed_with_the_previous_key_still_opens(monkeypatch) -> None:
    import os

    old = os.environ["HUB_CREDENTIALS_KEY"]
    sealed = credentials.vault("bitvavo").seal(ANA, "c:key", "secreto-de-prueba")

    monkeypatch.setenv("HUB_CREDENTIALS_KEY", os.urandom(32).hex())
    monkeypatch.setenv("HUB_CREDENTIALS_KEY_PREVIOUS", old)
    credentials.masters.cache_clear()
    try:
        box = credentials.vault("bitvavo")
        assert box.open(ANA, "c:key", sealed) == "secreto-de-prueba"
        assert box.stale(sealed)
    finally:
        monkeypatch.undo()
        credentials.masters.cache_clear()
