import re

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from kernel.db import engine
from kernel.isolation import ModuleNotProvisioned, describe
from kernel.main import app
from kernel.provision import MODULE_ID_PATTERN, provision, role_for

MODULE = "probe_a"
NEIGHBOUR = "probe_b"
SOURCE = "isolation-test"

INSERT_EVENT = text("""
    insert into kernel.events (ts, module, source, type, payload, dedup_hash)
    values (now(), :module, :source, 'probe_a.ping', '{}'::jsonb, :dedup_hash)
""")


async def _drop_everything() -> None:
    async with engine().begin() as connection:
        await connection.execute(
            text("delete from kernel.events where source = :source"), {"source": SOURCE}
        )
        for module in (MODULE, NEIGHBOUR):
            await connection.execute(text(f"drop schema if exists {module} cascade"))
            await connection.execute(
                text(
                    "do $$ begin "
                    f"if exists (select 1 from pg_roles where rolname = '{role_for(module)}') "
                    f"then execute 'drop owned by {role_for(module)}'; "
                    f"execute 'drop role {role_for(module)}'; "
                    "end if; end $$"
                )
            )


@pytest.fixture
async def provisioned(database_url: str):
    await _drop_everything()
    await provision(MODULE)
    await provision(NEIGHBOUR)
    async with engine().begin() as connection:
        await connection.execute(text(f"create table {NEIGHBOUR}.ledger (id int)"))
    yield
    await _drop_everything()
    await engine().dispose()


@pytest.fixture
async def api():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://kernel") as client:
        yield client


async def run_as(role: str, statement: str) -> list:
    async with engine().connect() as connection:
        await connection.execute(text(f"set role {role}"))
        return (await connection.execute(text(statement))).all()


async def test_provisioning_creates_the_schema_and_the_role(provisioned) -> None:
    async with engine().connect() as connection:
        report = await describe(connection, MODULE)

    assert report.db_schema == MODULE
    assert report.role == f"mod_{MODULE}"
    assert report.own_schema.usage and report.own_schema.create


async def test_the_module_role_cannot_read_another_module_schema(provisioned) -> None:
    with pytest.raises(DBAPIError) as failure:
        await run_as(f"mod_{MODULE}", f"select * from {NEIGHBOUR}.ledger")

    assert f"permission denied for schema {NEIGHBOUR}" in str(failure.value)


async def test_the_module_role_cannot_read_kernel_events_directly(provisioned) -> None:
    with pytest.raises(DBAPIError) as failure:
        await run_as(f"mod_{MODULE}", "select * from kernel.events")

    assert "permission denied for schema kernel" in str(failure.value)


async def test_the_module_only_sees_its_own_events(provisioned) -> None:
    async with engine().begin() as connection:
        for module in (MODULE, NEIGHBOUR):
            await connection.execute(
                INSERT_EVENT,
                {"module": module, "source": SOURCE, "dedup_hash": f"{SOURCE}:{module}"},
            )

    rows = await run_as(f"mod_{MODULE}", f"select module from {MODULE}.events")

    assert {row.module for row in rows} == {MODULE}
    assert rows


async def test_the_module_cannot_write_through_the_events_view(provisioned) -> None:
    with pytest.raises(DBAPIError) as failure:
        await run_as(
            f"mod_{MODULE}",
            f"insert into {MODULE}.events (ts, module, source, type, payload) "
            f"values (now(), '{MODULE}', 'x', '{MODULE}.ping', '{{}}'::jsonb)",
        )

    assert "permission denied for view events" in str(failure.value)


async def test_provisioning_is_idempotent(provisioned) -> None:
    async with engine().connect() as connection:
        before = await describe(connection, MODULE)

    await provision(MODULE)

    async with engine().connect() as connection:
        assert await describe(connection, MODULE) == before


@pytest.mark.parametrize(
    "module_id", ["Demo", "demo-1", "demo.1", "1demo", "d", "", "demo; drop schema kernel"]
)
async def test_provisioning_rejects_an_invalid_module_id(database_url: str, module_id: str) -> None:
    assert re.match(MODULE_ID_PATTERN, module_id) is None

    with pytest.raises(DBAPIError) as failure:
        await provision(module_id)

    assert "invalid module id" in str(failure.value)


async def test_the_endpoint_reports_the_effective_grants(provisioned, api) -> None:
    response = await api.get(f"/modules/{MODULE}/isolation")

    assert response.status_code == 200
    body = response.json()
    assert body["schema"] == MODULE
    assert body["role"] == f"mod_{MODULE}"
    assert body["events"]["name"] == f"{MODULE}.events"
    assert f"module = '{MODULE}'" in body["events"]["definition"]

    access = {entry["object"]: entry for entry in body["access"]}
    assert access[f"{MODULE}.events"] == {
        "object": f"{MODULE}.events",
        "granted": ["SELECT"],
        "usable": True,
    }
    assert access["kernel.events"]["granted"] == []
    assert access[f"{NEIGHBOUR}.ledger"]["usable"] is False


async def test_the_endpoint_404s_for_a_module_that_is_not_provisioned(
    database_url: str, api
) -> None:
    response = await api.get("/modules/nobody/isolation")

    assert response.status_code == 404
    assert "schema nobody" in response.json()["detail"]
    assert "role mod_nobody" in response.json()["detail"]


async def test_the_endpoint_rejects_an_invalid_module_id(database_url: str, api) -> None:
    assert (await api.get("/modules/Demo/isolation")).status_code == 422


async def test_describe_raises_when_the_module_is_unknown(database_url: str) -> None:
    async with engine().connect() as connection:
        with pytest.raises(ModuleNotProvisioned):
            await describe(connection, "nobody")
    await engine().dispose()
