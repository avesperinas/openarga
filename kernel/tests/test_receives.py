import json
from uuid import UUID

import pytest
from sqlalchemy import text

from arga_tenancy import current_user
from kernel.db import engine
from kernel.provision import provision, role_for

PRODUCER = "probe_producer"
READER = "probe_receiver"
BYSTANDER = "probe_deaf"
SOURCE = "receives-test"
STRANGER = UUID("00000000-0000-4000-8000-0000000057a6")
KERNEL_LIKE = "kernel_como_en_produccion"

INSERT_EVENT = text("""
    insert into kernel.events (ts, module, source, type, payload, dedup_hash)
    values (now(), :module, :source, :type, '{}'::jsonb, :dedup_hash)
""")

REGISTER = text("""
    insert into kernel.modules (id, version, enabled, manifest)
    values (:id, '0.1.0', true, cast(:manifest as jsonb))
    on conflict (id) do update set manifest = excluded.manifest
""")

MODULES = (PRODUCER, READER, BYSTANDER)


async def _drop_everything() -> None:
    async with engine().begin() as connection:
        await connection.execute(
            text("delete from kernel.events where source = :source"), {"source": SOURCE}
        )
        for module in MODULES:
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


async def declare(module: str, **manifest) -> None:
    async with engine().begin() as connection:
        await connection.execute(REGISTER, {"id": module, "manifest": json.dumps(manifest)})
    await provision(module)


async def emit(module: str, event_type: str, tag: str = "") -> None:
    async with engine().begin() as connection:
        await connection.execute(
            INSERT_EVENT,
            {
                "module": module,
                "source": SOURCE,
                "type": event_type,
                "dedup_hash": f"{SOURCE}:{module}:{event_type}:{tag}",
            },
        )


@pytest.fixture
async def provisioned(database_url: str):
    await _drop_everything()
    await declare(
        PRODUCER,
        publishes=[
            {"type": f"{PRODUCER}.session", "contract": "agenda"},
            {"type": f"{PRODUCER}.weight", "contract": "body_weight"},
        ],
    )
    await declare(READER, receives=["agenda"])
    await declare(BYSTANDER)
    for event_type in ("session", "weight", "secret"):
        await emit(PRODUCER, f"{PRODUCER}.{event_type}")
    await emit(READER, f"{READER}.note")
    yield
    await _drop_everything()
    await engine().dispose()


async def seen_by(module: str, role: str | None = None) -> set[str]:
    async with engine().connect() as connection:
        await connection.execute(text(f"set role {role or role_for(module)}"))
        rows = await connection.execute(
            text(f"select type from {module}.events where source = :source"), {"source": SOURCE}
        )
        return {row.type for row in rows}


async def test_a_module_sees_what_others_publish_under_the_contract_it_receives(
    provisioned,
) -> None:
    assert await seen_by(READER) == {f"{READER}.note", f"{PRODUCER}.session"}


async def test_the_rest_of_what_the_producer_writes_stays_out(provisioned) -> None:
    seen = await seen_by(READER)

    assert f"{PRODUCER}.weight" not in seen
    assert f"{PRODUCER}.secret" not in seen


async def test_a_module_that_receives_nothing_sees_only_its_own(provisioned) -> None:
    assert await seen_by(BYSTANDER) == set()


async def test_the_reader_role_sees_the_same(provisioned) -> None:
    assert await seen_by(READER, f"{role_for(READER)}_read") == {
        f"{READER}.note",
        f"{PRODUCER}.session",
    }


async def test_a_new_publisher_reaches_the_reader_when_it_registers(provisioned) -> None:
    await declare(BYSTANDER, publishes=[{"type": f"{BYSTANDER}.class", "contract": "agenda"}])
    await emit(BYSTANDER, f"{BYSTANDER}.class")

    assert f"{BYSTANDER}.class" in await seen_by(READER)


async def test_a_type_that_stops_being_published_leaves_the_reader(provisioned) -> None:
    await declare(PRODUCER, publishes=[])

    assert await seen_by(READER) == {f"{READER}.note"}


async def test_a_module_cannot_publish_under_another_module_name(provisioned) -> None:
    await declare(BYSTANDER, publishes=[{"type": f"{PRODUCER}.secret", "contract": "agenda"}])

    assert f"{PRODUCER}.secret" not in await seen_by(READER)


async def test_a_received_type_sent_by_another_app_never_arrives(provisioned) -> None:
    await emit(BYSTANDER, f"{PRODUCER}.session", tag="impostor")

    async with engine().connect() as connection:
        await connection.execute(text(f"set role {role_for(READER)}"))
        modules = {
            row.module
            for row in await connection.execute(
                text(f"select module from {READER}.events where type = :type"),
                {"type": f"{PRODUCER}.session"},
            )
        }
    assert modules == {PRODUCER}


async def test_what_another_person_publishes_never_arrives(provisioned) -> None:
    async with engine().begin() as connection:
        await connection.execute(
            text(
                "do $$ begin if not exists "
                f"(select 1 from pg_roles where rolname = '{KERNEL_LIKE}') "
                f"then create role {KERNEL_LIKE} nologin; end if; end $$"
            )
        )
        await connection.execute(text(f"grant usage on schema kernel to {KERNEL_LIKE}"))
        await connection.execute(
            text(f"grant select on kernel.events, kernel.modules to {KERNEL_LIKE}")
        )
        await connection.execute(text(f"alter view {READER}.events owner to {KERNEL_LIKE}"))
    token = current_user.set(STRANGER)
    try:
        await emit(PRODUCER, f"{PRODUCER}.session", "stranger")
    finally:
        current_user.reset(token)

    async with engine().connect() as connection:
        await connection.execute(text(f"set role {role_for(READER)}"))
        count = await connection.scalar(
            text(f"select count(*) from {READER}.events where type = :type"),
            {"type": f"{PRODUCER}.session"},
        )
    assert count == 1


async def test_a_module_still_cannot_write_through_its_view(provisioned) -> None:
    async with engine().connect() as connection:
        await connection.execute(text(f"set role {role_for(READER)}"))
        with pytest.raises(Exception, match="permission denied"):
            await connection.execute(
                text(f"insert into {READER}.events (module, type) values ('x', 'x.y')")
            )


async def test_whoever_receives_metric_sees_the_figures_of_every_app_that_publishes_them(
    provisioned,
) -> None:
    await declare(PRODUCER, publishes=[{"type": f"{PRODUCER}.metric", "contract": "metric"}])
    await declare(BYSTANDER, publishes=[{"type": f"{BYSTANDER}.metric", "contract": "metric"}])
    await declare(READER, receives=["metric"])
    await emit(PRODUCER, f"{PRODUCER}.metric")
    await emit(BYSTANDER, f"{BYSTANDER}.metric")

    assert await seen_by(READER) == {
        f"{READER}.note",
        f"{PRODUCER}.metric",
        f"{BYSTANDER}.metric",
    }
