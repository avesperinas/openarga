from __future__ import annotations

from pathlib import Path
from uuid import UUID

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from arga_tenancy import CURRENT_USER_SQL, as_user
from arga_testing import fresh_modules
from kernel.db import engine
from kernel.rls import IN_SPACE, enforce
from kernel.schemas import grant_to_reader

REPO = Path(__file__).resolve().parents[2]
MODULES = REPO / "modules"
ANA = UUID("0a0a0a0a-0000-4000-8000-00000000a0a0")
LUIS = UUID("0b0b0b0b-0000-4000-8000-00000000b0b0")
KERNEL_LIKE = "kernel_como_en_produccion"


async def as_role(role: str, person: UUID | None, statement: str, **params):
    with as_user(person):
        async with engine().begin() as connection:
            await connection.execute(text(f'set local role "{role}"'))
            result = await connection.execute(text(statement), params)
            return result.all() if result.returns_rows else result.rowcount


@pytest.fixture
async def two_people(database_url: str):
    async with engine().begin() as connection:
        await connection.execute(text("delete from kernel.events where module = 'training'"))
        await fresh_modules(connection, "training")
        await connection.execute(
            text(
                "do $$ begin if not exists "
                f"(select 1 from pg_roles where rolname = '{KERNEL_LIKE}') "
                f"then create role {KERNEL_LIKE} nologin; end if; end $$"
            )
        )
        await connection.execute(text(f"grant usage on schema kernel to {KERNEL_LIKE}"))
        await connection.execute(text(f"grant select, insert on kernel.events to {KERNEL_LIKE}"))
        await connection.execute(text(f"grant select on kernel.modules to {KERNEL_LIKE}"))
        await connection.execute(text(f"alter view training.events owner to {KERNEL_LIKE}"))
    for person, name in ((ANA, "Ana"), (LUIS, "Luis")):
        with as_user(person):
            async with engine().begin() as connection:
                await connection.execute(text('set local role "mod_training"'))
                await connection.execute(
                    text("insert into training.training_gym (name) values (:n)"),
                    {"n": f"Gimnasio de {name}"},
                )
                await connection.execute(
                    text(
                        "insert into training.training_bodyweight (day, kg) values ('2026-09-17', :kg)"
                    ),
                    {"kg": 70 if person == ANA else 80},
                )
            async with engine().begin() as connection:
                await connection.execute(
                    text(
                        "insert into kernel.events (ts, module, source, type, payload, dedup_hash) "
                        "values (now(), 'training', 'app', :type, '{}', 'misma-clave')"
                    ),
                    {"type": f"training.probe_{name.lower()}"},
                )
    with as_user(None):
        async with engine().begin() as connection:
            await connection.execute(
                text(
                    "insert into training.training_gym (name, user_id) values ('Gimnasio de todos', null)"
                )
            )
    yield
    async with engine().begin() as connection:
        await connection.execute(text("delete from kernel.events where module = 'training'"))
        await connection.execute(text("delete from kernel.modules where id = 'training'"))
    await engine().dispose()


@pytest.mark.parametrize("role", ["mod_training", "mod_training_read"])
async def test_each_person_reads_only_what_is_theirs(two_people, role: str) -> None:
    ana = await as_role(role, ANA, "select kg from training.training_bodyweight")
    luis = await as_role(role, LUIS, "select kg from training.training_bodyweight")

    assert [float(row.kg) for row in ana] == [70.0]
    assert [float(row.kg) for row in luis] == [80.0]


@pytest.mark.parametrize("role", ["mod_training", "mod_training_read"])
async def test_through_the_events_view_too(two_people, role: str) -> None:
    ana = await as_role(role, ANA, "select type from training.events")
    luis = await as_role(role, LUIS, "select type from training.events")

    assert [row.type for row in ana] == ["training.probe_ana"]
    assert [row.type for row in luis] == ["training.probe_luis"]


@pytest.mark.parametrize("role", ["mod_training", "mod_training_read"])
async def test_without_a_person_nothing_is_seen(two_people, role: str) -> None:
    assert await as_role(role, None, "select * from training.training_bodyweight") == []
    assert await as_role(role, None, "select * from training.events") == []


async def test_the_catalogue_shows_what_is_everyones_and_what_is_yours(two_people) -> None:
    ana = await as_role("mod_training", ANA, "select name from training.training_gym order by name")

    assert [row.name for row in ana] == ["Gimnasio de Ana", "Gimnasio de todos"]


