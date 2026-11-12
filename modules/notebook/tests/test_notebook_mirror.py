from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from itertools import count

import pytest
from sqlalchemy import text

import arga_contracts as contracts
from arga_tenancy import current_user
from notebook import export, mirror
from notebook import markdown as md

WRITE = {"x-arga-scopes": "notebook:write"}
APP = "biblio"
OTHER_APP = "cocina"
NAMES = {APP: "Biblioteca", OTHER_APP: "Cocina"}
_clock = count()


async def names() -> dict[str, str]:
    return NAMES


@pytest.fixture
async def apps(schema):
    async with schema.begin() as connection:
        for app in (APP, OTHER_APP):
            await connection.execute(
                text("delete from kernel.events where module = :m"), {"m": app}
            )
            await connection.execute(
                text(
                    "insert into kernel.modules (id, version, manifest) values (:id, '0.1.0', "
                    "cast(:manifest as jsonb)) on conflict (id) do update set manifest = "
                    "excluded.manifest"
                ),
                {
                    "id": app,
                    "manifest": json.dumps(
                        {
                            "id": app,
                            "name": NAMES[app],
                            "publishes": [{"type": f"{app}.record", "contract": "record"}],
                        }
                    ),
                },
            )
    yield schema
    async with schema.begin() as connection:
        for app in (APP, OTHER_APP):
            await connection.execute(
                text("delete from kernel.events where module = :m"), {"m": app}
            )
            await connection.execute(text("delete from kernel.modules where id = :m"), {"m": app})


async def publish(schema, item: dict, app: str = APP) -> None:
    body = contracts.record(**item)
    when = datetime(2026, 9, 30, 10, tzinfo=UTC) + timedelta(seconds=next(_clock))
    async with schema.begin() as connection:
        await connection.execute(
            text(
                "insert into kernel.events (ts, ingested_at, module, source, type, payload, "
                "user_id, dedup_hash) values (:ts, :ts, :app, 'app', :type, "
                "cast(:payload as jsonb), :person, :dedup)"
            ),
            {
                "ts": when,
                "app": app,
                "type": f"{app}.record",
                "payload": json.dumps({"record": body}),
                "person": current_user.get(),
                "dedup": f"{app}:{body['id']}:{when.isoformat()}",
            },
        )


async def derive(schema, full: bool = True) -> dict[str, int]:
    async with schema.begin() as connection:
        await connection.execute(text('set local role "mod_notebook"'))
        return await mirror.derive(connection, full, names)


def book(**changes) -> dict:
    return {
        "id": "reading:1",
        "title": "El nombre del viento",
        "kind": "Libro",
        "href": "/biblio/libro/1",
        "folder": "Libros",
        "properties": {"autor": "Patrick Rothfuss", "valoracion": 4.5},
        "body": "**Patrick Rothfuss** · 662 páginas\n\n## Lectura\nDel 2 al 10 de enero.",
        **changes,
    }


async def note_at(api, path: str) -> dict:
    found = (await api.get("/notes/resolve", params={"target": path})).json()["note"]
    assert found is not None, f"no hay nota en {path}"
    return (await api.get(f"/notes/{found['id']}")).json()


async def test_a_record_becomes_a_note_in_the_folder_of_its_app(api, apps) -> None:
    await publish(apps, book())

    assert await derive(apps) == {"notes": 1, "days": 0, "removed": 0, "skipped": 0}

    note = await note_at(api, "Biblioteca/Libros/El nombre del viento")
    assert note["folder"] == "Biblioteca/Libros"
    assert note["properties"] == {
        "arga": "biblio:reading:1",
        "tipo": "Libro",
        "autor": "Patrick Rothfuss",
        "valoracion": 4.5,
    }
    assert note["content"].startswith("---\narga: biblio:reading:1\ntipo: Libro\n")
    found = md.block(note["content"])
    assert found is not None and found.inner.startswith("**Patrick Rothfuss**")
    assert note["updated_by"] == "import" and note["updated_app"] == "Biblioteca"
    assert note["arga"] == {
        "apps": [{"app": APP, "name": "Biblioteca", "href": "/biblio/libro/1", "kind": "Libro"}],
        "properties": ["arga", "tipo", "autor", "valoracion"],
        "day": False,
    }
    assert await derive(apps) == {"notes": 0, "days": 0, "removed": 0, "skipped": 0}


