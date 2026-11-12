from __future__ import annotations

BRUGES = {"name": "Brujas", "lat": 51.2085, "lon": 3.2267, "osm_type": "relation", "osm_id": 1}
GHENT = {"name": "Gante", "lat": 51.0543, "lon": 3.7174, "osm_type": "relation", "osm_id": 2}
LILLE = {"name": "Lille", "lat": 50.6292, "lon": 3.0573, "osm_type": "relation", "osm_id": 3}
MADRID = {"name": "Madrid", "lat": 40.4168, "lon": -3.7038, "osm_type": "relation", "osm_id": 4}
SEVILLE = {"name": "Sevilla", "lat": 37.389, "lon": -5.984, "osm_type": "relation", "osm_id": 5}


async def make_trip(api, title="Flandes", starts="2025-04-10", ends="2025-04-15", **extra) -> dict:
    response = await api.post(
        "/trips", json={"title": title, "starts_on": starts, "ends_on": ends, **extra}
    )
    assert response.status_code == 201, response.text
    return response.json()


async def place(api, candidate: dict) -> dict:
    response = await api.post("/places", json=candidate)
    assert response.status_code == 201, response.text
    return response.json()


async def stay(api, trip_id: str, candidate: dict, arrives: str, leaves: str) -> dict:
    found = await place(api, candidate)
    response = await api.post(
        f"/trips/{trip_id}/stays",
        json={"place_id": found["id"], "arrives_on": arrives, "leaves_on": leaves},
    )
    assert response.status_code == 201, response.text
    return response.json()
