from __future__ import annotations

import httpx
from test_library_catalog import WORK, Library
from test_library_stats import read

from library.library import today

WRITE = {"x-arga-scopes": "library:write"}
READ = {"x-arga-scopes": "library:read"}


async def call(api, name: str, body: dict, headers=WRITE) -> httpx.Response:
    return await api.post(f"/tools/{name}", json=body, headers=headers)


async def test_the_pages_this_year_are_the_same_for_claude_and_the_app(api) -> None:
    year = today().year
    await read(api, "Uno", f"{year}-01-02", f"{year}-01-20", 321)
    await read(api, "Dos", f"{year}-01-21", f"{year}-01-25", 123)

    app = (await api.get("/stats")).json()
    claude = (await call(api, "get_reading_stats", {}, READ)).json()["content"]

    assert claude["pages"] == app["pages"] == 444
    assert claude["books"] == app["books"] == 2


async def test_grouped_by_author(api) -> None:
    await read(api, "Uno", "2025-01-02", "2025-01-20", 100, authors=["Ana"])
    await read(api, "Dos", "2025-02-02", "2025-02-20", 200, authors=["Ana", "Luis"])

    content = (
        await call(api, "get_reading_stats", {"group_by": "author", "year": 2025}, READ)
    ).json()["content"]

    assert [(g["key"], g["books"], g["pages"]) for g in content["groups"]] == [
        ("Ana", 2, 300),
        ("Luis", 1, 200),
    ]


async def test_a_book_without_isbn_is_saved_unresolved_and_then_started_and_finished(
    api, hub
) -> None:
    added = (await call(api, "add_book", {"title": "Sin ISBN", "authors": ["Alguien"]})).json()[
        "content"
    ]
    book_id = added["added"]["book_id"]

    started = await call(api, "start_reading", {"book_id": book_id, "on": "2026-09-01"})
    finished = await call(api, "finish_reading", {"book_id": book_id, "on": "2026-09-10"})
    rated = await call(api, "rate_book", {"book_id": book_id, "rating": 3.5})
    found = (await call(api, "find_books", {"query": "alguien"}, READ)).json()["content"]
    reading = (await call(api, "get_currently_reading", {}, READ)).json()["content"]

    assert added["resolved"] is False
    assert started.json()["content"]["book"]["status"] == "reading"
    assert finished.json()["content"]["book"]["days"] == 10
    assert rated.json()["content"]["book"]["rating"] == 3.5
    assert [b["title"] for b in found["books"]] == ["Sin ISBN"]
    assert reading == {"reading": []}


async def test_with_an_isbn_the_book_comes_from_the_catalog(api, hub) -> None:
    hub.answer(Library())

    content = (await call(api, "add_book", {"isbn": "84-204-7183-6", "status": "want"})).json()[
        "content"
    ]

    assert content["resolved"] is True
    assert (content["added"]["title"], content["added"]["isbn13"]) == (
        WORK["docs"][0]["title"],
        "9788420471839",
    )


async def test_an_isbn_nobody_has_is_kept_for_the_app(api, hub) -> None:
    hub.answer(lambda request: httpx.Response(200, json={"docs": []}))

    content = (await call(api, "add_book", {"isbn": "9780306406157", "title": "Raro"})).json()[
        "content"
    ]

    assert content["resolved"] is False
    assert content["added"]["isbn13"] == "9780306406157"


async def test_bad_dates_or_unknown_books_are_said_not_crashed(api, hub) -> None:
    bad = await call(api, "add_book", {"title": "Mal", "status": "read"})
    missing = await call(
        api, "rate_book", {"book_id": "00000000-0000-4000-8000-000000000000", "rating": 4}
    )

    assert bad.status_code == 409
    assert "inicio y de fin" in bad.json()["detail"]
    assert missing.status_code == 404


async def test_reading_scope_cannot_write(api, hub) -> None:
    response = await call(api, "add_book", {"title": "No"}, READ)

    assert response.status_code == 403


async def test_a_typed_book_is_resolved_in_the_app(api, hub) -> None:
    hub.answer(Library())
    added = (await call(api, "add_book", {"title": "Un libro"})).json()["content"]["added"]
    [candidate] = [
        c
        for c in (await api.get("/catalog/search", params={"q": "libro"})).json()["candidates"]
        if c["source"] == "openlibrary"
    ]
    candidate.pop("genre_hint")
    candidate.pop("known_id")

    resolved = await api.put(f"/books/{added['book_id']}/resolve", json={"candidate": candidate})

    book = resolved.json()
    assert resolved.status_code == 200, resolved.text
    assert (book["edition"], book["has_cover"], book["id"]) == ("catalog", True, added["book_id"])


async def test_what_is_being_read_says_how_many_days_it_has_been(api, hub) -> None:
    added = (await call(api, "add_book", {"title": "Empezado hoy", "authors": ["Alguien"]})).json()
    await call(api, "start_reading", {"book_id": added["content"]["added"]["book_id"]})

    found = (await call(api, "find_books", {"status": "reading"}, READ)).json()["content"]

    assert [(b["title"], b["days_so_far"]) for b in found["books"]] == [("Empezado hoy", 1)]
