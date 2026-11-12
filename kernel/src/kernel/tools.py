from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel
from sqlalchemy import text

from kernel.db import engine

router = APIRouter(tags=["tools"])

MODULE_TOOLS = text("""
    select m.id as module,
           tool->>'name' as name,
           tool->>'scope' as scope,
           tool->>'description' as description,
           m.manifest->'api'->>'prefix' as prefix
    from kernel.modules m
    cross join lateral jsonb_array_elements(coalesce(m.manifest->'tools', '[]'::jsonb)) as tool
    where m.enabled
    order by m.id, tool->>'name'
""")


class ToolEntry(BaseModel):
    module: str
    name: str
    scope: str
    description: str
    endpoint: str


@router.get("/tools")
async def tool_catalogue() -> list[ToolEntry]:
    async with engine().connect() as connection:
        rows = (await connection.execute(MODULE_TOOLS)).all()
    return [
        ToolEntry(
            module=row.module,
            name=row.name,
            scope=row.scope,
            description=row.description,
            endpoint=f"{row.prefix}/tools/{row.name}",
        )
        for row in rows
    ]
