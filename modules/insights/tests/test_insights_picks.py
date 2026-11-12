from __future__ import annotations

import json

import httpx
import pytest
from insights_taste_world import PNG, FakeKernel
from sqlalchemy import text

from insights import hub

READ = {"x-arga-scopes": "insights:read"}
WRITE = {"x-arga-scopes": "insights:read insights:write"}


@pytest.fixture
def kernel(monkeypatch) -> FakeKernel:
    fake = FakeKernel()
    monkeypatch.setattr(hub, "transport", lambda: httpx.MockTransport(fake))
    return fake


async def publish(api, *picks: dict, origin: str = "weekly") -> dict:
    response = await api.post(
        "/tools/publish_picks", json={"origin": origin, "picks": list(picks)}, headers=WRITE
    )
    assert response.status_code == 200, response.text
    return response.json()["content"]


BOOK = {
    "kind": "book",
    "title": "Las legiones malditas",
    "creators": ["Posteguillo"],
    "why": "Le gustó la novela histórica de Roma y lee sagas largas",
    "because": ["Novela histórica"],
}


async def test_a_book_is_checked_in_the_catalogue_with_its_cover_and_own_links(api, kernel) -> None:
    published = await publish(api, BOOK)

    one = published["published"][0]
    assert one["verified"] == "catalog"
    library = (await api.get("/picks")).json()
    found = library[0]
    assert found["creators"] == ["Santiago Posteguillo"]
    assert found["length"] == "720 páginas" and found["list"] == "read"
    assert found["links"][0]["url"] == "https://openlibrary.org/isbn/9788466648769"
    assert found["has_cover"] is True
    cover = await api.get(f"/picks/{found['id']}/cover")
    assert cover.content == PNG and cover.headers["content-type"] == "image/png"
    assert [name for name, _ in kernel.asked] == ["books.search", "books.cover"]


async def test_what_is_not_in_the_catalogue_or_already_given_is_not_published(api, kernel) -> None:
    await publish(api, BOOK)

    again = await publish(api, BOOK)
    invented = await publish(api, BOOK | {"title": "Un libro que no existe en ninguna parte"})
    wrong_author = await publish(api, BOOK | {"creators": ["Otra Persona"]})

    assert again["published"] == [] and "ya se lo recomendaste" in again["not_published"][0]
    assert invented["published"] == [] and "no aparece" in invented["not_published"][0]
    assert wrong_author["published"] == []


async def test_podcasts_films_and_videos(api, kernel) -> None:
    published = await publish(
        api,
        {
            "kind": "podcast",
            "title": "Fall of Civilizations",
            "why": "Le encanta la historia antigua",
        },
        {"kind": "film", "title": "Ágora", "year": 2009, "why": "Hipatia y la ciencia antigua"},
        {"kind": "video", "title": "La batalla de Leuctra", "why": "Para verla en un mapa"},
    )

    kinds = {one["kind"]: one for one in published["published"]}
    assert kinds["podcast"]["verified"] == "catalog"
    assert kinds["film"]["verified"] == "catalog"
    assert kinds["video"]["verified"] == "link"
    library = {one["kind"]: one for one in (await api.get("/picks")).json()}
    assert library["podcast"]["list"] == "listen"
    assert library["film"]["length"] == "127 min"
    assert any("justwatch" in link["url"] for link in library["film"]["links"])
    assert library["video"]["links"][0]["url"].startswith("https://www.youtube.com/results")


async def test_when_the_catalogue_is_down_nothing_unchecked_is_published(api, kernel) -> None:
    kernel.down = True

    published = await publish(api, BOOK)

    assert published["published"] == []
    assert "no se pudo comprobar" in published["not_published"][0]


async def test_saving_a_book_puts_it_in_your_readings(api, kernel) -> None:
    await publish(api, BOOK)
    pick = (await api.get("/picks")).json()[0]

    saved = (await api.post(f"/picks/{pick['id']}/save")).json()

    assert saved["state"] == "saved" and saved["sent_to"] == "library"
    want = next(body for name, body in kernel.asked if name == "books.want")
    assert want["isbn13"] == "9788466648769"
    assert want["title"] == "Las legiones malditas"


async def test_if_your_readings_do_not_answer_it_stays_saved_here_and_says_so(api, kernel) -> None:
    await publish(api, BOOK)
    pick = (await api.get("/picks")).json()[0]
    kernel.down = True

    failed = await api.post(f"/picks/{pick['id']}/save")

    assert failed.status_code == 502
    assert "Guardado aquí" in failed.json()["detail"]
    assert (await api.get("/picks")).json()[0]["state"] == "saved"


async def test_finishing_and_rating_teaches_insights_who_you_like(api, kernel) -> None:
    await publish(api, BOOK)
    pick = (await api.get("/picks")).json()[0]

    done = (
        await api.put(
            f"/picks/{pick['id']}",
            json={"state": "done", "rating": 4.5, "more_like": True, "collections": ["Roma"]},
        )
    ).json()
    traits = (await api.get("/tastes")).json()["traits"]
    library = (await api.post("/tools/get_library", json={"states": ["done"]}, headers=READ)).json()

    assert done["state"] == "done" and done["collections"] == ["Roma"]
    learned = next(one for one in traits if one["facet"] == "creator")
    assert learned["label"] == "Santiago Posteguillo" and learned["stance"] == 2
    assert learned["source"] == "rated" and learned["status"] == "confirmed"
    assert library["content"]["picks"][0]["rating"] == 4.5
    half = await api.put(f"/picks/{pick['id']}", json={"rating": 4.3})
    assert half.status_code == 422


SHELF = "probe_shelf"


@pytest.fixture
async def shelf(schema):
    async with schema.begin() as connection:
        await connection.execute(
            text(
                "insert into kernel.modules (id, version, enabled, manifest) "
                "values (:m, '0.1.0', true, cast(:manifest as jsonb)) "
                "on conflict (id) do update set manifest = excluded.manifest"
            ),
            {
                "m": SHELF,
                "manifest": json.dumps(
                    {"id": SHELF, "publishes": [{"type": f"{SHELF}.record", "contract": "record"}]}
                ),
            },
        )
        await connection.execute(
            text(
                "insert into kernel.events (ts, module, source, type, payload, dedup_hash, "
                "user_id) values (now(), :m, 'app', :type, cast(:payload as jsonb), 'shelf-1', "
                "nullif(current_setting('arga.user_id', true), '')::uuid)"
            ),
            {
                "m": SHELF,
                "type": f"{SHELF}.record",
                "payload": json.dumps(
                    {
                        "record": {
                            "id": "libro-1",
                            "title": "Las legiones malditas",
                            "kind": "Libro",
                            "href": "/estanteria/libro-1",
                        }
                    }
                ),
            },
        )
    yield schema
    async with schema.begin() as connection:
        await connection.execute(text("delete from kernel.events where module = :m"), {"m": SHELF})
        await connection.execute(text("delete from kernel.modules where id = :m"), {"m": SHELF})


async def test_books_you_already_have_are_not_recommended(shelf, api, kernel) -> None:
    published = await publish(api, BOOK)

    assert published["published"] == []
    assert "ya está en sus lecturas" in published["not_published"][0]
