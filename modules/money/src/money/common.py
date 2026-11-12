from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from types import SimpleNamespace
from typing import TYPE_CHECKING, Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from arga_tenancy import CURRENT_USER_SQL as ME
from money.interpret import fold
from money.shared import HALF, ZERO, Month, year_months

if TYPE_CHECKING:
    from money.book import Loaded
    from money.model import Category

KEEPER = "keeper"
MEMBER = "member"
ALONE = "alone"


def keeps(lo: Loaded) -> bool:
    return lo.settings.space_id is not None and any(
        a.shared_space for a in lo.book.accounts.values()
    )


def role_of(lo: Loaded) -> str:
    if lo.settings.space_id is None:
        return ALONE
    return KEEPER if keeps(lo) else MEMBER


ENTRIES = text("""
    select id, paid_by, on_date, amount, description, category, origin_id, user_id, created_at
    from money.money_v1_common_entry
    where space_id = cast(:space as uuid)
    order by on_date, created_at
""")


async def entries_fingerprint(connection: AsyncConnection, space: UUID | None) -> tuple:
    if space is None:
        return ()
    row = (
        await connection.execute(
            text(
                "select count(*) as n, max(created_at) as last, coalesce(sum(amount), 0) as total "
                "from money.money_v1_common_entry where space_id = cast(:space as uuid)"
            ),
            {"space": str(space)},
        )
    ).one()
    return (row.n, row.last, row.total)


async def entries_for_keeper(
    connection: AsyncConnection,
    space: UUID,
    user: UUID | None,
    own: list[Any],
    cats: dict[str, Category],
) -> list[Any]:
    by_name = {
        fold(c.name): c.id
        for c in cats.values()
        if c.nature == "expense" and c.ownership == "shared"
    }
    rows = (await connection.execute(ENTRIES, {"space": str(space)})).all()
    copied = {str(r.origin_id) for r in rows if r.origin_id}
    out = [e for e in own if str(e.id) not in copied]
    for r in rows:
        category = by_name.get(fold(r.category))
        if category is None:
            continue
        out.append(
            SimpleNamespace(
                id=r.id,
                payer="me" if user is not None and r.paid_by == user else "other",
                on_date=r.on_date,
                amount=r.amount,
                description=r.description,
                category_id=category,
                by=str(r.user_id),
            )
        )
    return out


ADOPT = text("""
    insert into money.money_v1_common_entry
        (space_id, paid_by, on_date, amount, description, category, origin_id)
    select cast(:space as uuid),
           case when e.payer = 'me' then e.user_id end,
           e.on_date, e.amount, e.description, c.name, e.id
    from money.money_v1_entry e
    join money.money_v1_category c on c.id = e.category_id
    on conflict (origin_id) do nothing
""")


async def adopt(connection: AsyncConnection, space: UUID) -> int:
    return (await connection.execute(ADOPT, {"space": str(space)})).rowcount


class Refused(Exception):
    pass


async def keeper_of(connection: AsyncConnection, space: UUID) -> UUID | None:
    return await connection.scalar(
        text(f"""
            select user_id from money.money_v1_common_year
            where space_id = cast(:space as uuid) and user_id <> {ME}
            order by updated_at desc limit 1
        """),
        {"space": str(space)},
    )


async def add_entry(
    connection: AsyncConnection,
    lo: Loaded,
    user: UUID,
    payer: str,
    on: date,
    amount: Decimal,
    description: str,
    category: str,
) -> str:
    space = lo.settings.space_id
    assert space is not None
    if keeps(lo):
        paid_by = user if payer == "me" else None
        names = {
            fold(c.name): c.name
            for c in lo.book.categories.values()
            if c.nature == "expense" and c.ownership == "shared"
        }
    else:
        keeper = await keeper_of(connection, space)
        if keeper is None:
            raise Refused("nadie del espacio lleva todavía la cuenta común en su Money")
        paid_by = user if payer == "me" else keeper
        names = {fold(c["name"]): c["name"] for c in await categories(connection, space, keeper)}
    name = names.get(fold(category))
    if name is None:
        raise Refused(f"no hay ninguna categoría común «{category}»")
    return str(
        await connection.scalar(
            text("""
                insert into money.money_v1_common_entry
                    (space_id, paid_by, on_date, amount, description, category)
                values (cast(:space as uuid), cast(:paid as uuid), :on, :amount, :text, :cat)
                returning id
            """),
            {
                "space": str(space),
                "paid": str(paid_by) if paid_by else None,
                "on": on,
                "amount": amount,
                "text": description,
                "cat": name,
            },
        )
    )


async def remove_entry(connection: AsyncConnection, entry_id: UUID) -> bool:
    gone = await connection.execute(
        text("delete from money.money_v1_common_entry where id = :i"), {"i": entry_id}
    )
    return gone.rowcount > 0


def _amounts(values: dict[str, Decimal]) -> str:
    return json.dumps({k: str(v) for k, v in sorted(values.items())})


