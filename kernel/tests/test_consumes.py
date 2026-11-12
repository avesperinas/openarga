import json

import pytest
from sqlalchemy import text

from kernel.db import engine
from kernel.provision import provision, role_for

READER = "probe_reader"
BYSTANDER = "probe_bystander"
SOURCE = "consumes-test"

INSERT_EVENT = text("""
    insert into kernel.events (ts, module, source, type, payload, dedup_hash)
    values (now(), :module, :source, :type, '{}'::jsonb, :dedup_hash)
""")

REGISTER = text("""
    insert into kernel.modules (id, version, enabled, manifest)
    values (:id, '0.1.0', true, cast(:manifest as jsonb))
    on conflict (id) do update set manifest = excluded.manifest
""")


async def _drop_everything() -> None:
    async with engine().begin() as connection:
        await connection.execute(
            text("delete from kernel.events where source = :source"), {"source": SOURCE}
        )
        for module in (READER, BYSTANDER):
            await connection.execute(
                text("delete from kernel.modules where id = :id"), {"id": module}
            )
            await connection.execute(text(f"drop schema if exists {module} cascade"))
            for role in (role_for(module), f"{role_for(module)}_read"):
                await connection.execute(
                    text(
                        "do $$ begin "
                        f"if exists (select 1 from pg_roles where rolname = '{role}') "
                        f"then execute 'drop owned by {role}'; execute 'drop role {role}'; "
                        "end if; end $$"
                    )
                )


async def declare(module: str, consumes: list[str]) -> None:
    async with engine().begin() as connection:
        await connection.execute(
            REGISTER, {"id": module, "manifest": json.dumps({"consumes": consumes})}
        )
    await provision(module)


@pytest.fixture
async def provisioned(database_url: str):
    await _drop_everything()
    await declare(READER, ["finance.movement"])
    await declare(BYSTANDER, [])
    async with engine().begin() as connection:
        for module, event_type in (
            ("hub", "finance.movement"),
            ("hub", "finance.balance"),
            (READER, f"{READER}.note"),
            (BYSTANDER, f"{BYSTANDER}.note"),
        ):
            await connection.execute(
                INSERT_EVENT,
                {
                    "module": module,
                    "source": SOURCE,
                    "type": event_type,
                    "dedup_hash": f"{SOURCE}:{module}:{event_type}",
                },
            )
    yield
    await _drop_everything()
    await engine().dispose()


async def seen_by(module: str) -> set[str]:
    async with engine().connect() as connection:
        await connection.execute(text(f"set role {role_for(module)}"))
        rows = await connection.execute(
            text(f"select type from {module}.events where source = :source"), {"source": SOURCE}
        )
        return {row.type for row in rows}


async def test_a_module_sees_its_own_events_and_what_it_consumes(provisioned) -> None:
    assert await seen_by(READER) == {f"{READER}.note", "finance.movement"}


async def test_what_it_does_not_declare_stays_out(provisioned) -> None:
    assert "finance.balance" not in await seen_by(READER)


async def test_a_module_that_consumes_nothing_sees_only_its_own(provisioned) -> None:
    assert await seen_by(BYSTANDER) == {f"{BYSTANDER}.note"}


async def test_dropping_a_type_from_the_manifest_takes_it_out_of_the_view(provisioned) -> None:
    await declare(READER, [])

    assert await seen_by(READER) == {f"{READER}.note"}


async def test_the_reader_role_sees_the_same(provisioned) -> None:
    async with engine().connect() as connection:
        await connection.execute(text(f"set role {role_for(READER)}_read"))
        rows = await connection.execute(
            text(f"select type from {READER}.events where source = :source"), {"source": SOURCE}
        )
        assert {row.type for row in rows} == {f"{READER}.note", "finance.movement"}
