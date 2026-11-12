from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from macros import meals, templates
from macros.common import TZ

HABIT_DAYS = 60
RECENT_DAYS = 14
AT_LEAST = 2

ITEMS = text("""
    select i.id, i.kind, i.food_id, i.recipe_id, i.name, i.quantity, i.unit, i.grams,
           i.nutrients, i.portion, e.eaten_at, e.tz, e.day
    from macros.macros_item i join macros.macros_entry e on e.id = i.entry_id
    where e.day between :first and :last and e.status = 'confirmed'
    order by e.eaten_at desc, i.position desc
""")


class UsualItem(BaseModel):
    name: str
    kind: str
    food_id: str | None
    recipe_id: str | None
    quantity: float
    unit: str
    grams: float | None
    portion: str | None = None
    kcal: float | None
    times: int
    item_id: str
    last_day: date


class Combo(BaseModel):
    label: str
    times: int
    kcal: float
    item_ids: list[str]


class Usual(BaseModel):
    meal: meals.Meal
    label: str
    day: date
    yesterday: list[UsualItem]
    usual: Combo | None
    items: list[UsualItem]
    recent: list[UsualItem]
    menus: list[templates.Template]


def _key(row: Any) -> tuple[str, str]:
    if row.kind == "food":
        return ("food", str(row.food_id))
    if row.kind == "recipe":
        return ("recipe", str(row.recipe_id))
    return (row.kind, row.name.strip().lower())


def _item(row: Any, times: int) -> UsualItem:
    return UsualItem(
        name=row.name,
        kind=row.kind,
        food_id=None if row.food_id is None else str(row.food_id),
        recipe_id=None if row.recipe_id is None else str(row.recipe_id),
        quantity=float(row.quantity),
        unit=row.unit,
        grams=None if row.grams is None else float(row.grams),
        portion=row.portion,
        kcal=None
        if "kcal" not in (row.nutrients or {})
        else round(float(row.nutrients["kcal"]), 1),
        times=times,
        item_id=str(row.id),
        last_day=row.day,
    )


async def usual(connection: AsyncConnection, meal: meals.Meal, day: date) -> Usual:
    rows = (
        await connection.execute(
            ITEMS, {"first": day - timedelta(days=HABIT_DAYS), "last": day - timedelta(days=1)}
        )
    ).all()
    in_meal = [row for row in rows if meals.meal_of(row.eaten_at, row.tz or TZ) == meal]

    yesterday = [_item(row, 1) for row in reversed(in_meal) if row.day == day - timedelta(days=1)]

    days_of: dict[tuple[str, str], set[date]] = {}
    latest: dict[tuple[str, str], Any] = {}
    by_day: dict[date, list[Any]] = {}
    for row in in_meal:
        key = _key(row)
        days_of.setdefault(key, set()).add(row.day)
        latest.setdefault(key, row)
        by_day.setdefault(row.day, []).append(row)
    items = sorted(
        (_item(latest[key], len(seen)) for key, seen in days_of.items()),
        key=lambda one: (-one.times, -one.last_day.toordinal()),
    )[:8]

    combos: dict[frozenset[tuple[str, str]], list[date]] = {}
    for on, found in by_day.items():
        combos.setdefault(frozenset(_key(row) for row in found), []).append(on)
    best = max(
        (pair for pair in combos.items() if len(pair[1]) >= AT_LEAST),
        key=lambda pair: (len(pair[1]), len(pair[0]), max(pair[1])),
        default=None,
    )
    combo = None
    if best is not None:
        last = list(reversed(by_day[max(best[1])]))
        combo = Combo(
            label=" + ".join(row.name for row in last),
            times=len(best[1]),
            kcal=round(sum(float((row.nutrients or {}).get("kcal", 0)) for row in last), 1),
            item_ids=[str(row.id) for row in last],
        )

    known = set(days_of)
    recent_seen: dict[tuple[str, str], Any] = {}
    for row in rows:
        if row.day < day - timedelta(days=RECENT_DAYS):
            continue
        key = _key(row)
        if key not in known and key not in recent_seen:
            recent_seen[key] = row
    recent = [_item(row, 1) for row in list(recent_seen.values())[:6]]

    return Usual(
        meal=meal,
        label=meals.label(meal),
        day=day,
        yesterday=yesterday,
        usual=combo,
        items=items,
        recent=recent,
        menus=await templates.all_of(connection),
    )
