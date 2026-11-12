from __future__ import annotations

import asyncio
from pathlib import Path

import httpx
import yaml
from httpx import ASGITransport
from sqlalchemy import text
from test_library_library import add, read_book, reading_of

from arga_contracts.records import Never
from arga_testing.contract import contract
from library import publisher
from library.main import MODULE_ID, service

MANIFEST = Path(__file__).resolve().parents[1] / "manifest.yaml"

globals().update(contract(service, MANIFEST))


def test_the_manifest_says_what_this_module_is() -> None:
    manifest = yaml.safe_load(MANIFEST.read_text())

    assert manifest["id"] == MODULE_ID
    assert manifest["database"] == {"schema": MODULE_ID, "role": f"mod_{MODULE_ID}", "reads": []}
    assert manifest["api"]["prefix"] == f"/api/{MODULE_ID}"
    assert manifest["ui"]["view"] == f"/{MODULE_ID}"
    assert manifest["connectors"] == []


async def test_the_genres_are_the_fixed_list(bare) -> None:
    genres = (await bare.get("/genres")).json()

    assert len(genres) == 11
    assert genres[0] == {"id": "novel", "name": "Novela"}
    assert genres[-1] == {"id": "other", "name": "Otros"}


async def test_a_finished_book_reaches_the_log_once_with_its_owner(
    api, schema, monkeypatch
) -> None:
    monkeypatch.setattr(publisher, "RECORDS", Never())
    monkeypatch.setattr(publisher, "METRICS", Never())
    from arga_tenancy import current_user
    from kernel import db as kernel_db
    from kernel import migrate
    from kernel.main import app as kernel_app

    await asyncio.to_thread(migrate.upgrade)
    kernel_db.engine.cache_clear()
    person = current_user.get()
    subject = f"library-tests-{person}"
    async with schema.begin() as connection:
        await connection.execute(text("delete from kernel.events where module = 'library'"))
        await connection.execute(
            text("insert into kernel.users (id, subject) values (:id, :s) on conflict do nothing"),
            {"id": person, "s": subject},
        )
    try:
        await publish_and_check(api, schema, person, kernel_app)
    finally:
        async with schema.begin() as connection:
            await connection.execute(text("delete from kernel.events where module = 'library'"))
            await connection.execute(
                text("delete from kernel.users where subject = :s"), {"s": subject}
            )
        await kernel_db.engine().dispose()
        kernel_db.engine.cache_clear()


async def publish_and_check(api, schema, person, kernel_app) -> None:
    added = await add(api, "Cien años de soledad", status="read", pages=471)
    await api.put(f"/books/{added['id']}", json=reading_of(await read_book(api, added["id"])))

    def down(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/internal/users":
            return httpx.Response(200, json=[{"id": str(person)}])
        raise httpx.ConnectError("el kernel no contesta", request=request)

    async with httpx.AsyncClient(transport=httpx.MockTransport(down)) as client:
        failed = await publisher.run_once(client)
    async with httpx.AsyncClient(transport=ASGITransport(app=kernel_app)) as client:
        ok = await publisher.run_once(client)
        again = await publisher.run_once(client)

    assert failed["published"] == 0 and failed["pending"] == 1
    assert ok["published"] == 1 and again == {"published": 0, "pending": 0, "more": 0}
    async with schema.connect() as connection:
        events = (
            await connection.execute(
                text("select type, user_id, payload from kernel.events where module = 'library'")
            )
        ).all()
    assert [(row.type, row.user_id) for row in events] == [("library.reading_finished", person)]
    assert events[0].payload["pages"] == 471
