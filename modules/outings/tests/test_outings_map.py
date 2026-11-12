from __future__ import annotations

from datetime import timedelta

from outings_world import IRATI, TODAY, Hub, derive, leisure, make_wish
from sqlalchemy import text

from outings import places, wishes
from outings.db import engine

BALUARTE = {
    "name": "Baluarte",
    "display_name": "Baluarte, Plaza del Baluarte, Pamplona, Navarra, Spain",
    "lat": "42.8136",
    "lon": "-1.6503",
    "osm_type": "way",
    "osm_id": "7",
    "addresstype": "building",
    "address": {"country_code": "es"},
}


async def locate() -> int:
    async with engine().begin() as connection:
        await connection.execute(text('set local role "mod_outings"'))
        return await places.locate(connection)


def test_a_venue_is_asked_with_its_town_and_then_the_town_alone(area) -> None:
    town, other = area.near.towns[0], area.region.towns[0]
    assert places.queries("Synthetic Hall · main", town) == [
        f"Synthetic Hall, {town}, {area.geocoding}",
        f"{town}, {area.geocoding}",
    ]
    assert places.queries(other, other) == [f"{other}, {area.geocoding}"]
    assert round(places.km((42.8136, -1.6503), (42.98, -1.17)), 0) == 43


async def test_each_venue_is_located_once_and_the_event_carries_it(api, kernel, hub) -> None:
    hub.places = [BALUARTE]
    await Hub(kernel).bring(
        leisure("Orchestra", TODAY + timedelta(days=2), venue="Baluarte · main hall"),
        leisure("Dance", TODAY + timedelta(days=3), venue="Baluarte · main hall"),
    )
    await derive()

    assert await locate() == 1
    assert await locate() == 0
    assert hub.asked == ["Baluarte, Pamplona, Navarra"]
    shown = (await api.get("/map")).json()
    assert {event["title"] for event in shown["events"]} == {"Orchestra", "Dance"}
    assert shown["events"][0]["lat"] == 42.8136


async def test_with_the_hub_down_nothing_is_written_and_it_is_tried_again(api, kernel, hub) -> None:
    hub.down = True
    await Hub(kernel).bring(leisure("Orchestra", TODAY + timedelta(days=2)))
    await derive()

    assert await locate() == 0
    hub.down = False
    hub.places = [BALUARTE]
    assert await locate() == 1


async def test_the_map_has_the_wishes_with_a_place_and_the_ones_near_an_event(
    api, kernel, hub
) -> None:
    hub.places = [BALUARTE]
    near = await make_wish(
        api,
        "Pintxos around San Nicolas",
        kind="eat",
        place={"name": "San Nicolas", "lat": 42.818, "lon": -1.644},
    )
    await make_wish(api, place=wishes.place_of(IRATI).model_dump())
    await make_wish(api, "Japan", kind="trip", place={"name": "Japan"})
    await Hub(kernel).bring(leisure("Orchestra", TODAY + timedelta(days=2)))
    await derive()
    await locate()
    [event] = (await api.get("/map")).json()["events"]

    shown = (await api.get("/map")).json()
    close = (await api.get(f"/events/{event['id']}/near")).json()

    assert {wish["name"] for wish in shown["wishes"]} == {
        "Pintxos around San Nicolas",
        "Selva de Irati",
    }
    assert [(one["id"], one["km"]) for one in close] == [(near["id"], 0.7)]
