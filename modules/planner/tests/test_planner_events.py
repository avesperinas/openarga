from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

MADRID = ZoneInfo("Europe/Madrid")


def at(text: str) -> str:
    return datetime.fromisoformat(text).replace(tzinfo=MADRID).isoformat()


async def window(api, start: str, end: str) -> list[dict]:
    response = await api.get("/occurrences", params={"from": at(start), "to": at(end)})
    assert response.status_code == 200, response.text
    return response.json()


async def create(api, **fields) -> dict:
    body = {"tz": "Europe/Madrid", **fields}
    response = await api.post("/events", json=body)
    assert response.status_code == 201, response.text
    return response.json()


def local_times(found: list[dict], title: str) -> list[str]:
    return [
        datetime.fromisoformat(o["start"]).astimezone(MADRID).strftime("%Y-%m-%d %H:%M")
        for o in found
        if o["title"] == title
    ]


async def test_a_first_look_brings_the_personal_layer(api) -> None:
    calendars = (await api.get("/calendars")).json()

    assert [(c["name"], c["tone"], c["origin"]) for c in calendars] == [("Personal", 1, "own")]


async def test_timed_and_all_day_events_show_in_their_week(api) -> None:
    await create(api, title="Dentista", start=at("2026-09-29T16:00"), end=at("2026-09-29T17:30"))
    await create(api, title="Fiesta", all_day=True, start="2026-10-01", end="2026-10-02")
    await create(api, title="Otra semana", start=at("2026-10-07T10:00"), end=at("2026-10-07T11:00"))

    found = await window(api, "2026-09-28T00:00", "2026-10-05T00:00")

    assert [o["title"] for o in found] == ["Fiesta", "Dentista"]
    fiesta = found[0]
    assert (fiesta["all_day"], fiesta["start"], fiesta["end"]) == (True, "2026-10-01", "2026-10-02")


async def test_a_weekly_series_stays_at_ten_across_the_clock_change(api) -> None:
    series = await create(
        api,
        title="Planificación",
        start=at("2026-10-19T10:00"),
        end=at("2026-10-19T10:30"),
        rrule="FREQ=WEEKLY;BYDAY=MO",
    )
    assert series["repeat"] == "cada semana, el lunes"

    found = await window(api, "2026-10-19T00:00", "2026-11-03T00:00")

    assert local_times(found, "Planificación") == [
        "2026-10-19 10:00",
        "2026-10-26 10:00",
        "2026-11-02 10:00",
    ]
    offsets = {datetime.fromisoformat(o["start"]).utcoffset().total_seconds() / 3600 for o in found}
    assert offsets == {2.0, 1.0}


async def test_just_this_one_moves_one_occurrence_and_names_it_by_where_it_was(api) -> None:
    series = await create(
        api,
        title="Inglés",
        start=at("2026-10-06T19:00"),
        end=at("2026-10-06T20:00"),
        rrule="FREQ=WEEKLY;BYDAY=TU,TH",
    )
    response = await api.patch(
        f"/events/{series['id']}",
        json={
            "changes": {"start": at("2026-10-08T18:00"), "end": at("2026-10-08T19:00")},
            "scope": "this",
            "original_start": "2026-10-08T19:00:00",
        },
    )
    assert response.status_code == 200, response.text

    found = await window(api, "2026-10-05T00:00", "2026-10-12T00:00")

    assert local_times(found, "Inglés") == ["2026-10-06 19:00", "2026-10-08 18:00"]
    moved = [o for o in found if o["moved"]]
    assert [o["original_start"] for o in moved] == ["2026-10-08T19:00:00"]


async def test_following_splits_the_series_and_keeps_a_change_already_made(api) -> None:
    series = await create(
        api,
        title="Gimnasio",
        start=at("2026-10-05T07:30"),
        end=at("2026-10-05T08:30"),
        rrule="FREQ=WEEKLY;BYDAY=MO",
    )
    await api.patch(
        f"/events/{series['id']}",
        json={
            "changes": {"start": at("2026-10-26T08:00"), "end": at("2026-10-26T09:00")},
            "scope": "this",
            "original_start": "2026-10-26T07:30:00",
        },
    )
    response = await api.patch(
        f"/events/{series['id']}",
        json={
            "changes": {"start": at("2026-10-19T18:00"), "end": at("2026-10-19T19:00")},
            "scope": "following",
            "original_start": "2026-10-19T07:30:00",
        },
    )
    assert response.status_code == 200, response.text
    tail = response.json()
    assert tail["id"] != series["id"]
    assert tail["repeat"] == "cada semana, el lunes"

    found = await window(api, "2026-10-05T00:00", "2026-11-03T00:00")

    assert local_times(found, "Gimnasio") == [
        "2026-10-05 07:30",
        "2026-10-12 07:30",
        "2026-10-19 18:00",
        "2026-10-26 08:00",
        "2026-11-02 18:00",
    ]
    head = (await api.get(f"/events/{series['id']}")).json()
    assert head["repeat"] == "cada semana, el lunes, hasta el 12 de octubre de 2026"
    after = [o for o in found if o["event_id"] == tail["id"] and o["moved"]]
    assert [o["original_start"] for o in after] == ["2026-10-26T18:00:00"]