async def test_what_you_write_stays_when_the_app_changes_its_part(api, apps) -> None:
    await publish(apps, book())
    await derive(apps)
    note = await note_at(api, "Biblioteca/Libros/El nombre del viento")
    mine = note["content"] + "\nLo que pensé al acabarlo.\n"
    written = await api.put(f"/notes/{note['id']}", json={"content": mine})
    assert written.status_code == 200
    await api.put(f"/notes/{note['id']}/properties", json={"set": {"prestado": "Ana"}})

    await publish(
        apps, book(properties={"autor": "Patrick Rothfuss"}, body="**Patrick Rothfuss** · 700")
    )
    await derive(apps)

    after = await note_at(api, "Biblioteca/Libros/El nombre del viento")
    assert after["properties"] == {
        "arga": "biblio:reading:1",
        "tipo": "Libro",
        "autor": "Patrick Rothfuss",
        "prestado": "Ana",
    }
    assert md.block(after["content"]).inner == "**Patrick Rothfuss** · 700"
    assert after["content"].endswith("Lo que pensé al acabarlo.\n")


async def test_a_new_title_moves_it_and_the_links_follow(api, apps) -> None:
    await publish(apps, book())
    await derive(apps)
    await api.post(
        "/notes", json={"title": "Lecturas", "content": "Me gustó [[El nombre del viento]]."}
    )

    await publish(apps, book(title="El nombre del viento: Crónica del asesino de reyes"))
    await derive(apps)

    moved = await note_at(
        api, "Biblioteca/Libros/El nombre del viento - Crónica del asesino de reyes"
    )
    assert moved["title"] == "El nombre del viento - Crónica del asesino de reyes"
    reader = await note_at(api, "Lecturas")
    assert "[[El nombre del viento - Crónica del asesino de reyes]]" in reader["content"]


async def test_where_you_put_it_is_kept_while_the_app_does_not_rename_it(api, apps) -> None:
    await publish(apps, book())
    await derive(apps)
    note = await note_at(api, "Biblioteca/Libros/El nombre del viento")
    await api.post(f"/notes/{note['id']}/move", json={"folder": "Favoritos"})

    await publish(apps, book(body="Otra cosa"))
    await derive(apps)

    kept = (await api.get(f"/notes/{note['id']}")).json()
    assert kept["folder"] == "Favoritos"
    assert md.block(kept["content"]).inner == "Otra cosa"

    await publish(apps, book(title="Otro nombre", body="Otra cosa"))
    await derive(apps)
    renamed = (await api.get(f"/notes/{note['id']}")).json()
    assert (renamed["folder"], renamed["title"]) == ("Favoritos", "Otro nombre")


async def test_two_things_with_the_same_title_get_two_notes(api, apps) -> None:
    await publish(apps, book())
    await publish(apps, book(id="reading:2"))
    await derive(apps)

    tree = (await api.get("/tree")).json()
    titles = sorted(n["title"] for n in tree["notes"] if n["folder"] == "Biblioteca/Libros")
    assert titles == ["El nombre del viento", "El nombre del viento (2)"]


async def test_gone_from_its_app_it_goes_to_the_trash_unless_you_wrote_in_it(api, apps) -> None:
    await publish(apps, book())
    await publish(apps, book(id="reading:2", title="Otro libro"))
    await derive(apps)
    other = await note_at(api, "Biblioteca/Libros/Otro libro")
    await api.put(
        f"/notes/{other['id']}", json={"content": other["content"] + "\nMis notas del libro.\n"}
    )

    await publish(apps, book(removed=True, body="", properties={}))
    await publish(
        apps, book(id="reading:2", title="Otro libro", removed=True, body="", properties={})
    )
    assert (await derive(apps))["removed"] == 2

    trash = [n["title"] for n in (await api.get("/trash")).json()]
    assert trash == ["El nombre del viento"]
    kept = (await api.get(f"/notes/{other['id']}")).json()
    assert md.block(kept["content"]) is None
    assert kept["properties"] == {}
    assert kept["content"] == "Mis notas del libro.\n"
    assert kept["arga"] is None


async def test_what_you_sent_to_the_trash_stays_there(api, apps) -> None:
    await publish(apps, book())
    await derive(apps)
    note = await note_at(api, "Biblioteca/Libros/El nombre del viento")
    await api.delete(f"/notes/{note['id']}")

    await publish(apps, book(body="cambia en su app"))
    await derive(apps)

    assert [n["id"] for n in (await api.get("/trash")).json()] == [note["id"]]
    assert (await api.get("/notes/resolve", params={"target": "El nombre del viento"})).json()[
        "note"
    ] is None


