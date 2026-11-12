import os
from uuid import UUID

import pytest

from arga_tenancy import current_user

TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL", "postgresql+asyncpg://openarga:changeme@localhost:5433/openarga"
)


@pytest.fixture
def database_url(monkeypatch: pytest.MonkeyPatch) -> str:
    monkeypatch.setenv("DATABASE_URL", TEST_DATABASE_URL)
    from kernel import db, migrate

    db.engine.cache_clear()
    db.session_factory.cache_clear()
    migrate.upgrade()
    yield TEST_DATABASE_URL
    db.engine.cache_clear()
    db.session_factory.cache_clear()


PERSON = UUID("00000000-0000-4000-8000-00000000a7e5")


@pytest.fixture(autouse=True)
def person(request: pytest.FixtureRequest):
    if "database_url" not in request.fixturenames:
        yield None
        return
    token = current_user.set(PERSON)
    yield PERSON
    current_user.reset(token)
