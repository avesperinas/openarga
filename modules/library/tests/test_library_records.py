from __future__ import annotations

import asyncio
import secrets
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text

import arga_contracts as contracts
from arga_contracts import records as write
from library import records
from library.db import engine

MODULES = Path(__file__).resolve().parents[2]


async def add(api, title: str, reading: dict, **edition) -> dict:
    response = await api.post(
        "/books",
        json={
            "edition": {"title": title, "authors": ["Synthetic Author"], **edition},
            "reading": {"genre": "novel", **reading},
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


async def built() -> list[dict]:
    async with engine().begin() as connection:
        await connection.execute(text('set local role "mod_library"'))
        return await records.build(connection)


async def test_each_book_is_a_record_and_its_days_go_to_the_diary(api) -> None:
    read = await add(
        api,
        "A synthetic book",
        {
            "status": "read",
            "started_on": "2026-08-01",
            "finished_on": "2026-08-20",
            "rating": 4.5,
            "note": "I liked the ending.",
        },
        pages=320,
        year=2001,
    )
    other = await add(api, "Another synthetic", {"status": "reading", "started_on": "2026-08-20"})
    await add(api, "Pending", {"status": "want"})

    found = {one["id"]: one for one in await built()}

    record = found[f"book:{read['id']}"]
    assert record == contracts.record(**record)
    assert record["folder"] == "Books" and record["kind"] == "Book"
    assert record["href"] == f"/library/books/{read['id']}"
    assert record["properties"] == {
        "authors": ["Synthetic Author"],
        "status": "read",
        "genre": "novel",
        "format": "paper",
        "rating": 4.5,
        "started": "2026-08-01",
        "finished": "2026-08-20",
        "days": 20,
        "pages": 320,
        "year": 2001,
    }
    assert record["body"].startswith("**Synthetic Author** · 2001 · 320 pages · Paper · Novel")
    assert "Read from 2026-08-01 to 2026-08-20, in 20 days. ★★★★½ (4,5)" in (record["body"])
    assert "## Note\n\nI liked the ending." in record["body"]

    day = found["day:2026-08-20"]
    assert day["day"] == "2026-08-20"
    assert day["body"] == (
        f"- You finished [[library:book:{read['id']}|A synthetic book]] · ★★★★½ (4,5)\n"
        f"- You started [[library:book:{other['id']}|Another synthetic]]"
    )
    assert "day:2026-08-01" in found
    pending = next(one for one in found.values() if one["title"] == "Pending")
    assert pending["properties"]["status"] == "want to read"


async def test_what_changed_is_queued_once(api) -> None:
    await add(api, "One", {"status": "want"})
    async with engine().begin() as connection:
        await connection.execute(text('set local role "mod_library"'))
        first = await write.publish(connection, "library", await records.build(connection))
        again = await write.publish(connection, "library", await records.build(connection))
    assert first == {"added": 1, "changed": 0, "removed": 0}
    assert again == {"added": 0, "changed": 0, "removed": 0}


@pytest.fixture
async def notebook(schema, database_url, monkeypatch):
    from arga_testing import fresh_modules
    from kernel import db as kernel_db
    from kernel import migrate
    from kernel.main import app as kernel_app
    from notebook import db as notebook_db
    from notebook import mirror
    from notebook.main import app as notebook_app

    kernel_db.engine.cache_clear()
    await asyncio.to_thread(migrate.upgrade)
    monkeypatch.setenv("MODULE_REGISTRATION_TOKEN", secrets.token_hex(16))
    async with schema.begin() as connection:
        await connection.execute(text("delete from kernel.events where module = 'library'"))
        await fresh_modules(connection, "library", "notebook", fresh=["notebook"])
    monkeypatch.setattr(mirror, "kernel_transport", lambda: ASGITransport(app=kernel_app))
    notebook_db.engine.cache_clear()
    to_kernel = AsyncClient(transport=ASGITransport(app=kernel_app), base_url="http://kernel")
    async with AsyncClient(
        transport=ASGITransport(app=notebook_app), base_url="http://notebook"
    ) as api:
        yield to_kernel, api
    await to_kernel.aclose()
    for cached in (kernel_db.engine, notebook_db.engine):
        await cached().dispose()
        cached.cache_clear()
    async with schema.begin() as connection:
        await connection.execute(text("delete from kernel.events where module = 'library'"))
        await connection.execute(text("delete from kernel.modules where id = 'notebook'"))


async def test_library_the_kernel_and_notebook_put_a_book_in_the_notes(
    api, notebook, person
) -> None:
    from library import publisher
    from notebook import mirror
    from notebook.db import engine as notebook_engine

    to_kernel, notes = notebook
    read = await add(
        api,
        "A synthetic book",
        {"status": "read", "started_on": "2026-08-01", "finished_on": "2026-08-20"},
    )

    async def worker() -> None:
        await write.refresh(to_kernel, engine, "library", records.build, write.Every(0), person)
        async with engine().begin() as connection:
            await connection.execute(text('set local role "mod_library"'))
            await publisher.publish_pending(connection, to_kernel)
        async with notebook_engine().begin() as connection:
            await connection.execute(text('set local role "mod_notebook"'))
            await mirror.derive(connection)

    await worker()

    found = (
        await notes.get("/notes/resolve", params={"target": "Books/Books/A synthetic book"})
    ).json()["note"]
    assert found is not None
    note = (await notes.get(f"/notes/{found['id']}")).json()
    assert note["properties"]["arga"] == f"library:book:{read['id']}"
    assert note["arga"]["apps"][0]["name"] == "Books"
    diary = (await notes.get("/notes/resolve", params={"target": "2026-08-20"})).json()["note"]
    assert diary is not None and diary["folder"] == "Diario"

    rated = await api.put(
        f"/books/{read['id']}",
        json={
            "status": "read",
            "started_on": "2026-08-01",
            "finished_on": "2026-08-20",
            "rating": 3,
            "genre": "novel",
        },
    )
    assert rated.status_code == 200, rated.text
    await worker()
    again = (await notes.get(f"/notes/{found['id']}")).json()
    assert again["properties"]["rating"] == 3

    async with engine().begin() as connection:
        await connection.execute(text('set local role "mod_library"'))
        await connection.execute(
            text("delete from library.library_reading where id = :id"), {"id": read["id"]}
        )
    await worker()
    trash = [one["title"] for one in (await notes.get("/trash")).json()]
    assert "A synthetic book" in trash