async def test_what_happened_on_a_day_goes_to_the_daily_note(api, apps) -> None:
    await api.post("/daily", params={"day": "2026-09-30"})
    diary = await note_at(api, "2026-09-30")
    await api.put(f"/notes/{diary['id']}", json={"content": "Hoy, lluvia.\n"})
    day = {"day": "2026-09-30", "kind": "Día", "href": "/biblio/"}
    await publish(
        apps,
        {
            **day,
            "id": "day:2026-09-30",
            "title": "Lectura",
            "body": "- Terminaste un libro",
            "properties": {"paginas_leidas": 40},
        },
    )
    await publish(
        apps,
        {
            **day,
            "id": "day:2026-09-30",
            "title": "Comidas",
            "href": "/cocina/",
            "body": "2150 kcal",
            "properties": {"kcal": 2150, "paginas_leidas": 1},
        },
        app=OTHER_APP,
    )

    assert (await derive(apps))["days"] == 1

    note = await note_at(api, "2026-09-30")
    assert note["id"] == diary["id"]
    assert note["content"].startswith("---\n")
    assert note["properties"] == {"paginas_leidas": 40, "kcal": 2150}
    body = md.split(note["content"]).body
    assert body.startswith("Hoy, lluvia.\n\n%% arga %%\n")
    inner = md.block(note["content"]).inner
    assert inner == "### Biblioteca\n\n- Terminaste un libro\n\n### Cocina\n\n2150 kcal"
    assert note["arga"]["day"] is True
    assert [one["name"] for one in note["arga"]["apps"]] == ["Biblioteca", "Cocina"]

    await publish(
        apps,
        {**day, "id": "day:2026-09-30", "title": "Lectura", "removed": True},
    )
    await derive(apps)
    after = await note_at(api, "2026-09-30")
    assert md.block(after["content"]).inner == "### Cocina\n\n2150 kcal"
    assert after["properties"] == {"kcal": 2150, "paginas_leidas": 1}


async def test_a_day_without_a_note_gets_one_in_the_diary(api, apps) -> None:
    await publish(
        apps,
        {
            "id": "day:2026-09-29",
            "title": "Lectura",
            "kind": "Día",
            "href": "/biblio/",
            "day": "2026-09-29",
            "body": "- 20 páginas",
        },
    )
    await derive(apps)

    note = await note_at(api, "2026-09-29")
    assert note["folder"] == "Diario"
    assert md.block(note["content"]).inner == "### Biblioteca\n\n- 20 páginas"


async def test_neither_claude_nor_the_form_changes_what_an_app_writes(api, apps) -> None:
    await publish(apps, book())
    await derive(apps)
    path = "Biblioteca/Libros/El nombre del viento"

    edit = await api.post(
        "/tools/edit_note",
        json={"note": path, "old_text": "662 páginas", "new_text": "663 páginas"},
        headers=WRITE,
    )
    assert edit.status_code == 422
    assert "lo escribe Biblioteca" in edit.json()["detail"]
    prop = await api.post(
        "/tools/set_properties", json={"note": path, "set": {"autor": "Otro"}}, headers=WRITE
    )
    assert prop.status_code == 422
    note = await note_at(api, path)
    form = await api.put(f"/notes/{note['id']}/properties", json={"remove": ["tipo"]})
    assert form.status_code == 422

    mine = await api.post(
        "/tools/set_properties", json={"note": path, "set": {"leido_en": "tren"}}, headers=WRITE
    )
    assert mine.status_code == 200
    appended = await api.post(
        "/tools/append_to_note", json={"note": path, "text": "Una cita."}, headers=WRITE
    )
    assert appended.status_code == 200
    read = (await api.post("/tools/read_note", json={"note": path}, headers=WRITE)).json()
    assert read["content"]["of_apps"]["apps"] == ["Biblioteca"]


