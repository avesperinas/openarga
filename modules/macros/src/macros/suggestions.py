from __future__ import annotations

from datetime import date, timedelta
from statistics import median

from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncConnection

from macros import catalog, detail, summary
from macros.common import NotFound
from macros.intake import Entry, Item, entries

WINDOW_DAYS = 60
MAX_NUTRIENTS = 3
MAX_FOODS = 3
BELOW = 0.9
ENOUGH = 0.1


class Food(BaseModel):
    food_id: str | None
    recipe_id: str | None
    name: str
    portion: str
    quantity: float
    unit: str
    amount: float
    share_of_reference: float
    times: int
    last_eaten: date


class Nutrient(BaseModel):
    key: str
    name: str
    unit: str
    average: float
    reference: float
    share: float
    foods: list[Food]


class Window(BaseModel):
    first: date
    last: date
    days: int


class Suggestions(BaseModel):
    window: Window
    nutrients: list[Nutrient]


def _portion(item: Item) -> str:
    amount = catalog.short(item.quantity)
    if item.portion:
        return f"{amount} {item.portion}"
    if item.unit == "unit":
        return catalog.t("portion.units", amount=amount)
    if item.unit == "serving":
        key = "portion.serving" if item.quantity == 1 else "portion.servings"
        return catalog.t(key, amount=amount)
    return f"{amount} {item.unit}"


def _supplement(item: Item) -> bool:
    return item.unit == "unit" and item.grams is None and item.kind == "food"


def candidates(found: list[Entry]) -> dict[str, list[tuple[Entry, Item]]]:
    groups: dict[str, list[tuple[Entry, Item]]] = {}
    for entry in found:
        for item in entry.items:
            if item.kind not in ("food", "recipe") or _supplement(item):
                continue
            key = item.recipe_id or item.food_id or item.name.lower()
            groups.setdefault(key, []).append((entry, item))
    return groups


def foods_for(
    key: str, reference: float, groups: dict[str, list[tuple[Entry, Item]]]
) -> list[Food]:
    picked: list[Food] = []
    for lines in groups.values():
        entries_seen = {entry.id for entry, _ in lines}
        if len(entries_seen) < 2:
            continue
        values = [item.nutrients.get(key) for _, item in lines]
        known = [value for value in values if value is not None]
        if not known:
            continue
        amount = median(known)
        if amount < reference * ENOUGH:
            continue
        by_grams = sorted(lines, key=lambda pair: pair[1].grams or pair[1].quantity)
        _, typical = by_grams[len(by_grams) // 2]
        last = max(entry.day for entry, _ in lines)
        picked.append(
            Food(
                food_id=typical.food_id,
                recipe_id=typical.recipe_id,
                name=typical.name,
                portion=_portion(typical),
                quantity=typical.quantity,
                unit=typical.unit,
                amount=round(amount, 2),
                share_of_reference=round(amount / reference, 3),
                times=len(entries_seen),
                last_eaten=last,
            )
        )
    picked.sort(key=lambda one: one.amount, reverse=True)
    return picked[:MAX_FOODS]


async def suggest(connection: AsyncConnection, last: date) -> Suggestions:
    week = await summary.week(connection, last)
    low = [
        micro
        for micro in week.micros
        if micro.reference is not None
        and micro.reference.kind == "min"
        and micro.reference.value > 0
        and micro.value is not None
        and micro.coverage >= summary.ENOUGH_COVERAGE
        and micro.value < micro.reference.value * BELOW
    ]
    low.sort(key=lambda micro: (micro.value or 0) / micro.reference.value)  # type: ignore[union-attr]
    found = await entries(connection, last - timedelta(days=WINDOW_DAYS - 1), last)
    groups = candidates(found)
    nutrients = [
        Nutrient(
            key=micro.key,
            name=micro.name,
            unit=micro.unit,
            average=round(micro.value or 0, 2),
            reference=micro.reference.value,  # type: ignore[union-attr]
            share=round((micro.value or 0) / micro.reference.value, 3),  # type: ignore[union-attr]
            foods=foods_for(micro.key, micro.reference.value, groups),  # type: ignore[union-attr]
        )
        for micro in low[:MAX_NUTRIENTS]
    ]
    days = week.counted.days if week.counted else week.days_logged
    return Suggestions(
        window=Window(first=week.first, last=week.last, days=days), nutrients=nutrients
    )


async def contributors(connection: AsyncConnection, nutrient: str, last: date) -> dict:
    first = last - timedelta(days=6)
    found = await entries(connection, first, last)
    complete = await summary.complete_days(connection, first, last)
    chosen = [entry for entry in found if entry.day in complete]
    if len({entry.day for entry in chosen}) < summary.MIN_COMPLETE:
        chosen = found
    try:
        return detail.contributors(chosen, nutrient).model_dump(mode="json")
    except ValueError as error:
        raise NotFound(str(error)) from error
