from __future__ import annotations

import asyncio
import io

import pytest
from httpx import ASGITransport, AsyncClient
from PIL import Image
from sqlalchemy import text

from arga_tenancy import SPACES_HEADER, USER_HEADER
from outings import spaces
from outings.main import app

SUBJECTS = {
    "ana": "4e5f6071-8293-44a5-b6c7-d8e9f0a1b2c3",
    "luis": "5f607182-93a4-45b6-87d8-e9f0a1b2c3d4",
    "eva": "60718293-a4b5-46c7-98e9-f0a1b2c3d4e5",
}


@pytest.fixture
async def people(schema, database_url, monkeypatch):
    from kernel import db as kernel_db
    from kernel import migrate
    from kernel.main import app as kernel_app

    kernel_db.engine.cache_clear()
    await asyncio.to_thread(migrate.upgrade)
    monkeypatch.setattr(spaces, "transport", lambda: ASGITransport(app=kernel_app))
    async with AsyncClient(transport=ASGITransport(app=kernel_app), base_url="http://k") as kernel:
        ids = {}
        for name, subject in SUBJECTS.items():
            found = await kernel.post("/internal/users", json={"subject": subject})
            ids[name] = found.json()["id"]
        ana = {USER_HEADER: ids["ana"]}
        casa = (await kernel.post("/internal/spaces", json={"name": "Casa"}, headers=ana)).json()
        code = (await kernel.post(f"/internal/spaces/{casa['id']}/invites", headers=ana)).json()
        await kernel.post(
            "/internal/spaces/join",
            json={"code": code["code"]},
            headers={USER_HEADER: ids["luis"]},
        )
    yield {**ids, "casa": casa["id"]}
    async with schema.begin() as connection:
        await connection.execute(
            text("delete from kernel.spaces where id = :id"), {"id": casa["id"]}
        )
        await connection.execute(
            text("delete from kernel.users where subject = any(:s)"),
            {"s": list(SUBJECTS.values())},
        )
    await kernel_db.engine().dispose()
    kernel_db.engine.cache_clear()


@pytest.fixture
async def call(people):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://d") as client:

        async def send(name: str, method: str, path: str, headers=None, **kw):
            spaces_of = {"ana": [people["casa"]], "luis": [people["casa"]], "eva": []}[name]
            sent = {
                USER_HEADER: people[name],
                SPACES_HEADER: ",".join(spaces_of),
                **(headers or {}),
            }
            return await client.request(method, path, headers=sent, **kw)

        yield send


def a_photo() -> bytes:
    out = io.BytesIO()
    Image.new("RGB", (40, 30), (200, 120, 40)).save(out, "JPEG")
    return out.getvalue()


async def irati(call) -> str:
    created = await call("ana", "POST", "/wishes", json={"kind": "getaway", "name": "Irati"})
    assert created.status_code == 201, created.text
    return created.json()["id"]


async def test_a_shared_wish_is_seen_and_done_by_the_space_with_its_photo(call, people) -> None:
    wish = await irati(call)
    before = await call("luis", "GET", f"/wishes/{wish}")

    shared = await call("ana", "PUT", f"/wishes/{wish}/space", json={"space_id": people["casa"]})
    photo = await call(
        "luis",
        "PUT",
        f"/wishes/{wish}/photo",
        content=a_photo(),
        headers={"content-type": "image/jpeg"},
    )
    done = await call("luis", "POST", f"/wishes/{wish}/done")
    ana = (await call("ana", "GET", f"/wishes/{wish}")).json()
    seen = await call("ana", "GET", f"/wishes/{wish}/photo")
    eva = await call("eva", "GET", f"/wishes/{wish}")

    assert before.status_code == 404
    assert shared.status_code == 200, shared.text
    assert (shared.json()["space_id"], shared.json()["mine"]) == (people["casa"], True)
    assert photo.status_code == 200, photo.text
    assert done.status_code == 200 and done.json()["mine"] is False
    assert (ana["done_at"] is not None, ana["has_photo"]) == (True, True)
    assert seen.status_code == 200
    assert eva.status_code == 404


async def test_only_whoever_wrote_it_shares_unshares_or_deletes_it(call, people) -> None:
    wish = await irati(call)
    await call("ana", "PUT", f"/wishes/{wish}/space", json={"space_id": people["casa"]})

    unshare = await call("luis", "PUT", f"/wishes/{wish}/space", json={"space_id": None})
    delete = await call("luis", "DELETE", f"/wishes/{wish}")
    outsider = await call("eva", "PUT", f"/wishes/{wish}/space", json={"space_id": people["casa"]})

    assert (unshare.status_code, delete.status_code) == (409, 409)
    assert outsider.status_code == 404
    assert (await call("luis", "GET", f"/wishes/{wish}")).status_code == 200


async def test_unsharing_keeps_the_photo_someone_else_put(call, people) -> None:
    wish = await irati(call)
    await call("ana", "PUT", f"/wishes/{wish}/space", json={"space_id": people["casa"]})
    await call(
        "luis",
        "PUT",
        f"/wishes/{wish}/photo",
        content=a_photo(),
        headers={"content-type": "image/jpeg"},
    )

    back = await call("ana", "PUT", f"/wishes/{wish}/space", json={"space_id": None})
    luis = await call("luis", "GET", f"/wishes/{wish}")
    photo = await call("ana", "GET", f"/wishes/{wish}/photo")

    assert back.status_code == 200, back.text
    assert (back.json()["space_id"], back.json()["has_photo"]) == (None, True)
    assert luis.status_code == 404
    assert photo.status_code == 200


async def test_claude_shares_a_wish_by_the_spaces_name(call, people) -> None:
    wish = await irati(call)

    async def tool(name: str, arguments: dict):
        return await call(
            name,
            "POST",
            "/tools/share_wish",
            json=arguments,
            headers={"x-arga-scopes": "outings:write"},
        )

    unknown = await tool("ana", {"wish_id": wish, "space": "Oficina"})
    shared = await tool("ana", {"wish_id": wish, "space": "casa"})
    by_luis = await tool("luis", {"wish_id": wish, "space": None})

    assert unknown.status_code == 409 and "«Casa»" in unknown.json()["detail"]["message"]
    assert shared.status_code == 200, shared.text
    assert (shared.json()["content"]["shared"], shared.json()["content"]["mine"]) == (True, True)
    assert by_luis.status_code == 409 and by_luis.json()["detail"]["code"] == "NOT_OWNER"
