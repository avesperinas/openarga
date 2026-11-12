from __future__ import annotations

import httpx

JPEG = b"\xff\xd8\xff\xe0" + b"\x01" * 5000

WORK = {
    "docs": [
        {
            "key": "/works/OL1W",
            "title": "Un libro sintético",
            "author_name": ["Autora Sintética"],
            "number_of_pages_median": 432,
            "subject": ["Fiction", "Magic realism"],
            "editions": {
                "docs": [
                    {
                        "key": "/books/OL2M",
                        "title": "Un libro sintético",
                        "isbn": ["9788420471839"],
                        "language": ["spa"],
                        "publish_year": [2007],
                        "cover_i": 222,
                    }
                ]
            },
        }
    ]
}


class Library:
    def __init__(self) -> None:
        self.down = False
        self.covers = 0

    def __call__(self, request: httpx.Request) -> httpx.Response:
        if self.down:
            raise httpx.ConnectError("sin red", request=request)
        if request.url.host == "covers.openlibrary.org":
            self.covers += 1
            return httpx.Response(200, content=JPEG)
        return httpx.Response(200, json=WORK)


READ = {"status": "read", "started_on": "2026-08-01", "finished_on": "2026-08-20", "genre": "novel"}


async def test_a_scanned_isbn_is_added_with_cover_pages_and_a_proposed_genre(api, hub) -> None:
    library = Library()
    hub.answer(library)

    found = (await api.get("/catalog/search", params={"q": "9788420471839"})).json()

    [candidate] = [c for c in found["candidates"] if c["source"] == "openlibrary"]
    assert (candidate["isbn13"], candidate["pages"], candidate["genre_hint"]) == (
        "9788420471839",
        432,
        "novel",
    )
    assert candidate["known_id"] is None
    assert [f["source"] for f in found["failed"]] == ["google_books"]

    candidate.pop("genre_hint")
    candidate.pop("known_id")
    added = await api.post("/books/catalog", json={"candidate": candidate, "reading": READ})
    book = added.json()
    assert added.status_code == 201, added.text
    assert (book["edition"], book["has_cover"], book["pages"], book["language"]) == (
        "catalog",
        True,
        432,
        "es",
    )

    library.down = True
    cover = await api.get(f"/books/{book['id']}/cover")
    assert cover.status_code == 200
    assert cover.content == JPEG
    assert cover.headers["content-type"] == "image/jpeg"

    again = (await api.get("/catalog/search", params={"q": "libro"})).json()
    assert [f["source"] for f in again["failed"]] == ["openlibrary", "google_books"]


async def test_reading_it_again_does_not_fetch_it_again(api, hub) -> None:
    library = Library()
    hub.answer(library)
    [candidate] = [
        c
        for c in (await api.get("/catalog/search", params={"q": "libro"})).json()["candidates"]
        if c["source"] == "openlibrary"
    ]
    first = (
        await api.post("/books/catalog", json={"candidate": candidate, "reading": READ})
    ).json()

    found = (await api.get("/catalog/search", params={"q": "libro"})).json()["candidates"][0]
    second = await api.post(
        "/books/catalog", json={"candidate": candidate, "reading": {"status": "want"}}
    )

    assert found["known_id"] == first["id"]
    assert second.json()["edition_id"] == first["edition_id"]
    assert library.covers == 1


async def test_without_a_cover_the_book_is_saved_anyway(api, hub) -> None:
    def no_cover(request: httpx.Request) -> httpx.Response:
        if request.url.host == "covers.openlibrary.org":
            return httpx.Response(404)
        return httpx.Response(200, json=WORK)

    hub.answer(no_cover)
    [candidate] = [
        c
        for c in (await api.get("/catalog/search", params={"q": "libro"})).json()["candidates"]
        if c["source"] == "openlibrary"
    ]

    book = (await api.post("/books/catalog", json={"candidate": candidate, "reading": READ})).json()

    assert book["has_cover"] is False
    assert (await api.get(f"/books/{book['id']}/cover")).status_code == 404


async def test_with_the_hub_down_both_sources_say_so(api, schema) -> None:
    from library.main import app

    def down(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("el kernel no contesta", request=request)

    app.state.client = httpx.AsyncClient(transport=httpx.MockTransport(down))
    try:
        found = (await api.get("/catalog/search", params={"q": "libro"})).json()
    finally:
        await app.state.client.aclose()

    assert found["candidates"] == []
    assert [f["source"] for f in found["failed"]] == ["openlibrary", "google_books"]
