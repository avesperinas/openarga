from __future__ import annotations

from datetime import timedelta

from outings_world import TODAY

from outings import profile

WRITE = {"x-arga-scopes": "outings:write"}
READ = {"x-arga-scopes": "outings:read"}


def found(title: str, days: int, town: str = "Pamplona", **extra) -> dict:
    return {
        "title": title,
        "starts_on": (TODAY + timedelta(days=days)).isoformat(),
        "category": "stage",
        "town": town,
        "link": "https://press.example/news",
        **extra,
    }


async def add(api, *events: dict) -> list[str]:
    said = await api.post("/tools/add_events", json={"events": list(events)}, headers=WRITE)
    assert said.status_code == 200, said.text
    return [one["event_id"] for one in said.json()["content"]["events"]]


async def explore(api, **params) -> dict:
    got = await api.get("/explore", params=params)
    assert got.status_code == 200, got.text
    return got.json()


def titles(answer: dict) -> list[str]:
    return [one["title"] for one in answer["events"]]


def test_the_zone_is_near_for_the_core_towns_and_region_for_the_rest(area) -> None:
    assert all(area.zone(town) == "near" for town in area.near.towns)
    assert all(area.zone(town) == "region" for town in area.region.towns)
    assert area.zone(f"{area.near.towns[0]} centro") == "near"
    assert area.zone(None) == "region"


def test_a_town_is_known_with_or_without_accents_or_capitals(area) -> None:
    for town in area.near.towns:
        assert area.zone(town.upper()) == "near"
        assert area.zone(profile.fold(town)) == "near"


def test_an_unknown_area_falls_back_to_the_default() -> None:
    assert profile.resolve("Munich") == "munich"
    assert profile.resolve("atlantis") == profile.DEFAULT
    assert profile.resolve(None) == profile.DEFAULT


async def test_a_festival_is_one_event_with_its_programme(api, area) -> None:
    [event_id] = await add(
        api,
        found(
            "Synthetic Vegetable Fiesta",
            4,
            town="Synthetic Village",
            category="eat",
            ends_on=(TODAY + timedelta(days=6)).isoformat(),
            programme=["Sat, 12:00 · Omelette contest", "Sun, 13:00 · Tasting"],
            highlight=True,
        ),
    )

    event = (await api.get(f"/events/{event_id}")).json()
    assert event["programme"] == [
        "Sat, 12:00 · Omelette contest",
        "Sun, 13:00 · Tasting",
    ]
    assert event["highlight"] is True and event["zone"] == "region"
    assert titles(await explore(api, q="omelette")) == ["Synthetic Vegetable Fiesta"]


async def test_the_search_ignores_accents_and_takes_the_start_of_words(api) -> None:
    await add(
        api,
        found("Synthetic Organ Concert at the Ölberg", 3, venue="Cathedral"),
        found("Synthetic Croquette Week", 5, category="eat"),
    )

    assert titles(await explore(api, q="olberg")) == ["Synthetic Organ Concert at the Ölberg"]
    assert titles(await explore(api, q="CROQ")) == ["Synthetic Croquette Week"]
    assert titles(await explore(api, q="cathedral organ")) == [
        "Synthetic Organ Concert at the Ölberg"
    ]
    assert titles(await explore(api, q="nothing alike")) == []


async def test_since_keeps_only_what_arrived_from_that_day(api) -> None:
    from sqlalchemy import text

    from outings.main import as_app

    old_one, new_one = found("Old synthetic concert", 3), found("New synthetic concert", 4)
    [old, new] = await add(api, old_one, new_one)
    async with as_app() as connection:
        await connection.execute(
            text(
                "update outings.outings_event set first_seen = now() - interval '10 days'"
                " where id = cast(:id as uuid)"
            ),
            {"id": old},
        )
        madrid = text("select (now() at time zone 'Europe/Madrid')::date")
        today = (await connection.execute(madrid)).scalar_one()

    fresh = await explore(api, since=(today - timedelta(days=2)).isoformat(), sort="best")
    assert titles(fresh) == ["New synthetic concert"]
    assert fresh["events"][0]["id"] == new
    everything = set(titles(await explore(api)))
    assert everything >= {"Old synthetic concert", "New synthetic concert"}


