from __future__ import annotations

import asyncio
import secrets
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient
from outings_world import IRATI, make_wish
from sqlalchemy import text

import arga_contracts as contracts
from arga_contracts import records as write
from outings import records, wishes
from outings.db import engine

MODULES = Path(__file__).resolve().parents[2]


async def built() -> list[dict]:
    async with engine().begin() as connection:
        await connection.execute(text('set local role "mod_outings"'))
        return await records.build(connection)


async def test_each_wish_is_a_record_and_doing_it_goes_to_the_diary(api) -> None:
    irati = await make_wish(
        api,
        body="Go in November, with the beech wood red.",
        place=wishes.place_of(IRATI).model_dump(),
    )
    other = await make_wish(api, "Japan", kind="trip", place={"name": "Japan"})
    await api.post(f"/wishes/{other['id']}/done")

    found = {one["id"]: one for one in await built()}

    record = found[f"wish:{irati['id']}"]
    assert record == contracts.record(**record)
    assert record["folder"] == "Wishes" and record["kind"] == "Wish"
    assert record["href"] == f"/outings/wishes/{irati['id']}"
    assert record["properties"] == {
        "kind": "getaway",
        "status": "pending",
        "place": "Selva de Irati, Orbaizeta, Spain",
        "coordinates": "42.98000, -1.17000",
    }
    assert record["body"] == (
        "**Getaway** · Selva de Irati, Orbaizeta, Spain\n\nGo in November, with the beech wood red."
    )
    done = found[f"wish:{other['id']}"]
    assert done["properties"]["status"] == "done"
    day = next(one for one in found.values() if one.get("day"))
    assert day["body"] == f"- You did [[outings:wish:{other['id']}|Japan]]"


async def test_what_changed_is_queued_once(api) -> None:
    await make_wish(api, "Una")
    async with engine().begin() as connection:
        await connection.execute(text('set local role "mod_outings"'))
        first = await write.publish(connection, "outings", await records.build(connection))
        again = await write.publish(connection, "outings", await records.build(connection))
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
        await connection.execute(text("delete from kernel.events where module = 'outings'"))
        await fresh_modules(connection, "outings", "notebook", fresh=["notebook"])
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
        await connection.execute(text("delete from kernel.events where module = 'outings'"))
        await connection.execute(text("delete from kernel.modules where id = 'notebook'"))


async def test_outings_the_kernel_and_notebook_put_a_wish_in_the_notes(
    api, notebook, person
) -> None:
    from notebook import mirror
    from notebook.db import engine as notebook_engine
    from outings import publisher

    to_kernel, notes = notebook
    irati = await make_wish(api, body="Cube route.", place=wishes.place_of(IRATI).model_dump())

    async def worker() -> None:
        await write.refresh(to_kernel, engine, "outings", records.build, write.Every(0), person)
        async with engine().begin() as connection:
            await connection.execute(text('set local role "mod_outings"'))
            await publisher.publish_pending(connection, to_kernel)
        async with notebook_engine().begin() as connection:
            await connection.execute(text('set local role "mod_notebook"'))
            await mirror.derive(connection)

    await worker()

    found = (
        await notes.get("/notes/resolve", params={"target": "Outings/Wishes/Selva de Irati"})
    ).json()["note"]
    assert found is not None
    note = (await notes.get(f"/notes/{found['id']}")).json()
    assert note["properties"]["arga"] == f"outings:wish:{irati['id']}"
    assert note["properties"]["kind"] == "getaway"

    await api.post(f"/wishes/{irati['id']}/done")
    await worker()
    again = (await notes.get(f"/notes/{found['id']}")).json()
    assert again["properties"]["status"] == "done"

    await api.delete(f"/wishes/{irati['id']}")
    await worker()
    trash = [one["title"] for one in (await notes.get("/trash")).json()]
    assert "Selva de Irati" in trash
