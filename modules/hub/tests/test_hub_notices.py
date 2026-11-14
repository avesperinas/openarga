from __future__ import annotations

from datetime import UTC, datetime, timedelta

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


async def lost(schema, account, key: str, outcome: str, code: str | None, ago: timedelta) -> None:
    async with schema.begin() as connection:
        await connection.execute(
            text(
                "insert into hub.hub_run (connection_id, capability, operation, "
                "idempotency_key, started_at, finished_at, outcome, code, detail) "
                "values (:c, 'action', 'run', :key, :at, :at, :outcome, :code, :detail)"
            ),
            {
                "c": account,
                "key": key,
                "at": datetime.now(UTC) - ago,
                "outcome": outcome,
                "code": code,
                "detail": "Sin hueco en tu uso de Claude: «Principal»: la semana va al 99 %.",
            },
        )


async def test_a_run_no_account_could_do_says_so_until_one_goes_well(schema) -> None:
    account = await connect(schema, "Principal", provider="claude")
    await lost(
        schema, account, "insights:morning:2026-10-20", "skipped", "no_room", timedelta(hours=3)
    )
    [notice] = await built()
    assert notice["kind"] == "claude_blocked"
    assert notice["title"] == "Insights could not use your Claude"
    assert "99 %" in notice["body"]

    await lost(schema, account, "insights:morning:2026-10-20#2", "ok", None, timedelta(hours=1))
    assert await built() == []