async def test_writing_in_someone_elses_name_is_refused_by_postgres(two_people) -> None:
    with pytest.raises(DBAPIError, match="row-level security"):
        await as_role(
            "mod_training",
            ANA,
            "insert into training.training_bodyweight (day, kg, user_id) values ('2026-09-18', 1, :luis)",
            luis=LUIS,
        )
    with pytest.raises(DBAPIError, match="row-level security"):
        await as_role(
            "mod_training",
            ANA,
            "insert into training.training_gym (name, user_id) values ('De todos', null)",
        )


async def test_changing_someone_elses_rows_changes_nothing(two_people) -> None:
    changed = await as_role(
        "mod_training", ANA, "update training.training_bodyweight set kg = 1 where kg = 80"
    )
    removed = await as_role(
        "mod_training", ANA, "delete from training.training_bodyweight where kg = 80"
    )

    assert (changed, removed) == (0, 0)
    assert [
        float(r.kg)
        for r in await as_role("mod_training", LUIS, "select kg from training.training_bodyweight")
    ] == [80.0]


async def test_even_the_owner_of_the_table_is_filtered(two_people) -> None:
    owner = await as_role(
        "mod_training",
        None,
        "select pg_get_userbyid(relowner) as owner, relrowsecurity, relforcerowsecurity "
        "from pg_class where oid = 'training.training_bodyweight'::regclass",
    )

    assert (owner[0].owner, owner[0].relrowsecurity, owner[0].relforcerowsecurity) == (
        "mod_training",
        True,
        True,
    )
    assert await as_role("mod_training", None, "select * from training.training_bodyweight") == []


async def test_two_people_can_have_the_same_day(two_people) -> None:
    days = await as_role("mod_training", ANA, "select day from training.training_bodyweight")
    events = await as_role(
        KERNEL_LIKE, LUIS, "select dedup_hash from kernel.events where module = 'training'"
    )

    assert [str(row.day) for row in days] == ["2026-09-17"]
    assert [row.dedup_hash for row in events] == ["misma-clave"]


SHARED = "espacio"
HOME = UUID("0c0c0c0c-0000-4000-8000-00000000c0c0")
OTHER = UUID("0d0d0d0d-0000-4000-8000-00000000d0d0")
EVA = UUID("0e0e0e0e-0000-4000-8000-00000000e0e0")


async def in_space(role: str, person: UUID | None, spaces: tuple[UUID, ...], statement: str, **p):
    with as_user(person, spaces):
        async with engine().begin() as connection:
            await connection.execute(text(f'set local role "{role}"'))
            result = await connection.execute(text(statement), p)
            return result.all() if result.returns_rows else result.rowcount


@pytest.fixture
async def a_shared_space(database_url: str):
    async with engine().begin() as connection:
        await connection.execute(text(f'drop schema if exists "{SHARED}" cascade'))
        await connection.execute(text("select kernel.provision_module(:m)"), {"m": SHARED})
        await connection.execute(text(f'set local role "mod_{SHARED}"'))
        await connection.execute(
            text(f"""
                create table {SHARED}.{SHARED}_expense (
                    concept  text not null,
                    user_id  uuid not null default {CURRENT_USER_SQL},
                    space_id uuid
                )
            """)
        )
        await connection.execute(
            text(f"comment on table {SHARED}.{SHARED}_expense is 'arga:shared'")
        )
        await connection.execute(text("reset role"))
        await grant_to_reader(connection, SHARED)
        await connection.execute(text("reset role"))
        touched = await enforce(connection, SHARED)
    assert touched == [f"{SHARED}.{SHARED}_expense"]

    rows = [
        (ANA, (HOME,), "home groceries", HOME),
        (LUIS, (HOME,), "home electricity", HOME),
        (ANA, (HOME,), "Ana dinner", None),
        (LUIS, (HOME,), "Luis book", None),
        (EVA, (OTHER,), "Eva rent", OTHER),
    ]
    for person, spaces, concept, space in rows:
        await in_space(
            f"mod_{SHARED}",
            person,
            spaces,
            f"insert into {SHARED}.{SHARED}_expense (concept, space_id) values (:c, :s)",
            c=concept,
            s=space,
        )
    yield
    async with engine().begin() as connection:
        await connection.execute(text(f'drop schema if exists "{SHARED}" cascade'))
    await engine().dispose()


