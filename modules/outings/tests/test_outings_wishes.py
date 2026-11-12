from __future__ import annotations

import io

from outings_world import BARDENAS, IRATI, jpeg, make_wish
from PIL import Image

from outings import wishes


async def test_a_getaway_is_noted_with_its_place_and_listed_first(api) -> None:
    place = wishes.place_of(IRATI).model_dump()
    first = await make_wish(api, "Bardenas", place=wishes.place_of(BARDENAS).model_dump())
    second = await make_wish(
        api, "Selva de Irati", body="En noviembre, el hayedo rojo.", place=place
    )

    listed = (await api.get("/wishes")).json()

    assert [one["id"] for one in listed] == [second["id"], first["id"]]
    assert second["place"] == {
        "name": "Selva de Irati",
        "detail": "Orbaizeta, Navarra",
        "town": "Orbaizeta",
        "country": "España",
        "country_code": "ES",
        "lat": 42.98,
        "lon": -1.17,
        "osm_ref": "way/101",
    }
    assert second["body"] == "En noviembre, el hayedo rojo."
    assert second["has_photo"] is False and second["done_at"] is None


async def test_a_trip_can_be_just_a_name_and_saving_without_place_works(api) -> None:
    trip = await make_wish(api, "Japón", kind="trip", place={"name": "Japón"})
    bare = await make_wish(api, "Pintxos por San Nicolás", kind="eat")

    assert trip["place"]["name"] == "Japón" and trip["place"]["lat"] is None
    assert bare["place"] is None


async def test_by_kind(api) -> None:
    await make_wish(api, "Bardenas")
    eat = await make_wish(api, "Asador en la Ribera", kind="eat")

    listed = (await api.get("/wishes", params={"kind": "eat"})).json()

    assert [one["id"] for one in listed] == [eat["id"]]


async def test_done_goes_to_the_archive_and_comes_back(api) -> None:
    wish = await make_wish(api)

    done = (await api.post(f"/wishes/{wish['id']}/done")).json()
    pending = (await api.get("/wishes")).json()
    archive = (await api.get("/wishes", params={"archived": "true"})).json()

    assert done["done_at"] is not None
    assert pending == []
    assert [one["id"] for one in archive] == [wish["id"]]

    back = (await api.post(f"/wishes/{wish['id']}/restore")).json()
    assert back["done_at"] is None
    assert [one["id"] for one in (await api.get("/wishes")).json()] == [wish["id"]]


async def test_patch_overwrites_what_it_sends_and_nothing_else(api) -> None:
    wish = await make_wish(api, body="Ruta del Cubo.", place=wishes.place_of(IRATI).model_dump())

    renamed = (await api.patch(f"/wishes/{wish['id']}", json={"name": "Irati en otoño"})).json()
    cleared = (await api.patch(f"/wishes/{wish['id']}", json={"place": None, "body": None})).json()

    assert renamed["name"] == "Irati en otoño" and renamed["body"] == "Ruta del Cubo."
    assert renamed["place"]["name"] == "Selva de Irati"
    assert (
        cleared["name"] == "Irati en otoño" and cleared["place"] is None and cleared["body"] is None
    )


async def test_an_empty_name_is_refused(api) -> None:
    response = await api.post("/wishes", json={"kind": "plan", "name": "   "})

    assert response.status_code == 422


async def test_the_photo_is_shrunk_with_its_thumbnail(api) -> None:
    wish = await make_wish(api)

    uploaded = await api.put(
        f"/wishes/{wish['id']}/photo", content=jpeg(), headers={"content-type": "image/jpeg"}
    )
    assert uploaded.status_code == 200, uploaded.text
    assert uploaded.json()["has_photo"] is True and uploaded.json()["photo_version"]

    full = await api.get(f"/wishes/{wish['id']}/photo")
    thumb = await api.get(f"/wishes/{wish['id']}/photo", params={"size": "thumb"})
    assert full.headers["content-type"] == "image/jpeg"
    assert max(Image.open(io.BytesIO(full.content)).size) == wishes.PHOTO_SIDE
    assert max(Image.open(io.BytesIO(thumb.content)).size) == wishes.THUMB_SIDE

    gone = (await api.delete(f"/wishes/{wish['id']}/photo")).json()
    assert gone["has_photo"] is False
    assert (await api.get(f"/wishes/{wish['id']}/photo")).status_code == 404


async def test_something_that_is_not_a_photo_is_refused(api) -> None:
    wish = await make_wish(api)

    response = await api.put(f"/wishes/{wish['id']}/photo", content=b"no soy una foto")

    assert response.status_code == 409


async def test_delete_takes_the_photo_with_it(api, schema) -> None:
    from sqlalchemy import text

    wish = await make_wish(api)
    await api.put(f"/wishes/{wish['id']}/photo", content=jpeg(400, 300))

    assert (await api.delete(f"/wishes/{wish['id']}")).status_code == 204
    assert (await api.get(f"/wishes/{wish['id']}")).status_code == 404
    async with schema.connect() as connection:
        left = await connection.scalar(text("select count(*) from outings.outings_photo"))
    assert left == 0


async def test_a_place_is_searched_through_the_kernel_and_the_hub(api, hub) -> None:
    hub.places = [
        {
            "name": "Selva de Irati",
            "display_name": "Selva de Irati, Orbaizeta, Navarra, 31671, España",
            "lat": "42.98",
            "lon": "-1.17",
            "osm_type": "way",
            "osm_id": "101",
            "addresstype": "forest",
            "address": {"country_code": "es", "ISO3166-2-lvl4": "ES-NA"},
        }
    ]

    found = (await api.get("/places/search", params={"q": "Irati"})).json()

    assert hub.asked == ["Irati"]
    assert found["failed"] == []
    assert found["candidates"][0]["name"] == "Selva de Irati"
    assert found["candidates"][0]["town"] == "Orbaizeta"
    assert found["candidates"][0]["osm_ref"] == "way/101"


async def test_a_dead_hub_is_said_and_not_an_empty_list(api, hub) -> None:
    hub.down = True

    found = (await api.get("/places/search", params={"q": "Irati"})).json()

    assert found["candidates"] == []
    assert found["failed"][0]["source"] == "nominatim"
