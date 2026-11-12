from __future__ import annotations

import pytest
from sqlalchemy import text

import arga_agenda
from shopping import shopping


async def add(api, *items: str | dict) -> dict:
    body = [{"name": one} if isinstance(one, str) else one for one in items]
    response = await api.post("/list/items", json={"items": body})
    assert response.status_code == 201, response.text
    return response.json()


def pending(listing: dict) -> list[str]:
    return [one["name"] for group in listing["groups"] for one in group["items"]]


def item(listing: dict, name: str) -> dict:
    everything = [one for group in listing["groups"] for one in group["items"]] + listing["cart"]
    return next(one for one in everything if one["name"] == name)


async def buy(api, schema, *names: str, days_ago: int = 0) -> None:
    listing = (await add(api, *names))["list"]
    for name in names:
        listing = (
            await api.put(f"/list/items/{item(listing, name)['id']}/cart", json={"in_cart": True})
        ).json()
    trip = (await api.post("/list/finish")).json()["trip"]["id"]
    async with schema.begin() as connection:
        for table, column in (("shopping_trip", "finished_at"), ("shopping_item", "closed_at")):
            where = "id" if table == "shopping_trip" else "trip_id"
            await connection.execute(
                text(
                    f"update shopping.{table} set {column} = (now() at time zone 'Europe/Madrid'"
                    " - make_interval(days => :d)) at time zone 'Europe/Madrid' "
                    f"where {where} = cast(:t as uuid)"
                ),
                {"d": days_ago, "t": trip},
            )


async def test_a_new_list_is_empty(api) -> None:
    listing = (await api.get("/list")).json()

    assert listing["groups"] == [] and listing["cart"] == []
    assert (listing["pending"], listing["in_cart"]) == (0, 0)


async def test_what_is_added_falls_in_its_section_in_the_order_of_the_shop(api) -> None:
    listing = (await add(api, "Lejía", "Leche", "Tomates", "Cosa rara"))["list"]

    assert [group["category_id"] for group in listing["groups"]] == [
        "produce",
        "dairy",
        "cleaning",
        "other",
    ]
    assert [group["emoji"] for group in listing["groups"]][0] == "🥬"


async def test_what_the_dictionary_guessed_is_said(api) -> None:
    added = (await add(api, "Leche", "Cosa rara", {"name": "Otra", "category_id": "pantry"}))[
        "added"
    ]

    assert [(one["category_id"], one["guessed"]) for one in added] == [
        ("dairy", True),
        ("other", True),
        ("pantry", False),
    ]


async def test_the_same_product_is_on_the_list_once(api) -> None:
    await add(api, {"name": "Leche", "quantity": "2"})
    again = await add(api, {"name": "  leche "}, {"name": "LECHE", "quantity": "6"})

    assert [one["already_on_list"] for one in again["added"]] == [True, True]
    assert pending(again["list"]) == ["Leche"]
    assert item(again["list"], "Leche")["quantity"] == "6"


async def test_checking_moves_it_to_the_cart_and_unchecking_brings_it_back(api) -> None:
    listing = (await add(api, "Pan", "Leche"))["list"]
    bread = item(listing, "Pan")["id"]

    checked = (await api.put(f"/list/items/{bread}/cart", json={"in_cart": True})).json()
    unchecked = (await api.put(f"/list/items/{bread}/cart", json={"in_cart": False})).json()

    assert pending(checked) == ["Leche"] and [one["name"] for one in checked["cart"]] == ["Pan"]
    assert (checked["pending"], checked["in_cart"]) == (1, 1)
    assert sorted(pending(unchecked)) == ["Leche", "Pan"] and unchecked["cart"] == []


async def test_finishing_keeps_what_was_not_picked_for_next_time(api) -> None:
    listing = (await add(api, "Pan", "Leche"))["list"]
    await api.put(f"/list/items/{item(listing, 'Pan')['id']}/cart", json={"in_cart": True})

    finished = (await api.post("/list/finish")).json()

    assert finished["trip"]["items"] == 1
    assert [one["name"] for one in finished["trip"]["products"]] == ["Pan"]
    assert pending(finished["list"]) == ["Leche"] and finished["list"]["cart"] == []
    trips = (await api.get("/trips")).json()
    assert [trip["items"] for trip in trips] == [1]


