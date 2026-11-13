from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

import test_planner_subscriptions as subscriptions
from test_planner_subscriptions import CONNECTION, HOLIDAY, Hub

kernel = subscriptions.kernel
migrated = subscriptions.migrated

MADRID = ZoneInfo("Europe/Madrid")
WEEK = {"from": "2026-10-05T00:00:00+02:00", "to": "2026-10-19T00:00:00+02:00"}
READ = {"x-arga-scopes": "planner:read"}


def at(local: str) -> str:
    return datetime.fromisoformat(local).replace(tzinfo=MADRID).isoformat()


async def layer(api, name: str, display: str = "events", **extra) -> dict:
    response = await api.post(
        "/calendars", json={"name": name, "tone": 3, "display": display, **extra}
    )
    assert response.status_code == 201, response.text
    return response.json()


async def event(api, calendar_id: str, title: str, start: str, end: str, **extra) -> dict:
    response = await api.post(
        "/events",
        json={
            "calendar_id": calendar_id,
            "title": title,
            "start": start,
            "end": end,
            "tz": "Europe/Madrid",
            **extra,
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


async def work_days(api, calendar_id: str) -> list[str]:
    response = await api.get("/occurrences", params=WEEK)
    assert response.status_code == 200, response.text
    return [
        datetime.fromisoformat(one["start"]).astimezone(MADRID).date().isoformat()
        for one in response.json()
        if one["calendar_id"] == calendar_id
    ]


async def subscribed_holidays(api, kernel) -> dict:
    await Hub(kernel).run({"h1": HOLIDAY}, label="Festivos de prueba")
    layers = (await api.get("/calendars")).json()
    return next(one for one in layers if one["connection_id"] == CONNECTION)


async def workweek(api) -> tuple[dict, dict]:
    work = await layer(api, "Trabajo", "background")
    series = await event(
        api,
        work["id"],
        "Jornada",
        at("2026-10-05T08:30"),
        at("2026-10-05T18:00"),
        rrule="FREQ=WEEKLY;BYDAY=MO,TU,WE,TH,FR",
    )
    return work, series


EVERY_DAY = [
    "2026-10-05",
    "2026-10-06",
    "2026-10-07",
    "2026-10-08",
    "2026-10-09",
    "2026-10-12",
    "2026-10-13",
    "2026-10-14",
    "2026-10-15",
    "2026-10-16",
]


async def test_work_does_not_show_on_a_subscribed_holiday(api, kernel) -> None:
    holidays = await subscribed_holidays(api, kernel)
    work, _ = await workweek(api)
    assert work["days_off_from"] == []
    assert await work_days(api, work["id"]) == EVERY_DAY

    changed = await api.patch(f"/calendars/{work['id']}", json={"days_off_from": [holidays["id"]]})

    assert changed.status_code == 200, changed.text
    assert changed.json()["days_off_from"] == [holidays["id"]]
    assert "2026-10-12" not in await work_days(api, work["id"])
    assert len(await work_days(api, work["id"])) == len(EVERY_DAY) - 1


async def test_the_local_ones_go_in_a_layer_of_your_own(api, kernel) -> None:
    holidays = await subscribed_holidays(api, kernel)
    local = await layer(api, "Festivos locales")
    await event(
        api, local["id"], "Local test holiday", "2026-10-15", "2026-10-16", all_day=True
    )
    work, _ = await workweek(api)

    await api.patch(
        f"/calendars/{work['id']}", json={"days_off_from": [holidays["id"], local["id"]]}
    )

    days = await work_days(api, work["id"])
    assert "2026-10-12" not in days and "2026-10-15" not in days
    assert len(days) == len(EVERY_DAY) - 2


async def test_a_week_of_holidays_frees_each_of_its_days(api) -> None:
    holidays = await layer(api, "Vacaciones")
    await event(api, holidays["id"], "Vacaciones", "2026-10-13", "2026-10-16", all_day=True)
    await event(api, holidays["id"], "Doctor", at("2026-10-06T09:00"), at("2026-10-06T10:00"))
    work = await layer(api, "Trabajo", "background", days_off_from=[holidays["id"]])
    await event(
        api,
        work["id"],
        "Jornada",
        at("2026-10-05T08:30"),
        at("2026-10-05T18:00"),
        rrule="FREQ=WEEKLY;BYDAY=MO,TU,WE,TH,FR",
    )

    assert await work_days(api, work["id"]) == [
        "2026-10-05",
        "2026-10-06",
        "2026-10-07",
        "2026-10-08",
        "2026-10-09",
        "2026-10-12",
        "2026-10-16",
    ]


async def test_what_you_put_on_that_day_by_hand_does_show(api, kernel) -> None:
    holidays = await subscribed_holidays(api, kernel)
    work, series = await workweek(api)
    await api.patch(f"/calendars/{work['id']}", json={"days_off_from": [holidays["id"]]})
    await event(api, work["id"], "Guardia", at("2026-10-12T09:00"), at("2026-10-12T14:00"))
    moved = await api.patch(
        f"/events/{series['id']}",
        json={
            "changes": {"start": at("2026-10-12T15:00"), "end": at("2026-10-12T18:00")},
            "scope": "this",
            "original_start": "2026-10-13T08:30:00",
        },
    )
    assert moved.status_code == 200, moved.text

    found = (await api.get("/occurrences", params=WEEK)).json()
    monday = [
        (one["title"], datetime.fromisoformat(one["start"]).astimezone(MADRID).hour)
        for one in found
        if one["calendar_id"] == work["id"] and one["start"].startswith("2026-10-12")
    ]
    assert sorted(monday) == [("Guardia", 9), ("Jornada", 15)]


async def test_hiding_the_layer_is_not_working_on_holidays_but_hiding_one_is(api, kernel) -> None:
    holidays = await subscribed_holidays(api, kernel)
    work, _ = await workweek(api)
    await api.patch(f"/calendars/{work['id']}", json={"days_off_from": [holidays["id"]]})

    await api.patch(f"/calendars/{holidays['id']}", json={"visible": False})
    assert "2026-10-12" not in await work_days(api, work["id"])

    found = (await api.get("/occurrences", params=WEEK)).json()
    [holiday] = [one for one in found if one["calendar_id"] == holidays["id"]]
    hidden = await api.post(f"/feed/{holiday['id'].removeprefix('feed:')}/hide")
    assert hidden.status_code == 204, hidden.text
    assert "2026-10-12" in await work_days(api, work["id"])


async def test_claude_sees_it_the_same_with_the_read_role(api, kernel) -> None:
    holidays = await subscribed_holidays(api, kernel)
    work, _ = await workweek(api)
    await api.patch(f"/calendars/{work['id']}", json={"days_off_from": [holidays["id"]]})

    response = await api.post(
        "/tools/get_events",
        json={"from": "2026-10-12", "to": "2026-10-14", "calendars": ["Trabajo"]},
        headers=READ,
    )
    assert response.status_code == 200, response.text
    day = response.json()["content"]
    assert [one["start"][:10] for one in day["backgrounds"]] == ["2026-10-13"]

    response = await api.post("/tools/get_calendars", json={}, headers=READ)
    layers = {one["name"]: one for one in response.json()["content"]["calendars"]}
    assert layers["Trabajo"]["days_off_from"] == ["Festivos de prueba"]
    assert "days_off_from" not in layers["Festivos de prueba"]


async def test_what_cannot_free_a_day_is_said(api, kernel) -> None:
    holidays = await subscribed_holidays(api, kernel)
    work, _ = await workweek(api)

    itself = await api.patch(f"/calendars/{work['id']}", json={"days_off_from": [work["id"]]})
    assert itself.status_code == 422
    nowhere = await api.patch(
        f"/calendars/{work['id']}",
        json={"days_off_from": ["00000000-0000-4000-8000-000000000000"]},
    )
    assert nowhere.status_code == 404
    subscribed = await api.patch(
        f"/calendars/{holidays['id']}", json={"days_off_from": [work["id"]]}
    )
    assert subscribed.status_code == 422
    assert (await api.get("/calendars")).json()[0]["days_off_from"] == []
