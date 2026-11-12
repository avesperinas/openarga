from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import text

from arga_testing import fresh_modules
from arga_testing import manifests as repo_manifests
from kernel.db import engine

REPO = Path(__file__).resolve().parents[2]
MODULES = REPO / "modules"

FOREIGN_KEYS = text("""
    select n.nspname || '.' || c.relname as table_, con.conname as name,
           (select string_agg(a.attname, ', ' order by k.n)
              from unnest(con.conkey) with ordinality as k(attnum, n)
              join pg_attribute a on a.attrelid = con.conrelid and a.attnum = k.attnum) as columns
    from pg_constraint con
    join pg_class c on c.oid = con.conrelid
    join pg_namespace n on n.oid = c.relnamespace
    where con.contype = 'f'
      and n.nspname = any(:schemas)
      and not exists (
        select 1 from pg_index i
        where i.indrelid = con.conrelid
          and (i.indkey::int2[])[0:cardinality(con.conkey) - 1] = con.conkey
      )
    order by 1, 2
""")

OWNERS = text("""
    select n.nspname || '.' || c.relname as table_
    from pg_class c
    join pg_namespace n on n.oid = c.relnamespace
    join pg_attribute a on a.attrelid = c.oid and a.attname = 'user_id' and not a.attisdropped
    where c.relkind in ('r', 'p')
      and n.nspname = any(:schemas)
      and not exists (
        select 1 from pg_index i where i.indrelid = c.oid and i.indkey[0] = a.attnum
      )
    order by 1
""")


@pytest.fixture
async def schemas(database_url: str) -> list[str]:
    manifests = repo_manifests(MODULES)
    async with engine().begin() as connection:
        await fresh_modules(connection, *(m.id for m in manifests))
    return ["kernel", *(m.id for m in manifests)]


async def test_every_foreign_key_has_its_index(schemas: list[str]) -> None:
    async with engine().connect() as connection:
        missing = (await connection.execute(FOREIGN_KEYS, {"schemas": schemas})).all()
    assert not missing, "claves foráneas sin índice:\n" + "\n".join(
        f"  {row.table_} ({row.columns})  [{row.name}]" for row in missing
    )


async def test_every_owned_table_has_an_index_by_its_owner(schemas: list[str]) -> None:
    async with engine().connect() as connection:
        missing = [
            row.table_ for row in (await connection.execute(OWNERS, {"schemas": schemas})).all()
        ]
    assert not missing, "tablas con user_id y sin índice que empiece por él:\n  " + "\n  ".join(
        missing
    )


FIGURE = """
    select distinct on (left(payload->'metric'->>'day', 4)) payload
    from kernel.events where type = any(array['money.metric', 'vitals.metric'])
      and payload ? 'metric' and payload->'metric'->>'key' = 'income'
    order by left(payload->'metric'->>'day', 4), payload->'metric'->>'day' desc
"""
RECORD = """
    select payload from kernel.events
    where type = any(array['training.record'])
      and payload ? 'record' and payload->'record'->>'id' = 'x'
"""


@pytest.mark.parametrize(
    ("query", "index"), [(FIGURE, "events_metric_key_day_idx"), (RECORD, "events_record_id_idx")]
)
async def test_figures_and_records_have_an_index_that_serves_them(
    database_url: str, query: str, index: str
) -> None:
    async with engine().connect() as connection:
        await connection.execute(text("set local enable_seqscan = off"))
        # On an empty table the type index ties on cost and wins; without it the plan shows
        # whether the index under test can serve the query at all.
        await connection.execute(text("drop index kernel.events_type_idx"))
        plan = "\n".join((await connection.execute(text(f"explain {query}"))).scalars())
        await connection.rollback()
    assert index in plan, plan
