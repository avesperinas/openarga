from __future__ import annotations

from datetime import timedelta

from outings_world import TODAY
from sqlalchemy import text

from outings import agenda, foryou

WRITE = {"x-arga-scopes": "outings:write"}
READ = {"x-arga-scopes": "outings:read"}


def found(title: str, days: int, town: str = "Synthetic Village", **extra) -> dict:
    return {
        "title": title,
        "starts_on": (TODAY + timedelta(days=days)).isoformat(),
        "category": "stage",
        "town": town,
        "link": "https://press.example/news",
        **extra,
    }


async def call(api, name: str, body: dict, headers: dict = WRITE):
    answer = await api.post(f"/tools/{name}", json=body, headers=headers)
    assert answer.status_code == 200, answer.text
    return answer.json()["content"]


async def add(api, *events: dict) -> list[str]:
    said = await call(api, "add_events", {"events": list(events)})
    return [one["event_id"] for one in said["events"]]


async def built() -> list[dict]:
    from outings.main import as_app

    async with as_app() as connection:
        return await foryou.build(connection)


async def arrived_on() -> str:
    from outings.main import as_app

    async with as_app() as connection:
        query = text(
            "select (max(first_seen) at time zone 'Europe/Madrid')::date from outings.outings_event"
        )
        return (await connection.execute(query)).scalar_one().isoformat()


async def test_what_you_like_what_is_big_nearby_and_what_names_a_wish_come_with_their_reason(
    api, area
) -> None:
    await call(api, "add_interest", {"kind": "like", "term": "jazz"})
    await call(api, "add_wish", {"kind": "getaway", "name": "Synthetic Badlands"})
    await add(
        api,
        found("Synthetic jazz night", 3),
        found("Synthetic Autumn Fair", 5, town=area.near.towns[0], highlight=True),
        found("Walk through the Synthetic Badlands", 8),
        found("Any old talk", 4),
    )

    picked = (await api.get("/foryou")).json()

    reasons = {one["event"]["title"]: one["reasons"] for one in picked}
    assert reasons == {
        "Synthetic jazz night": ["You like “jazz”"],
        "Synthetic Autumn Fair": [f"Big in {area.near.name}"],
        "Walk through the Synthetic Badlands": [
            "Near “Synthetic Badlands”, which is in your Wishes"
        ],
    }


async def test_what_you_set_aside_or_already_saved_is_not_for_you(api) -> None:
    await call(api, "add_interest", {"kind": "like", "term": "jazz"})
    aside, saved = await add(api, found("Jazz set aside", 3), found("Jazz saved", 4))
    await call(api, "hide_events", {"event_ids": [aside]})
    await call(api, "save_event", {"event_id": saved})

    assert (await api.get("/foryou")).json() == []


async def test_one_notice_per_day_with_the_title_or_the_count(api) -> None:
    await call(api, "add_interest", {"kind": "like", "term": "jazz"})
    await add(api, found("Synthetic jazz one", 3))

    [one] = [notice for notice in await built() if notice["kind"] == "for_you"]
    assert one["title"] == "You might like: Synthetic jazz one"
    assert one["key"] == f"for_you:{await arrived_on()}"
    assert one["href"] == f"/outings/explore?new={await arrived_on()}"
    assert "You like “jazz”" in one["body"]

    await add(api, found("Synthetic jazz two", 6))
    [both] = [notice for notice in await built() if notice["kind"] == "for_you"]
    assert both["title"] == "2 plans for you"
    assert both["key"] == one["key"]


async def test_the_weekend_comes_on_thursday(api) -> None:
    await call(api, "add_interest", {"kind": "like", "term": "jazz"})
    friday, _ = agenda.window("weekend", TODAY)
    await add(api, found("Weekend jazz", (friday - TODAY).days))

    [weekend] = [notice for notice in await built() if notice["kind"] == "weekend"]
    assert weekend["key"] == f"weekend:{friday.isoformat()}"
    assert weekend["href"] == "/outings/explore?when=weekend"
    assert weekend["at"].startswith((friday - timedelta(days=1)).isoformat())
    assert weekend["body"] == "Weekend jazz"


async def test_what_you_saved_and_starts_tomorrow_warns_the_day_before(api) -> None:
    [event_id] = await add(api, found("Saved concert", 1))
    saved = await call(api, "save_event", {"event_id": event_id})

    [soon] = [notice for notice in await built() if notice["kind"] == "saved_soon"]
    assert soon["title"] == "Saved concert starts tomorrow"
    assert soon["href"] == f"/outings/wishes/{saved['wish_id']}"


async def test_the_ai_asks_for_what_you_may_like(api) -> None:
    await call(api, "add_interest", {"kind": "like", "term": "jazz"})
    await add(api, found("Synthetic jazz", 3), found("Synthetic theatre", 4))

    answer = await call(api, "find_events", {"for_you": True}, READ)

    assert answer["total"] == 1
    [one] = answer["events"]
    assert one["title"] == "Synthetic jazz" and one["why"] == ["You like “jazz”"]


async def test_the_reasons_follow_the_person_language(api, monkeypatch) -> None:
    from arga_module.i18n import t
    from outings.words import CATALOGS

    monkeypatch.setenv("OPENARGA_LOCALE", "es")
    await call(api, "add_interest", {"kind": "like", "term": "jazz"})
    await add(api, found("Synthetic jazz", 3))

    [one] = (await api.get("/foryou")).json()
    assert one["reasons"] == [t(CATALOGS, "reason.liked", "es", term="jazz")]
    assert one["reasons"] != [t(CATALOGS, "reason.liked", "en", term="jazz")]


def test_both_catalogs_have_the_same_keys() -> None:
    from arga_module.i18n import missing
    from outings.words import CATALOGS

    assert missing(CATALOGS) == []
