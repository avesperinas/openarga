from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import text
from test_shopping_list import add, buy

from arga_module import i18n, preferences
from shopping import catalog, habits

MADRID = {"x-arga-timezone": "Europe/Madrid"}
NEW_YORK = {"x-arga-timezone": "America/New_York"}
READ = {"x-arga-scopes": "shopping:read"}
LATE = datetime(2026, 3, 1, 23, 30, tzinfo=UTC)


def person(**chosen: str) -> preferences.Preferences:
    headers = {preferences.HEADERS[key]: value for key, value in chosen.items()}
    return preferences.from_headers(headers)


async def bought_late_at_night(api, schema) -> None:
    await buy(api, schema, "Milk")
    async with schema.begin() as connection:
        await connection.execute(
            text("update shopping.shopping_trip set finished_at = cast(:at as timestamptz)"),
            {"at": LATE},
        )
        await connection.execute(
            text(
                "update shopping.shopping_item set closed_at = cast(:at as timestamptz) "
                "where trip_id is not null"
            ),
            {"at": LATE},
        )


async def history(api, zone: dict[str, str]) -> dict:
    response = await api.post("/tools/get_purchase_history", json={}, headers={**READ, **zone})
    assert response.status_code == 200, response.text
    return response.json()["content"]


async def test_a_purchase_counts_on_the_day_of_the_person_time_zone(api, schema) -> None:
    await bought_late_at_night(api, schema)

    madrid = await history(api, MADRID)
    new_york = await history(api, NEW_YORK)

    assert madrid["recent_trips"][0]["date"] == "2026-03-02"
    assert madrid["products"][0]["last_bought"] == "2026-03-02"
    assert new_york["recent_trips"][0]["date"] == "2026-03-01"
    assert new_york["products"][0]["last_bought"] == "2026-03-01"


async def test_the_trip_reaches_the_calendar_in_the_person_time_zone(api, schema) -> None:
    listing = (await add(api, "Bread"))["list"]
    bread = listing["groups"][0]["items"][0]["id"]
    await api.put(f"/list/items/{bread}/cart", json={"in_cart": True})

    await api.post("/list/finish", headers=NEW_YORK)

    async with schema.connect() as connection:
        payload = (
            await connection.execute(
                text("select payload from shopping.shopping_outbox where type = 'shopping.trip'")
            )
        ).scalar_one()
    event = next(value for value in payload.values() if isinstance(value, dict))
    assert event["tz"] == "America/New_York"


async def test_server_texts_follow_the_locale_of_the_person(api) -> None:
    spanish = i18n.catalogs(catalog.CATALOGS)["es"]

    english_card = (await api.get("/widgets/list", headers={"x-arga-locale": "en"})).json()
    spanish_card = (await api.get("/widgets/list", headers={"x-arga-locale": "es"})).json()

    assert english_card["body"]["detail"] == "nothing on the list"
    assert spanish_card["body"]["detail"] == spanish["list.empty"]


def test_habits_are_said_in_the_locale_of_the_person() -> None:
    spanish = i18n.catalogs(catalog.CATALOGS)["es"]

    token = preferences.use(person(locale="en"))
    try:
        assert habits.every_label(14) == "every 2 weeks"
        assert habits.since_label(3) == "3 days ago"
    finally:
        preferences.reset(token)

    token = preferences.use(person(locale="es"))
    try:
        assert habits.every_label(14) == spanish["every.weeks"].format(weeks=2)
        assert habits.since_label(3) == spanish["since.days"].format(days=3)
    finally:
        preferences.reset(token)


def test_both_catalogs_have_the_same_keys() -> None:
    assert i18n.missing(catalog.CATALOGS) == []
