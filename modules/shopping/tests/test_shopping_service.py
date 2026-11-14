from __future__ import annotations

import asyncio
from pathlib import Path

import httpx
import yaml
from httpx import ASGITransport
from sqlalchemy import text
from test_shopping_list import buy

from arga_contracts.records import Never
from arga_testing.contract import contract
from shopping import publisher
from shopping.main import MODULE_ID, service

MANIFEST = Path(__file__).resolve().parents[1] / "manifest.yaml"

globals().update(contract(service, MANIFEST))


def test_the_manifest_says_what_this_module_is() -> None:
    manifest = yaml.safe_load(MANIFEST.read_text())

    assert manifest["id"] == MODULE_ID
    assert manifest["database"] == {"schema": MODULE_ID, "role": f"mod_{MODULE_ID}", "reads": []}
    assert manifest["api"]["prefix"] == f"/api/{MODULE_ID}"
    assert manifest["ui"]["view"] == f"/{MODULE_ID}"
    assert manifest["connectors"] == []


async def test_the_sections_come_with_the_module_in_the_order_of_a_shop(api) -> None:
    categories = (await api.get("/categories")).json()

    assert len(categories) == 13
    assert [c["id"] for c in categories[:2]] == ["produce", "bakery"]
    assert categories[-1]["id"] == "other"
    assert all(c["emoji"] for c in categories)


async def test_without_a_scope_a_tool_call_never_opens_the_database(bare) -> None:
    response = await bare.post("/tools/get_shopping_list", json={}, headers={"x-arga-scopes": ""})

    assert response.status_code == 403


async def test_a_finished_purchase_reaches_the_log_with_its_owner(api, schema, monkeypatch) -> None:
    monkeypatch.setattr(publisher, "RECORDS", Never())
    from arga_tenancy import current_user
    from kernel import db as kernel_db
    from kernel import migrate
    from kernel.main import app as kernel_app

    await asyncio.to_thread(migrate.upgrade)
    kernel_db.engine.cache_clear()
    person = current_user.get()
    subject = f"shopping-tests-{person}"
    async with schema.begin() as connection:
        await connection.execute(text("delete from kernel.events where module = 'shopping'"))
        await connection.execute(
            text("insert into kernel.users (id, subject) values (:id, :s) on conflict do nothing"),
            {"id": person, "s": subject},
        )
    try:
        await publish_and_check(api, schema, person, kernel_app)
    finally:
        async with schema.begin() as connection:
            await connection.execute(text("delete from kernel.events where module = 'shopping'"))
            await connection.execute(
                text("delete from kernel.users where subject = :s"), {"s": subject}
            )
        await kernel_db.engine().dispose()
        kernel_db.engine.cache_clear()


async def publish_and_check(api, schema, person, kernel_app) -> None:
    await buy(api, schema, "Bread", "Milk")

    def down(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/internal/users":
            return httpx.Response(200, json=[{"id": str(person)}])
        raise httpx.ConnectError("the kernel does not answer", request=request)

    async with httpx.AsyncClient(transport=httpx.MockTransport(down)) as client:
        failed = await publisher.run_once(client)
    async with httpx.AsyncClient(transport=ASGITransport(app=kernel_app)) as client:
        ok = await publisher.run_once(client)
        again = await publisher.run_once(client)

    assert failed["published"] == 0 and failed["pending"] == 2
    assert ok["published"] == 2 and again == {"published": 0, "pending": 0, "more": 0}
    async with schema.connect() as connection:
        events = (
            await connection.execute(
                text(
                    "select type, user_id, payload from kernel.events "
                    "where module = 'shopping' order by type desc"
                )
            )
        ).all()
    assert [(row.type, row.user_id) for row in events] == [
        ("shopping.trip_finished", person),
        ("shopping.trip", person),
    ]
    assert events[0].payload["items"] == 2
