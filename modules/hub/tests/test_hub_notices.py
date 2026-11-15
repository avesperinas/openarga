from __future__ import annotations

from datetime import timedelta

from sqlalchemy import text
from test_hub_connections import NOW, connect, ran

from hub import notices
from hub.db import engine


async def built() -> list[dict]:
    async with engine().begin() as connection:
        await connection.execute(text('set local role "mod_hub"'))
        return await notices.build(connection)


async def test_three_errors_in_a_row_say_a_source_fails(schema) -> None:
    broken = await connect(schema, "Bitvavo")
    await ran(schema, broken, "ok", timedelta(hours=4))
    await ran(schema, broken, "error", timedelta(hours=3))
    await ran(schema, broken, "error", timedelta(hours=2))
    assert await built() == []

    await ran(
        schema, broken, "error", timedelta(hours=1), detail="Bitvavo 403 305: No active API key."
    )
    [notice] = await built()
    assert notice["kind"] == "failing" and notice["title"] == "Bitvavo brings no data"
    assert "No active API key" in notice["body"] and notice["href"] == "/hub"


async def test_a_bank_consent_warns_a_week_before_and_the_day(schema) -> None:
    await connect(schema, "Banco sintético", consent_expires_at=NOW + timedelta(days=30))
    found = await built()
    assert [one["kind"] for one in found] == ["reauth", "reauth"]
    days = sorted(one["at"][:10] for one in found)
    expires = (NOW + timedelta(days=30)).date()
    assert days == [(expires - timedelta(days=7)).isoformat(), expires.isoformat()]
