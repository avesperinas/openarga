from __future__ import annotations

from test_shopping_list import add, buy

from arga_widgets import validate


async def test_an_empty_list_says_so(api) -> None:
    body = (await api.get("/widgets/list")).json()

    assert body["state"] == "empty"
    assert body["body"]["detail"] == "nothing on the list"


async def test_the_list_card_shows_what_is_left_and_how_much(api) -> None:
    listing = (await add(api, {"name": "Milk", "quantity": "2"}, "Bread", "Bleach"))["list"]
    bread = next(one for g in listing["groups"] for one in g["items"] if one["name"] == "Bread")
    await api.put(f"/list/items/{bread['id']}/cart", json={"in_cart": True})

    body = (await api.get("/widgets/list")).json()

    assert body["state"] == "ready"
    validate("tasks", body["body"], "ready")
    assert [(t["title"], t.get("detail"), t.get("done")) for t in body["body"]["tasks"]] == [
        ("Milk", "2", None),
        ("Bleach", None, None),
        ("Bread", None, True),
    ]
    assert body["body"]["count"] == 2
    assert body["body"]["checkable"] is True


async def test_the_list_is_ticked_from_the_card_and_given_back(api) -> None:
    await add(api, "Bread", "Milk")
    card = (await api.get("/widgets/list")).json()["body"]
    bread = next(t for t in card["tasks"] if t["title"] == "Bread")

    taken = await api.post("/widgets/list/act", json={"verb": "complete", "id": bread["id"]})
    assert taken.status_code == 200, taken.text
    assert taken.json()["body"]["count"] == 1
    assert next(t for t in taken.json()["body"]["tasks"] if t["title"] == "Bread")["done"] is True

    back = await api.post("/widgets/list/act", json={"verb": "reopen", "id": bread["id"]})
    assert back.json()["body"]["count"] == 2

    assert (
        await api.post("/widgets/due/act", json={"verb": "complete", "id": bread["id"]})
    ).status_code == 404
    assert (
        await api.post("/widgets/list/act", json={"verb": "drop", "id": bread["id"]})
    ).status_code == 422


async def test_without_three_purchases_the_due_card_says_why_it_is_empty(api) -> None:
    body = (await api.get("/widgets/due")).json()

    assert body["state"] == "empty"
    assert body["body"]["detail"] == "it takes three purchases of something"


async def test_the_due_card_shows_what_is_running_out(api, schema) -> None:
    for days_ago in (22, 15, 8):
        await buy(api, schema, "Milk", days_ago=days_ago)

    body = (await api.get("/widgets/due")).json()

    assert body["state"] == "ready"
    assert body["body"]["rows"] == [{"label": "Milk", "value": "8 days ago"}]


async def test_a_widget_that_does_not_exist_is_a_404(api) -> None:
    assert (await api.get("/widgets/whatever")).status_code == 404
