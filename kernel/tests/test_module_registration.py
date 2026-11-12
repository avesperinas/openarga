from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient
from rendered_module import render
from sqlalchemy import text

from kernel import schemas
from kernel.db import engine
from kernel.main import app
from kernel.manifests import load_all
from kernel.modules import disable_stale
from kernel.provision import role_for

REPO = Path(__file__).resolve().parents[2]
MODULE = "probe"
ROLE = role_for(MODULE)
TOKEN = "un-secreto-de-prueba"


@pytest.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://kernel") as client:
        yield client


def body(root: Path, version: str = "v9.9.9", module: str = MODULE) -> dict:
    manifest = next(m for m in load_all(root) if m.id == module)
    return {
        "manifest": manifest.model_dump(by_alias=True, mode="json"),
        "schema": [
            {"name": file.name, "sql": file.sql} for file in schemas.from_disk(root, module)
        ],
        "version": version,
    }


@pytest.fixture
async def clean(database_url: str, monkeypatch: pytest.MonkeyPatch, tmp_path):
    monkeypatch.setenv("MODULE_REGISTRATION_TOKEN", TOKEN)
    render(tmp_path, MODULE)
    async with engine().begin() as connection:
        await connection.execute(text(f"drop schema if exists {MODULE} cascade"))
        await connection.execute(
            text("delete from kernel.module_migrations where module = :m"), {"m": MODULE}
        )
        await connection.execute(text("delete from kernel.modules where id = :m"), {"m": MODULE})
        await connection.execute(
            text(
                "do $$ begin "
                f"if exists (select 1 from pg_roles where rolname = '{ROLE}') "
                f"then execute 'drop owned by {ROLE}'; execute 'drop role {ROLE}'; "
                "end if; end $$"
            )
        )
    yield tmp_path
    async with engine().begin() as connection:
        await connection.execute(text("delete from kernel.modules where id = :m"), {"m": MODULE})


async def test_a_module_registers_itself_and_gets_its_schema(clean, client) -> None:
    response = await client.put(
        f"/internal/modules/{MODULE}", json=body(clean), headers={"x-module-token": TOKEN}
    )

    assert response.status_code == 200
    assert response.json()["version"] == "v9.9.9"
    assert "0001_init.sql" in response.json()["applied"]

    async with engine().connect() as connection:
        version, enabled = (
            await connection.execute(
                text("select version, enabled from kernel.modules where id = :m"), {"m": MODULE}
            )
        ).one()
        tables = (
            await connection.execute(
                text("select count(*) from pg_tables where schemaname = :s"), {"s": MODULE}
            )
        ).scalar()
    assert (version, enabled) == ("v9.9.9", True)
    assert tables > 0


async def test_registering_again_applies_nothing_and_updates_the_version(clean, client) -> None:
    await client.put(
        f"/internal/modules/{MODULE}", json=body(clean), headers={"x-module-token": TOKEN}
    )
    again = await client.put(
        f"/internal/modules/{MODULE}",
        json=body(clean, version="v9.9.10"),
        headers={"x-module-token": TOKEN},
    )

    assert again.status_code == 200
    assert again.json() == {"id": MODULE, "version": "v9.9.10", "applied": []}


async def test_without_the_secret_nothing_is_registered(clean, client) -> None:
    assert (await client.put(f"/internal/modules/{MODULE}", json=body(clean))).status_code == 401
    wrong = await client.put(
        f"/internal/modules/{MODULE}", json=body(clean), headers={"x-module-token": "otro"}
    )
    assert wrong.status_code == 401

    async with engine().connect() as connection:
        rows = await connection.scalar(
            text("select count(*) from kernel.modules where id = :m"), {"m": MODULE}
        )
    assert rows == 0


async def test_a_module_cannot_register_under_another_id(clean, client) -> None:
    response = await client.put(
        "/internal/modules/training", json=body(clean), headers={"x-module-token": TOKEN}
    )
    assert response.status_code == 422
    assert "training" in response.json()["detail"]


async def test_an_invalid_manifest_is_rejected(clean, client) -> None:
    broken = body(clean)
    broken["manifest"]["database"] = {"schema": "otro", "role": "mod_otro"}
    response = await client.put(
        f"/internal/modules/{MODULE}", json=broken, headers={"x-module-token": TOKEN}
    )
    assert response.status_code == 422


