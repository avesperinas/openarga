from __future__ import annotations

import asyncio

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text

from arga_tenancy import SPACES_HEADER, USER_HEADER
from recipes import spaces
from recipes.main import app

SUBJECTS = {
    "ana": "1b2c3d4e-5f60-4718-8293-a4b5c6d7e8f9",
    "luis": "2c3d4e5f-6071-4829-93a4-b5c6d7e8f901",
    "eva": "3d4e5f60-7182-493a-a4b5-c6d7e8f90112",
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
        home = (await kernel.post("/internal/spaces", json={"name": "Home"}, headers=ana)).json()
        code = (await kernel.post(f"/internal/spaces/{home['id']}/invites", headers=ana)).json()
        await kernel.post(
            "/internal/spaces/join",
            json={"code": code["code"]},
            headers={USER_HEADER: ids["luis"]},
        )
    yield {**ids, "home": home["id"]}
    async with schema.begin() as connection:
        await connection.execute(
            text("delete from kernel.spaces where id = :id"), {"id": home["id"]}
        )
        await connection.execute(
            text("delete from kernel.users where subject = any(:s)"),
            {"s": list(SUBJECTS.values())},
        )
    await kernel_db.engine().dispose()
    kernel_db.engine.cache_clear()


@pytest.fixture
async def call(people):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://a") as client:

        async def send(name: str, method: str, path: str, headers=None, **kw):
            spaces_of = {"ana": [people["home"]], "luis": [people["home"]], "eva": []}[name]
            sent = {
                USER_HEADER: people[name],
                SPACES_HEADER: ",".join(spaces_of),
                **(headers or {}),
            }
            return await client.request(method, path, headers=sent, **kw)

        yield send


async def food(call, name: str, macros: dict, **measures) -> str:
    response = await call(
        "ana",
        "POST",
        "/foods/manual",
        json={"name": name, "category_id": "vegetable", "macros": macros, **measures},
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


async def leek_soup(call) -> str:
    puerro = await food(call, "Leek", {"kcal": 61, "protein": 1.5, "fat": 0.3, "carbs": 14.15})
    patata = await food(call, "Potato", {"kcal": 77, "protein": 2, "fat": 0.1, "carbs": 17.5})
    created = await call(
        "ana",
        "POST",
        "/recipes",
        json={
            "name": "Leek soup",
            "servings": 4,
            "tags": ["winter"],
            "ingredients": [
                {"food_id": puerro, "quantity": 400, "unit": "g"},
                {"food_id": patata, "quantity": 600, "unit": "g"},
            ],
        },
    )
    assert created.status_code == 201, created.text
    return created.json()["id"]


async def test_a_shared_recipe_is_cooked_by_the_space_with_all_its_macros(call, people) -> None:
    recipe = await leek_soup(call)
    before = await call("luis", "GET", f"/recipes/{recipe}")

    shared = await call("ana", "PUT", f"/recipes/{recipe}/space", json={"space_id": people["home"]})
    luis = (await call("luis", "GET", f"/recipes/{recipe}")).json()
    eva = await call("eva", "GET", f"/recipes/{recipe}")
    listed = (await call("luis", "GET", "/recipes")).json()

    assert before.status_code == 404
    assert shared.status_code == 200, shared.text
    assert (shared.json()["space_id"], shared.json()["mine"]) == (people["home"], True)
    assert luis["mine"] is False
    assert (luis["nutrition"]["counted"], luis["nutrition"]["ingredients"]) == (2, 2)
    assert (
        luis["nutrition"]["per_serving"]["kcal"]
        == shared.json()["nutrition"]["per_serving"]["kcal"]
    )
    assert luis["tags"] == []
    assert [(one["name"], one["space_id"] is not None) for one in listed] == [("Leek soup", True)]
    assert eva.status_code == 404


async def test_a_member_writes_a_new_version_that_is_born_in_the_space(call, people) -> None:
    recipe = await leek_soup(call)
    await call("ana", "PUT", f"/recipes/{recipe}/space", json={"space_id": people["home"]})
    current = (await call("luis", "GET", f"/recipes/{recipe}")).json()
    ingredients = [
        {"food_id": one["food_id"], "quantity": one["quantity"] * 2, "unit": one["unit"]}
        for group in current["groups"]
        for one in group["ingredients"]
    ]

    edited = await call(
        "luis",
        "PUT",
        f"/recipes/{recipe}",
        json={"name": "Leek soup", "servings": 8, "tags": ["Luis's"], "ingredients": ingredients},
    )
    ana = (await call("ana", "GET", f"/recipes/{recipe}")).json()

    assert edited.status_code == 200, edited.text
    assert (ana["version"], ana["servings"], ana["versions"]) == (2, 8, 2)
    assert [tag["name"] for tag in ana["tags"]] == ["winter"]
    assert [tag["name"] for tag in edited.json()["tags"]] == ["Luis's"]


async def test_only_whoever_created_it_shares_unshares_or_deletes_it(call, people) -> None:
    recipe = await leek_soup(call)
    await call("ana", "PUT", f"/recipes/{recipe}/space", json={"space_id": people["home"]})

    unshare = await call("luis", "PUT", f"/recipes/{recipe}/space", json={"space_id": None})
    delete = await call("luis", "DELETE", f"/recipes/{recipe}")
    outsider = await call(
        "eva", "PUT", f"/recipes/{recipe}/space", json={"space_id": people["home"]}
    )

    assert (unshare.status_code, delete.status_code) == (409, 409)
    assert outsider.status_code == 404
    assert (await call("luis", "GET", f"/recipes/{recipe}")).status_code == 200


async def test_unsharing_takes_back_every_version_and_sealed_stays_sealed(call, people) -> None:
    recipe = await leek_soup(call)
    await call("ana", "PUT", f"/recipes/{recipe}/space", json={"space_id": people["home"]})
    current = (await call("luis", "GET", f"/recipes/{recipe}")).json()
    await call(
        "luis",
        "PUT",
        f"/recipes/{recipe}",
        json={
            "name": "Leek soup",
            "servings": 6,
            "ingredients": [
                {"food_id": one["food_id"], "quantity": one["quantity"], "unit": one["unit"]}
                for group in current["groups"]
                for one in group["ingredients"]
            ],
        },
    )

    back = await call("ana", "PUT", f"/recipes/{recipe}/space", json={"space_id": None})
    luis = await call("luis", "GET", f"/recipes/{recipe}")
    async with app_connection(people["ana"]) as connection:
        owners = (
            (
                await connection.execute(
                    text(
                        "select distinct user_id::text from recipes.recipes_recipe_version "
                        "where recipe_id = cast(:id as uuid)"
                    ),
                    {"id": recipe},
                )
            )
            .scalars()
            .all()
        )
        with pytest.raises(Exception, match="sealed"):
            await connection.execute(
                text(
                    "update recipes.recipes_recipe_version set note = 'tocada' "
                    "where recipe_id = cast(:id as uuid)"
                ),
                {"id": recipe},
            )

    assert back.status_code == 200, back.text
    assert (back.json()["space_id"], back.json()["versions"]) == (None, 2)
    assert luis.status_code == 404
    assert owners == [people["ana"]]


async def test_claude_shares_a_recipe_by_the_spaces_name(call, people) -> None:
    recipe = await leek_soup(call)

    async def tool(name: str, arguments: dict) -> dict:
        response = await call(
            name,
            "POST",
            "/tools/share_recipe",
            json=arguments,
            headers={"x-arga-scopes": "recipes:write"},
        )
        assert response.status_code == 200, response.text
        return response.json()["content"]

    unknown = await tool("ana", {"recipe_id": recipe, "space": "Office"})
    shared = await tool("ana", {"recipe_id": recipe, "space": "home"})
    by_luis = await tool("luis", {"recipe_id": recipe, "space": None})

    assert unknown["recipe"] is None and "'Home'" in unknown["note"]
    assert (shared["recipe"]["shared"], shared["recipe"]["mine"]) == (True, True)
    assert by_luis["recipe"] is None and "only whoever" in by_luis["note"]


def app_connection(person: str):
    from contextlib import asynccontextmanager
    from uuid import UUID

    from arga_tenancy import as_user
    from recipes.db import engine

    @asynccontextmanager
    async def opened():
        with as_user(UUID(person)):
            async with engine().begin() as connection:
                await connection.execute(text('set local role "mod_recipes"'))
                yield connection

    return opened()