async def test_finishing_with_an_empty_cart_is_not_a_purchase(api) -> None:
    await add(api, "Pan")

    refused = await api.post("/list/finish")

    assert refused.status_code == 409
    assert "carro" in refused.json()["detail"]
    assert (await api.get("/trips")).json() == []


async def test_removing_does_not_delete_the_product_or_its_history(api, schema) -> None:
    await buy(api, schema, "Leche")
    listing = (await add(api, "Leche"))["list"]

    removed = (await api.post(f"/list/items/{item(listing, 'Leche')['id']}/drop")).json()

    assert pending(removed) == []
    products = (await api.get("/products")).json()
    assert [(one["name"], one["times"]) for one in products] == [("Leche", 1)]
    async with schema.connect() as connection:
        statuses = (
            (
                await connection.execute(
                    text("select status from shopping.shopping_item order by added_at")
                )
            )
            .scalars()
            .all()
        )
    assert statuses == ["bought", "dropped"]


async def test_the_quantity_of_last_time_comes_back(api, schema) -> None:
    await buy(api, schema, "Huevos")
    listing = (await add(api, {"name": "Huevos", "quantity": "docena"}))["list"]
    await api.post(f"/list/items/{item(listing, 'Huevos')['id']}/drop")

    again = (await add(api, "Huevos"))["list"]

    assert item(again, "Huevos")["quantity"] == "docena"


async def test_changing_the_quantity_and_note_of_what_is_on_the_list(api) -> None:
    listing = (await add(api, "Leche"))["list"]
    milk = item(listing, "Leche")["id"]

    changed = (
        await api.put(f"/list/items/{milk}", json={"quantity": "6", "note": "sin lactosa"})
    ).json()
    cleared = (await api.put(f"/list/items/{milk}", json={"quantity": " ", "note": None})).json()

    assert (item(changed, "Leche")["quantity"], item(changed, "Leche")["note"]) == (
        "6",
        "sin lactosa",
    )
    assert (item(cleared, "Leche")["quantity"], item(cleared, "Leche")["note"]) == (None, None)


async def test_moving_a_product_to_another_section_is_remembered(api) -> None:
    listing = (await add(api, "Cosa rara"))["list"]
    product = item(listing, "Cosa rara")["product_id"]

    moved = (await api.put(f"/products/{product}/category", json={"category_id": "pantry"})).json()
    await api.post(f"/list/items/{item(moved, 'Cosa rara')['id']}/drop")
    again = await add(api, "cosa rara")

    assert moved["groups"][0]["category_id"] == "pantry"
    assert again["added"][0]["category_id"] == "pantry"
    assert again["added"][0]["guessed"] is False


async def test_a_section_that_does_not_exist_is_a_404(api) -> None:
    missing = await api.post(
        "/list/items", json={"items": [{"name": "Pan", "category_id": "garage"}]}
    )

    assert missing.status_code == 404


ITEM_ID = "00000000-0000-4000-8000-0000000000a1"
TRIP_ID = "00000000-0000-4000-8000-0000000000b1"


async def test_what_comes_twice_from_the_offline_queue_is_added_once(api, schema) -> None:
    first = await add(api, {"id": ITEM_ID, "name": "Leche"})
    again = await add(api, {"id": ITEM_ID, "name": "Leche"})

    assert first["added"][0]["item_id"] == ITEM_ID
    assert again["added"][0] == {
        **first["added"][0],
        "new_product": False,
        "already_on_list": True,
        "guessed": False,
    }
    assert pending(again["list"]) == ["Leche"]
    async with schema.begin() as connection:
        rows = await connection.execute(text("select count(*) from shopping.shopping_item"))
        assert rows.scalar() == 1


async def test_what_was_removed_in_between_is_not_added_back_by_a_repeat(api) -> None:
    await add(api, {"id": ITEM_ID, "name": "Leche"})
    await api.post(f"/list/items/{ITEM_ID}/drop")

    assert pending((await add(api, {"id": ITEM_ID, "name": "Leche"}))["list"]) == []


async def test_removing_twice_is_removing_once(api) -> None:
    await add(api, {"id": ITEM_ID, "name": "Leche"})

    assert (await api.post(f"/list/items/{ITEM_ID}/drop")).status_code == 200
    assert (await api.post(f"/list/items/{ITEM_ID}/drop")).status_code == 200


