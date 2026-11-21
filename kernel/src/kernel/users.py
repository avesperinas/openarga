from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import text

from kernel.db import engine
from kernel.demo_copies import active_window, copies_on, is_copy_subject
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


SEEN = text("""
    update kernel.users set last_seen_at = now() where subject = :subject returning id
""")


@router.post("/internal/users")
async def resolve_user(body: UserIn) -> ResolvedPerson:
    async with engine().begin() as connection:
        if is_copy_subject(body.subject):
            # Only the demo keeper makes a copy's people; once the copy is gone, its visitor goes
            # back to the door instead of getting an empty person.
            user = await connection.scalar(SEEN, {"subject": body.subject})
            if user is None:
                raise HTTPException(status_code=404, detail="this demo copy is gone")
        else:
            user = await connection.scalar(UPSERT, {"subject": body.subject})
        spaces = await spaces_of(connection, user)
    return ResolvedPerson(id=user, spaces=spaces, preferences=await of_user(user))


EVERYONE = text("""
    select u.id,
           coalesce(array_agg(m.space_id order by m.created_at, m.space_id)
                    filter (where m.space_id is not null), '{}') as spaces
    from kernel.users u
    left join kernel.space_members m on m.user_id = u.id and m.status = 'accepted'
    where cast(:since as timestamptz) is null or u.last_seen_at >= :since
    group by u.id, u.created_at
    order by u.created_at
""")


@router.get("/internal/users")
async def list_users() -> list[ResolvedUser]:
    # With a copy of the demo per visitor, the workers only keep up the people someone is using.
    since = datetime.now(UTC) - active_window() if copies_on() else None
    async with engine().connect() as connection:
        rows = await connection.execute(EVERYONE, {"since": since})
        return [ResolvedUser(id=row.id, spaces=list(row.spaces)) for row in rows]
