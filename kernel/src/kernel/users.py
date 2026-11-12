from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter
from pydantic import BaseModel, Field
from sqlalchemy import text

from kernel.db import engine
from kernel.preferences import Preferences, of_user
from kernel.spaces import spaces_of

router = APIRouter(tags=["users"])


class UserIn(BaseModel):
    subject: Annotated[str, Field(min_length=1, max_length=255)]


class UserOut(BaseModel):
    id: UUID


class ResolvedUser(UserOut):
    spaces: list[UUID]


class ResolvedPerson(ResolvedUser):
    preferences: Preferences


UPSERT = text("""
    insert into kernel.users (subject, last_seen_at) values (:subject, now())
    on conflict (subject) do update set last_seen_at = now()
    returning id
""")


@router.post("/internal/users")
async def resolve_user(body: UserIn) -> ResolvedPerson:
    async with engine().begin() as connection:
        user = await connection.scalar(UPSERT, {"subject": body.subject})
        spaces = await spaces_of(connection, user)
    return ResolvedPerson(id=user, spaces=spaces, preferences=await of_user(user))


EVERYONE = text("""
    select u.id,
           coalesce(array_agg(m.space_id order by m.created_at, m.space_id)
                    filter (where m.space_id is not null), '{}') as spaces
    from kernel.users u
    left join kernel.space_members m on m.user_id = u.id and m.status = 'accepted'
    group by u.id, u.created_at
    order by u.created_at
""")


@router.get("/internal/users")
async def list_users() -> list[ResolvedUser]:
    async with engine().connect() as connection:
        rows = await connection.execute(EVERYONE)
        return [ResolvedUser(id=row.id, spaces=list(row.spaces)) for row in rows]