async def test_best_puts_the_near_area_and_what_is_big_first(api, area) -> None:
    here = area.near.towns[0]
    await add(
        api,
        found("Far and small", 2, town=area.region.towns[0]),
        found("Far and big", 3, town=area.region.towns[1], highlight=True),
        found("Here and small", 4, town=here),
        found("Here and big", 5, town=here, highlight=True),
    )

    best = await explore(api, sort="best")
    assert titles(best) == ["Here and big", "Far and big", "Here and small", "Far and small"]
    by_date = await explore(api)
    assert titles(by_date)[0] == "Far and small"
    assert titles(await explore(api, zone="near")) == ["Here and small", "Here and big"]
    assert titles(await explore(api, zone="region")) == ["Far and small", "Far and big"]


async def test_what_you_like_goes_up(api) -> None:
    await add(api, found("Synthetic Jazz Concert", 9), found("Another Synthetic Thing", 2))
    await api.post("/interests", json={"kind": "like", "term": "Jazz"})

    assert titles(await explore(api, sort="best"))[0] == "Synthetic Jazz Concert"
    assert "Jazz" in (await api.get("/agenda/prompt")).json()["prompt"]


async def test_dismissed_and_muted_do_not_show_unless_they_are_yours(api) -> None:
    dismissed, muted, kept, saved = await add(
        api,
        found("Synthetic Leaders Congress", 2),
        found("Synthetic Talk at Hall X", 3, venue="Hall X"),
        found("Synthetic Concert", 4),
        found("Synthetic Recital at Hall X", 5, venue="Hall X"),
    )
    await api.post(f"/events/{saved}/save")
    hid = await api.post("/tools/hide_events", json={"event_ids": [dismissed]}, headers=WRITE)
    assert hid.json()["content"] == {"hidden": 1, "not_found": []}
    added = await api.post(
        "/tools/add_interest", json={"kind": "mute", "term": "hall x"}, headers=WRITE
    )
    assert added.status_code == 200, added.text

    assert set(titles(await explore(api))) == {
        "Synthetic Concert",
        "Synthetic Recital at Hall X",
    }
    week = (await api.post("/tools/find_events", json={"when": "week"}, headers=READ)).json()
    assert {one["event_id"] for one in week["content"]["events"]} == {kept, saved}
    await add(api, found("Synthetic Leaders Congress", 2, summary="Another version."))
    assert dismissed not in {one["id"] for one in (await explore(api))["events"]}
    await api.put(f"/events/{dismissed}/dismiss", params={"on": "false"})
    await api.post("/tools/remove_interest", json={"kind": "mute", "term": "Hall X"}, headers=WRITE)
    assert len((await explore(api))["events"]) == 4
    assert muted in {one["id"] for one in (await explore(api))["events"]}


async def test_mine_is_only_what_you_saved_or_sent_to_planner(api) -> None:
    saved, sent, _other = await add(
        api, found("Synthetic Saved", 3), found("Synthetic In Planner", 6), found("Other", 8)
    )
    await api.post(f"/events/{saved}/save")
    await api.put(f"/events/{sent}/calendar", params={"on": "true"})

    got = await api.get(
        "/mine",
        params={"from": TODAY.isoformat(), "to": (TODAY + timedelta(days=30)).isoformat()},
    )

    assert got.status_code == 200, got.text
    assert [one["id"] for one in got.json()["events"]] == [saved, sent]


async def test_find_events_and_the_brief_are_tools_for_the_ai(api, area) -> None:
    await add(api, found("Synthetic Film Festival", 20, town=area.near.towns[1], highlight=True))
    await api.post("/interests", json={"kind": "mute", "term": "conference"})

    got = await api.post(
        "/tools/find_events", json={"query": "film", "when": "quarter"}, headers=READ
    )
    brief = await api.post("/tools/get_agenda_brief", json={}, headers=READ)

    [event] = got.json()["content"]["events"]
    assert event["title"] == "Synthetic Film Festival" and event["highlight"] is True
    assert event["zone"] == "near"
    said = brief.json()["content"]["brief"]
    assert "add_events" in said and "conference" in said and area.agendas[0].url in said


async def test_interests_are_listed_and_not_repeated(api) -> None:
    await api.post("/interests", json={"kind": "like", "term": "Jazz"})
    await api.post("/interests", json={"kind": "like", "term": "jazz"})
    listed = (await api.get("/interests")).json()

    assert [(one["kind"], one["term"]) for one in listed] == [("like", "jazz")]
    removed = await api.delete(f"/interests/{listed[0]['id']}")
    assert removed.status_code == 200
    assert (await api.get("/interests")).json() == []
