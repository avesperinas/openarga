from __future__ import annotations

from datetime import timedelta

from outings_world import TODAY, Hub, derive, leisure

from outings import by_hand

WRITE = {"x-arga-scopes": "outings:write"}


def found(title: str, days: int, **extra) -> dict:
    return {
        "title": title,
        "starts_on": (TODAY + timedelta(days=days)).isoformat(),
        "category": "eat",
        "town": "Pamplona",
        "link": "https://press.example/news",
        **extra,
    }


async def add(api, *events: dict):
    return await api.post("/tools/add_events", json={"events": list(events)}, headers=WRITE)


async def test_what_claude_finds_goes_in_with_its_page_and_twice_is_once(api) -> None:
    first = await add(api, found("Synthetic Pintxo Days", 5, summary="Twenty bars."))
    again = await add(api, found("Synthetic Pintxo Days", 5, summary="Twenty bars."))

    assert first.status_code == 200, first.text
    assert first.json()["content"]["summary"] == {"added": 1}
    assert again.json()["content"]["summary"] == {"unchanged": 1}
    [event] = (await api.get("/agenda", params={"period": "month"})).json()["events"]
    assert event["links"] == [
        {
            "name": "AI · press.example",
            "url": "https://press.example/news",
            "page": "https://press.example/news",
        }
    ]


async def test_it_joins_what_already_came_from_an_agenda(api, kernel) -> None:
    await Hub(kernel).bring(leisure("Synthetic Concert", TODAY + timedelta(days=4)))
    await derive()

    said = await add(
        api, found("SYNTHETIC CONCERT", 4, category="stage", link="https://other.example/c")
    )

    assert said.json()["content"]["summary"] == {"joined": 1}
    [event] = (await api.get("/agenda", params={"period": "month"})).json()["events"]
    assert len(event["links"]) == 2


async def test_what_is_past_far_or_without_a_page_does_not_go_in(api) -> None:
    said = await add(api, found("Already past", -10), found("Far away", 500))
    no_page = await add(api, found("No page", 3, link="not an address"))

    assert said.json()["content"]["summary"] == {"dropped": 2}
    assert no_page.status_code == 422
    assert (await api.get("/agenda", params={"period": "year"})).json()["events"] == []


async def test_a_read_token_cannot_add_events(api) -> None:
    refused = await api.post(
        "/tools/add_events",
        json={"events": [found("Algo que pasa", 3)]},
        headers={"x-arga-scopes": "outings:read"},
    )

    assert refused.status_code == 403


async def test_the_prompt_has_today_the_agendas_and_the_tool(api, area) -> None:
    said = (await api.get("/agenda/prompt")).json()["prompt"]

    assert "add_events" in said and "find_events" in said and "hide_events" in said
    assert "programme" in said
    assert all(one.url in said for one in area.agendas)
    assert area.months[TODAY.month - 1] in said
    assert area.searches.always[0] in said and area.near.name in said
    assert (
        area.searches.monthly[0].format(month=area.months[TODAY.month - 1], year=TODAY.year) in said
    )


def test_every_search_of_every_area_is_filled_and_said_once(area) -> None:
    from datetime import date

    found = by_hand.searches(date(2026, 10, 3), date(2027, 1, 1), date(2027, 10, 3), area)

    assert len(found) == len(set(found))
    assert not any("{" in one or "}" in one for one in found)
    assert any(area.months[0] in one and "2027" in one for one in found)
    assert any(area.traditions[7][0] in one for one in found)


def test_it_searches_each_month_with_what_its_season_gives(area) -> None:
    from datetime import date

    found = by_hand.searches(date(2026, 10, 3), date(2027, 1, 1), area=area)

    monthly = area.searches.monthly[0]
    assert monthly.format(month=area.months[9], year=2026) in found
    assert monthly.format(month=area.months[0], year=2027) in found
    for month, year in ((10, 2026), (1, 2027)):
        for thing in area.season[month]:
            asked = area.searches.season.format(
                thing=thing, month=area.months[month - 1], year=year
            )
            assert asked in found
    assert len(found) == len(set(found))


def test_far_months_look_for_what_returns_each_year(area) -> None:
    from datetime import date

    found = by_hand.searches(date(2026, 10, 5), date(2027, 1, 3), date(2027, 10, 5), area)

    july = area.months[6]
    assert area.searches.tradition.format(thing=area.traditions[7][0], year=2027) in found
    assert area.searches.yearly[0].format(month=july, year=2027) in found
    assert area.searches.monthly[0].format(month=july, year=2027) not in found
    assert area.searches.monthly[2].format(month=area.months[10], year=2026) in found
    assert len(found) == len(set(found))


def test_the_prompt_says_the_area_what_to_add_and_what_to_skip(area) -> None:
    from datetime import date

    said = by_hand.prompt(date(2026, 10, 5), area=area)

    assert "2027-10-05" in said and f"in {by_hand.LANGUAGES[area.language]}" in said
    assert area.focus in said and area.include in said and area.skip in said
    assert area.near.name in said and area.region.name in said


async def test_there_is_no_update_with_the_api(api, hub_app) -> None:
    gone = await api.post("/agenda/refresh", json={"search": False})

    assert gone.status_code in (404, 405)