async def test_the_whole_text_from_the_app_keeps_what_is_not_yours(api, apps) -> None:
    await publish(apps, book())
    await derive(apps)
    note = await note_at(api, "Biblioteca/Libros/El nombre del viento")
    broken = note["content"].replace("662 páginas", "cambiado").replace("tipo: Libro\n", "")

    saved = (await api.put(f"/notes/{note['id']}", json={"content": broken + "Mío.\n"})).json()

    assert "662 páginas" in saved["content"] and saved["properties"]["tipo"] == "Libro"
    assert saved["content"].endswith("Mío.\n")

    versions = (await api.get(f"/notes/{note['id']}/revisions")).json()
    first = versions[-1]
    assert first["written_app"] == "Biblioteca"
    back = (await api.post(f"/notes/{note['id']}/revisions/{first['id']}/restore")).json()
    assert "662 páginas" in back["content"]


async def test_linking_a_thing_is_linking_its_note(api, apps, schema) -> None:
    await publish(apps, book(body="Parte de [[biblio:saga:1|la saga]]."))
    await publish(
        apps,
        book(
            id="saga:1",
            title="Crónica del asesino de reyes",
            kind="Saga",
            folder="Sagas",
            body="",
            properties={},
        ),
    )
    await derive(apps)
    mine = (
        await api.post(
            "/notes",
            json={"title": "Pendientes", "content": "Releer [[biblio:reading:1|el libro]]"},
        )
    ).json()
    ficha = await note_at(api, "Biblioteca/Libros/El nombre del viento")
    saga = await note_at(api, "Biblioteca/Sagas/Crónica del asesino de reyes")

    links = (await api.get(f"/notes/{mine['id']}/links")).json()
    assert links["links"][0]["note"]["id"] == ficha["id"]
    backlinks = (await api.get(f"/notes/{ficha['id']}/links")).json()["backlinks"]
    assert [b["note"]["title"] for b in backlinks] == ["Pendientes"]
    graph = (await api.get("/graph")).json()
    assert [mine["id"], ficha["id"]] in graph["edges"]
    assert [ficha["id"], saga["id"]] in graph["edges"]
    resolved = (await api.get("/notes/resolve", params={"target": "biblio:saga:1"})).json()["note"]
    assert resolved["id"] == saga["id"]
    offered = {one["target"]: one for one in (await api.get("/linkables")).json()}
    assert offered["biblio:reading:1"]["note_id"] == ficha["id"]

    async with schema.connect() as connection:
        mentioned = (
            (
                await connection.execute(
                    text(
                        "select payload->'mention'->>'id' as id from notebook.notebook_outbox "
                        "where type = 'notebook.mention'"
                    )
                )
            )
            .scalars()
            .all()
        )
    assert mentioned == ["reading:1"]


async def test_other_apps_listing_their_notes_do_not_get_fichas(api, apps) -> None:
    from arga_contracts import NotesList
    from notebook import service
    from notebook.db import engine

    await publish(apps, book(folder=""))
    await derive(apps)
    await api.post("/notes", json={"folder": "Biblioteca", "title": "Apunte", "content": "x"})

    async with engine().begin() as connection:
        await connection.execute(text('set local role "mod_notebook"'))
        found = await service.listed(connection, NotesList(folder="Biblioteca"))
    assert [n["title"] for n in found["notes"]] == ["Apunte"]


async def test_the_copy_opens_in_obsidian(api, apps, schema) -> None:
    await publish(apps, book())
    await derive(apps)
    await api.post(
        "/notes",
        json={"title": "Pendientes", "content": "Releer [[biblio:reading:1]] y [[biblio:x|y]]"},
    )

    async with schema.begin() as connection:
        await connection.execute(text('set local role "mod_notebook"'))
        found = await export.change(connection)

    assert found.texts["Pendientes.md"] == (
        "Releer [[Biblioteca/Libros/El nombre del viento|El nombre del viento]] y [[biblio:x|y]]"
    )
    assert "%% arga %%" in found.texts["Biblioteca/Libros/El nombre del viento.md"]


def test_a_big_copy_goes_in_batches_and_the_rest_stays_pending() -> None:
    found = export.Change(
        texts={f"n{i:03}.md": "x" for i in range(5)},
        binaries={"Adjuntos/a.png": "AA=="},
        deletes=["viejo.md"],
        hashes={**{f"n{i:03}.md": f"h{i}" for i in range(5)}, "Adjuntos/a.png": "ha"},
        by_claude=2,
    )

    first = export.batch(found, limit=3)

    assert sorted([*first.texts, *first.binaries, *first.deletes]) == [
        "Adjuntos/a.png",
        "n000.md",
        "n001.md",
    ]
    assert set(first.hashes) == {"Adjuntos/a.png", "n000.md", "n001.md"}
    assert export.batch(found, limit=100) is found


