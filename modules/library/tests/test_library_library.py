from __future__ import annotations

from datetime import timedelta

from library import isbn
from library.library import today

READING_FIELDS = ("status", "started_on", "finished_on", "rating", "format", "genre", "note")


def reading_of(book: dict) -> dict:
    return {field: book[field] for field in READING_FIELDS}


async def read_book(api, reading_id: str) -> dict:
    response = await api.get(f"/books/{reading_id}")
    assert response.status_code == 200, response.text
    return response.json()


async def add(api, title: str, status: str = "want", **edition) -> dict:
    dates = {
        "want": {},
        "reading": {"started_on": "2026-09-01"},
        "read": {"started_on": "2026-08-01", "finished_on": "2026-08-20"},
    }[status]
    response = await api.post(
        "/books",
        json={
            "edition": {"title": title, "authors": ["Autora Sintética"], **edition},
            "reading": {"status": status, "genre": "novel", **dates},
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


async def test_a_book_typed_by_hand_is_read_with_its_dates(api) -> None:
    added = await add(api, "El libro de prueba", pages=320, language="es", year=2019)

    started = await api.post(f"/books/{added['id']}/start", json={"on": "2026-09-02"})
    finished = await api.post(
        f"/books/{added['id']}/finish", json={"on": "2026-09-20", "rating": 4.5}
    )

    assert started.json()["status"] == "reading"
    book = finished.json()
    assert finished.status_code == 200, finished.text
    assert book["status"] == "read"
    assert (book["started_on"], book["finished_on"]) == ("2026-09-02", "2026-09-20")
    assert book["rating"] == 4.5
    assert book["days"] == 19
    assert book["edition"] == "manual"
    assert (book["title"], book["authors"], book["pages"]) == (
        "El libro de prueba",
        ["Autora Sintética"],
        320,
    )


async def test_the_library_puts_what_you_read_first_then_the_latest_finished(api) -> None:
    await add(api, "Pendiente")
    await add(api, "Terminado", status="read")
    await add(api, "En curso", status="reading")

    titles = [book["title"] for book in (await api.get("/books")).json()]
    read = [book["title"] for book in (await api.get("/books?status=read")).json()]
    this_year = [book["title"] for book in (await api.get("/books?year=2026")).json()]

    assert titles == ["En curso", "Terminado", "Pendiente"]
    assert read == ["Terminado"]
    assert this_year == ["En curso", "Terminado"]


async def test_the_dates_must_say_the_status(api) -> None:
    added = await add(api, "Sin fechas")
    body = reading_of(added)

    read_without_dates = await api.put(f"/books/{added['id']}", json={**body, "status": "read"})
    backwards = await api.put(
        f"/books/{added['id']}",
        json={**body, "status": "read", "started_on": "2026-09-10", "finished_on": "2026-09-01"},
    )
    tomorrow = (today() + timedelta(days=1)).isoformat()
    future = await api.put(
        f"/books/{added['id']}", json={**body, "status": "reading", "started_on": tomorrow}
    )
    odd_rating = await api.put(f"/books/{added['id']}", json={**body, "rating": 3.3})

    assert read_without_dates.status_code == 422
    assert "inicio y de fin" in read_without_dates.text
    assert backwards.status_code == 422
    assert future.status_code == 422
    assert odd_rating.status_code == 422


async def test_finishing_needs_to_know_when_it_started(api) -> None:
    added = await add(api, "Nunca empezado")

    response = await api.post(f"/books/{added['id']}/finish", json={})

    assert response.status_code == 409
    assert "empezaste" in response.json()["detail"]


async def test_finishing_without_a_date_is_today(api) -> None:
    added = await add(api, "Hoy", status="reading")

    book = (await api.post(f"/books/{added['id']}/finish", json={})).json()

    assert book["finished_on"] == today().isoformat()


async def test_a_finished_book_is_not_started_again(api) -> None:
    added = await add(api, "Releído", status="read")

    response = await api.post(f"/books/{added['id']}/start", json={})

    assert response.status_code == 409


async def test_a_typed_book_can_be_corrected(api) -> None:
    added = await add(api, "Titlo con errata")

    response = await api.put(
        f"/books/{added['id']}/edition",
        json={
            "title": "  Título   corregido ",
            "authors": ["Una", " ", "Otra"],
            "isbn": "84-376-0494-X",
        },
    )

    book = response.json()
    assert response.status_code == 200, response.text
    assert book["title"] == "Título corregido"
    assert book["authors"] == ["Una", "Otra"]
    assert book["isbn13"] == "9788437604947"


async def test_an_isbn_with_a_wrong_digit_is_refused(api) -> None:
    response = await api.post(
        "/books",
        json={
            "edition": {"title": "Mal tecleado", "isbn": "9788437604948"},
            "reading": {"status": "want"},
        },
    )

    assert response.status_code == 422


async def test_a_book_that_is_not_there_is_a_404(api) -> None:
    response = await api.get("/books/00000000-0000-4000-8000-000000000000")

    assert response.status_code == 404


def test_isbn_ten_and_thirteen_are_the_same_book() -> None:
    assert isbn.to_isbn13("0-306-40615-2") == "9780306406157"
    assert isbn.to_isbn13("978-0-306-40615-7") == "9780306406157"
    assert isbn.to_isbn13("0306406153") is None
    assert isbn.to_isbn13("1234") is None