async def test_a_module_that_stops_registering_is_switched_off(clean, client) -> None:
    await client.put(
        f"/internal/modules/{MODULE}", json=body(clean), headers={"x-module-token": TOKEN}
    )
    async with engine().begin() as connection:
        await connection.execute(
            text(
                "update kernel.modules set registered_at = now() - interval '30 days' where id = :m"
            ),
            {"m": MODULE},
        )
        apagados = await disable_stale(connection, 7)
        enabled = await connection.scalar(
            text("select enabled from kernel.modules where id = :m"), {"m": MODULE}
        )

    assert apagados == [MODULE]
    assert enabled is False


async def test_a_service_another_app_already_serves_is_refused(clean, client) -> None:
    async with engine().begin() as connection:
        await connection.execute(
            text(
                "insert into kernel.modules (id, version, enabled, manifest) "
                "values ('probe_other', '0.1.0', true, '{\"provides\": [\"shopping.add\"]}') "
                "on conflict (id) do update set manifest = excluded.manifest, enabled = true"
            )
        )
    serving = body(clean)
    serving["manifest"]["provides"] = ["shopping.add"]
    try:
        response = await client.put(
            f"/internal/modules/{MODULE}", json=serving, headers={"x-module-token": TOKEN}
        )
    finally:
        async with engine().begin() as connection:
            await connection.execute(text("delete from kernel.modules where id = 'probe_other'"))

    assert response.status_code == 409
    assert "probe_other" in response.json()["detail"]


@pytest.mark.parametrize("taken", ["/probe_other", "/lugar"])
async def test_an_address_another_app_lives_at_is_refused(clean, client, taken: str) -> None:
    async with engine().begin() as connection:
        await connection.execute(
            text(
                "insert into kernel.modules (id, version, enabled, manifest) "
                "values ('probe_other', '0.1.0', true, '{\"ui\": {\"view\": \"/lugar\"}}') "
                "on conflict (id) do update set manifest = excluded.manifest, enabled = true"
            )
        )
    moved = body(clean)
    moved["manifest"]["ui"]["view"] = taken
    for widget in moved["manifest"]["ui"].get("widgets", []):
        widget.pop("link", None)
    try:
        response = await client.put(
            f"/internal/modules/{MODULE}", json=moved, headers={"x-module-token": TOKEN}
        )
    finally:
        async with engine().begin() as connection:
            await connection.execute(text("delete from kernel.modules where id = 'probe_other'"))

    assert response.status_code == 409
    assert "probe_other" in response.json()["detail"]


TOGETHER = [f"probe{letter}" for letter in "abcdef"]


async def _forget(module: str) -> None:
    role = role_for(module)
    async with engine().begin() as connection:
        await connection.execute(text(f"drop schema if exists {module} cascade"))
        await connection.execute(
            text("delete from kernel.module_migrations where module = :m"), {"m": module}
        )
        await connection.execute(text("delete from kernel.modules where id = :m"), {"m": module})
        await connection.execute(
            text(
                "do $$ begin "
                f"if exists (select 1 from pg_roles where rolname = '{role}') "
                f"then execute 'drop owned by {role}'; execute 'drop role {role}'; "
                "end if; end $$"
            )
        )


async def test_modules_that_register_at_the_same_time_all_get_in(
    database_url: str, monkeypatch: pytest.MonkeyPatch, tmp_path, client
) -> None:
    monkeypatch.setenv("MODULE_REGISTRATION_TOKEN", TOKEN)
    for module in TOGETHER:
        await _forget(module)
        render(tmp_path, module)
    try:
        answers = await asyncio.gather(
            *(
                client.put(
                    f"/internal/modules/{module}",
                    json=body(tmp_path, module=module),
                    headers={"x-module-token": TOKEN},
                )
                for module in TOGETHER
            )
        )
        assert [answer.status_code for answer in answers] == [200] * len(TOGETHER), [
            answer.text for answer in answers if answer.status_code != 200
        ]
    finally:
        for module in TOGETHER:
            await _forget(module)
