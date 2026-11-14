from __future__ import annotations

import json
import os
from datetime import date

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

import arga_contracts as contracts
from arga_contracts import records
from arga_contracts.records import OUTBOX_KEY

TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL", "postgresql+asyncpg://openarga:changeme@localhost:5433/openarga"
)
APP = "zzrecords"


def book(**changes) -> dict:
    return contracts.record(
        **{
            "id": "reading:1",
            "title": "El nombre del viento",
            "kind": "Libro",
            "href": "/library/libro/1",
            "folder": "Libros",
            "properties": {"autor": "Patrick Rothfuss", "valoracion": 4.5, "paginas": 662},
            "body": "**Patrick Rothfuss** · 2007",
            **changes,
        }
    )


def test_a_record_is_a_note_of_an_app_or_a_day() -> None:
    found = book()
    assert found["day"] is None and found["removed"] is False
    assert found["properties"]["valoracion"] == 4.5
    day = contracts.record(
        id="day:2026-09-30",
        title="Comidas",
        kind="Día",
        href="/macros/",
        day=date(2026, 9, 30),
        properties={"kcal": 2150, "proteina_g": 160.5},
        body="2150 kcal",
    )
    assert day["day"] == "2026-09-30"


@pytest.mark.parametrize(
    ("changes", "where"),
    [
        ({"properties": {"Valoración": 4}}, "properties"),
        ({"properties": {"arga": "otro:1"}}, "whoever writes"),
        ({"properties": {"tipo": "Otro"}}, "whoever writes"),
        ({"properties": {"type": "Other"}}, "whoever writes"),
        ({"properties": {"nota": float("nan")}}, "finite number"),
        ({"properties": {"nota": {"a": 1}}}, "properties"),
        ({"folder": "Libros/../Otros"}, "folder"),
        ({"folder": "/Libros"}, "folder"),
        ({"href": "https://fuera.example"}, "href"),
        ({"id": "con espacio"}, "id"),
        ({"body": "a\n%% arga %%\nb"}, "block markers"),
    ],
)
def test_a_record_that_does_not_fit_fails_where_it_is_written(changes, where) -> None:
    with pytest.raises(contracts.BadContract, match=where):
        book(**changes)


def test_how_things_are_written_is_the_same_in_every_app() -> None:
    assert records.number(11200) == "11.200"
    assert records.euros(-45.2) == "-45,20 €"
    assert records.trimmed(78.20) == "78,2"
    assert records.trimmed(80.0) == "80"
    assert records.long_date(date(2026, 1, 2)) == "2 de enero de 2026"
    assert records.link("training", "variant:1", "Press [banca] | plano") == (
        "[[training:variant:1|Press (banca) - plano]]"
    )
    assert records.table(["A", "B"], [["x|y", None]]) == "| A | B |\n| --- | --- |\n| x\\|y |  |"
    assert records.sections("a", "", None, "b\n") == "a\n\nb"
    assert records.property_name("Primera matriculación") == "primera_matriculacion"
    assert records.property_name("Kilómetros a fecha de") == "kilometros_a_fecha_de"
    assert records.property_name("2º titular") == "c_2o_titular"
    assert records.property_name("Tipo") == "tipo_"
    assert records.property_name("Type") == "type_"


@pytest.fixture
async def outbox():
    engine = create_async_engine(TEST_DATABASE_URL)
    async with engine.begin() as connection:
        await connection.execute(text(f"drop schema if exists {APP} cascade"))
        await connection.execute(text(f"create schema {APP}"))
        await connection.execute(
            text(
                f"create table {APP}.{APP}_outbox ("
                "  id bigint generated always as identity primary key,"
                "  type text not null, ts timestamptz not null default now(),"
                "  payload jsonb not null, dedup_hash text not null,"
                "  published_at timestamptz,"
                "  user_id uuid not null default '00000000-0000-0000-0000-000000000001',"
                f"  key text generated always as ({OUTBOX_KEY}) stored,"
                "  unique (user_id, dedup_hash))"
            )
        )
    yield engine
    async with engine.begin() as connection:
        await connection.execute(text(f"drop schema if exists {APP} cascade"))
    await engine.dispose()


async def queued(engine) -> list[dict]:
    async with engine.begin() as connection:
        rows = (
            await connection.execute(
                text(f"select type, payload from {APP}.{APP}_outbox order by id")
            )
        ).all()
    for row in rows:
        assert row.type == f"{APP}.record"
    return [row.payload["record"] for row in rows]


