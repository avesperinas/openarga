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
OTHER_APP = "meals"
NAMES = {APP: "Library", OTHER_APP: "Meals"}
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
        "title": "The Wind Book",
        "kind": "Book",
        "href": "/biblio/book/1",
        "folder": "Books",
        "properties": {"author": "Synthetic Author", "rating": 4.5},
        "body": "**Synthetic Author** · 662 pages\n\n## Reading\nFrom 2 to 10 January.",
        **changes,
    }


async def note_at(api, path: str) -> dict:
    found = (await api.get("/notes/resolve", params={"target": path})).json()["note"]
    assert found is not None, f"no note at {path}"
    return (await api.get(f"/notes/{found['id']}")).json()


async def test_a_record_becomes_a_note_in_the_folder_of_its_app(api, apps) -> None:
    await publish(apps, book())

    assert await derive(apps) == {"notes": 1, "days": 0, "removed": 0, "skipped": 0}

    note = await note_at(api, "Library/Books/The Wind Book")
    assert note["folder"] == "Library/Books"
    assert note["properties"] == {
        "arga": "biblio:reading:1",
        "type": "Book",
        "author": "Synthetic Author",
        "rating": 4.5,
    }
    assert note["content"].startswith("---\narga: biblio:reading:1\ntype: Book\n")
    found = md.block(note["content"])
    assert found is not None and found.inner.startswith("**Synthetic Author**")
    assert note["updated_by"] == "import" and note["updated_app"] == "Library"
    assert note["arga"] == {
        "apps": [{"app": APP, "name": "Library", "href": "/biblio/book/1", "kind": "Book"}],
        "properties": ["arga", "type", "author", "rating"],
        "day": False,
    }
    assert await derive(apps) == {"notes": 0, "days": 0, "removed": 0, "skipped": 0}


async def test_what_you_write_stays_when_the_app_changes_its_part(api, apps) -> None:
    await publish(apps, book())
    await derive(apps)
    note = await note_at(api, "Library/Books/The Wind Book")
    mine = note["content"] + "\nWhat I thought when I finished it.\n"
    written = await api.put(f"/notes/{note['id']}", json={"content": mine})
    assert written.status_code == 200
    await api.put(f"/notes/{note['id']}/properties", json={"set": {"prestado": "Ana"}})

    await publish(
        apps, book(properties={"author": "Synthetic Author"}, body="**Synthetic Author** · 700")
    )
    await derive(apps)

    after = await note_at(api, "Library/Books/The Wind Book")
    assert after["properties"] == {
        "arga": "biblio:reading:1",
        "type": "Book",
        "author": "Synthetic Author",
        "prestado": "Ana",
    }
    assert md.block(after["content"]).inner == "**Synthetic Author** · 700"
    assert after["content"].endswith("What I thought when I finished it.\n")


async def test_a_new_title_moves_it_and_the_links_follow(api, apps) -> None:
    await publish(apps, book())
    await derive(apps)
    await api.post("/notes", json={"title": "Readings", "content": "I liked [[The Wind Book]]."})

    await publish(apps, book(title="The Wind Book: The Second Part"))
    await derive(apps)

    moved = await note_at(api, "Library/Books/The Wind Book - The Second Part")
    assert moved["title"] == "The Wind Book - The Second Part"
    reader = await note_at(api, "Readings")
    assert "[[The Wind Book - The Second Part]]" in reader["content"]


async def test_where_you_put_it_is_kept_while_the_app_does_not_rename_it(api, apps) -> None:
    await publish(apps, book())
    await derive(apps)
    note = await note_at(api, "Library/Books/The Wind Book")
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
    titles = sorted(n["title"] for n in tree["notes"] if n["folder"] == "Library/Books")
    assert titles == ["The Wind Book", "The Wind Book (2)"]


async def test_gone_from_its_app_it_goes_to_the_trash_unless_you_wrote_in_it(api, apps) -> None:
    await publish(apps, book())
    await publish(apps, book(id="reading:2", title="Another book"))
    await derive(apps)
    other = await note_at(api, "Library/Books/Another book")
    await api.put(
        f"/notes/{other['id']}", json={"content": other["content"] + "\nMy notes on the book.\n"}
    )

    await publish(apps, book(removed=True, body="", properties={}))
    await publish(
        apps, book(id="reading:2", title="Another book", removed=True, body="", properties={})
    )
    assert (await derive(apps))["removed"] == 2

    trash = [n["title"] for n in (await api.get("/trash")).json()]
    assert trash == ["The Wind Book"]
    kept = (await api.get(f"/notes/{other['id']}")).json()
    assert md.block(kept["content"]) is None
    assert kept["properties"] == {}
    assert kept["content"] == "My notes on the book.\n"
    assert kept["arga"] is None


