from __future__ import annotations

from collections import defaultdict
from datetime import date
from typing import Any

from sqlalchemy.ext.asyncio import AsyncConnection

import arga_contracts as contracts
from arga_contracts import records as write
from arga_module import preferences
from arga_tenancy import current_spaces
from shopping import lists, shopping

APP = "shopping"
ALL_TRIPS = 100_000


def _thing(name: str, quantity: str | None) -> str:
    return f"{name} ({quantity})" if quantity else name


def shopping_list(found: shopping.ShoppingList) -> dict[str, Any]:
    parts = []
    for group in found.groups:
        lines = "\n".join(
            f"- [ ] {_thing(one.name, one.quantity)}" + (f" · {one.note}" if one.note else "")
            for one in group.items
        )
        parts.append(f"### {group.emoji} {group.name}\n\n{lines}")
    if found.cart:
        lines = "\n".join(f"- [x] {_thing(one.name, one.quantity)}" for one in found.cart)
        parts.append(f"### In the trolley\n\n{lines}")
    if found.due:
        lines = "\n".join(
            f"- {one.name}" + (f" · {one.every}, last {one.since}" if one.every else "")
            for one in found.due
        )
        parts.append(f"### Due\n\n{lines}")
    empty = "Nothing on the list." if not found.groups and not found.cart else None
    return contracts.record(
        id="list",
        title="Shopping list",
        kind="Shopping list",
        href="/shopping/",
        properties={"pending": found.pending, "in_trolley": found.in_cart},
        body=write.sections(empty, *parts),
    )


def habits(products: list[shopping.Product], sections: dict[str, str]) -> dict[str, Any]:
    rows = [
        [
            one.name,
            sections.get(one.category_id, ""),
            one.times,
            one.every or "",
            one.last.isoformat() if one.last else "",
        ]
        for one in products
        if one.times
    ]
    return contracts.record(
        id="habits",
        title="What you buy",
        kind="Shopping habits",
        href="/shopping/history",
        properties={"products": len(rows)},
        body=write.sections(
            "Everything you have bought, how many times and how often, from most to least.",
            write.table(["Product", "Section", "Times", "How often", "Last"], rows)
            or "You have not finished any shopping yet.",
        ),
    )


async def build(connection: AsyncConnection) -> list[dict[str, Any]]:
    chosen = await lists.chosen(connection)
    sections = {one.id: one.name for one in await shopping.categories(connection)}
    found = [
        shopping_list(await shopping.read(connection, space=chosen)),
        habits(await shopping.products(connection, space=chosen), sections),
    ]
    trips: list[shopping.Trip] = []
    for space in (None, *current_spaces.get()):
        trips.extend(await shopping.trips(connection, ALL_TRIPS, space))
    zone = preferences.current().zone
    by_day: dict[date, list[shopping.Trip]] = defaultdict(list)
    for trip in trips:
        by_day[trip.finished_at.astimezone(zone).date()].append(trip)
    for day, done in sorted(by_day.items()):
        lines = []
        for trip in sorted(done, key=lambda one: one.finished_at):
            things = ", ".join(_thing(one.name, one.quantity) for one in trip.products)
            count = f"{trip.items} {'thing' if trip.items == 1 else 'things'}"
            lines.append(f"- Shopping of {count}: {things}")
        found.append(
            contracts.record(
                id=f"day:{day.isoformat()}",
                title="Shopping",
                kind="Day",
                href="/shopping/history",
                day=day,
                properties={"shopping_items": sum(one.items for one in done)},
                body="\n".join(lines),
            )
        )
    return found
