from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import yaml

from arga_widgets import validate

MANIFEST = Path(__file__).resolve().parents[1] / "manifest.yaml"
READ = {"x-arga-scopes": "planner:read"}
WRITE = {"x-arga-scopes": "planner:read planner:write"}
MADRID = ZoneInfo("Europe/Madrid")


async def content(api, name: str, arguments: dict, headers: dict = WRITE) -> dict:
    response = await api.post(f"/tools/{name}", json=arguments, headers=headers)
    assert response.status_code == 200, response.text
    return response.json()["content"]


async def test_the_listed_tools_are_the_ones_the_manifest_declares(api) -> None:
    manifest = yaml.safe_load(MANIFEST.read_text())
    served = (await api.get("/tools")).json()

    assert {tool["name"] for tool in served} == {tool["name"] for tool in manifest["tools"]}
    assert len(served) == 10


async def test_the_repeat_is_an_object_not_rrule_text(api) -> None:
    schema = next(t for t in (await api.get("/tools")).json() if t["name"] == "create_event")
    text = str(schema["input_schema"])

    assert "by_day" in text and "freq" in text
    assert "rrule" not in text.lower().replace("repeat", "")


async def test_claude_creates_an_english_class_on_tuesdays_and_thursdays_until_june(api) -> None:
    created = await content(
        api,
        "create_event",
        {
            "title": "English class",
            "start": "2026-10-06T19:00",
            "end": "2026-10-06T20:00",
            "repeat": {
                "freq": "weekly",
                "by_day": [{"weekday": "TU"}, {"weekday": "TH"}],
                "until": "2027-06-30",
            },
        },
    )

    event = created["created"]
    assert event["repeat"] == "cada semana, martes y jueves, hasta el 30 de junio de 2027"
    assert event["calendar"] == "Personal"
    assert datetime.fromisoformat(event["start"]).astimezone(MADRID).hour == 19

    week = await content(api, "get_events", {"from": "2026-10-05", "to": "2026-10-12"}, READ)
    assert [e["start"][:16] for e in week["events"]] == ["2026-10-06T19:00", "2026-10-08T19:00"]
    assert all(e["original_start"] for e in week["events"])


async def test_claude_moves_one_class_and_cancels_the_rest(api) -> None:
    created = (
        await content(
            api,
            "create_event",
            {"title": "Tutorial", "start": "2026-10-07T10:00", "repeat": {"freq": "weekly"}},
        )
    )["created"]
    await content(
        api,
        "update_event",
        {
            "event_id": created["event_id"],
            "scope": "this",
            "original_start": "2026-10-14T10:00:00",
            "start": "2026-10-14T12:00",
            "location": "Despacho 2",
        },
    )
    await content(
        api,
        "cancel_event",
        {
            "event_id": created["event_id"],
            "scope": "following",
            "original_start": "2026-10-21T10:00:00",
        },
    )

    found = await content(api, "get_events", {"from": "2026-10-05", "to": "2026-11-05"}, READ)

    assert [(e["start"][:16], e.get("location")) for e in found["events"]] == [
        ("2026-10-07T10:00", None),
        ("2026-10-14T12:00", "Despacho 2"),
    ]


async def test_a_layer_by_its_name_and_an_all_day_span_that_includes_its_last_day(api) -> None:
    await api.post("/calendars", json={"name": "Viajes", "tone": 6})
    created = (
        await content(
            api,
            "create_event",
            {
                "title": "Lisboa",
                "start": "2026-10-01",
                "end": "2026-10-04",
                "all_day": True,
                "calendar": "viajes",
            },
        )
    )["created"]

    assert (created["calendar"], created["start"], created["end"]) == (
        "Viajes",
        "2026-10-01",
        "2026-10-05",
    )
    wrong = await content(
        api, "create_event", {"title": "x", "start": "2026-10-01", "calendar": "Nothing"}
    )
    assert "there is no layer “Nothing”" in wrong["error"]


async def test_find_and_the_reader_cannot_write(api) -> None:
    await content(
        api,
        "create_event",
        {"title": "Dentist", "start": "2026-11-03T16:00", "location": "Main Street"},
    )

    found = await content(api, "get_events", {"query": "main"}, READ)
    assert [e["title"] for e in found["events"]] == ["Dentist"]
    window = {"query": "main", "from": "2026-12-01", "to": "2026-12-31"}
    assert (await content(api, "get_events", window, READ))["events"] == []
    assert "`from` and `to` are needed" in (await content(api, "get_events", {}, READ))["error"]
    mixed = {"query": "main", "calendars": ["Personal"]}
    assert "is not valid with `query`" in (await content(api, "get_events", mixed, READ))["error"]

    denied = await api.post(
        "/tools/create_event", json={"title": "x", "start": "2026-11-03T16:00"}, headers=READ
    )
    assert denied.status_code == 403
    nobody = await api.post(
        "/tools/get_calendars", json={}, headers={"x-arga-scopes": "shopping:read"}
    )
    assert nobody.status_code == 403


