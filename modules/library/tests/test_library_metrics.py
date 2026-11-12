from __future__ import annotations

from sqlalchemy import text
from test_library_records import add

import arga_contracts as contracts
from library import metrics
from library.db import engine


async def built() -> dict[str, dict]:
    async with engine().begin() as connection:
        await connection.execute(text('set local role "mod_library"'))
        found = await metrics.build(connection)
    for one in found:
        assert one == contracts.metric("library", **one)
    return {contracts.metric_identity(one): one for one in found}


async def test_a_finished_book_counts_its_day_and_spreads_its_pages(api) -> None:
    await add(
        api,
        "Un libro sintético",
        {"status": "read", "started_on": "2026-08-01", "finished_on": "2026-08-10"},
        pages=300,
    )
    await add(api, "Uno a medias", {"status": "reading", "started_on": "2026-09-01"})

    found = await built()

    assert found["library.books_finished@2026-08-10"]["value"] == 1
    assert found["library.pages@2026-08-01"]["value"] == 30
    assert found["library.pages@2026-08-10"]["value"] == 30
    assert not [key for key in found if key.startswith("library.pages@2026-09")]
