from __future__ import annotations

from test_library_catalog import WORK, Library


def headers(token: str) -> dict:
    return {"x-module-token": token, "x-arga-module": "insights"}


async def test_only_the_kernel_asks_and_only_for_what_library_does(api, monkeypatch) -> None:
    monkeypatch.setenv("MODULE_REGISTRATION_TOKEN", "el-token")
    body = {"title": "Un libro sin ISBN", "authors": ["Alguien"]}

    refused = await api.post("/capabilities/books.want", json=body)
    unknown = await api.post("/capabilities/books.burn", json=body, headers=headers("el-token"))
    bad = await api.post(
        "/capabilities/books.want", json={"title": ""}, headers=headers("el-token")
    )

    assert refused.status_code == 401
    assert unknown.status_code == 404
    assert bad.status_code == 422


async def test_a_book_without_isbn_is_wanted_once(api, monkeypatch) -> None:
    monkeypatch.setenv("MODULE_REGISTRATION_TOKEN", "el-token")
    body = {
        "title": "Un libro sin ISBN",
        "authors": ["Alguien"],
        "note": "Te lo recomendó Insights",
    }

    made = await api.post("/capabilities/books.want", json=body, headers=headers("el-token"))
    again = await api.post(
        "/capabilities/books.want",
        json=body | {"title": "un libro, sin isbn"},
        headers=headers("el-token"),
    )
    shelf = (await api.get("/books", params={"status": "want"})).json()

    assert made.status_code == 200, made.text
    assert made.json()["already"] is False and made.json()["resolved"] is False
    assert again.json() == {**made.json(), "already": True}
    assert [(one["title"], one["note"]) for one in shelf] == [
        ("Un libro sin ISBN", "Te lo recomendó Insights")
    ]


async def test_with_an_isbn_it_comes_from_the_catalog(api, hub, monkeypatch) -> None:
    hub.answer(Library())
    import os

    token = os.environ["MODULE_REGISTRATION_TOKEN"]
    body = {"title": "Cualquier título", "isbn13": "9788420471839"}

    made = await api.post("/capabilities/books.want", json=body, headers=headers(token))

    assert made.status_code == 200, made.text
    assert made.json()["resolved"] is True
    shelf = (await api.get("/books", params={"status": "want"})).json()
    assert shelf[0]["title"] == WORK["docs"][0]["title"]