async def test_the_widgets_answer_their_envelope(api) -> None:
    await api.get("/calendars")
    for widget, kind in (
        ("upnext", "upnext"),
        ("calendar", "calendar"),
        ("today", "agenda"),
        ("week", "week"),
    ):
        response = await api.get(f"/widgets/{widget}")
        assert response.status_code == 200, response.text
        envelope = response.json()
        validate(kind, envelope.get("body") or {}, envelope["state"])

    soon = (datetime.now(MADRID) + timedelta(days=2)).strftime("%Y-%m-%dT09:00")
    await content(api, "create_event", {"title": "Tomorrow", "start": soon})
    upnext = (await api.get("/widgets/upnext")).json()
    assert upnext["state"] == "ready"
    assert upnext["body"]["events"][0]["title"] == "Tomorrow"


async def test_the_agenda_says_what_there_is_with_its_hour_and_its_layer(api) -> None:
    personal = (await api.get("/calendars")).json()[0]
    soon = (datetime.now(MADRID) + timedelta(days=1)).date()
    await content(
        api,
        "create_event",
        {"title": "Dentist", "start": f"{soon}T10:00", "end": f"{soon}T11:00", "location": "Sur"},
    )
    await content(api, "create_event", {"title": "Trip", "start": str(soon), "all_day": True})

    for widget in ("today", "week"):
        body = (await api.get(f"/widgets/{widget}")).json()["body"]
        dentist = next(e for e in body["entries"] if e["title"] == "Dentist")
        assert dentist["tone"] == personal["tone"]
        assert dentist["detail"] == "Sur"
        assert dentist["start"].startswith(f"{soon}T10:00")
        trip = next(e for e in body["entries"] if e["title"] == "Trip")
        assert trip["all_day"] is True
        assert trip["start"] == str(soon)

    if soon.month == datetime.now(MADRID).month:
        month = (await api.get("/widgets/calendar")).json()["body"]
        assert {e["title"] for e in month["entries"]} >= {"Dentist", "Trip"}
        assert soon.day in month["marked"]


async def test_a_background_layer_is_the_frame_and_not_what_takes_the_time(api) -> None:
    personal = (await api.get("/calendars")).json()[0]
    work = (
        await api.post("/calendars", json={"name": "Horario", "tone": 2, "display": "background"})
    ).json()
    assert work["display"] == "background"
    await api.put("/calendars/order", json={"ids": [work["id"], personal["id"]]})

    soon = (datetime.now(MADRID) + timedelta(days=2)).date()
    await content(
        api,
        "create_event",
        {
            "title": "Jornada",
            "start": f"{soon}T08:00",
            "end": f"{soon}T17:00",
            "calendar": "Horario",
            "repeat": {"freq": "daily"},
        },
    )
    meeting = (await content(api, "create_event", {"title": "Review", "start": f"{soon}T10:00"}))[
        "created"
    ]
    assert meeting["calendar"] == "Personal"

    day = await content(
        api, "get_events", {"from": str(soon), "to": str(soon + timedelta(days=1))}, READ
    )
    assert [e["title"] for e in day["events"]] == ["Review"]
    assert day["count"] == 1
    assert [(e["title"], e["calendar"]) for e in day["backgrounds"]] == [("Jornada", "Horario")]

    layers = (await content(api, "get_calendars", {}, READ))["calendars"]
    assert {c["name"]: c["display"] for c in layers} == {
        "Horario": "background",
        "Personal": "events",
    }

    upnext = (await api.get("/widgets/upnext")).json()
    assert [e["title"] for e in upnext["body"]["events"]] == ["Review"]

    back = await api.patch(f"/calendars/{work['id']}", json={"display": "events"})
    assert back.json()["display"] == "events"
    day = await content(
        api, "get_events", {"from": str(soon), "to": str(soon + timedelta(days=1))}, READ
    )
    assert "backgrounds" not in day
    assert day["count"] == 2


async def test_a_display_that_does_not_exist_is_said(api) -> None:
    await api.get("/calendars")
    wrong = await api.post("/calendars", json={"name": "Raro", "tone": 2, "display": "stripes"})
    assert wrong.status_code == 422


async def test_creating_what_already_is_in_another_layer_warns_without_refusing(api) -> None:
    for name, tone in (("Trip", 5), ("Personal", 1)):
        made = await api.post("/calendars", json={"name": name, "tone": tone})
        assert made.status_code == 201, made.text
    first = await content(
        api,
        "create_event",
        {
            "title": "Museum: permanent collection and gardens",
            "start": "2027-01-16T09:00",
            "end": "2027-01-16T13:30",
            "calendar": "Trip",
        },
    )
    assert "duplicates" not in first
    again = await content(
        api,
        "create_event",
        {
            "title": "Museum (collection and gardens)",
            "start": "2027-01-16T09:00",
            "end": "2027-01-16T13:30",
            "calendar": "Personal",
        },
    )
    assert again["created"]["calendar"] == "Personal"
    assert [(one["title"], one["calendar"]) for one in again["duplicates"]] == [
        ("Museum: permanent collection and gardens", "Trip")
    ]

    other_time = await content(
        api,
        "create_event",
        {
            "title": "Museo",
            "start": "2027-01-16T16:00",
            "end": "2027-01-16T17:00",
            "calendar": "Personal",
        },
    )
    assert "duplicates" not in other_time
    other_title = await content(
        api,
        "create_event",
        {
            "title": "Lunch",
            "start": "2027-01-16T09:00",
            "end": "2027-01-16T13:30",
            "calendar": "Personal",
        },
    )
    assert "duplicates" not in other_title