def concepts(rows) -> list[str]:
    return sorted(row.concept for row in rows)


@pytest.mark.parametrize("role", [f"mod_{SHARED}", f"mod_{SHARED}_read"])
async def test_a_member_sees_the_space_and_what_is_theirs_and_nothing_else(
    a_shared_space, role: str
) -> None:
    ana = await in_space(role, ANA, (HOME,), f"select concept from {SHARED}.{SHARED}_expense")
    luis = await in_space(role, LUIS, (HOME,), f"select concept from {SHARED}.{SHARED}_expense")

    assert concepts(ana) == ["Ana dinner", "home electricity", "home groceries"]
    assert concepts(luis) == ["Luis book", "home electricity", "home groceries"]


@pytest.mark.parametrize("role", [f"mod_{SHARED}", f"mod_{SHARED}_read"])
async def test_someone_outside_the_space_does_not_see_it(a_shared_space, role: str) -> None:
    eva = await in_space(role, EVA, (OTHER,), f"select concept from {SHARED}.{SHARED}_expense")

    assert concepts(eva) == ["Eva rent"]


@pytest.mark.parametrize("role", [f"mod_{SHARED}", f"mod_{SHARED}_read"])
async def test_without_the_guc_only_what_is_yours_is_seen(a_shared_space, role: str) -> None:
    ana = await in_space(role, ANA, (), f"select concept from {SHARED}.{SHARED}_expense")
    nobody = await in_space(role, None, (), f"select concept from {SHARED}.{SHARED}_expense")

    assert concepts(ana) == ["Ana dinner", "home groceries"]
    assert nobody == []


async def test_after_leaving_what_you_put_stays_with_everyone_but_you_no_longer_write_it(
    a_shared_space,
) -> None:
    with pytest.raises(DBAPIError, match="row-level security"):
        await in_space(
            f"mod_{SHARED}",
            ANA,
            (),
            f"update {SHARED}.{SHARED}_expense set concept = 'groceries, changed' "
            "where concept = 'home groceries'",
        )
    luis = await in_space(
        f"mod_{SHARED}", LUIS, (HOME,), f"select concept from {SHARED}.{SHARED}_expense"
    )
    taken = await in_space(
        f"mod_{SHARED}",
        ANA,
        (),
        f"update {SHARED}.{SHARED}_expense set space_id = null where concept = 'home groceries'",
    )
    after = await in_space(
        f"mod_{SHARED}", LUIS, (HOME,), f"select concept from {SHARED}.{SHARED}_expense"
    )

    assert concepts(luis) == ["Luis book", "home electricity", "home groceries"]
    assert taken == 1
    assert concepts(after) == ["Luis book", "home electricity"]


async def test_someone_with_no_spaces_cannot_put_a_row_of_theirs_in_a_space(a_shared_space) -> None:
    with pytest.raises(DBAPIError, match="row-level security"):
        await in_space(
            f"mod_{SHARED}",
            ANA,
            (),
            f"insert into {SHARED}.{SHARED}_expense (concept, space_id) values ('colada', :s)",
            s=OTHER,
        )
    with pytest.raises(DBAPIError, match="row-level security"):
        await in_space(
            f"mod_{SHARED}",
            ANA,
            (),
            f"update {SHARED}.{SHARED}_expense set space_id = :s where concept = 'Ana dinner'",
            s=OTHER,
        )


async def test_a_policy_with_an_old_rule_is_rewritten_on_the_next_boot(a_shared_space) -> None:
    name = f"{SHARED}.{SHARED}_expense"
    async with engine().begin() as connection:
        await connection.execute(text(f'set local role "mod_{SHARED}"'))
        await connection.execute(
            text(f"alter policy arga_owner on {name} using ({IN_SPACE}) with check ({IN_SPACE})")
        )
        await connection.execute(text(f"comment on policy arga_owner on {name} is null"))
    before = await in_space(f"mod_{SHARED}", ANA, (), f"select concept from {name}")

    async with engine().begin() as connection:
        rewritten = await enforce(connection, SHARED)
    async with engine().begin() as connection:
        again = await enforce(connection, SHARED)
    after = await in_space(f"mod_{SHARED}", ANA, (), f"select concept from {name}")

    assert concepts(before) == ["Ana dinner"]
    assert rewritten == [name]
    assert again == []
    assert concepts(after) == ["Ana dinner", "home groceries"]