async def test_what_you_sent_to_the_trash_stays_there(api, apps) -> None:
    await publish(apps, book())
    await derive(apps)
    note = await note_at(api, "Library/Books/The Wind Book")
    await api.delete(f"/notes/{note['id']}")

    await publish(apps, book(body="changes in its app"))
    await derive(apps)

    assert [n["id"] for n in (await api.get("/trash")).json()] == [note["id"]]
    assert (await api.get("/notes/resolve", params={"target": "The Wind Book"})).json()[
        "note"
    ] is None


async def test_what_happened_on_a_day_goes_to_the_daily_note(api, apps) -> None:
    await api.post("/daily", params={"day": "2026-09-30"})
    diary = await note_at(api, "2026-09-30")
    await api.put(f"/notes/{diary['id']}", json={"content": "Today, rain.\n"})
    day = {"day": "2026-09-30", "kind": "Day", "href": "/biblio/"}
    await publish(
        apps,
        {
            **day,
            "id": "day:2026-09-30",
            "title": "Reading",
            "body": "- You finished a book",
            "properties": {"pages_read": 40},
        },
    )
    await publish(
        apps,
        {
            **day,
            "id": "day:2026-09-30",
            "title": "Meals",
            "href": "/meals/",
            "body": "2150 kcal",
            "properties": {"kcal": 2150, "pages_read": 1},
        },
        app=OTHER_APP,
    )

    assert (await derive(apps))["days"] == 1

    note = await note_at(api, "2026-09-30")
    assert note["id"] == diary["id"]
    assert note["content"].startswith("---\n")
    assert note["properties"] == {"pages_read": 40, "kcal": 2150}
    body = md.split(note["content"]).body
    assert body.startswith("Today, rain.\n\n%% arga %%\n")
    inner = md.block(note["content"]).inner
    assert inner == "### Library\n\n- You finished a book\n\n### Meals\n\n2150 kcal"
    assert note["arga"]["day"] is True
    assert [one["name"] for one in note["arga"]["apps"]] == ["Library", "Meals"]

    await publish(
        apps,
        {**day, "id": "day:2026-09-30", "title": "Reading", "removed": True},
    )
    await derive(apps)
    after = await note_at(api, "2026-09-30")
    assert md.block(after["content"]).inner == "### Meals\n\n2150 kcal"
    assert after["properties"] == {"kcal": 2150, "pages_read": 1}


async def test_a_day_without_a_note_gets_one_in_the_diary(api, apps) -> None:
    await publish(
        apps,
        {
            "id": "day:2026-09-29",
            "title": "Reading",
            "kind": "Day",
            "href": "/biblio/",
            "day": "2026-09-29",
            "body": "- 20 pages",
        },
    )
    await derive(apps)

    note = await note_at(api, "2026-09-29")
    assert note["folder"] == "Diario"
    assert md.block(note["content"]).inner == "### Library\n\n- 20 pages"


async def test_neither_claude_nor_the_form_changes_what_an_app_writes(api, apps) -> None:
    await publish(apps, book())
    await derive(apps)
    path = "Library/Books/The Wind Book"

    edit = await api.post(
        "/tools/edit_note",
        json={"note": path, "old_text": "662 pages", "new_text": "663 pages"},
        headers=WRITE,
    )
    assert edit.status_code == 422
    assert "written by Library" in edit.json()["detail"]
    prop = await api.post(
        "/tools/set_properties", json={"note": path, "set": {"author": "Otro"}}, headers=WRITE
    )
    assert prop.status_code == 422
    note = await note_at(api, path)
    form = await api.put(f"/notes/{note['id']}/properties", json={"remove": ["type"]})
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
    assert read["content"]["of_apps"]["apps"] == ["Library"]


async def test_the_whole_text_from_the_app_keeps_what_is_not_yours(api, apps) -> None:
    await publish(apps, book())
    await derive(apps)
    note = await note_at(api, "Library/Books/The Wind Book")
    broken = note["content"].replace("662 pages", "changed").replace("type: Book\n", "")

    saved = (await api.put(f"/notes/{note['id']}", json={"content": broken + "Mine.\n"})).json()

    assert "662 pages" in saved["content"] and saved["properties"]["type"] == "Book"
    assert saved["content"].endswith("Mine.\n")

    versions = (await api.get(f"/notes/{note['id']}/revisions")).json()
    first = versions[-1]
    assert first["written_app"] == "Library"
    back = (await api.post(f"/notes/{note['id']}/revisions/{first['id']}/restore")).json()
    assert "662 pages" in back["content"]


