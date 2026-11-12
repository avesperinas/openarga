from uuid import UUID, uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text

from arga_tenancy import as_user
from kernel import resolver, seed
from kernel.db import engine
from kernel.entities import SURVIVING
from kernel.main import app


@pytest.fixture
async def api(database_url: str):
    await seed.clear()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://kernel") as client:
        yield client
    await seed.clear()
    await engine().dispose()


async def ids_of(spellings: list[str]) -> dict[str, str]:
    async with engine().connect() as connection:
        rows = await connection.execute(
            text(
                "select alias, cast(entity_id as text) as id from kernel.entity_aliases "
                "where alias = any(:names)"
            ),
            {"names": spellings},
        )
        return {row.alias: row.id for row in rows}


async def test_the_three_spellings_end_in_the_same_entity(api) -> None:
    await seed.load()
    async with engine().begin() as connection:
        await resolver.run(connection)
    ids = await ids_of(seed.SPELLINGS)

    answer = (await api.post("/entities/surviving", json={"ids": list(ids.values())})).json()

    assert len(answer) == 3
    assert len({item["surviving"] for item in answer}) == 1
    assert len({item["name"] for item in answer}) == 1


async def test_undoing_a_merge_shows_in_the_next_answer(api) -> None:
    await seed.load()
    async with engine().begin() as connection:
        outcome = await resolver.run(connection)
    absorbed = outcome.merged[0].candidate
    await api.post(f"/entities/{absorbed}/unmerge")

    answer = (await api.post("/entities/surviving", json={"ids": [absorbed]})).json()

    assert answer == [{"id": absorbed, "surviving": absorbed, "name": answer[0]["name"]}]


KERNEL_LIKE = "kernel_como_en_produccion"
PERSON = UUID("00000000-0000-4000-8000-00000000a7e5")


async def test_someone_elses_entity_does_not_come_back(api) -> None:
    await seed.load()
    ids = list((await ids_of(seed.SPELLINGS)).values())
    stranger = UUID("00000000-0000-4000-8000-00000000b0b0")
    async with engine().begin() as connection:
        await connection.execute(
            text(
                "do $$ begin if not exists "
                f"(select 1 from pg_roles where rolname = '{KERNEL_LIKE}') "
                f"then create role {KERNEL_LIKE} nologin; end if; end $$"
            )
        )
        await connection.execute(text(f"grant usage on schema kernel to {KERNEL_LIKE}"))
        await connection.execute(text(f"grant select on kernel.entities to {KERNEL_LIKE}"))

    async def asked_by(person: UUID | None) -> list:
        with as_user(person):
            async with engine().begin() as connection:
                await connection.execute(text(f'set local role "{KERNEL_LIKE}"'))
                return (await connection.execute(SURVIVING, {"ids": ids})).all()

    mine = await asked_by(PERSON)
    theirs = await asked_by(stranger)
    unknown = (await api.post("/entities/surviving", json={"ids": [str(uuid4())]})).json()

    assert len(mine) == 3
    assert theirs == []
    assert unknown == []
