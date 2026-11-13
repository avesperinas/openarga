from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncConnection

from arga_widgets import envelope
from library import library, stats
from library.library import today
from library.words import say

KINDS = {"reading": "list", "goal": "ring", "pages": "bars"}

ROWS = 6


async def reading(connection: AsyncConnection) -> dict:
    found = await library.books(connection, "reading")
    if not found:
        return envelope(KINDS["reading"], "empty", {"detail": say("widget.reading.empty")})
    now = today()
    rows = []
    for one in found[:ROWS]:
        days = (now - one.started_on).days + 1 if one.started_on else None
        rows.append({"label": one.title, "value": f"{days} d" if days else ""})
    return envelope(KINDS["reading"], "ready", {"rows": rows})


async def goal(connection: AsyncConnection) -> dict:
    found = await stats.year_stats(connection)
    if not found.goal:
        detail = say("widget.goal.none", books=found.books)
        return envelope(KINDS["goal"], "empty", {"detail": detail})
    detail = None
    if found.goal_pace is not None:
        ahead = found.books - found.goal_pace
        detail = (
            say("widget.goal.on_pace")
            if abs(ahead) < 0.5
            else (
                say("widget.goal.ahead", count=f"{ahead:+.0f}")
                if ahead > 0
                else say("widget.goal.behind", count=f"{-ahead:.0f}")
            )
        )
    return envelope(
        KINDS["goal"],
        "ready",
        {
            "value": found.books,
            "target": found.goal,
            "label": say("widget.goal.label"),
            "detail": detail,
            **({"expected": round(found.goal_pace, 2)} if found.goal_pace is not None else {}),
        },
    )


async def pages(connection: AsyncConnection) -> dict:
    found = await stats.year_stats(connection)
    if not found.pages:
        return envelope(KINDS["pages"], "empty", {"detail": say("widget.pages.empty")})
    months = found.months[: today().month] if found.year == today().year else found.months
    return envelope(
        KINDS["pages"],
        "ready",
        {
            "value": found.pages,
            "unit": say("widget.pages.unit"),
            "series": [float(month.pages) for month in months],
            "labels": [month.label for month in months],
            "highlight": len(months) - 1,
            "detail": say("widget.pages.detail", books=found.books),
        },
    )


RENDERERS = {"reading": reading, "goal": goal, "pages": pages}