UPSERT_MONTH = text("""
    insert into money.money_v1_common_month
        (space_id, year, month, source, by_category, split_of, paid_account, paid_keeper,
         paid_other, deposits_keeper, deposits_other)
    values (cast(:space as uuid), :year, :month, :source, cast(:cats as jsonb),
            cast(:splits as jsonb), :account, :keeper, :other, :dk, :do)
    on conflict (space_id, user_id, year, month) do update
    set source = excluded.source, by_category = excluded.by_category,
        split_of = excluded.split_of, paid_account = excluded.paid_account,
        paid_keeper = excluded.paid_keeper, paid_other = excluded.paid_other,
        deposits_keeper = excluded.deposits_keeper, deposits_other = excluded.deposits_other,
        updated_at = now()
    where (money.money_v1_common_month.source, money.money_v1_common_month.by_category,
           money.money_v1_common_month.split_of, money.money_v1_common_month.paid_account,
           money.money_v1_common_month.paid_keeper, money.money_v1_common_month.paid_other,
           money.money_v1_common_month.deposits_keeper,
           money.money_v1_common_month.deposits_other)
          is distinct from
          (excluded.source, excluded.by_category, excluded.split_of, excluded.paid_account,
           excluded.paid_keeper, excluded.paid_other, excluded.deposits_keeper,
           excluded.deposits_other)
""")

UPSERT_YEAR = text("""
    insert into money.money_v1_common_year
        (space_id, year, ratio_keeper, settled, keeper_name, other_name)
    values (cast(:space as uuid), :year, :ratio, :settled, :keeper, :other)
    on conflict (space_id, user_id, year) do update
    set ratio_keeper = excluded.ratio_keeper, settled = excluded.settled,
        keeper_name = excluded.keeper_name, other_name = excluded.other_name, updated_at = now()
""")


def years_of(lo: Loaded, today: date) -> list[int]:
    found = {h.year for h in lo.history} | {f.on.year for f in lo.book.facts} | {today.year}
    return sorted(y for y in found if y <= today.year)


async def publish(connection: AsyncConnection, lo: Loaded, today: date) -> int:
    from money.book import ratio_of

    space = lo.settings.space_id
    if space is None or not keeps(lo):
        return 0
    await adopt(connection, space)
    params = {"space": str(space)}
    changed = 0
    kept: list[tuple[int, int]] = []
    for year in years_of(lo, today):
        for m in year_months(lo.book, lo.history, year, lo.settings.cutoff, today):
            kept.append((year, m.month))
            changed += (
                await connection.execute(
                    UPSERT_MONTH,
                    {
                        **params,
                        "year": year,
                        "month": m.month,
                        "source": m.source,
                        "cats": _amounts(m.by_category),
                        "splits": json.dumps(dict(sorted(m.split_of.items()))),
                        "account": m.paid_account,
                        "keeper": m.paid_me,
                        "other": m.paid_other,
                        "dk": m.deposits_me,
                        "do": m.deposits_other,
                    },
                )
            ).rowcount
        await connection.execute(
            UPSERT_YEAR,
            {
                **params,
                "year": year,
                "ratio": round(ratio_of(lo, year), 6),
                "settled": lo.settled.get(year, False),
                "keeper": lo.settings.me_name[:40],
                "other": lo.settings.other_name[:40],
            },
        )
    await connection.execute(
        text(f"""
            delete from money.money_v1_common_month
            where space_id = cast(:space as uuid) and user_id = {ME}
              and not ((year, month) in (select * from unnest(cast(:years as int[]),
                                                               cast(:months as int[]))))
        """),
        {**params, "years": [y for y, _ in kept], "months": [m for _, m in kept]},
    )
    shared = [
        c
        for c in lo.book.categories.values()
        if c.nature == "expense" and c.ownership == "shared" and c.split
    ]
    await connection.execute(
        text(f"""
            delete from money.money_v1_common_category
            where space_id = cast(:space as uuid) and user_id = {ME}
              and not (name = any(:names))
        """),
        {**params, "names": [c.name[:60] for c in shared]},
    )
    for position, c in enumerate(shared):
        await connection.execute(
            text("""
                insert into money.money_v1_common_category (space_id, name, split, position)
                values (cast(:space as uuid), :name, :split, :position)
                on conflict (space_id, user_id, name) do update
                set split = excluded.split, position = excluded.position
                where (money.money_v1_common_category.split,
                       money.money_v1_common_category.position)
                      is distinct from (excluded.split, excluded.position)
            """),
            {**params, "name": c.name[:60], "split": c.split, "position": position},
        )
    return changed


async def categories(connection: AsyncConnection, space: UUID, keeper: UUID) -> list[dict]:
    rows = await connection.execute(
        text("""
            select name, split from money.money_v1_common_category
            where space_id = cast(:space as uuid) and user_id = :keeper
            order by position, name
        """),
        {"space": str(space), "keeper": keeper},
    )
    return [{"name": r.name, "split": r.split} for r in rows]