async def test_moving_every_occurrence_to_another_day_moves_the_weekdays(api) -> None:
    series = await create(
        api,
        title="Pádel",
        start=at("2026-10-06T19:00"),
        end=at("2026-10-06T20:30"),
        rrule="FREQ=WEEKLY;BYDAY=TU",
    )
    response = await api.patch(
        f"/events/{series['id']}",
        json={
            "changes": {"start": at("2026-10-14T20:00")},
            "scope": "all",
            "original_start": "2026-10-13T19:00:00",
        },
    )
    assert response.status_code == 200, response.text
    assert response.json()["repeat"] == "cada semana, el miércoles"

    found = await window(api, "2026-10-05T00:00", "2026-10-19T00:00")

    assert local_times(found, "Pádel") == ["2026-10-07 20:00", "2026-10-14 20:00"]


async def test_cancel_this_following_and_all(api) -> None:
    series = await create(
        api,
        title="Standup",
        start=at("2026-10-05T09:00"),
        end=at("2026-10-05T09:15"),
        rrule="FREQ=DAILY",
    )
    one = await api.post(
        f"/events/{series['id']}/cancel",
        json={"scope": "this", "original_start": "2026-10-06T09:00:00"},
    )
    assert one.status_code == 200, one.text
    rest = await api.post(
        f"/events/{series['id']}/cancel",
        json={"scope": "following", "original_start": "2026-10-09T09:00:00"},
    )
    assert rest.status_code == 200, rest.text

    found = await window(api, "2026-10-05T00:00", "2026-10-12T00:00")

    assert [t[8:10] for t in local_times(found, "Standup")] == ["05", "07", "08"]

    everything = await api.post(f"/events/{series['id']}/cancel", json={"scope": "all"})
    assert everything.json()["status"] == "cancelled"
    assert local_times(await window(api, "2026-10-05T00:00", "2026-10-12T00:00"), "Standup") == []


async def test_an_all_day_yearly_series_on_the_29th_of_february(api) -> None:
    await create(
        api,
        title="Aniversario",
        all_day=True,
        start="2028-02-29",
        end="2028-03-01",
        rrule="FREQ=YEARLY;BYMONTH=2;BYMONTHDAY=29",
    )

    years = {
        year: [
            o["start"] for o in await window(api, f"{year}-01-01T00:00", f"{year + 1}-01-01T00:00")
        ]
        for year in (2028, 2029, 2032)
    }

    assert years == {2028: ["2028-02-29"], 2029: [], 2032: ["2032-02-29"]}


async def test_what_makes_no_sense_is_said(api) -> None:
    backwards = await api.post(
        "/events",
        json={
            "title": "Al revés",
            "start": at("2026-10-06T19:00"),
            "end": at("2026-10-06T18:00"),
            "tz": "Europe/Madrid",
        },
    )
    assert backwards.status_code == 422
    series = await create(
        api,
        title="Serie",
        start=at("2026-10-06T19:00"),
        end=at("2026-10-06T20:00"),
        rrule="FREQ=WEEKLY",
    )
    nowhere = await api.patch(
        f"/events/{series['id']}",
        json={"changes": {"title": "x"}, "scope": "this", "original_start": "2026-10-07T19:00:00"},
    )
    assert nowhere.status_code == 422
    assert "no es una ocurrencia" in nowhere.json()["detail"]


async def test_layers_are_created_renamed_hidden_and_ordered(api) -> None:
    personal = (await api.get("/calendars")).json()[0]
    work = (await api.post("/calendars", json={"name": "Trabajo", "tone": 5})).json()
    hidden = await api.patch(f"/calendars/{work['id']}", json={"visible": False, "name": "Oficina"})
    assert (hidden.json()["name"], hidden.json()["visible"]) == ("Oficina", False)

    ordered = (await api.put("/calendars/order", json={"ids": [work["id"], personal["id"]]})).json()

    assert [c["name"] for c in ordered] == ["Oficina", "Personal"]


async def test_search_finds_the_next_one_of_a_series_first(api) -> None:
    await create(
        api,
        title="Clase de yoga",
        start=at("2020-01-07T19:00"),
        end=at("2020-01-07T20:00"),
        rrule="FREQ=WEEKLY;BYDAY=TU",
        location="Estudio Arrieta",
    )
    await create(
        api,
        title="Cena",
        start=at("2020-02-01T21:00"),
        end=at("2020-02-01T23:00"),
        notes="traer yoga mat",
    )

    found = (await api.get("/search", params={"q": "yoga"})).json()

    assert [o["title"] for o in found] == ["Clase de yoga", "Cena"]
    assert datetime.fromisoformat(found[0]["start"]) > datetime.now(MADRID)
    assert (await api.get("/search", params={"q": "arrieta"})).json()[0]["title"] == "Clase de yoga"


async def test_every_change_goes_to_the_outbox_in_the_common_dated_shape(api, schema) -> None:
    from sqlalchemy import text

    created = await create(
        api, title="Revisión", start=at("2026-10-06T10:00"), end=at("2026-10-06T11:00")
    )
    await api.post(f"/events/{created['id']}/cancel", json={"scope": "all"})

    async with schema.begin() as connection:
        rows = (
            await connection.execute(
                text("select type, payload from planner.planner_outbox order by id")
            )
        ).all()

    assert [row.type for row in rows] == ["planner.event", "planner.event"]
    agenda = rows[-1].payload["agenda"]
    assert agenda["uid"] == f"planner:event:{created['id']}"
    assert agenda["status"] == "cancelled"
    assert agenda["href"] == f"/planner?event={created['id']}"


def test_titles_are_the_same_plan_with_or_without_details() -> None:
    from planner.calendar import similar

    assert similar("Tour por la sierra", "Tour organizado por la sierra")
    assert similar("Baños termales del centro", "Baños termales (centro)")
    assert similar("Museo: colección permanente y jardines", "Museo (colección y jardines)")
    assert not similar("Cena", "Comida")
    assert not similar("Dentista", "Peluquería")