async def test_only_what_changed_is_queued_and_what_is_gone_is_removed(outbox) -> None:
    async with outbox.begin() as connection:
        first = await records.publish(connection, APP, [book(), book(id="reading:2", title="Otro")])
    assert first == {"added": 2, "changed": 0, "removed": 0}

    async with outbox.begin() as connection:
        again = await records.publish(connection, APP, [book(), book(id="reading:2", title="Otro")])
    assert again == {"added": 0, "changed": 0, "removed": 0}
    assert len(await queued(outbox)) == 2

    async with outbox.begin() as connection:
        changed = await records.publish(connection, APP, [book(properties={"valoracion": 5})])
    assert changed == {"added": 0, "changed": 1, "removed": 1}
    items = await queued(outbox)
    assert items[2]["properties"] == {"valoracion": 5}
    gone = items[3]
    assert gone["id"] == "reading:2" and gone["removed"] is True and gone["body"] == ""
    assert gone["title"] == "Otro"

    async with outbox.begin() as connection:
        back = await records.publish(
            connection,
            APP,
            [book(properties={"valoracion": 5}), book(id="reading:2", title="Otro")],
        )
    assert back == {"added": 1, "changed": 0, "removed": 0}


async def test_going_back_to_what_it_said_before_is_a_new_event(outbox) -> None:
    for version in (4.5, 3, 4.5):
        async with outbox.begin() as connection:
            await records.publish(connection, APP, [book(properties={"valoracion": version})])
    assert [item["properties"]["valoracion"] for item in await queued(outbox)] == [4.5, 3, 4.5]


async def test_what_was_overtaken_long_ago_is_pruned_and_the_last_of_each_thing_stays(
    outbox,
) -> None:
    for version in (1, 2, 3):
        async with outbox.begin() as connection:
            await records.publish(connection, APP, [book(properties={"valoracion": version})])
    async with outbox.begin() as connection:
        await records.publish(
            connection,
            APP,
            [book(properties={"valoracion": 3}), book(id="reading:2", title="Otro")],
        )
    async with outbox.begin() as connection:
        await connection.execute(
            text(
                f"update {APP}.{APP}_outbox set published_at = now() - interval '30 days' "
                "where payload->'record'->'properties'->>'valoracion' = '1'"
            )
        )
        await connection.execute(
            text(
                f"update {APP}.{APP}_outbox set published_at = now() - interval '1 day' "
                "where payload->'record'->'properties'->>'valoracion' = '2'"
            )
        )
        await records.publish(
            connection,
            APP,
            [book(properties={"valoracion": 3}), book(id="reading:2", title="Otro")],
        )

    left = [(item["id"], item["properties"].get("valoracion")) for item in await queued(outbox)]
    assert left == [("reading:1", 2), ("reading:1", 3), ("reading:2", 4.5)]
    async with outbox.begin() as connection:
        last = (
            await connection.execute(text(records.last_published(APP)), {"type": f"{APP}.record"})
        ).all()
    assert {row.item["id"]: row.item["properties"].get("valoracion") for row in last} == {
        "reading:1": 3,
        "reading:2": 4.5,
    }


async def test_a_prune_that_fails_does_not_take_the_records_with_it(outbox, monkeypatch) -> None:
    monkeypatch.setattr(records, "prune_superseded", lambda app: "select no_existe()")
    async with outbox.begin() as connection:
        first = await records.publish(connection, APP, [book()])
    assert first == {"added": 1, "changed": 0, "removed": 0}
    assert len(await queued(outbox)) == 1


async def test_the_same_id_twice_is_a_bug_of_whoever_builds_them(outbox) -> None:
    async with outbox.begin() as connection:
        with pytest.raises(contracts.BadContract, match="repeated"):
            await records.publish(connection, APP, [book(), book()])


def test_an_app_id_that_is_not_one_is_refused() -> None:
    with pytest.raises(ValueError, match="not an app id"):
        records.last_published('x"; drop table y; --')


def test_every_says_now_the_first_time_and_then_waits() -> None:
    every = records.Every(3600)
    assert every.due("ana") is True
    assert every.due("ana") is False
    assert every.due("luis") is True


def test_the_payload_travels_as_json() -> None:
    assert json.loads(json.dumps({contracts.RECORD: book()}))["record"]["id"] == "reading:1"
