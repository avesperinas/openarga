from __future__ import annotations

from datetime import timedelta

from outings_world import IRATI, Hub, derive, leisure, make_wish

from arga_widgets import validate
from outings import agenda, wishes

WRITE = {"x-arga-scopes": "outings:write"}
READ = {"x-arga-scopes": "outings:read"}


async def call(api, name: str, body: dict, headers: dict = WRITE):
    return await api.post(f"/tools/{name}", json=body, headers=headers)


async def test_this_weekend_says_the_same_to_claude_and_on_the_widget(api, kernel) -> None:
    friday, sunday = agenda.window("weekend")
    await Hub(kernel).bring(
        leisure("Orquesta del finde", friday, time="20:00"),
        leisure("Feria del finde", sunday, category="festival", time="21:00"),
        leisure("Lo de después", sunday + timedelta(days=3)),
    )
    await derive()

    told = (await call(api, "find_events", {"when": "weekend"}, READ)).json()["content"]
    card = (await api.get("/widgets/weekend")).json()

    validate("upnext", card["body"], card["state"])
    assert [event["title"] for event in told["events"]] == ["Orquesta del finde", "Feria del finde"]
    assert [event["title"] for event in card["body"]["events"]] == [
        "Orquesta del finde",
        "Feria del finde",
    ]
    assert card["body"]["events"][0]["at"].endswith("+02:00") or card["body"]["events"][0][
        "at"
    ].endswith("+01:00")


async def test_note_irati_in_autumn_leaves_a_getaway_with_its_place(api, hub) -> None:
    hub.places = [
        {
            "name": "Selva de Irati",
            "display_name": "Selva de Irati, Orbaizeta, Navarra, 31671, España",
            "lat": "42.98",
            "lon": "-1.17",
            "osm_type": "way",
            "osm_id": "101",
            "addresstype": "forest",
            "address": {"country_code": "es"},
        }
    ]
    [place] = (await call(api, "find_place", {"query": "Irati"}, READ)).json()["content"][
        "candidates"
    ]

    added = await call(
        api, "add_wish", {"kind": "getaway", "name": "Irati", "text": "En otoño.", "place": place}
    )

    assert added.status_code == 200, added.text
    wish = added.json()["content"]
    assert (wish["kind"], wish["text"], wish["place"]["town"]) == (
        "getaway",
        "En otoño.",
        "Orbaizeta",
    )
    listed = (await call(api, "get_wishes", {"kind": "getaway"}, READ)).json()["content"]["wishes"]
    assert [one["name"] for one in listed] == ["Irati"]
    card = (await api.get("/widgets/wishes")).json()
    validate("list", card["body"], card["state"])
    assert card["body"]["rows"][0] == {"label": "Irati", "value": "Orbaizeta"}


async def test_a_write_with_a_read_token_is_refused_by_postgres(api) -> None:
    refused = await call(api, "add_wish", {"kind": "plan", "name": "Algo"}, READ)

    assert refused.status_code == 403


async def test_edit_done_restore_and_delete_by_exact_name(api) -> None:
    wish = await make_wish(api, place=wishes.place_of(IRATI).model_dump())

    renamed = (
        await call(api, "update_wish", {"wish_id": wish["id"], "name": "Irati en otoño"})
    ).json()["content"]
    done = (await call(api, "mark_wish_done", {"wish_id": wish["id"]})).json()["content"]
    pending = (await call(api, "get_wishes", {}, READ)).json()["content"]["wishes"]
    archived = (await call(api, "get_wishes", {"include_archived": True}, READ)).json()["content"][
        "wishes"
    ]
    back = (await call(api, "restore_wish", {"wish_id": wish["id"]})).json()["content"]
    wrong = await call(api, "delete_wish", {"wish_id": wish["id"], "name": "Irati"})
    gone = await call(api, "delete_wish", {"wish_id": wish["id"], "name": "Irati en otoño"})

    assert renamed["name"] == "Irati en otoño" and renamed["place"]["town"] == "Orbaizeta"
    assert done["done_on"] is not None and pending == [] and len(archived) == 1
    assert back["done_on"] is None
    assert wrong.status_code == 409 and wrong.json()["detail"]["code"] == "NAME_MISMATCH"
    assert gone.status_code == 200
    assert (await call(api, "get_wishes", {"include_archived": True}, READ)).json()["content"][
        "wishes"
    ] == []


async def test_save_an_event_and_send_it_to_the_calendar(api, kernel) -> None:
    await Hub(kernel).bring(leisure("Concierto", agenda.window("week")[0] + timedelta(days=2)))
    await derive()
    [event] = (await call(api, "find_events", {"when": "week"}, READ)).json()["content"]["events"]

    saved = (await call(api, "save_event", {"event_id": event["event_id"]})).json()["content"]
    sent = (await call(api, "send_to_calendar", {"event_id": event["event_id"]})).json()["content"]
    found = (await call(api, "get_event", {"event_id": event["event_id"]}, READ)).json()["content"]

    assert saved["kind"] == "plan" and saved["dates"]["from"] == event["starts_on"]
    assert sent["in_calendar"] is True
    assert found["saved_as_wish"] == saved["wish_id"] and found["links"]


async def test_an_unknown_event_is_a_404_with_its_code(api) -> None:
    missing = await call(
        api, "get_event", {"event_id": "00000000-0000-4000-8000-000000000000"}, READ
    )

    assert missing.status_code == 404 and missing.json()["detail"]["code"] == "NOT_FOUND"


async def test_find_events_also_reads_between_two_days_and_by_town(api, kernel) -> None:
    start = agenda.today() + timedelta(days=40)
    await Hub(kernel).bring(
        leisure("Concierto en Olite", start, town="Olite"),
        leisure("Concierto en Pamplona", start),
        leisure("Lo de después", start + timedelta(days=10), town="Olite"),
    )
    await derive()

    body = {
        "from": start.isoformat(),
        "to": (start + timedelta(days=2)).isoformat(),
        "town": "Olite",
    }
    told = (await call(api, "find_events", body, READ)).json()["content"]

    assert told["from"] == start.isoformat()
    assert [event["title"] for event in told["events"]] == ["Concierto en Olite"]