async def test_linking_a_thing_is_linking_its_note(api, apps, schema) -> None:
    await publish(apps, book(body="Part of [[biblio:saga:1|the saga]]."))
    await publish(
        apps,
        book(
            id="saga:1",
            title="The Second Part",
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
            json={"title": "To do", "content": "Reread [[biblio:reading:1|the book]]"},
        )
    ).json()
    ficha = await note_at(api, "Library/Books/The Wind Book")
    saga = await note_at(api, "Library/Sagas/The Second Part")

    links = (await api.get(f"/notes/{mine['id']}/links")).json()
    assert links["links"][0]["note"]["id"] == ficha["id"]
    backlinks = (await api.get(f"/notes/{ficha['id']}/links")).json()["backlinks"]
    assert [b["note"]["title"] for b in backlinks] == ["To do"]
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


async def test_other_apps_listing_their_notes_do_not_get_cards(api, apps) -> None:
    from arga_contracts import NotesList
    from notebook import service
    from notebook.db import engine

    await publish(apps, book(folder=""))
    await derive(apps)
    await api.post("/notes", json={"folder": "Library", "title": "Apunte", "content": "x"})

    async with engine().begin() as connection:
        await connection.execute(text('set local role "mod_notebook"'))
        found = await service.listed(connection, NotesList(folder="Library"))
    assert [n["title"] for n in found["notes"]] == ["Apunte"]


async def test_the_copy_opens_in_obsidian(api, apps, schema) -> None:
    await publish(apps, book())
    await derive(apps)
    await api.post(
        "/notes",
        json={"title": "To do", "content": "Reread [[biblio:reading:1]] and [[biblio:x|y]]"},
    )

    async with schema.begin() as connection:
        await connection.execute(text('set local role "mod_notebook"'))
        found = await export.change(connection)

    assert found.texts["To do.md"] == (
        "Reread [[Library/Books/The Wind Book|The Wind Book]] and [[biblio:x|y]]"
    )
    assert "%% arga %%" in found.texts["Library/Books/The Wind Book.md"]


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
    await publish(apps, book(id="reading:2", title="The Rain Book"))
    written = mirror._note

    async def fails_once(connection, app, app_name, item, placed, old):
        if item["id"] == "reading:2":
            raise RuntimeError("roto a posta")
        return await written(connection, app, app_name, item, placed, old)

    monkeypatch.setattr(mirror, "_note", fails_once)
    assert await derive(apps) == {"notes": 1, "days": 0, "removed": 0, "skipped": 1}
    await note_at(api, "Library/Books/The Wind Book")

    monkeypatch.setattr(mirror, "_note", written)
    assert (await derive(apps))["notes"] == 1
    await note_at(api, "Library/Books/The Rain Book")


async def test_what_an_app_rewrites_is_not_among_your_recent_notes(api, apps) -> None:
    from notebook import widgets
    from notebook.db import engine

    await publish(apps, book())
    await derive(apps)
    await api.post("/notes", json={"title": "Mine", "content": "x"})

    async with engine().begin() as connection:
        await connection.execute(text('set local role "mod_notebook_read"'))
        recent = await widgets.recent(connection)
    assert [row["label"] for row in recent["body"]["rows"]] == ["Mine"]


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
    mine = (await api.post("/notes", json={"title": "Wind in the orchard"})).json()

    found = (await api.get("/search", params={"q": "wind"})).json()

    by_title = {hit["title"]: hit for hit in found}
    record = by_title["The Wind Book"]
    assert record["href"] == f"/notebook/note/{record['id']}"
    assert record["source"] == {"app": APP, "name": "Library", "href": "/biblio/book/1"}
    assert record["snippet"]
    assert by_title["Wind in the orchard"]["href"] == f"/notebook/note/{mine['id']}"
    assert by_title["Wind in the orchard"]["source"] is None


async def test_the_search_of_arga_opens_a_record_in_its_app_and_a_note_in_notebook(
    api, apps
) -> None:
    await publish(apps, book())
    await derive(apps)
    mine = (await api.post("/notes", json={"title": "Wind", "folder": "Ideas"})).json()

    found = (await api.get("/search/arga", params={"q": "Wind", "limit": 8})).json()
    one = (await api.get("/search/arga", params={"q": "wind", "limit": 1})).json()
    nothing = (await api.get("/search/arga", params={"q": " "})).json()

    by_title = {hit["title"]: hit for hit in found["results"]}
    assert by_title["The Wind Book"] == {
        "title": "The Wind Book",
        "detail": "Library · Books",
        "href": "/biblio/book/1",
    }
    assert by_title["Wind"] == {
        "title": "Wind",
        "detail": "Note · Ideas",
        "href": f"/notebook/note/{mine['id']}",
    }
    assert len(one["results"]) == 1
    assert nothing == {"results": []}
