from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from arga_tenancy import current_spaces
from shopping import shopping

CHOSEN = text("select list_space_id from shopping.shopping_setting")

CHOOSE = text("""
    insert into shopping.shopping_setting (list_space_id) values (cast(:space as uuid))
    on conflict (user_id) do update set list_space_id = excluded.list_space_id, updated_at = now()
""")


class ListOwner(BaseModel):
    space_id: UUID | None


async def chosen(connection: AsyncConnection) -> UUID | None:
    space = await connection.scalar(CHOSEN)
    return space if space in current_spaces.get() else None


async def choose(connection: AsyncConnection, request: ListOwner) -> None:
    if request.space_id is not None and request.space_id not in current_spaces.get():
        raise shopping.NotFound(f"space {request.space_id}")
    await connection.execute(CHOOSE, {"space": str(request.space_id) if request.space_id else None})
