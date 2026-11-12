from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncConnection

from arga_widgets import envelope
from outings import agenda, explore, wishes
from outings.common import MADRID

KINDS = {"weekend": "upnext", "wishes": "list"}
ROWS = 8
CATEGORY = {
    "eat": "comer",
    "stage": "escena",
    "culture": "cultura",
    "festival": "fiestas",
    "outdoors": "fuera",
}
KIND = {"eat": "comer", "plan": "plan", "getaway": "escapada", "trip": "viaje"}


def at(event: agenda.Event) -> str:
    if event.time:
        hour, minute = (int(part) for part in event.time.split(":"))
        moment = datetime(
            event.starts_on.year, event.starts_on.month, event.starts_on.day, hour % 24, minute,
            tzinfo=MADRID,
        )  # fmt: skip
        return moment.isoformat()
    return event.starts_on.isoformat()


async def weekend(connection: AsyncConnection) -> dict:
    first, last = agenda.window("weekend")
    found = sorted(
        await agenda.events(connection, first, last),
        key=lambda one: (-explore.score(one, []), one.starts_on, one.time or ""),
    )
    items = []
    for event in found:
        where = event.venue or event.town
        detail = " · ".join(part for part in (CATEGORY[event.category], where) if part)
        items.append({"at": at(event), "title": event.title, "detail": detail})
    if not items:
        return envelope(KINDS["weekend"], "empty", {"detail": "nada este finde"})
    return envelope(KINDS["weekend"], "ready", {"events": items[:ROWS]})


async def pending(connection: AsyncConnection) -> dict:
    found = [
        one for one in await wishes.wishes(connection) if one.kind in ("getaway", "plan", "trip")
    ]
    if not found:
        return envelope(KINDS["wishes"], "empty", {"detail": "nada apuntado"})
    rows = [
        {
            "label": one.name,
            "value": one.place.town or one.place.name if one.place else KIND[one.kind],
        }
        for one in found[:ROWS]
    ]
    return envelope(
        KINDS["wishes"],
        "ready",
        {"rows": rows, "detail": f"{len(found)} pendiente{'s' if len(found) != 1 else ''}"},
    )


RENDERERS: dict[str, Callable[[AsyncConnection], Awaitable[dict]]] = {
    "weekend": weekend,
    "wishes": pending,
}
