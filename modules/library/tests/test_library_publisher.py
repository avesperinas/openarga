from __future__ import annotations

import asyncio
from uuid import UUID

import httpx
import pytest
from httpx import ASGITransport
from sqlalchemy import text
from test_library_library import add

from arga_module import publisher as kit
from arga_tenancy import current_user
from library import publisher


@pytest.fixture
async def kernel(schema):
    from kernel import db as kernel_db
    from kernel import migrate
    from kernel.main import app as kernel_app

    await asyncio.to_thread(migrate.upgrade)
    kernel_db.engine.cache_clear()
    person = current_user.get()
    subject = f"library-publisher-{person}"
    async with schema.begin() as connection:
        await connection.execute(text("delete from kernel.events where module = 'library'"))
        await connection.execute(
            text("insert into kernel.users (id, subject) values (:id, :s) on conflict do nothing"),
            {"id": person, "s": subject},
        )
    async with httpx.AsyncClient(transport=ASGITransport(app=kernel_app)) as client:
        yield client
    async with schema.begin() as connection:
        await connection.execute(text("delete from kernel.events where module = 'library'"))
        await connection.execute(
            text("delete from kernel.users where subject = :s"), {"s": subject}
        )
    await kernel_db.engine().dispose()
    kernel_db.engine.cache_clear()


async def queue(count: int) -> None:
    async with publisher.PUBLISHER.as_module() as connection:
        for index in range(count):
            await connection.execute(
                text(
                    "insert into library.library_outbox (type, payload, dedup_hash) "
                    "values ('library.probe', '{}', :dedup)"
                ),
                {"dedup": f"probe:{index}"},
            )


async def unpublished(schema) -> int:
    async with schema.connect() as connection:
        return await connection.scalar(
            text(
                "select count(*) from library.library_outbox "
                "where published_at is null and type = 'library.probe'"
            )
        )


async def test_a_backlog_goes_out_in_one_pass(schema, kernel, monkeypatch) -> None:
    monkeypatch.setattr(publisher.PUBLISHER, "refresh", None)
    await queue(120)

    result = await publisher.run_once(kernel)

    assert result["published"] == 120 and result["pending"] == 0
    assert await unpublished(schema) == 0


async def test_a_queue_longer_than_a_pass_says_there_is_more(schema, kernel, monkeypatch) -> None:
    monkeypatch.setattr(publisher.PUBLISHER, "refresh", None)
    monkeypatch.setattr(kit, "BATCH", 5)
    monkeypatch.setattr(kit, "BATCHES", 2)
    await queue(12)

    first = await publisher.run_once(kernel)
    second = await publisher.run_once(kernel)

    assert (first["published"], first["more"]) == (10, 1)
    assert (second["published"], second["more"]) == (2, 0)


async def test_what_another_process_is_publishing_for_the_person_is_left_to_it(
    schema, kernel, monkeypatch
) -> None:
    monkeypatch.setattr(publisher.PUBLISHER, "refresh", None)
    await queue(3)
    person = current_user.get()

    async with schema.connect() as other:
        transaction = await other.begin()
        await other.execute(
            text("select pg_advisory_xact_lock(hashtext('library_outbox'), hashtext(:user))"),
            {"user": str(person)},
        )
        while_busy = await publisher.run_once(kernel)
        await transaction.rollback()
    after = await publisher.run_once(kernel)

    assert while_busy["published"] == 0
    assert after["published"] == 3


async def test_writing_in_the_app_rebuilds_the_fichas_at_once(
    api, schema, kernel, monkeypatch
) -> None:
    asked: list[tuple[UUID, bool]] = []

    async def refresh(client, user, fresh) -> None:
        asked.append((user, fresh))

    monkeypatch.setattr(publisher.PUBLISHER, "refresh", refresh)
    person = current_user.get()
    publisher.PUBLISHER._touched.clear()
    await publisher.run_once(kernel)

    await add(api, "Rayuela", status="want", pages=600)
    await publisher.run_once(kernel)
    await publisher.run_once(kernel)

    assert asked == [(person, False), (person, True), (person, False)]


async def test_reading_through_a_tool_does_not_count_as_writing(api, schema, monkeypatch) -> None:
    publisher.PUBLISHER._touched.clear()

    read = await api.post(
        "/tools/get_reading_stats", json={}, headers={"x-arga-scopes": "library:read"}
    )

    assert read.status_code == 200
    assert publisher.PUBLISHER._touched == set()
