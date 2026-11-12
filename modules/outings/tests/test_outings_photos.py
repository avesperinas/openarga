from __future__ import annotations

from datetime import UTC, datetime, timedelta

from outings_world import IRATI, jpeg, make_wish
from sqlalchemy import text

from outings import photos, wishes
from outings.db import engine


async def fill() -> int:
    async with engine().begin() as connection:
        await connection.execute(text('set local role "mod_outings"'))
        return await photos.fill(connection)


IRATI_PLACE = wishes.place_of(IRATI).model_dump()


async def test_a_getaway_without_a_photo_gets_its_place_with_its_credit(api, kernel, hub) -> None:
    hub.photos = {"Selva Irati": "Irati.jpg"}
    made = await make_wish(api, place=IRATI_PLACE)

    assert await fill() == 1
    shown = (await api.get(f"/wishes/{made['id']}")).json()

    assert shown["has_photo"]
    assert shown["photo_credit"] == {
        "author": "Autora Sintética",
        "license": "CC BY-SA 4.0",
        "page": "https://commons.wikimedia.org/wiki/File:Irati.jpg",
    }
    assert hub.photo_asks[0] == "Selva Irati"
    photo = await api.get(f"/wishes/{made['id']}/photo?size=thumb")
    assert photo.headers["content-type"] == "image/jpeg"


async def test_it_is_looked_for_once_and_a_photo_removed_does_not_come_back(
    api, kernel, hub
) -> None:
    hub.photos = {"Selva Irati": "Irati.jpg"}
    made = await make_wish(api, place=IRATI_PLACE)
    await fill()
    await api.delete(f"/wishes/{made['id']}/photo")
    asked = len(hub.photo_asks)

    assert await fill() == 0
    assert len(hub.photo_asks) == asked
    assert not (await api.get(f"/wishes/{made['id']}")).json()["has_photo"]


async def test_without_a_photo_of_that_place_none_and_a_new_place_is_looked_for_again(
    api, kernel, hub
) -> None:
    made = await make_wish(api, place=IRATI_PLACE)
    assert await fill() == 0
    assert await fill() == 0

    hub.photos = {"Bardenas": "Bardenas.jpg"}
    await api.patch(
        f"/wishes/{made['id']}",
        json={"place": IRATI_PLACE | {"name": "Bardenas", "lat": 42.2, "lon": -1.5}},
    )

    assert await fill() == 1


async def test_your_photo_is_left_alone_and_clears_the_credit(api, kernel, hub) -> None:
    hub.photos = {"Selva Irati": "Irati.jpg"}
    mine = await make_wish(api, "Mía", place=IRATI_PLACE)
    await api.put(f"/wishes/{mine['id']}/photo", content=jpeg())
    theirs = await make_wish(api, place=IRATI_PLACE)
    await fill()

    await api.put(f"/wishes/{theirs['id']}/photo", content=jpeg())

    assert hub.photo_asks == ["Selva Irati"]
    assert (await api.get(f"/wishes/{theirs['id']}")).json()["photo_credit"] is None


async def test_only_getaways_and_trips_with_a_place(api, kernel, hub) -> None:
    hub.photos = {"Selva Irati": "Irati.jpg"}
    await make_wish(api, "Sidrería", kind="eat", place=IRATI_PLACE)
    await make_wish(api, "Sin sitio")
    trip = await make_wish(api, "Selva de Irati", kind="trip", place=IRATI_PLACE)

    assert await fill() == 1
    assert (await api.get(f"/wishes/{trip['id']}")).json()["has_photo"]


async def test_with_the_hub_down_nothing_is_marked_and_it_is_tried_again(api, kernel, hub) -> None:
    hub.photos = {"Selva Irati": "Irati.jpg"}
    await make_wish(api, place=IRATI_PLACE)
    hub.down = True

    assert await fill() == 0
    hub.down = False
    assert await fill() == 1


async def test_a_better_search_looks_again_for_what_was_not_found_but_not_for_what_you_removed(
    api, kernel, hub, monkeypatch
) -> None:
    hub.photos = {"Selva Irati": "Irati.jpg"}
    removed = await make_wish(api, place=IRATI_PLACE)
    await fill()
    await api.delete(f"/wishes/{removed['id']}/photo")
    hub.photos = {}
    missing = await make_wish(api, "Robledal sintético", place=IRATI_PLACE)
    assert await fill() == 0

    hub.around = ["Alrededor.jpg"]
    monkeypatch.setattr(photos, "FINDER", datetime.now(UTC) + timedelta(minutes=1))

    assert await fill() == 1
    assert (await api.get(f"/wishes/{missing['id']}")).json()["has_photo"]
    assert not (await api.get(f"/wishes/{removed['id']}")).json()["has_photo"]
    assert await fill() == 0
