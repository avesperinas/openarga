from __future__ import annotations

import asyncio
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest
import yaml
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text

AT_ONCE_SECONDS = 3.0


def contract(service: Any, manifest_path: Path) -> dict[str, Callable]:
    module_id = service.module_id
    app = service.app

    def client() -> AsyncClient:
        return AsyncClient(transport=ASGITransport(app=app), base_url=f"http://{module_id}")

    async def test_it_says_it_is_alive_without_touching_the_database() -> None:
        async with client() as bare:
            response = await bare.get("/healthz")

        assert response.status_code == 200
        assert response.json() == {"status": "ok", "module": module_id}

    async def test_it_says_its_version() -> None:
        async with client() as bare:
            response = await bare.get("/version")

        assert response.json() == {"service": module_id, "version": app.version}

    def test_what_the_manifest_declares_is_what_the_module_serves() -> None:
        manifest = yaml.safe_load(manifest_path.read_text())

        assert manifest["id"] == module_id
        assert {tool["name"] for tool in manifest.get("tools") or []} == set(service.tools)
        declared = (manifest.get("ui") or {}).get("widgets") or []
        assert {widget["id"] for widget in declared} == set(service.widgets)

    def test_the_scopes_decide_the_postgres_role() -> None:
        role_for = service.role_for_scopes

        assert role_for({f"{module_id}:write"}) == f"mod_{module_id}"
        assert role_for({f"{module_id}:read"}) == f"mod_{module_id}_read"
        assert role_for({f"{module_id}:read", f"{module_id}:write"}) == f"mod_{module_id}"
        assert role_for({"otra:read", "otra:write"}) is None

    async def test_a_tool_that_does_not_exist_is_a_404() -> None:
        async with client() as bare:
            response = await bare.post(
                "/tools/vaciar_todo", json={}, headers={"x-arga-scopes": f"{module_id}:write"}
            )

        assert response.status_code == 404

    async def test_a_tool_without_a_scope_of_the_module_is_a_403() -> None:
        if not service.tools:
            pytest.skip("este módulo no tiene tools")
        name = next(iter(service.tools))
        async with client() as bare:
            response = await bare.post(
                f"/tools/{name}", json={}, headers={"x-arga-scopes": "otra:write"}
            )

        assert response.status_code == 403

    async def test_a_widget_that_does_not_exist_is_a_404() -> None:
        async with client() as bare:
            response = await bare.get("/widgets/no_existe")

        assert response.status_code == 404

    async def test_every_screen_of_the_app_is_its_index(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        if not service.ui:
            pytest.skip("este módulo no tiene app")
        (tmp_path / "index.html").write_text("<div id=root></div>")
        (tmp_path / "assets").mkdir()
        (tmp_path / "assets" / "index-abc123.js").write_text("export {}")
        (tmp_path.parent / "secreto.txt").write_text("no")
        monkeypatch.setenv("UI_DIST", str(tmp_path))
        root = service.ui_root

        async with client() as bare:
            screen = await bare.get(f"{root}/una/pantalla")
            asset = await bare.get(f"{root}/assets/index-abc123.js")
            outside = await bare.get(f"{root}/%2E%2E/secreto.txt")
            gone = await bare.get(f"{root}/assets/index-viejo.js")

        assert screen.text == "<div id=root></div>"
        assert screen.headers["cache-control"] == "no-cache"
        assert "immutable" in asset.headers["cache-control"]
        assert outside.text != "no"
        assert gone.status_code == 404

    async def test_what_is_queued_reaches_the_kernel_at_once(
        schema, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        if service.publisher is None:
            pytest.skip("este módulo no publica")
        import httpx

        from arga_module import publisher as kit
        from arga_tenancy import current_user
        from kernel import db as kernel_db
        from kernel import migrate
        from kernel.main import app as kernel_app

        await asyncio.to_thread(migrate.upgrade)
        kernel_db.engine.cache_clear()
        monkeypatch.setattr(kit, "TICK_SECONDS", 3600.0)
        monkeypatch.setattr(service.publisher, "refresh", None)
        person = current_user.get()
        subject = f"{module_id}-tests-{person}"
        dedup = f"probe:{uuid4()}"
        async with schema.begin() as connection:
            await connection.execute(
                text(
                    "insert into kernel.users (id, subject) values (:id, :s) on conflict do nothing"
                ),
                {"id": person, "s": subject},
            )
        async with httpx.AsyncClient(transport=ASGITransport(app=kernel_app)) as to_kernel:
            running = asyncio.create_task(service.publisher.loop(to_kernel))
            try:
                await asyncio.sleep(1.0)
                async with service.publisher.as_module() as connection:
                    await connection.execute(
                        text(
                            f"insert into {module_id}.{module_id}_outbox "
                            "(type, payload, dedup_hash) values (:type, '{}', :dedup)"
                        ),
                        {"type": f"{module_id}.probe", "dedup": dedup},
                    )
                started = time.monotonic()
                arrived = None
                while time.monotonic() - started < AT_ONCE_SECONDS:
                    async with schema.connect() as connection:
                        arrived = await connection.scalar(
                            text("select user_id from kernel.events where dedup_hash = :dedup"),
                            {"dedup": dedup},
                        )
                    if arrived is not None:
                        break
                    await asyncio.sleep(0.1)
            finally:
                running.cancel()
                with pytest.raises(asyncio.CancelledError):
                    await running
                async with schema.begin() as connection:
                    await connection.execute(
                        text("delete from kernel.events where dedup_hash = :dedup"),
                        {"dedup": dedup},
                    )
                    await connection.execute(
                        text("delete from kernel.users where subject = :s"), {"s": subject}
                    )
                await kernel_db.engine().dispose()
                kernel_db.engine.cache_clear()

        assert arrived == person

    found = dict(locals())
    return {name: value for name, value in found.items() if name.startswith("test_")}
