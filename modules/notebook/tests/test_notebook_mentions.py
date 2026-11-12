from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from sqlalchemy import text

from arga_tenancy import current_user

MODULES = Path(__file__).resolve().parents[2]


async def outbox(schema) -> list[dict]:
    async with schema.connect() as connection:
        rows = (
            await connection.execute(
                text(
                    "select payload from notebook.notebook_outbox where type = 'notebook.mention' "
                    "order by id"
                )
            )
        ).all()
    return [row.payload["mention"] for row in rows]


async def test_a_link_to_another_app_is_announced_updated_and_withdrawn(api, schema) -> None:
    note = (
        await api.post(
            "/notes",
            json={"title": "Técnica", "content": "Bajar la carga: [[training:v-1|Press banca]]\n"},
        )
    ).json()
    await api.post(f"/notes/{note['id']}/move", json={"title": "Técnica de banca"})
    await api.put(f"/notes/{note['id']}", json={"content": "Ya no.\n"})

    announced = await outbox(schema)

    assert [(m["app"], m["id"], m["note_title"], m["removed"]) for m in announced] == [
        ("training", "v-1", "Técnica", False),
        ("training", "v-1", "Técnica de banca", False),
        ("training", "v-1", "Técnica de banca", True),
    ]
    assert announced[0]["line"] == "Bajar la carga: [[training:v-1|Press banca]]"
    assert announced[0]["note_href"] == f"/notebook/nota/{note['id']}"


async def test_the_trash_withdraws_and_restoring_announces_again(api, schema) -> None:
    note = (await api.post("/notes", json={"title": "N", "content": "[[training:v-2]]"})).json()
    await api.delete(f"/notes/{note['id']}")
    await api.post(f"/trash/{note['id']}/restore")

    assert [m["removed"] for m in await outbox(schema)] == [False, True, False]


async def test_a_link_between_notes_is_not_a_mention(api, schema) -> None:
    await api.post("/notes", json={"title": "A", "content": "[[B]] y [[training:|nada]]"})

    assert await outbox(schema) == []


async def test_what_other_apps_publish_as_linkable_is_offered(api, schema) -> None:

    from arga_testing import fresh_modules

    async with schema.begin() as connection:
        await fresh_modules(connection, "notebook", "training", fresh=["training"])
        await connection.execute(text("delete from kernel.events where module = 'training'"))
        person = current_user.get()
        for item, ts in (
            (
                {
                    "id": "v-1",
                    "title": "Press banca",
                    "kind": "Ejercicio",
                    "href": "/training/stats?variante=v-1",
                },
                "2026-09-28T10:00:00Z",
            ),
            (
                {
                    "id": "v-1",
                    "title": "Press de banca",
                    "kind": "Ejercicio",
                    "href": "/training/stats?variante=v-1",
                },
                "2026-09-28T11:00:00Z",
            ),
            (
                {
                    "id": "v-2",
                    "title": "Sentadilla",
                    "kind": "Ejercicio",
                    "href": "/training/stats?variante=v-2",
                    "removed": True,
                },
                "2026-09-28T10:00:00Z",
            ),
        ):
            await connection.execute(
                text(
                    "insert into kernel.events "
                    "(ts, module, source, type, payload, user_id, dedup_hash) "
                    "values (:ts, 'training', 'app', 'training.variant', "
                    "cast(:payload as jsonb), :person, md5(cast(:ts2 as text) || :title))"
                ),
                {
                    "ts": datetime.fromisoformat(ts),
                    "ts2": ts,
                    "title": item["title"],
                    "payload": json.dumps({"linkable": item}),
                    "person": person,
                },
            )
    try:
        offered = (await api.get("/linkables")).json()
    finally:
        async with schema.begin() as connection:
            await connection.execute(text("delete from kernel.events where module = 'training'"))
            await connection.execute(text("delete from kernel.modules where id = 'training'"))

    assert offered == [
        {
            "app": "training",
            "id": "v-1",
            "target": "training:v-1",
            "title": "Press de banca",
            "kind": "Ejercicio",
            "href": "/training/stats?variante=v-1",
            "note_id": None,
        }
    ]
