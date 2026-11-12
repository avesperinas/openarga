from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from arga_tenancy import CURRENT_USER_SQL, current_spaces

KEY = "carrera.net_year"

SOURCES = text("select year, person, source from money.money_v1_income_source")

FIGURES = text("""
    select distinct on (left(payload->'metric'->>'day', 4))
           left(payload->'metric'->>'day', 4)::int as year,
           (payload->'metric'->>'value')::numeric as value
    from money.events
    where payload ? 'metric' and payload->'metric'->>'key' = :key
    order by left(payload->'metric'->>'day', 4), payload->'metric'->>'day' desc, ingested_at desc
""")

FIGURES_PRINT = text("""
    select count(*) as n, max(ingested_at) as last
    from money.events
    where payload ? 'metric' and payload->'metric'->>'key' = :key
""")

OTHERS = text(f"""
    select year, amount from money.money_v1_space_income
    where space_id = :space and user_id <> {CURRENT_USER_SQL}
""")

OTHERS_PRINT = text("""
    select count(*) as n, max(updated_at) as last
    from money.money_v1_space_income where space_id = :space
""")


@dataclass(frozen=True)
class Incomes:
    sources: dict[tuple[int, str], str]
    mine: dict[int, Decimal]
    theirs: dict[int, Decimal]
    space_id: UUID | None

    @classmethod
    def empty(cls) -> Incomes:
        return cls({}, {}, {}, None)


def linked(space: UUID | None) -> UUID | None:
    return space if space is not None and space in current_spaces.get() else None


async def fingerprint(connection: AsyncConnection, space: UUID | None) -> tuple:
    mine = (await connection.execute(FIGURES_PRINT, {"key": KEY})).first()
    out: tuple = (mine.n, mine.last)
    if space is not None:
        theirs = (await connection.execute(OTHERS_PRINT, {"space": space})).first()
        out += (space, theirs.n, theirs.last)
    return out


async def load(connection: AsyncConnection, space: UUID | None) -> Incomes:
    sources = {(r.year, r.person): r.source for r in (await connection.execute(SOURCES)).all()}
    mine = {
        r.year: Decimal(str(r.value))
        for r in (await connection.execute(FIGURES, {"key": KEY})).all()
    }
    theirs = (
        {
            r.year: Decimal(str(r.amount))
            for r in (await connection.execute(OTHERS, {"space": space})).all()
        }
        if space is not None
        else {}
    )
    return Incomes(sources, mine, theirs, space)


def source_of(found: Incomes, year: int, person: str) -> str:
    return found.sources.get((year, person), "typed")


def from_carrera(found: Incomes, year: int, person: str) -> Decimal | None:
    if source_of(found, year, person) != "carrera":
        return None
    return (found.mine if person == "me" else found.theirs).get(year)


def fixed(found: Incomes, year: int) -> dict[str, Decimal]:
    out = {}
    for person in ("me", "other"):
        value = from_carrera(found, year, person)
        if value is not None:
            out[person] = value
    return out


def missing(found: Incomes, year: int) -> list[str]:
    return [
        person
        for person in ("me", "other")
        if source_of(found, year, person) == "carrera" and from_carrera(found, year, person) is None
    ]


SHARE = text("""
    insert into money.money_v1_space_income (space_id, year, amount)
    values (:space, :year, :amount)
    on conflict (space_id, user_id, year) do update
    set amount = excluded.amount, updated_at = now()
    where money.money_v1_space_income.amount is distinct from excluded.amount
""")

UNSHARE = text(f"""
    delete from money.money_v1_space_income
    where user_id = {CURRENT_USER_SQL} and (space_id <> :space or not (year = any(:years)))
""")

UNSHARE_ALL = text(f"""
    delete from money.money_v1_space_income where user_id = {CURRENT_USER_SQL}
""")


async def share(connection: AsyncConnection, found: Incomes) -> bool:
    years = sorted(
        year
        for (year, person), source in found.sources.items()
        if person == "me" and source == "carrera" and year in found.mine
    )
    if found.space_id is None:
        gone = await connection.execute(UNSHARE_ALL)
        return gone.rowcount > 0
    changed = (
        await connection.execute(UNSHARE, {"space": found.space_id, "years": years})
    ).rowcount > 0
    for year in years:
        done = await connection.execute(
            SHARE, {"space": found.space_id, "year": year, "amount": found.mine[year]}
        )
        changed = changed or done.rowcount > 0
    return changed
