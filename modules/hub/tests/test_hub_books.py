from __future__ import annotations

import base64
import secrets

import httpx
import pytest

from hub import capabilities
from hub.providers import books

TOKEN = secrets.token_hex(16)
JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 4000

WORK = {
    "docs": [
        {
            "key": "/works/OL1W",
            "title": "Un libro sintético",
            "author_name": ["Autora Sintética"],
            "number_of_pages_median": 432,
            "first_publish_year": 1967,
            "subject": ["Fiction", "Magic realism", "Novela"],
            "cover_i": 111,
            "editions": {
                "docs": [
                    {
                        "key": "/books/OL2M",
                        "title": "Un libro sintético",
                        "isbn": ["8420471836", "9788420471839"],
                        "language": ["spa"],
                        "publish_year": [2007],
                        "cover_i": 222,
                    }
                ]
            },
        }
    ]
}

VOLUME = {
    "items": [
        {
            "id": "AbCdEf123",
            "volumeInfo": {
                "title": "Otro libro sintético",
                "authors": ["Autor Inventado"],
                "pageCount": 200,
                "language": "es",
                "publishedDate": "2021-03-04",
                "categories": ["Fiction / General"],
                "industryIdentifiers": [{"type": "ISBN_13", "identifier": "9780306406157"}],
                "imageLinks": {"thumbnail": "http://books.google.com/x"},
            },
        }
    ]
}


class Sources:
    def __init__(self) -> None:
        self.asked: list[httpx.URL] = []
        self.library_down = False
        self.cover: bytes | None = JPEG

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.asked.append(request.url)
        host = request.url.host
        if host == "openlibrary.org":
            if self.library_down:
                raise httpx.ConnectError("sin red", request=request)
            return httpx.Response(200, json=WORK)
        if host == "www.googleapis.com":
            return httpx.Response(200, json=VOLUME)
        if host in ("covers.openlibrary.org", "books.google.com"):
            if self.cover is None:
                return httpx.Response(404)
            return httpx.Response(200, content=self.cover)
        raise AssertionError(f"nadie debería pedir {request.url}")


@pytest.fixture
def sources(monkeypatch) -> Sources:
    fake = Sources()
    monkeypatch.setenv("MODULE_REGISTRATION_TOKEN", TOKEN)
    monkeypatch.setattr(capabilities, "source_transport", lambda: httpx.MockTransport(fake))
    return fake


def ask(api, capability: str, body: dict):
    return api.post(
        f"/capabilities/{capability}",
        json=body,
        headers={"x-module-token": TOKEN, "x-arga-module": "library"},
    )


async def by_provider(api) -> dict:
    return {c["provider"]: c for c in (await api.get("/connections")).json()}


async def test_open_library_is_asked_in_spanish_and_connects_itself(api, sources) -> None:
    answer = (await ask(api, "books.search", {"query": "libro sintético"})).json()

    [found] = answer["candidates"]
    assert found == {
        "source": "openlibrary",
        "source_ref": "OL2M",
        "title": "Un libro sintético",
        "subtitle": None,
        "authors": ["Autora Sintética"],
        "isbn13": "9788420471839",
        "pages": 432,
        "language": "es",
        "year": 2007,
        "subjects": ["Fiction", "Magic realism", "Novela"],
        "cover_ref": "222",
    }
    assert answer["failed"] == [
        {"source": "google_books", "reason": "no Google Books key: add it in Hub"}
    ]
    [url] = sources.asked
    assert (url.params["q"], url.params["lang"]) == ("libro sintético", "es")
    connected = await by_provider(api)
    assert set(connected) == {"openlibrary"}
    ficha = (await api.get(f"/connections/{connected['openlibrary']['id']}")).json()
    assert [(r["operation"], r["outcome"]) for r in ficha["runs"]] == [("search", "ok")]


async def test_an_isbn_ten_is_searched_as_its_thirteen(api, sources) -> None:
    await ask(api, "books.search", {"query": "84-204-7183-6"})

    assert sources.asked[0].params["q"] == "isbn:9788420471839"


async def test_with_its_key_google_books_is_asked_too(api, sources) -> None:
    created = await api.post(
        "/connections", json={"provider": "google_books", "secrets": {"api_key": "clave-1"}}
    )
    assert created.status_code == 201, created.text

    answer = (await ask(api, "books.search", {"query": "9780306406157"})).json()

    assert answer["failed"] == []
    google = next(c for c in answer["candidates"] if c["source"] == "google_books")
    assert (google["isbn13"], google["year"], google["cover_ref"]) == (
        "9780306406157",
        2021,
        "AbCdEf123",
    )
    [asked] = [url for url in sources.asked if url.host == "www.googleapis.com"]
    assert (asked.params["key"], asked.params["q"]) == ("clave-1", "isbn:9780306406157")


async def test_a_source_down_does_not_sink_the_search(api, sources) -> None:
    await api.post(
        "/connections", json={"provider": "google_books", "secrets": {"api_key": "clave-1"}}
    )
    sources.library_down = True

    answer = (await ask(api, "books.search", {"query": "libro"})).json()

    assert [c["source"] for c in answer["candidates"]] == ["google_books"]
    assert answer["failed"] == [
        {"source": "openlibrary", "reason": "Open Library no contestó: ConnectError"}
    ]


async def test_a_cover_comes_back_as_an_image(api, sources) -> None:
    answer = (await ask(api, "books.cover", {"source": "openlibrary", "ref": "222"})).json()

    assert answer["type"] == "image/jpeg"
    assert base64.b64decode(answer["cover"]) == JPEG
    [url] = sources.asked
    assert str(url) == "https://covers.openlibrary.org/b/id/222-L.jpg?default=false"


async def test_without_a_cover_or_with_something_else_there_is_none(api, sources) -> None:
    sources.cover = None
    missing = (await ask(api, "books.cover", {"source": "openlibrary", "ref": "222"})).json()
    sources.cover = b"<html>no soy una imagen</html>" * 100
    html = (await ask(api, "books.cover", {"source": "google_books", "ref": "AbCdEf123"})).json()

    assert missing == {"cover": None, "type": None, "failed": None}
    assert html["cover"] is None


async def test_a_cover_is_never_asked_to_an_address_from_outside(api, sources) -> None:
    response = await ask(api, "books.cover", {"source": "openlibrary", "ref": "../../evil.example"})

    assert response.status_code == 422
    assert sources.asked == []


def test_isbn_and_language_are_normalised() -> None:
    assert books.isbn13("0-306-40615-2") == "9780306406157"
    assert books.isbn13("9780306406158") is None
    assert books.looks_like_isbn("cien años") is None
    assert books._language("spa") == "es" and books._language("xxx") is None
