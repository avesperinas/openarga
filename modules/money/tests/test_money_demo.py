from __future__ import annotations

from datetime import timedelta
from pathlib import Path

import pytest
from sqlalchemy import text

from arga_module import demo as cast_of
from arga_tenancy import current_spaces, current_user
from money import book as books
from money import demo
from money.api import as_app
from money.texts import today

CAST = cast_of.load(Path(__file__).resolve().parents[3] / "demo" / "personas.yaml")
TODAY = today()
TABLES = (
    "money_v1_account",
    "money_v1_category",
    "money_v1_rule",
    "money_v1_entry",
    "money_v1_income",
    "money_v1_valuation",
    "money_v1_statement_line",
    "money_v1_statement_balance",
    "money_v1_position",
    "money_v1_fund",
)


@pytest.fixture(autouse=True)
def fresh_cache():
    books._CACHE.clear()
    yield
    books._CACHE.clear()


async def counts() -> dict[str, int]:
    async with as_app() as connection:
        return {
            table: await connection.scalar(text(f"select count(*) from money.{table}"))
            for table in TABLES
        }


async def seed_everyone() -> dict[str, dict[str, int]]:
    seen = {}
    for persona in CAST.people:
        token = current_user.set(persona.id)
        spaces = current_spaces.set((CAST.space_id,))
        try:
            async with as_app() as connection:
                await demo.seed(connection, persona, TODAY)
            seen[persona.key] = await counts()
        finally:
            current_spaces.reset(spaces)
            current_user.reset(token)
    return seen


async def test_the_seed_runs_twice_without_duplicates(schema) -> None:
    first = await seed_everyone()
    again = await seed_everyone()

    assert first["alex"] == again["alex"] and first["sam"] == again["sam"]
    assert first["alex"]["money_v1_statement_line"] > 200
    assert first["alex"]["money_v1_position"] == 2 and first["sam"]["money_v1_position"] == 1
    assert first["alex"]["money_v1_entry"] > 60 and first["sam"]["money_v1_entry"] == 0


async def test_alex_has_eighteen_months_that_add_up(api) -> None:
    await seed_everyone()
    token = current_user.set(CAST.people[0].id)
    try:
        summary = (await api.get("/summary")).json()
        networth = next(k for k in summary["kpis"] if k["key"] == "networth")
        assert networth["value"] > 0
        rows = (
            await api.get(
                "/movements",
                params={"from": (TODAY - timedelta(days=399)).isoformat(), "to": TODAY.isoformat()},
            )
        ).json()["movements"]
        assert len(rows) > 150
        assert {"everyday", "savings"} <= {r["account"] for r in rows}
        card = (await api.get("/accounts/brokerage/positions")).json()
        assert [p["symbol"] for p in card["positions"]] == ["IE00B4L5Y983", "IE00BKM4GZ66"]
        assert card["value"] > card["cost"] and card["currency"] == "EUR"
        classified = (await api.get("/funds")).json()
        assert {f["classified"] for f in classified if f["symbol"].startswith("IE")} == {"yours"}
    finally:
        current_user.reset(token)


async def test_sam_sees_only_sam(api) -> None:
    await seed_everyone()
    token = current_user.set(CAST.people[1].id)
    try:
        card = (await api.get("/accounts/brokerage/positions")).json()
        assert [p["symbol"] for p in card["positions"]] == ["IE00B4L5Y983"]
    finally:
        current_user.reset(token)
