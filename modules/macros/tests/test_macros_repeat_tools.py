from __future__ import annotations

from datetime import timedelta

from test_macros_usual import APPLE, READ, WRITE, call, snacks

from macros.common import today


async def test_claude_asks_for_the_usual_and_repeats_it(api, world) -> None:
    yogurt, nuts, apple = await snacks(api, world)

    found = await call(api, "get_usual", {"meal": "snack"}, READ)
    assert found["usual"]["times"] == 3
    assert found["menus"] == []

    repeated = await call(api, "repeat_intake", {"item_ids": found["usual"]["item_ids"]})
    assert repeated["logged"]["meal"] == "snack"
    assert repeated["logged"]["day"] == today().isoformat()

    again = await call(
        api,
        "repeat_intake",
        {
            "from_day": (today() - timedelta(days=1)).isoformat(),
            "from_meal": "snack",
            "meal": "dinner",
        },
    )
    assert again["logged"]["meal"] == "dinner"
    assert [one["name"] for one in again["logged"]["items"]] == ["Yogur natural", "Nueces"]

    refused = await api.post(
        "/tools/repeat_intake",
        json={"item_ids": found["usual"]["item_ids"], "from_day": today().isoformat()},
        headers=WRITE,
    )
    assert refused.status_code == 422
    refused = await api.post(
        "/tools/repeat_intake",
        json={"item_ids": found["usual"]["item_ids"], "nutrients": {"kcal": 1}},
        headers=WRITE,
    )
    assert refused.status_code == 422


async def test_claude_logs_and_moves_with_the_meal(api, world) -> None:
    apple = await world.manual_food("Manzana", APPLE)
    yesterday = today() - timedelta(days=1)

    logged = await call(
        api,
        "log_intake",
        {
            "meal": "snack",
            "eaten_at": f"{yesterday.isoformat()}T09:00:00",
            "items": [{"food_id": apple, "quantity": 180, "unit": "g"}],
        },
    )
    assert (logged["logged"]["meal"], logged["logged"]["day"]) == ("snack", yesterday.isoformat())

    moved = await call(
        api, "update_intake", {"entry_id": logged["logged"]["entry_id"], "meal": "lunch"}
    )
    assert (moved["updated"]["meal"], moved["updated"]["day"]) == ("lunch", yesterday.isoformat())
    assert moved["updated"]["time"] == "14:30"
