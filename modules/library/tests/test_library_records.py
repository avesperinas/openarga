from __future__ import annotations

import asyncio
import secrets
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text

import arga_contracts as contracts
from arga_contracts import records as write
from library import records
from library.db import engine

MODULES = Path(__file__).resolve().parents[2]


async def add(api, title: str, reading: dict, **edition) -> dict:
    response = await api.post(
        "/books",
        json={
            "edition": {"title": title, "authors": ["Autora Sintética"], **edition},
            "reading": {"genre": "novel", **reading},
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


async def built() -> list[dict]:
    async with engine().begin() as connection:
        await connection.execute(text('set local role "mod_library"'))
        return await records.build(connection)


async def test_each_book_is_a_ficha_and_its_days_go_to_the_diary(api) -> None:
    read = await add(
        api,
        "Un libro sintético",
        {
            "status": "read",
            "started_on": "2026-08-01",
            "finished_on": "2026-08-20",
            "rating": 4.5,
            "note": "Me gustó el final.",
        },
        pages=320,
        year=2001,
    )
    other = await add(api, "Otro sintético", {"status": "reading", "started_on": "2026-08-20"})
    await add(api, "Pendiente", {"status": "want"})

    found = {one["id"]: one for one in await built()}

    ficha = found[f"book:{read['id']}"]
    assert ficha == contracts.record(**ficha)
    assert ficha["folder"] == "Libros" and ficha["kind"] == "Libro"
    assert ficha["href"] == f"/library/libro/{read['id']}"
    assert ficha["properties"] == {
        "autores": ["Autora Sintética"],
        "estado": "leído",
        "genero": "novela",
        "formato": "papel",
        "valoracion": 4.5,
        "empezado": "2026-08-01",
        "terminado": "2026-08-20",
        "dias": 20,
        "paginas": 320,
        "anio": 2001,
    }
    assert ficha["body"].startswith("**Autora Sintética** · 2001 · 320 páginas · papel · Novela")
    assert (
        "Leído del 1 de agosto de 2026 al 20 de agosto de 2026, en 20 días. ★★★★½ (4,5)"
        in (ficha["body"])
    )
    assert "## Nota\n\nMe gustó el final." in ficha["body"]

    day = found["day:2026-08-20"]
    assert day["day"] == "2026-08-20"
    assert day["body"] == (
        f"- Empezaste [[library:book:{other['id']}|Otro sintético]]\n"
        f"- Terminaste [[library:book:{read['id']}|Un libro sintético]] · ★★★★½ (4,5)"
    )
    assert "day:2026-08-01" in found
    pending = next(one for one in found.values() if one["title"] == "Pendiente")
    assert pending["properties"]["estado"] == "quiero leer"


async def test_what_changed_is_queued_once(api) -> None:
    await add(api, "Uno", {"status": "want"})
    async with engine().begin() as connection:
        await connection.execute(text('set local role "mod_library"'))
        first = await write.publish(connection, "library", await records.build(connection))
        again = await write.publish(connection, "library", await records.build(connection))
    assert first == {"added": 1, "changed": 0, "removed": 0}
    assert again == {"added": 0, "changed": 0, "removed": 0}


@pytest.fixture
async def notebook(schema, database_url, monkeypatch):
    from arga_testing import fresh_modules
    from kernel import db as kernel_db
    from kernel import migrate
    from kernel.main import app as kernel_app
    from notebook import db as notebook_db
    from notebook import mirror
    from notebook.main import app as notebook_app

    kernel_db.engine.cache_clear()
    await asyncio.to_thread(migrate.upgrade)
    monkeypatch.setenv("MODULE_REGISTRATION_TOKEN", secrets.token_hex(16))
    async with schema.begin() as connection:
        await connection.execute(text("delete from kernel.events where module = 'library'"))
        await fresh_modules(connection, "library", "notebook", fresh=["notebook"])
    monkeypatch.setattr(mirror, "kernel_transport", lambda: ASGITransport(app=kernel_app))
    notebook_db.engine.cache_clear()
    to_kernel = AsyncClient(transport=ASGITransport(app=kernel_app), base_url="http://kernel")
    async with AsyncClient(
        transport=ASGITransport(app=notebook_app), base_url="http://notebook"
    ) as api:
        yield to_kernel, api
    await to_kernel.aclose()
    for cached in (kernel_db.engine, notebook_db.engine):
        await cached().dispose()
        cached.cache_clear()
    async with schema.begin() as connection:
        await connection.execute(text("delete from kernel.events where module = 'library'"))
        await connection.execute(text("delete from kernel.modules where id = 'notebook'"))


async def test_library_the_kernel_and_notebook_put_a_book_in_the_notes(
    api, notebook, person
) -> None:
    from library import publisher
    from notebook import mirror
    from notebook.db import engine as notebook_engine

    to_kernel, notes = notebook
    read = await add(
        api,
        "Un libro sintético",
        {"status": "read", "started_on": "2026-08-01", "finished_on": "2026-08-20"},
    )

    async def worker() -> None:
        await write.refresh(to_kernel, engine, "library", records.build, write.Every(0), person)
        async with engine().begin() as connection:
            await connection.execute(text('set local role "mod_library"'))
            await publisher.publish_pending(connection, to_kernel)
        async with notebook_engine().begin() as connection:
            await connection.execute(text('set local role "mod_notebook"'))
            await mirror.derive(connection)

    await worker()

    found = (
        await notes.get("/notes/resolve", params={"target": "Books/Libros/Un libro sintético"})
    ).json()["note"]
    assert found is not None
    note = (await notes.get(f"/notes/{found['id']}")).json()
    assert note["properties"]["arga"] == f"library:book:{read['id']}"
    assert note["arga"]["apps"][0]["name"] == "Books"
    diary = (await notes.get("/notes/resolve", params={"target": "2026-08-20"})).json()["note"]
    assert diary is not None and diary["folder"] == "Diario"

    rated = await api.put(
        f"/books/{read['id']}",
        json={
            "status": "read",
            "started_on": "2026-08-01",
            "finished_on": "2026-08-20",
            "rating": 3,
            "genre": "novel",
        },
    )
    assert rated.status_code == 200, rated.text
    await worker()
    again = (await notes.get(f"/notes/{found['id']}")).json()
    assert again["properties"]["valoracion"] == 3

    async with engine().begin() as connection:
        await connection.execute(text('set local role "mod_library"'))
        await connection.execute(
            text("delete from library.library_reading where id = :id"), {"id": read["id"]}
        )
    await worker()
    trash = [one["title"] for one in (await notes.get("/trash")).json()]
    assert "Un libro sintético" in trash
