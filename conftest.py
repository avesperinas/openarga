import os

import pytest

_worker = os.environ.get("PYTEST_XDIST_WORKER")
_urls = os.environ.get("TEST_DATABASE_URLS", "").split()
if _worker and _urls:
    os.environ["TEST_DATABASE_URL"] = _urls[int(_worker.removeprefix("gw")) % len(_urls)]

# Modules' tests were written for an instance in Madrid; each sets its own zone when it cares.
os.environ.setdefault("OPENARGA_TIMEZONE", "Europe/Madrid")

_WITH_DATABASE = ("kernel", "modules", "mcp", "tests", "packages/contracts", "packages/testing")


@pytest.fixture(scope="session", autouse=True)
def _kernel_migrated(request: pytest.FixtureRequest) -> None:
    root = request.config.rootpath
    paths = {item.path.relative_to(root).as_posix() for item in request.session.items}
    if not any(path.startswith(_WITH_DATABASE) for path in paths):
        return
    from kernel import db, migrate

    url = os.environ.get(
        "TEST_DATABASE_URL", "postgresql+asyncpg://openarga:changeme@localhost:5433/openarga"
    )
    previous = os.environ.get("DATABASE_URL")
    os.environ["DATABASE_URL"] = url
    db.engine.cache_clear()
    migrate.upgrade()
    db.engine.cache_clear()
    if previous is None:
        del os.environ["DATABASE_URL"]
    else:
        os.environ["DATABASE_URL"] = previous