async def test_what_does_not_fit_the_contract_is_skipped(api, apps) -> None:
    await publish(apps, book())
    async with apps.begin() as connection:
        await connection.execute(
            text(
                "insert into kernel.events (ts, module, source, type, payload, user_id, "
                "dedup_hash) values (now(), :app, 'app', :type, cast(:payload as jsonb), "
                ":person, 'roto')"
            ),
            {
                "app": APP,
                "type": f"{APP}.record",
                "payload": json.dumps({"record": {"id": "x", "title": ""}}),
                "person": current_user.get(),
            },
        )

    assert await derive(apps) == {"notes": 1, "days": 0, "removed": 0, "skipped": 1}


async def test_one_record_that_cannot_be_written_does_not_stop_the_rest(
    api, apps, monkeypatch
) -> None:
    await publish(apps, book())
    await publish(apps, book(id="reading:2", title="El temor de un hombre sabio"))
    written = mirror._note

    async def fails_once(connection, app, app_name, item, placed, old):
        if item["id"] == "reading:2":
            raise RuntimeError("roto a posta")
        return await written(connection, app, app_name, item, placed, old)

    monkeypatch.setattr(mirror, "_note", fails_once)
    assert await derive(apps) == {"notes": 1, "days": 0, "removed": 0, "skipped": 1}
    await note_at(api, "Biblioteca/Libros/El nombre del viento")

    monkeypatch.setattr(mirror, "_note", written)
    assert (await derive(apps))["notes"] == 1
    await note_at(api, "Biblioteca/Libros/El temor de un hombre sabio")


async def test_what_an_app_rewrites_is_not_among_your_recent_notes(api, apps) -> None:
    from notebook import widgets
    from notebook.db import engine

    await publish(apps, book())
    await derive(apps)
    await api.post("/notes", json={"title": "Mía", "content": "x"})

    async with engine().begin() as connection:
        await connection.execute(text('set local role "mod_notebook_read"'))
        recent = await widgets.recent(connection)
    assert [row["label"] for row in recent["body"]["rows"]] == ["Mía"]


async def test_a_pass_that_only_looks_at_recent_days_still_applies_what_is_new(api, apps) -> None:
    await publish(apps, book())
    async with apps.begin() as connection:
        await connection.execute(
            text("update kernel.events set ts = now() where module = :app"), {"app": APP}
        )
    assert (await derive(apps, full=False))["notes"] == 1


async def test_search_says_where_each_thing_opens_and_whose_record_it_is(api, apps) -> None:
    await publish(apps, book())
    await derive(apps)
    mine = (await api.post("/notes", json={"title": "Viento en el huerto"})).json()

    found = (await api.get("/search", params={"q": "viento"})).json()

    by_title = {hit["title"]: hit for hit in found}
    record = by_title["El nombre del viento"]
    assert record["href"] == f"/notebook/nota/{record['id']}"
    assert record["source"] == {"app": APP, "name": "Biblioteca", "href": "/biblio/libro/1"}
    assert record["snippet"]
    assert by_title["Viento en el huerto"]["href"] == f"/notebook/nota/{mine['id']}"
    assert by_title["Viento en el huerto"]["source"] is None


async def test_the_search_of_arga_opens_a_record_in_its_app_and_a_note_in_notebook(
    api, apps
) -> None:
    await publish(apps, book())
    await derive(apps)
    mine = (await api.post("/notes", json={"title": "Viento", "folder": "Ideas"})).json()

    found = (await api.get("/search/arga", params={"q": "Viento", "limit": 8})).json()
    one = (await api.get("/search/arga", params={"q": "viento", "limit": 1})).json()
    nothing = (await api.get("/search/arga", params={"q": " "})).json()

    by_title = {hit["title"]: hit for hit in found["results"]}
    assert by_title["El nombre del viento"] == {
        "title": "El nombre del viento",
        "detail": "Biblioteca · Libros",
        "href": "/biblio/libro/1",
    }
    assert by_title["Viento"] == {
        "title": "Viento",
        "detail": "Nota · Ideas",
        "href": f"/notebook/nota/{mine['id']}",
    }
    assert len(one["results"]) == 1
    assert nothing == {"results": []}
