from __future__ import annotations

from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

import pytest

from macros import meals
from macros.common import today

MADRID = ZoneInfo("Europe/Madrid")

COFFEE = {"kcal": 2, "protein": 0.3, "fat": 0, "carbs": 0}
TOAST = {"kcal": 266, "protein": 7.6, "fat": 3.3, "carbs": 50.6}


@pytest.mark.parametrize(
    ("at", "meal"),
    [
        (time(0, 0), "night"),
        (time(3, 59), "night"),
        (time(4, 0), "breakfast"),
        (time(10, 29), "breakfast"),
        (time(10, 30), "morning"),
        (time(12, 59), "morning"),
        (time(13, 0), "lunch"),
        (time(16, 59), "lunch"),
        (time(17, 0), "snack"),
        (time(19, 59), "snack"),
        (time(20, 0), "dinner"),
        (time(23, 59), "dinner"),
    ],
)
def test_each_hour_belongs_to_one_meal(at: time, meal: str) -> None:
    assert meals.meal_of(at) == meal


def test_the_meal_is_read_in_its_zone() -> None:
    assert meals.meal_of(datetime(2026, 10, 20, 11, 45, tzinfo=MADRID)) == "morning"
    utc = datetime.fromisoformat("2026-10-20T19:30:00+00:00")
    assert meals.meal_of(utc) == "dinner"


def test_a_meal_has_started_today_from_its_hour_and_always_on_a_past_day() -> None:
    noon = datetime(2026, 10, 20, 12, 0, tzinfo=MADRID)
    on = noon.date()
    assert meals.started("breakfast", on, noon)
    assert meals.started("morning", on, noon)
    assert not meals.started("lunch", on, noon)
    assert meals.started("dinner", on - timedelta(days=1), noon)
    assert not meals.started("breakfast", on + timedelta(days=1), noon)


def iso(day: date, at: str) -> str:
    return f"{day.isoformat()}T{at}:00"


async def log(api, food: str, grams: float, **body):
    response = await api.post(
        "/entries", json={"items": [{"food_id": food, "quantity": grams, "unit": "g"}], **body}
    )
    assert response.status_code == 201, response.text
    return response.json()


async def test_without_history_each_meal_has_its_default_hour_and_then_the_median(
    api, world
) -> None:
    toast = await world.manual_food("Toast", TOAST)
    day = (await api.get("/day")).json()
    usual = {one["meal"]: one["usual_at"] for one in day["meals"]}
    assert usual == {
        "breakfast": "08:30",
        "morning": "11:00",
        "lunch": "14:30",
        "snack": "18:00",
        "dinner": "21:30",
    }

    for back, at in ((1, "07:00"), (2, "07:10"), (3, "07:40")):
        await log(api, toast, 50, eaten_at=iso(today() - timedelta(days=back), at))
    day = (await api.get("/day")).json()
    assert {one["meal"]: one["usual_at"] for one in day["meals"]}["breakfast"] == "07:10"


async def test_the_day_comes_by_meals_with_their_ids_and_night_only_with_something(
    api, world
) -> None:
    coffee = await world.manual_food("Coffee", COFFEE)
    toast = await world.manual_food("Toast", TOAST)
    past = today() - timedelta(days=3)
    breakfast = await log(api, coffee, 150, eaten_at=iso(past, "08:00"))
    second = await log(api, toast, 100, eaten_at=iso(past, "09:10"))
    dinner = await log(api, toast, 50, eaten_at=iso(past, "21:00"))

    day = (await api.get("/day", params={"day": past.isoformat()})).json()
    assert [one["meal"] for one in day["meals"]] == [
        "breakfast",
        "morning",
        "lunch",
        "snack",
        "dinner",
    ]
    first = day["meals"][0]
    assert first["entry_ids"] == [breakfast["id"], second["id"]]
    assert first["kcal"] == pytest.approx(3 + 266)
    assert first["started"] and not first["current"]
    assert day["meals"][4]["entry_ids"] == [dinner["id"]]
    assert {entry["meal"] for entry in day["entries"]} == {"breakfast", "dinner"}

    await log(api, toast, 30, eaten_at=iso(past, "01:30"))
    day = (await api.get("/day", params={"day": past.isoformat()})).json()
    assert day["meals"][0]["meal"] == "night"
    assert day["meals"][0]["label"] == "Night"


async def test_logging_with_the_meal_puts_it_at_its_usual_hour(api, world) -> None:
    toast = await world.manual_food("Toast", TOAST)
    past = today() - timedelta(days=2)

    logged = await log(api, toast, 50, meal="lunch", eaten_at=iso(past, "09:00"))
    moment = datetime.fromisoformat(logged["eaten_at"]).astimezone(MADRID)
    assert (moment.date(), moment.time()) == (past, time(14, 30))
    assert logged["meal"] == "lunch"

    logged = await log(api, toast, 50, meal="lunch", eaten_at=iso(past, "15:10"))
    assert datetime.fromisoformat(logged["eaten_at"]).astimezone(MADRID).time() == time(15, 10)

    moved = await api.patch(f"/entries/{logged['id']}", json={"meal": "dinner"})
    assert moved.status_code == 200, moved.text
    moment = datetime.fromisoformat(moved.json()["eaten_at"]).astimezone(MADRID)
    assert (moment.date(), moved.json()["meal"]) == (past, "dinner")


