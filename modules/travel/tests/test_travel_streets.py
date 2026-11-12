from __future__ import annotations

from sqlalchemy import text
from travel_kit import make_trip, place

PAMPLONA = {"name": "Pamplona", "lat": 42.8169, "lon": -1.6436, "osm_type": "relation", "osm_id": 9}
CITADEL = {"name": "Ciudadela", "lat": 42.8125, "lon": -1.6510, "osm_type": "way", "osm_id": 10}
TACONERA = {"name": "Taconera", "lat": 42.8186, "lon": -1.6497, "osm_type": "way", "osm_id": 11}


async def test_a_tile_comes_through_the_hub_once_and_then_from_travel(api, hub, schema) -> None:
    first = await api.get("/tiles/9/253/188")
    asked = hub.tiles_asked
    again = await api.get("/tiles/9/253/188")

    assert first.status_code == 200, first.text
    assert first.headers["content-type"] == "application/x-protobuf"
    assert len(first.content) == 344_760
    assert again.content == first.content
    assert hub.tiles_asked == asked
    async with schema.connect() as connection:
        saved = await connection.scalar(text("select count(*) from travel.travel_tile"))
    assert saved == 1


async def test_nothing_there_is_204_and_the_hub_down_is_503_and_not_kept(api, hub, schema) -> None:
    sea = await api.get("/tiles/9/100/100")
    hub.down = True
    down = await api.get("/tiles/9/252/188")
    hub.down = False
    back = await api.get("/tiles/9/252/188")

    assert sea.status_code == 204
    assert down.status_code == 503
    assert back.status_code == 200
    assert (await api.get("/tiles/3/9/0")).status_code == 404


async def test_the_day_route_goes_from_where_you_slept_through_what_you_do(api, hub) -> None:
    trip = await make_trip(api, "Sanfermines", "2026-07-06", "2026-07-08")
    hotel = await place(api, PAMPLONA)
    citadel = await place(api, CITADEL)
    taconera = await place(api, TACONERA)
    await api.post(
        f"/trips/{trip['id']}/stays",
        json={"place_id": hotel["id"], "arrives_on": "2026-07-06", "leaves_on": "2026-07-08"},
    )
    for title, found in (("Ciudadela", citadel), ("Taconera", taconera)):
        await api.post(
            f"/trips/{trip['id']}/blocks",
            json={"title": title, "day": "2026-07-07", "place_id": found["id"]},
        )
    await api.post(f"/trips/{trip['id']}/blocks", json={"title": "Siesta", "day": "2026-07-07"})

    walk = await api.get(f"/trips/{trip['id']}/days/2026-07-07/route")
    lone = await api.get(f"/trips/{trip['id']}/days/2026-07-08/route?profile=car")

    route = walk.json()
    assert walk.status_code == 200, walk.text
    assert [(s["type"], s["number"], s["title"]) for s in route["stops"]] == [
        ("stay", None, "Pamplona"),
        ("block", 1, "Ciudadela"),
        ("block", 2, "Taconera"),
        ("stay", None, "Pamplona"),
    ]
    assert (route["distance_m"], route["duration_s"], len(route["legs"])) == (1800, 1350, 3)
    assert route["line"][0] == [-1.6436, 42.8169]
    assert hub.routes == [hub.routes[0]] and hub.routes[0].startswith("/routed-foot/")
    assert lone.json()["stops"][0]["title"] == "Pamplona"
    assert lone.json()["line"] is None and lone.json()["failed"] is None
