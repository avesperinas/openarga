from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from arga_widgets import envelope

KINDS = {"recipes": "stats", "quick": "list"}

QUICK_MINUTES = 30

SUMMARY = text("""
    select count(*) as recipes,
           avg(v.total_minutes) filter (where v.total_minutes is not null) as average_minutes,
           count(*) filter (
               where v.total_minutes is not null and v.total_minutes <= :quick
           ) as quick
    from recipes.recipes_recipe r
    join recipes.recipes_recipe_version v on v.id = r.current_version_id
""")

QUICK = text("""
    select r.name, v.total_minutes, v.active_minutes
    from recipes.recipes_recipe r
    join recipes.recipes_recipe_version v on v.id = r.current_version_id
    where v.total_minutes is not null and v.total_minutes <= :quick
    order by v.total_minutes, lower(r.name)
    limit 6
""")


async def recipe_book(connection: AsyncConnection) -> dict:
    row = (await connection.execute(SUMMARY, {"quick": QUICK_MINUTES})).one()
    if row.recipes == 0:
        return envelope(KINDS["recipes"], "empty", {"detail": "sin recetas todavía"})

    stats = [{"label": "Recetas", "value": row.recipes}]
    if row.average_minutes is not None:
        stats.append(
            {"label": "De media", "value": round(float(row.average_minutes)), "unit": "min"}
        )
    stats.append({"label": "En 30 min", "value": row.quick})
    return envelope(KINDS["recipes"], "ready", {"stats": stats})


async def quick_recipes(connection: AsyncConnection) -> dict:
    rows = (await connection.execute(QUICK, {"quick": QUICK_MINUTES})).all()
    if not rows:
        return envelope(
            KINDS["quick"],
            "empty",
            {"detail": f"nada por debajo de {QUICK_MINUTES} minutos"},
        )
    return envelope(
        KINDS["quick"],
        "ready",
        {"rows": [{"label": row.name, "value": f"{row.total_minutes} min"} for row in rows]},
    )


RENDERERS = {"recipes": recipe_book, "quick": quick_recipes}
