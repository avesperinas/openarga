import asyncio

import pytest
from sqlalchemy import text

from kernel import db, migrate

FUTURO = "0099_del_futuro"


async def _stamp(revision: str) -> None:
    engine = db.engine()
    try:
        async with engine.begin() as connection:
            await connection.execute(
                text("update alembic_version set version_num = :revision"),
                {"revision": revision},
            )
    finally:
        await engine.dispose()
        db.engine.cache_clear()


async def _current() -> str:
    engine = db.engine()
    try:
        async with engine.connect() as connection:
            return await connection.scalar(text("select version_num from alembic_version"))
    finally:
        await engine.dispose()
        db.engine.cache_clear()


def stamp(revision: str) -> None:
    asyncio.run(_stamp(revision))


def current() -> str:
    return asyncio.run(_current())


@pytest.fixture
def stamped(database_url: str):
    original = current()
    yield
    stamp(original)


def test_the_code_knows_its_own_revisions() -> None:
    known = migrate.known_revisions()

    assert "0001_core" in known
    assert FUTURO not in known


def test_a_database_ahead_starts_instead_of_dying(stamped, capsys) -> None:
    stamp(FUTURO)

    assert migrate.main() == 0
    assert "es un rollback" in capsys.readouterr().err


def test_it_does_not_touch_the_schema_when_it_is_ahead(stamped) -> None:
    stamp(FUTURO)

    migrate.main()

    assert current() == FUTURO


def test_the_normal_case_still_migrates(stamped) -> None:
    assert migrate.main() == 0
    assert current() in migrate.known_revisions()
