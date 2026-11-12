import pytest
from alembic.script import ScriptDirectory
from fastapi.testclient import TestClient

from kernel.main import app
from kernel.migrate import alembic_config


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def test_healthz_ignores_the_database(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://nobody@127.0.0.1:1/nothing")
    from kernel import db

    db.engine.cache_clear()
    with TestClient(app) as client:
        response = client.get("/healthz")
    db.engine.cache_clear()

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_readyz_is_503_when_the_database_is_unreachable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://nobody@127.0.0.1:1/nothing")
    from kernel import db

    db.engine.cache_clear()
    with TestClient(app) as client:
        response = client.get("/readyz")
    db.engine.cache_clear()

    assert response.status_code == 503
    assert response.json()["status"] == "not ready"


def test_readyz_reports_the_applied_revision(database_url: str) -> None:
    with TestClient(app) as client:
        response = client.get("/readyz")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ready"
    assert body["revision"] == ScriptDirectory.from_config(alembic_config()).get_current_head()