async def test_writing_into_a_space_you_are_not_in_is_refused_by_postgres(a_shared_space) -> None:
    with pytest.raises(DBAPIError, match="row-level security"):
        await in_space(
            f"mod_{SHARED}",
            EVA,
            (OTHER,),
            f"insert into {SHARED}.{SHARED}_expense (concept, space_id) values ('intruso', :s)",
            s=HOME,
        )


async def test_a_member_can_change_what_is_the_spaces_but_not_what_is_the_others(
    a_shared_space,
) -> None:
    shared = await in_space(
        f"mod_{SHARED}",
        ANA,
        (HOME,),
        f"update {SHARED}.{SHARED}_expense set concept = 'home electricity, revisada' "
        "where concept = 'home electricity'",
    )
    private = await in_space(
        f"mod_{SHARED}",
        ANA,
        (HOME,),
        f"delete from {SHARED}.{SHARED}_expense where concept = 'Luis book'",
    )
    outside = await in_space(
        f"mod_{SHARED}",
        ANA,
        (HOME,),
        f"delete from {SHARED}.{SHARED}_expense where concept = 'Eva rent'",
    )

    assert (shared, private, outside) == (1, 0, 0)


@pytest.fixture
async def a_shared_catalog(a_shared_space):
    name = f"{SHARED}.{SHARED}_alimento"
    async with engine().begin() as connection:
        await connection.execute(text(f'set local role "mod_{SHARED}"'))
        await connection.execute(
            text(f"""
                create table {name} (
                    food     text not null,
                    user_id  uuid default {CURRENT_USER_SQL},
                    space_id uuid
                )
            """)
        )
        await connection.execute(text(f"comment on table {name} is 'arga:catalog'"))
        await connection.execute(text(f"insert into {name} (food, user_id) values ('sal', null)"))
        await connection.execute(text("reset role"))
        await grant_to_reader(connection, SHARED)
        await connection.execute(text("reset role"))
        touched = await enforce(connection, SHARED)
    assert touched == [name]
    for person, spaces, food, space in [
        (ANA, (HOME,), "sofrito de Ana", None),
        (ANA, (HOME,), "caldo de casa", HOME),
        (EVA, (OTHER,), "masa de Eva", OTHER),
    ]:
        await in_space(
            f"mod_{SHARED}",
            person,
            spaces,
            f"insert into {name} (food, space_id) values (:f, :s)",
            f=food,
            s=space,
        )
    return name


def foods(rows) -> list[str]:
    return sorted(row.food for row in rows)


@pytest.mark.parametrize("role", [f"mod_{SHARED}", f"mod_{SHARED}_read"])
async def test_a_catalog_with_a_space_is_seen_by_all_its_members(a_shared_catalog, role) -> None:
    luis = await in_space(role, LUIS, (HOME,), f"select food from {a_shared_catalog}")
    eva = await in_space(role, EVA, (OTHER,), f"select food from {a_shared_catalog}")
    ana_gone = await in_space(role, ANA, (), f"select food from {a_shared_catalog}")

    assert foods(luis) == ["caldo de casa", "sal"]
    assert foods(eva) == ["masa de Eva", "sal"]
    assert foods(ana_gone) == ["caldo de casa", "sal", "sofrito de Ana"]


async def test_a_member_edits_the_spaces_food_but_not_everyones_nor_anothers(
    a_shared_catalog,
) -> None:
    def update(food: str) -> str:
        return f"update {a_shared_catalog} set food = food || '!' where food = '{food}'"

    shared = await in_space(f"mod_{SHARED}", LUIS, (HOME,), update("caldo de casa"))
    private = await in_space(f"mod_{SHARED}", LUIS, (HOME,), update("sofrito de Ana"))
    with pytest.raises(DBAPIError, match="row-level security"):
        await in_space(f"mod_{SHARED}", LUIS, (HOME,), update("sal"))
    with pytest.raises(DBAPIError, match="row-level security"):
        await in_space(
            f"mod_{SHARED}",
            ANA,
            (HOME,),
            f"insert into {a_shared_catalog} (food, space_id) values ('intruso', :s)",
            s=OTHER,
        )

    assert (shared, private) == (1, 0)
