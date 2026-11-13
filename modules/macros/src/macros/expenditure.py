from __future__ import annotations

import math
from datetime import date, timedelta

from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from macros import catalog, weight
from macros.common import Conflict

KCAL_PER_KG = 7700.0
WINDOW_DAYS = 28
MIN_DAYS = 14
MIN_WEIGHT_SPAN = 7
RATES = (0.0, -0.3)
ROUND_TO = 50

COMPLETE = text("select day from macros.macros_day_complete where day between :first and :last")
MARK = text("insert into macros.macros_day_complete (day) values (:day) on conflict do nothing")
UNMARK = text("delete from macros.macros_day_complete where day = :day")
KCAL_BY_DAY = text("""
    select e.day, sum(coalesce((i.nutrients->>'kcal')::numeric, 0)) as kcal
    from macros.macros_entry e join macros.macros_item i on i.entry_id = e.id
    where e.status = 'confirmed' and e.day = any(cast(:days as date[]))
    group by e.day
""")
IS_COMPLETE = text("select exists (select 1 from macros.macros_day_complete where day = :day)")

HENRY = {
    "male": ((30, 16.0, 545), (60, 14.2, 593), (200, 13.5, 514)),
    "female": ((30, 13.1, 558), (60, 9.74, 694), (200, 10.1, 569)),
}


class Proposal(BaseModel):
    rate_kg_week: float
    kcal: float
    floored: bool = False


class Expenditure(BaseModel):
    kcal: float | None
    days: int
    first: date
    last: date
    intake: float | None = None
    weight_change_kg_week: float | None = None
    bmr: float | None = None
    proposals: list[Proposal] = []
    missing: str | None = None


async def is_complete(connection: AsyncConnection, day: date) -> bool:
    return bool(await connection.scalar(IS_COMPLETE, {"day": day}))


async def mark(connection: AsyncConnection, day: date, complete: bool, today: date) -> bool:
    if day > today:
        raise Conflict("a day that has not come yet cannot be complete")
    await connection.execute(MARK if complete else UNMARK, {"day": day})
    return complete


def bmr(sex: str | None, age: int | None, kg: float) -> float:
    years = age if age is not None else 45
    sexes = [sex] if sex in HENRY else list(HENRY)
    values = []
    for one in sexes:
        a, b = next((a, b) for top, a, b in HENRY[one] if years < top)
        values.append(a * kg + b)
    return round(sum(values) / len(values))


def slope(points: list[tuple[int, float]]) -> float:
    n = len(points)
    mean_x = sum(x for x, _ in points) / n
    mean_y = sum(y for _, y in points) / n
    spread = sum((x - mean_x) ** 2 for x, _ in points)
    return sum((x - mean_x) * (y - mean_y) for x, y in points) / spread if spread else 0.0


def rounded(kcal: float) -> float:
    return float(round(kcal / ROUND_TO) * ROUND_TO)


async def estimate(connection: AsyncConnection, today: date) -> Expenditure:
    from macros import summary

    last = today - timedelta(days=1)
    first = last - timedelta(days=WINDOW_DAYS - 1)
    complete = list((await connection.execute(COMPLETE, {"first": first, "last": last})).scalars())
    eaten = {
        row.day: float(row.kcal)
        for row in (await connection.execute(KCAL_BY_DAY, {"days": complete})).all()
        if row.kcal and float(row.kcal) > 0
    }
    out = Expenditure(kcal=None, days=len(eaten), first=first, last=last)
    if len(eaten) < MIN_DAYS:
        out.missing = catalog.t("expenditure.missing_days", needed=MIN_DAYS, have=len(eaten))
        return out
    history = await weight.history(connection)
    weighed = [one for one in history.days if first <= one.day <= last]
    if len(weighed) < 2 or (weighed[-1].day - weighed[0].day).days < MIN_WEIGHT_SPAN:
        out.missing = catalog.t("expenditure.missing_weight")
        return out
    per_day = slope([((one.day - first).days, one.kg) for one in weighed])
    intake = sum(eaten.values()) / len(eaten)
    kcal = intake - per_day * KCAL_PER_KG
    person = await summary.profile(connection, today)
    floor = bmr(person.sex, person.age, weighed[-1].kg)
    out.kcal = rounded(kcal)
    out.intake = round(intake)
    out.weight_change_kg_week = round(per_day * 7, 2)
    out.bmr = floor
    for rate in RATES:
        wanted = kcal + rate * KCAL_PER_KG / 7
        kcal_wanted = max(rounded(wanted), math.ceil(floor / ROUND_TO) * ROUND_TO)
        out.proposals.append(
            Proposal(rate_kg_week=rate, kcal=float(kcal_wanted), floored=wanted < floor)
        )
    return out


def proposal_label(one: Proposal) -> str:
    kcal = catalog.number(one.kcal)
    if one.rate_kg_week == 0:
        return catalog.t("expenditure.keep", kcal=kcal)
    way = "lose" if one.rate_kg_week < 0 else "gain"
    return catalog.t(f"expenditure.{way}", amount=catalog.short(abs(one.rate_kg_week)), kcal=kcal)
