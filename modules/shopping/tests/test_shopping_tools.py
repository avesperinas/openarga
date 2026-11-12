from __future__ import annotations

from pathlib import Path

import yaml
from sqlalchemy import text

MANIFEST = Path(__file__).resolve().parents[1] / "manifest.yaml"
READ = {"x-arga-scopes": "shopping:read"}
WRITE = {"x-arga-scopes": "shopping:read shopping:write"}


def call(api, name: str, arguments: dict, headers: dict = WRITE):
    return api.post(f"/tools/{name}", json=arguments, headers=headers)


async def content(api, name: str, arguments: dict, headers: dict = WRITE) -> dict:
    response = await call(api, name, arguments, headers)
    assert response.status_code == 200, response.text
    return response.json()["content"]


async def test_the_listed_tools_are_the_ones_the_manifest_declares(api) -> None:
    manifest = yaml.safe_load(MANIFEST.read_text())
    served = (await api.get("/tools")).json()

    assert {tool["name"] for tool in served} == {tool["name"] for tool in manifest["tools"]}
    assert {tool["name"] for tool in served} == {
        "get_shopping_list",
        "get_purchase_history",
        "add_to_list",
        "remove_from_list",
    }
    assert all("properties" in tool["input_schema"] for tool in served)


def test_what_changes_the_list_carries_the_write_scope() -> None:
    manifest = yaml.safe_load(MANIFEST.read_text())

    writing = {t["name"] for t in manifest["tools"] if t["scope"] == "shopping:write"}

    assert writing == {"add_to_list", "remove_from_list"}


async def test_without_a_scope_of_this_module_nothing_runs(api) -> None:
    assert (await call(api, "get_shopping_list", {}, headers={})).status_code == 403
    refused = await call(api, "get_shopping_list", {}, headers={"x-arga-scopes": "training:read"})
    assert refused.status_code == 403


async def test_writing_with_only_the_read_scope_is_refused_by_postgres(api) -> None:
    response = await call(api, "add_to_list", {"items": [{"name": "Leche"}]}, headers=READ)

    assert response.status_code == 403
    assert "mod_shopping_read" in response.json()["detail"]


async def test_a_recipe_goes_to_the_list_in_one_call(api) -> None:
    await content(api, "add_to_list", {"items": [{"name": "Leche", "quantity": "2 L"}]})

    added = await content(
        api,
        "add_to_list",
        {
            "items": [
                {"name": "Carne picada", "quantity": "500 g"},
                {"name": "Tomate triturado", "quantity": "1 lata"},
                {"name": "Placas de lasaña"},
                {"name": "leche", "note": "entera"},
                {"name": "Bechamel casera", "section": "dairy"},
            ]
        },
    )
    listing = await content(api, "get_shopping_list", {}, READ)

    assert [(one["name"], one["section"], one["already_on_list"]) for one in added["added"]] == [
        ("Carne picada", "meat", False),
        ("Tomate triturado", "pantry", False),
        ("Placas de lasaña", "pantry", False),
        ("Leche", "dairy", True),
        ("Bechamel casera", "dairy", False),
    ]
    assert added["pending"] == 5
    milk = next(
        one for section in listing["sections"] for one in section["items"] if one["name"] == "Leche"
    )
    assert (milk["quantity"], milk["note"]) == ("2 L", "entera")


async def test_a_list_that_does_not_validate_writes_nothing(api) -> None:
    refused = await call(
        api, "add_to_list", {"items": [{"name": "Pan"}, {"name": "Algo", "section": "garage"}]}
    )

    assert refused.status_code == 422
    assert (await content(api, "get_shopping_list", {}, READ))["pending"] == 0


async def test_a_name_with_nothing_in_it_leaves_the_list_as_it_was(api) -> None:
    answer = await content(api, "add_to_list", {"items": [{"name": "Pan"}, {"name": "   "}]})

    assert answer["added"] == []
    assert answer["note"].startswith("no he apuntado nada")
    assert (await content(api, "get_shopping_list", {}, READ))["pending"] == 0


async def test_removing_by_name_keeps_the_product(api, schema) -> None:
    await content(api, "add_to_list", {"items": [{"name": "Leche"}, {"name": "Pan"}]})

    removed = await content(api, "remove_from_list", {"name": "leche"})

    assert removed["removed"] == {"name": "Leche"}
    assert removed["pending"] == 1
    async with schema.connect() as connection:
        products = (
            (
                await connection.execute(
                    text("select name from shopping.shopping_product order by name")
                )
            )
            .scalars()
            .all()
        )
    assert products == ["Leche", "Pan"]


async def test_a_name_that_could_be_several_removes_none(api) -> None:
    await content(
        api, "add_to_list", {"items": [{"name": "Leche entera"}, {"name": "Leche de avena"}]}
    )

    answer = await content(api, "remove_from_list", {"name": "leche"})

    assert answer["removed"] is None
    assert sorted(answer["candidates"]) == ["Leche de avena", "Leche entera"]
    assert (await content(api, "get_shopping_list", {}, READ))["pending"] == 2


async def test_what_is_not_on_the_list_is_said(api) -> None:
    answer = await content(api, "remove_from_list", {"name": "caviar"})

    assert answer["removed"] is None
    assert "no está en la lista" in answer["note"]


async def test_the_history_says_how_often_and_when(api, schema) -> None:
    from test_shopping_list import buy

    for days_ago in (21, 14, 7):
        await buy(api, schema, "Café", days_ago=days_ago)

    history = await content(api, "get_purchase_history", {"query": "caf"}, READ)

    assert history["products_known"] == 1
    product = history["products"][0]
    assert (product["name"], product["times_bought"], product["every_days"]) == ("Café", 3, 7)
    assert product["due"] is True
    assert [trip["products"] for trip in history["recent_trips"]] == [["Café"]] * 3
