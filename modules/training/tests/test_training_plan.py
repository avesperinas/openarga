from __future__ import annotations

from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.ext.asyncio import create_async_engine

from arga_tenancy import install
from training import db, seed
from training.main import MODULE_ID, app

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
async def provisioned(database_url: str):

    from arga_testing import fresh_modules

    setup = install(create_async_engine(database_url))
    async with setup.begin() as connection:
        await fresh_modules(connection, MODULE_ID, root=ROOT)
    yield setup
    async with setup.begin() as connection:
        await connection.execute(text("delete from kernel.modules where id = :m"), {"m": MODULE_ID})
    await setup.dispose()
    await db.engine().dispose()
    db.engine.cache_clear()


async def as_module(setup, statement: str, role: str = "mod_training"):
    async with setup.begin() as connection:
        await connection.execute(text(f'set local role "{role}"'))
        result = await connection.execute(text(statement))
        return result.all() if result.returns_rows else []


async def seeded(setup) -> None:
    async with setup.begin() as connection:
        await connection.execute(text('set local role "mod_training"'))
        await seed.seed(connection)


@pytest.fixture
async def api():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://training") as client:
        yield client


async def test_without_a_plan_today_says_so_and_brings_the_settings(api, provisioned) -> None:
    body = (await api.get("/today")).json()

    assert body["plan"] is None
    assert body["settings"]["weekly_goal"] == 5


async def test_today_brings_the_active_plan_with_its_days_slots_and_options(
    api, provisioned
) -> None:
    await seeded(provisioned)

    body = (await api.get("/today")).json()
    plan = body["plan"]

    assert [(d["name"], d["kind"]) for d in plan["days"]] == [
        ("Push", "push"),
        ("Pull", "pull"),
        ("Leg", "leg"),
    ]
    first = plan["days"][0]["slots"][0]
    assert first["exercise"] == "Press banca"
    assert (first["target_sets"], first["rep_min"], first["rep_max"]) == (4, 6, 10)
    assert [o["name"] for o in first["options"]] == [
        "Press banca con barra",
        "Press banca en máquina",
    ]
    leg = plan["days"][2]["slots"][0]
    assert leg["allow_both"] is True


async def test_a_published_version_cannot_be_rewritten(provisioned) -> None:
    await seeded(provisioned)

    for statement in (
        "update training.training_plan_slot set target_sets = 5",
        "delete from training.training_plan_day",
        "update training.training_plan_version set number = 9",
    ):
        with pytest.raises(DBAPIError, match="publicada"):
            await as_module(provisioned, statement)


async def test_a_draft_is_editable_and_does_not_show_on_today(api, provisioned) -> None:
    await seeded(provisioned)
    await as_module(
        provisioned,
        "insert into training.training_plan_version (plan_id, number) "
        "select id, 2 from training.training_plan where active",
    )
    await as_module(
        provisioned,
        "insert into training.training_plan_day (plan_version_id, name, kind, position) "
        "select id, 'Full', 'full', 1 from training.training_plan_version where number = 2",
    )

    body = (await api.get("/today")).json()

    assert body["plan"]["version"] == 1
    assert len(body["plan"]["days"]) == 3


async def test_a_slot_option_is_a_variant_never_a_bare_exercise(provisioned) -> None:
    await seeded(provisioned)

    with pytest.raises(IntegrityError):
        await as_module(
            provisioned,
            "insert into training.training_plan_slot_option (plan_slot_id, variant_id, priority) "
            "select s.id, e.id, 9 from training.training_plan_slot s, training.training_exercise e limit 1",
        )


async def test_bodyweight_factor_only_exists_when_the_body_is_the_load(provisioned) -> None:
    with pytest.raises(IntegrityError):
        await as_module(
            provisioned,
            "insert into training.training_exercise (name, pattern, load_type, bodyweight_factor) "
            "values ('Press raro', 'horizontal_push', 'external', 0.9)",
        )


async def test_only_one_plan_is_active(provisioned) -> None:
    await seeded(provisioned)

    with pytest.raises(IntegrityError):
        await as_module(
            provisioned, "insert into training.training_plan (name, active) values ('Otro', true)"
        )


async def test_the_synthetic_seed_refuses_to_mix_with_a_real_plan(provisioned) -> None:
    await seeded(provisioned)

    with pytest.raises(RuntimeError, match="ya hay un plan"):
        await seeded(provisioned)


async def test_the_read_role_reads_the_plan_and_cannot_change_it(provisioned) -> None:
    await seeded(provisioned)

    rows = await as_module(
        provisioned, "select count(*) from training.training_variant", "mod_training_read"
    )
    assert rows[0][0] == 10
    with pytest.raises(DBAPIError, match="permission denied"):
        await as_module(
            provisioned, "delete from training.training_bodyweight", "mod_training_read"
        )


async def test_without_a_plan_the_widgets_are_empty_not_broken(api, provisioned) -> None:
    week = (await api.get("/widgets/week")).json()
    upcoming = (await api.get("/widgets/next")).json()

    assert (week["state"], upcoming["state"]) == ("empty", "empty")
    assert "detail" not in upcoming["body"]
