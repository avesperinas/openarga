from __future__ import annotations

from sqlalchemy import text

import arga_contracts as contracts
from shopping import records
from shopping.db import engine
from shopping.shopping import today


async def built() -> dict[str, dict]:
    async with engine().begin() as connection:
        await connection.execute(text('set local role "mod_shopping"'))
        found = await records.build(connection)
    for one in found:
        assert one == contracts.record(**one)
    return {one["id"]: one for one in found}


async def test_the_list_what_you_buy_and_each_trip_on_its_day(api) -> None:
    added = (
        await api.post(
            "/list/items",
            json={
                "items": [
                    {"name": "Bread", "category_id": "bakery"},
                    {"name": "Milk", "quantity": "2 l", "category_id": "dairy"},
                ]
            },
        )
    ).json()
    bread = next(one for one in added["added"] if one["name"] == "Bread")
    await api.put(f"/list/items/{bread['item_id']}/cart", json={"in_cart": True})
    finished = await api.post("/list/finish")
    assert finished.status_code == 201, finished.text

    found = await built()

    shopping_list = found["list"]
    assert shopping_list["title"] == "Shopping list"
    assert shopping_list["properties"] == {"pending": 1, "in_trolley": 0}
    assert "- [ ] Milk (2 l)" in shopping_list["body"]
    assert "Bread" not in shopping_list["body"]

    habits = found["habits"]
    assert "| Bread | Bakery | 1 |" in habits["body"]

    day = found[f"day:{today().isoformat()}"]
    assert day["properties"] == {"shopping_items": 1}
    assert day["body"] == "- Shopping of 1 thing: Bread"
