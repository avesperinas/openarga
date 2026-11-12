from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncConnection

from arga_widgets import envelope
from library import library, stats
from library.library import today

KINDS = {"reading": "list", "goal": "ring", "pages": "bars"}

ROWS = 6


async def reading(connection: AsyncConnection) -> dict:
    found = await library.books(connection, "reading")
    if not found:
        return envelope(KINDS["reading"], "empty", {"detail": "no estás leyendo nada"})
    now = today()
    rows = []
    for one in found[:ROWS]:
        days = (now - one.started_on).days + 1 if one.started_on else None
        rows.append({"label": one.title, "value": f"{days} d" if days else ""})
    return envelope(KINDS["reading"], "ready", {"rows": rows})


async def goal(connection: AsyncConnection) -> dict:
    found = await stats.year_stats(connection)
    if not found.goal:
        detail = f"{found.books} leídos este año · sin objetivo"
        return envelope(KINDS["goal"], "empty", {"detail": detail})
    detail = None
    if found.goal_pace is not None:
        ahead = found.books - found.goal_pace
        detail = (
            "vas al día"
            if abs(ahead) < 0.5
            else (
                f"{ahead:+.0f} sobre el ritmo"
                if ahead > 0
                else f"{-ahead:.0f} por debajo del ritmo"
            )
        )
    return envelope(
        KINDS["goal"],
        "ready",
        {
            "value": found.books,
            "target": found.goal,
            "label": "libros",
            "detail": detail,
            **({"expected": round(found.goal_pace, 2)} if found.goal_pace is not None else {}),
        },
    )


async def pages(connection: AsyncConnection) -> dict:
    found = await stats.year_stats(connection)
    if not found.pages:
        return envelope(KINDS["pages"], "empty", {"detail": "ningún libro terminado este año"})
    months = found.months[: today().month] if found.year == today().year else found.months
    return envelope(
        KINDS["pages"],
        "ready",
        {
            "value": found.pages,
            "unit": "págs.",
            "series": [float(month.pages) for month in months],
            "labels": [month.label for month in months],
            "highlight": len(months) - 1,
            "detail": f"{found.books} libros este año",
        },
    )


RENDERERS = {"reading": reading, "goal": goal, "pages": pages}