async def test_finishing_twice_with_its_id_is_one_purchase(api, schema) -> None:
    listing = (await add(api, "Pan", "Huevos"))["list"]
    for name in ("Pan", "Huevos"):
        await api.put(f"/list/items/{item(listing, name)['id']}/cart", json={"in_cart": True})

    first = await api.post("/list/finish", json={"id": TRIP_ID})
    again = await api.post("/list/finish", json={"id": TRIP_ID})

    assert first.status_code == again.status_code == 201
    assert again.json()["trip"] == first.json()["trip"]
    assert first.json()["trip"]["id"] == TRIP_ID
    async with schema.begin() as connection:
        rows = await connection.execute(text("select count(*) from shopping.shopping_trip"))
        assert rows.scalar() == 1


async def test_what_you_buy_regularly_is_proposed_when_it_is_due(api, schema) -> None:
    for days_ago in (22, 15, 8):
        await buy(api, schema, "Leche", days_ago=days_ago)
    await buy(api, schema, "Pan", days_ago=1)

    listing = (await api.get("/list")).json()

    assert [(one["name"], one["every"], one["since"]) for one in listing["due"]] == [
        ("Leche", "cada semana", "hace 8 días")
    ]
    assert pending(listing) == []
    assert [one["name"] for one in listing["usual"]] == []


async def test_what_is_already_on_the_list_is_not_proposed(api, schema) -> None:
    for days_ago in (22, 15, 8):
        await buy(api, schema, "Leche", days_ago=days_ago)
    listing = (await add(api, "Leche"))["list"]

    assert listing["due"] == [] and listing["usual"] == []


async def test_the_usual_ones_are_what_you_buy_most(api, schema) -> None:
    for days_ago in (20, 10, 5):
        await buy(api, schema, "Pan", days_ago=days_ago)
    for days_ago in (20, 10):
        await buy(api, schema, "Leche", days_ago=days_ago)
    await buy(api, schema, "Lejía", days_ago=3)

    usual = (await api.get("/list")).json()["usual"]

    assert [(one["name"], one["times"]) for one in usual] == [("Pan", 3), ("Leche", 2)]


async def test_typing_completes_with_what_you_have_bought(api, schema) -> None:
    await buy(api, schema, "Plátanos", "Papel de plata", "Espátula")

    found = (await api.get("/products", params={"query": "plat"})).json()

    assert sorted(one["name"] for one in found) == ["Papel de plata", "Plátanos"]


@pytest.mark.parametrize(
    ("method", "path", "body"),
    [
        ("put", "/list/items/00000000-0000-4000-8000-000000000000/cart", {"in_cart": True}),
        ("put", "/list/items/00000000-0000-4000-8000-000000000000", {"quantity": "2"}),
        ("post", "/list/items/00000000-0000-4000-8000-000000000000/drop", None),
        (
            "put",
            "/products/00000000-0000-4000-8000-000000000000/category",
            {"category_id": "pantry"},
        ),
    ],
)
async def test_what_is_not_there_is_a_404(api, method: str, path: str, body) -> None:
    response = await api.request(method, path, json=body)

    assert response.status_code == 404


async def test_finishing_queues_the_purchase_for_the_log(api, schema) -> None:
    await buy(api, schema, "Pan", "Leche")

    async with schema.connect() as connection:
        rows = (
            await connection.execute(
                text("select type, payload, dedup_hash from shopping.shopping_outbox order by id")
            )
        ).all()

    assert [row.type for row in rows] == ["shopping.trip_finished", "shopping.trip"]
    assert rows[0].payload["items"] == 2
    assert sorted(one["name"] for one in rows[0].payload["products"]) == ["Leche", "Pan"]
    assert rows[0].dedup_hash == f"trip:{rows[0].payload['trip_id']}"
    item = arga_agenda.check_event(rows[1].payload)
    assert item["uid"] == f"shopping:trip:{rows[0].payload['trip_id']}"
    assert item["title"] == "Compra de 2 productos"
    assert item["start"] == item["end"]


async def test_the_purchases_of_before_reach_the_calendar_once(api, schema) -> None:
    await buy(api, schema, "Pan")
    async with schema.begin() as connection:
        await connection.execute(text('set local role "mod_shopping"'))
        await connection.execute(text("delete from shopping.shopping_outbox"))

    for _ in range(2):
        async with schema.begin() as connection:
            await connection.execute(text('set local role "mod_shopping"'))
            await shopping.backfill(connection)

    async with schema.connect() as connection:
        types = (
            (await connection.execute(text("select type from shopping.shopping_outbox")))
            .scalars()
            .all()
        )
    assert types == ["shopping.trip"]