async def test_like_yesterday_copies_that_meal_with_its_numbers(api, world) -> None:
    coffee = await world.manual_food("Coffee", COFFEE)
    toast = await world.manual_food("Toast", TOAST)
    yesterday = today() - timedelta(days=1)
    await log(api, coffee, 150, eaten_at=iso(yesterday, "08:00"))
    await log(api, toast, 100, eaten_at=iso(yesterday, "08:05"))
    await log(api, toast, 300, eaten_at=iso(yesterday, "14:00"))

    world.recipes_down()
    copied = await api.post(
        "/meals/repeat", json={"from_day": yesterday.isoformat(), "meal": "breakfast"}
    )
    assert copied.status_code == 201, copied.text
    entry = copied.json()
    assert [item["name"] for item in entry["items"]] == ["Coffee", "Toast"]
    assert entry["nutrients"]["kcal"] == pytest.approx(3 + 266)
    assert (entry["day"], entry["meal"]) == (today().isoformat(), "breakfast")

    empty = await api.post(
        "/meals/repeat", json={"from_day": yesterday.isoformat(), "meal": "snack"}
    )
    assert empty.status_code == 404


async def test_the_meal_sheet_moves_saves_as_menu_and_deletes(api, world) -> None:
    coffee = await world.manual_food("Coffee", COFFEE)
    toast = await world.manual_food("Toast", TOAST)
    past = today() - timedelta(days=4)
    await log(api, coffee, 150, eaten_at=iso(past, "08:00"))
    await log(api, toast, 100, eaten_at=iso(past, "09:00"))

    moved = await api.put(f"/meals/{past.isoformat()}/breakfast/time", json={"at": "09:45"})
    assert moved.status_code == 200, moved.text
    assert {
        datetime.fromisoformat(one["eaten_at"]).astimezone(MADRID).time() for one in moved.json()
    } == {time(9, 45)}

    menu = await api.post(
        "/templates/from-meal",
        json={"day": past.isoformat(), "meal": "breakfast", "name": "Usual breakfast"},
    )
    assert menu.status_code == 201, menu.text
    assert [one["food_id"] for one in menu.json()["items"]] == [coffee, toast]

    gone = await api.delete(f"/meals/{past.isoformat()}/breakfast")
    assert gone.status_code == 204
    day = (await api.get("/day", params={"day": past.isoformat()})).json()
    assert day["entries"] == []


async def test_one_thing_moves_to_another_meal_and_leaves_the_rest(api, world) -> None:
    coffee = await world.manual_food("Coffee", COFFEE)
    toast = await world.manual_food("Toast", TOAST)
    past = today() - timedelta(days=5)
    entry = (
        await api.post(
            "/entries",
            json={
                "eaten_at": iso(past, "08:00"),
                "items": [
                    {"food_id": coffee, "quantity": 150, "unit": "g"},
                    {"food_id": toast, "quantity": 100, "unit": "g"},
                ],
            },
        )
    ).json()
    toast_item = entry["items"][1]["id"]

    moved = await api.post(f"/items/{toast_item}/move", json={"meal": "morning"})
    assert moved.status_code == 200, moved.text
    assert moved.json()["meal"] == "morning"
    day = (await api.get("/day", params={"day": past.isoformat()})).json()
    by_meal = {one["meal"]: one for one in day["meals"]}
    assert by_meal["breakfast"]["kcal"] == pytest.approx(3)
    assert by_meal["morning"]["kcal"] == pytest.approx(266)
    assert day["nutrients"]["kcal"] == pytest.approx(269)

    alone = moved.json()["items"][0]["id"]
    again = await api.post(f"/items/{alone}/move", json={"meal": "dinner"})
    assert again.json()["id"] == moved.json()["id"]
    assert again.json()["meal"] == "dinner"


async def test_get_day_says_the_meal_and_the_ids(api, world) -> None:
    toast = await world.manual_food("Toast", TOAST)
    past = today() - timedelta(days=6)
    entry = await log(api, toast, 100, eaten_at=iso(past, "14:00"))
    found = (
        await api.post(
            "/tools/get_day",
            json={"day": past.isoformat()},
            headers={"x-arga-scopes": "macros:read"},
        )
    ).json()["content"]
    [logged] = found["entries"]
    assert (logged["entry_id"], logged["meal"]) == (entry["id"], "lunch")
    assert logged["items"][0]["item_id"] == entry["items"][0]["id"]
    lunch = next(one for one in found["meals"] if one["meal"] == "lunch")
    assert lunch["entry_ids"] == [entry["id"]]