@dataclass
class Mirror:
    keeper: UUID
    ratio_me: Decimal
    settled: bool
    me_name: str
    other_name: str
    months: list[Month]
    kept_at: datetime | None
    categories: list[dict] = field(default_factory=list)


def _decimals(raw: dict) -> dict[str, Decimal]:
    return {k: Decimal(str(v)) for k, v in raw.items()}


async def mirror(connection: AsyncConnection, space: UUID, year: int) -> Mirror | None:
    keeper = await keeper_of(connection, space)
    if keeper is None:
        return None
    head = (
        await connection.execute(
            text("""
                select ratio_keeper, settled, keeper_name, other_name, updated_at
                from money.money_v1_common_year
                where space_id = cast(:space as uuid) and user_id = :keeper and year = :year
            """),
            {"space": str(space), "keeper": keeper, "year": year},
        )
    ).first()
    rows = (
        await connection.execute(
            text("""
                select * from money.money_v1_common_month
                where space_id = cast(:space as uuid) and user_id = :keeper and year = :year
                order by month
            """),
            {"space": str(space), "keeper": keeper, "year": year},
        )
    ).all()
    months = []
    for r in rows:
        m = Month(year, r.month, r.source)
        m.by_category = _decimals(r.by_category)
        m.split_of = dict(r.split_of)
        m.paid_account = r.paid_account
        m.paid_me, m.paid_other = r.paid_other, r.paid_keeper
        m.deposits_me, m.deposits_other = r.deposits_other, r.deposits_keeper
        months.append(m)
    stamps = [r.updated_at for r in rows] + ([head.updated_at] if head else [])
    return Mirror(
        keeper=keeper,
        ratio_me=(Decimal(1) - head.ratio_keeper) if head else HALF,
        settled=head.settled if head else False,
        me_name=head.other_name if head else "Yo",
        other_name=head.keeper_name if head else "La otra persona",
        months=months,
        kept_at=max(stamps) if stamps else None,
        categories=await categories(connection, space, keeper),
    )


async def mirrored_years(connection: AsyncConnection, space: UUID, keeper: UUID) -> list[int]:
    rows = await connection.execute(
        text("""
            select distinct year from money.money_v1_common_year
            where space_id = cast(:space as uuid) and user_id = :keeper order by year
        """),
        {"space": str(space), "keeper": keeper},
    )
    return [r.year for r in rows]


async def member_entries(
    connection: AsyncConnection, space: UUID, user: UUID, year: int
) -> list[dict]:
    out = []
    for r in (await connection.execute(ENTRIES, {"space": str(space)})).all():
        if r.on_date.year != year:
            continue
        mine = r.paid_by is None or r.paid_by == user
        out.append(
            {
                "id": str(r.id),
                "fact": f"entry:{r.id}",
                "on": r.on_date,
                "amount": float(r.amount),
                "description": r.description,
                "payer": "me" if mine else "other",
                "category": r.category,
                "category_name": r.category,
            }
        )
    out.sort(key=lambda e: e["on"], reverse=True)
    return out


def total_balance(months: list[Month], r: Decimal) -> Decimal:
    return sum((m.balance_me(r) for m in months), ZERO)


@dataclass
class YearView:
    role: str
    year: int
    months: list[Month]
    ratio_me: Decimal
    settled: bool
    me_name: str
    other_name: str
    keeper: UUID | None = None
    kept_at: datetime | None = None
    categories: list[dict] = field(default_factory=list)

    @property
    def balance_me(self) -> Decimal:
        return total_balance(self.months, self.ratio_me)


async def year_view(connection: AsyncConnection, lo: Loaded, year: int, today: date) -> YearView:
    from money.book import ratio_of

    role = role_of(lo)
    if role == MEMBER:
        space = lo.settings.space_id
        assert space is not None
        seen = await mirror(connection, space, year)
        if seen is None:
            return YearView(
                role, year, [], HALF, False, lo.settings.me_name, lo.settings.other_name
            )
        return YearView(
            role,
            year,
            seen.months,
            seen.ratio_me,
            seen.settled,
            seen.me_name,
            seen.other_name,
            seen.keeper,
            seen.kept_at,
            seen.categories,
        )
    return YearView(
        role,
        year,
        year_months(lo.book, lo.history, year, lo.settings.cutoff, today),
        ratio_of(lo, year),
        lo.settled.get(year, False),
        lo.settings.me_name,
        lo.settings.other_name,
    )


async def years(connection: AsyncConnection, lo: Loaded, today: date) -> list[int]:
    if role_of(lo) == MEMBER:
        space = lo.settings.space_id
        assert space is not None
        keeper = await keeper_of(connection, space)
        return await mirrored_years(connection, space, keeper) if keeper else []
    return years_of(lo, today)
