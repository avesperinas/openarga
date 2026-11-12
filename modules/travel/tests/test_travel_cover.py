from __future__ import annotations

import base64
import io

from PIL import Image
from test_travel_tools import content
from travel_kit import BRUGES, make_trip, stay

from travel import covers, hub
from travel.db import engine


def photo(width: int = 2400, height: int = 1200, colour=(30, 120, 200)) -> bytes:
    out = io.BytesIO()
    Image.new("RGB", (width, height), colour).save(out, "PNG")
    return out.getvalue()


async def test_an_uploaded_cover_is_shrunk_with_its_thumbnail(api) -> None:
    trip = await make_trip(api, "Flandes", "2025-04-10", "2025-04-12")

    saved = await api.put(
        f"/trips/{trip['id']}/cover", content=photo(), headers={"content-type": "image/png"}
    )
    full = await api.get(f"/trips/{trip['id']}/cover")
    thumb = await api.get(f"/trips/{trip['id']}/cover?size=thumb")

    assert saved.status_code == 200, saved.text
    assert saved.json()["cover"]["page"] is None
    assert Image.open(io.BytesIO(full.content)).size == (1600, 800)
    assert Image.open(io.BytesIO(thumb.content)).size == (480, 240)
    assert "immutable" in full.headers["cache-control"]


async def test_something_that_is_not_a_photo_is_refused(api) -> None:
    trip = await make_trip(api, "Flandes", "2025-04-10", "2025-04-12")

    refused = await api.put(f"/trips/{trip['id']}/cover", content=b"no soy una foto")

    assert refused.status_code == 409, refused.text


async def test_the_worker_brings_the_destination_from_wikimedia_once(api, monkeypatch) -> None:
    trip = await make_trip(api, "Flandes", "2025-04-10", "2025-04-12")
    await stay(api, trip["id"], BRUGES, "2025-04-10", "2025-04-12")
    asked: list[dict] = []

    async def wikimedia(body: dict) -> dict:
        asked.append(body)
        return {
            "photo": {
                "content": base64.b64encode(photo()).decode(),
                "author": "Alguien",
                "license": "CC BY-SA 4.0",
                "page": "https://commons.wikimedia.org/wiki/File:Brujas.jpg",
            }
        }

    monkeypatch.setattr(hub, "place_photo", wikimedia)
    async with engine().begin() as connection:
        first = await covers.fill(connection)
    async with engine().begin() as connection:
        second = await covers.fill(connection)
    found = await content(api, "get_trip", {"trip_id": trip["id"]})

    assert (first, second) == (1, 0)
    assert asked[0]["name"] == "Brujas"
    assert found["cover"] == {
        "from_wikimedia": True,
        "author": "Alguien",
        "page": "https://commons.wikimedia.org/wiki/File:Brujas.jpg",
    }


async def test_removing_the_cover_does_not_bring_it_back(api, monkeypatch) -> None:
    trip = await make_trip(api, "Flandes", "2025-04-10", "2025-04-12")
    await stay(api, trip["id"], BRUGES, "2025-04-10", "2025-04-12")
    await api.put(f"/trips/{trip['id']}/cover", content=photo())

    async def wikimedia(body: dict) -> dict:
        raise AssertionError("no se vuelve a buscar")

    monkeypatch.setattr(hub, "place_photo", wikimedia)
    removed = await api.delete(f"/trips/{trip['id']}/cover")
    async with engine().begin() as connection:
        placed = await covers.fill(connection)

    assert removed.json()["cover"] is None
    assert placed == 0


async def test_the_summary_is_written_by_claude_and_kept_by_the_app(api) -> None:
    created = await content(
        api,
        "create_trip",
        {
            "title": "Budapest",
            "starts_on": "2027-11-11",
            "ends_on": "2027-11-14",
            "status": "plan",
            "summary": "Cuatro días: termas, ruin bars y el Danubio de noche.",
        },
    )
    trip_id = created["trip"]["trip_id"]
    edited = await api.put(
        f"/trips/{trip_id}",
        json={"title": "Budapest", "starts_on": "2027-11-11", "ends_on": "2027-11-15"},
    )
    changed = await content(
        api, "update_trip", {"trip_id": trip_id, "summary": "Cinco días.", "dry_run": False}
    )

    assert edited.json()["summary"] == "Cuatro días: termas, ruin bars y el Danubio de noche."
    assert changed["trip"]["summary"] == "Cinco días."
