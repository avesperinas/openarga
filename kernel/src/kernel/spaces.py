from __future__ import annotations

import secrets
from datetime import datetime, timedelta
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field, StringConstraints
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from arga_tenancy import require_person
from kernel.db import engine

router = APIRouter(tags=["spaces"])

INVITE_LIFETIME = timedelta(hours=48)
ALPHABET = "23456789ABCDEFGHJKMNPQRSTUVWXYZ"


def new_code() -> str:
    raw = "".join(secrets.choice(ALPHABET) for _ in range(12))
    return f"{raw[:4]}-{raw[4:8]}-{raw[8:]}"


def normalise(code: str) -> str:
    raw = "".join(ch for ch in code.upper() if ch.isalnum())
    return f"{raw[:4]}-{raw[4:8]}-{raw[8:]}"


MemberName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=40)]


class SpaceIn(BaseModel):
    name: Annotated[str, Field(min_length=1, max_length=80)]
    me: MemberName | None = None


class Member(BaseModel):
    user_id: UUID
    role: str
    name: str | None = None


class Former(BaseModel):
    user_id: UUID
    left_at: datetime


class SpaceOut(BaseModel):
    id: UUID
    name: str
    role: str
    me: UUID | None = None
    members: list[Member]
    former: list[Former] = []


class InviteOut(BaseModel):
    code: str
    expires_at: datetime


class JoinIn(BaseModel):
    code: Annotated[str, Field(min_length=12, max_length=32)]
    me: MemberName | None = None


class NameIn(BaseModel):
    name: MemberName


ACCEPTED = text("""
    select space_id from kernel.space_members
    where user_id = :user and status = 'accepted'
    order by created_at, space_id
""")


async def spaces_of(connection: AsyncConnection, user: UUID) -> list[UUID]:
    return [row.space_id for row in await connection.execute(ACCEPTED, {"user": user})]


async def describe(connection: AsyncConnection, user: UUID, space: UUID) -> SpaceOut | None:
    rows = (
        await connection.execute(
            text("""
                select s.id, s.name, m.user_id, m.role, m.display_name
                from kernel.spaces s
                join kernel.space_members m on m.space_id = s.id and m.status = 'accepted'
                where s.id = :space
                  and exists (select 1 from kernel.space_members me
                              where me.space_id = s.id and me.user_id = :user
                                and me.status = 'accepted')
                order by m.created_at, m.user_id
            """),
            {"space": space, "user": user},
        )
    ).all()
    if not rows:
        return None
    members = [Member(user_id=row.user_id, role=row.role, name=row.display_name) for row in rows]
    role = next(m.role for m in members if m.user_id == user)
    former = [
        Former(user_id=row.user_id, left_at=row.left_at)
        for row in await connection.execute(
            text(
                "select user_id, left_at from kernel.space_members "
                "where space_id = :space and status = 'left' order by left_at, user_id"
            ),
            {"space": space},
        )
    ]
    return SpaceOut(
        id=rows[0].id, name=rows[0].name, role=role, me=user, members=members, former=former
    )


@router.post("/spaces", status_code=201)
@router.post("/internal/spaces", status_code=201)
async def create_space(body: SpaceIn) -> SpaceOut:
    user = require_person()
    async with engine().begin() as connection:
        space = await connection.scalar(
            text("insert into kernel.spaces (name) values (:name) returning id"),
            {"name": body.name.strip()},
        )
        await connection.execute(
            text(
                "insert into kernel.space_members (space_id, user_id, role, status, display_name) "
                "values (:space, :user, 'owner', 'accepted', :me)"
            ),
            {"space": space, "user": user, "me": body.me},
        )
        return await describe(connection, user, space)


@router.get("/spaces")
@router.get("/internal/spaces")
async def list_spaces() -> list[SpaceOut]:
    user = require_person()
    async with engine().connect() as connection:
        found = [await describe(connection, user, s) for s in await spaces_of(connection, user)]
        return [space for space in found if space is not None]


@router.post("/spaces/{space_id}/invites", status_code=201)
@router.post("/internal/spaces/{space_id}/invites", status_code=201)
async def invite(space_id: UUID) -> InviteOut:
    user = require_person()
    async with engine().begin() as connection:
        space = await describe(connection, user, space_id)
        if space is None:
            raise HTTPException(status_code=404, detail="no existe ese espacio")
        if space.role != "owner":
            raise HTTPException(status_code=403, detail="solo quien es dueño del espacio invita")
        code = new_code()
        expires_at = await connection.scalar(
            text(
                "insert into kernel.space_invites (code, space_id, created_by, expires_at) "
                "values (:code, :space, :user, now() + :lifetime) returning expires_at"
            ),
            {"code": code, "space": space_id, "user": user, "lifetime": INVITE_LIFETIME},
        )
        return InviteOut(code=code, expires_at=expires_at)


@router.post("/spaces/join")
@router.post("/internal/spaces/join")
async def join(body: JoinIn) -> SpaceOut:
    user = require_person()
    code = normalise(body.code)
    async with engine().begin() as connection:
        invite = (
            await connection.execute(
                text(
                    "select space_id, used_at, expires_at <= now() as expired "
                    "from kernel.space_invites where code = :code for update"
                ),
                {"code": code},
            )
        ).first()
        if invite is None:
            raise HTTPException(status_code=404, detail="ese código no existe")
        already = await describe(connection, user, invite.space_id)
        if already is not None:
            return already
        if invite.used_at is not None or invite.expired:
            raise HTTPException(status_code=410, detail="ese código ya se usó o ha caducado")
        await connection.execute(
            text(
                "update kernel.space_invites set used_at = now(), used_by = :user "
                "where code = :code"
            ),
            {"code": code, "user": user},
        )
        await connection.execute(
            text(
                "insert into kernel.space_members (space_id, user_id, role, status, display_name) "
                "values (:space, :user, 'member', 'accepted', :me) "
                "on conflict (space_id, user_id) do update set status = 'accepted', "
                "left_at = null, "
                "display_name = coalesce(excluded.display_name, space_members.display_name)"
            ),
            {"space": invite.space_id, "user": user, "me": body.me},
        )
        return await describe(connection, user, invite.space_id)


@router.put("/spaces/{space_id}/me")
@router.put("/internal/spaces/{space_id}/me")
async def rename_me(space_id: UUID, body: NameIn) -> SpaceOut:
    user = require_person()
    async with engine().begin() as connection:
        changed = await connection.execute(
            text(
                "update kernel.space_members set display_name = :name "
                "where space_id = :space and user_id = :user and status = 'accepted'"
            ),
            {"name": body.name, "space": space_id, "user": user},
        )
        if changed.rowcount == 0:
            raise HTTPException(status_code=404, detail="no existe ese espacio")
        return await describe(connection, user, space_id)


@router.delete("/spaces/{space_id}/members/{member_id}", status_code=204)
@router.delete("/internal/spaces/{space_id}/members/{member_id}", status_code=204)
async def leave(space_id: UUID, member_id: UUID) -> None:
    user = require_person()
    async with engine().begin() as connection:
        await connection.execute(
            text("select 1 from kernel.space_members where space_id = :space for update"),
            {"space": space_id},
        )
        space = await describe(connection, user, space_id)
        if space is None:
            raise HTTPException(status_code=404, detail="no existe ese espacio")
        target = next((m for m in space.members if m.user_id == member_id), None)
        if target is None:
            raise HTTPException(status_code=404, detail="esa persona no está en el espacio")
        if member_id != user and space.role != "owner":
            raise HTTPException(
                status_code=403, detail="solo quien es dueño del espacio quita a alguien"
            )
        if len(space.members) == 1:
            raise HTTPException(status_code=409, detail="eres la única persona del espacio")
        await connection.execute(
            text(
                "update kernel.space_members set status = 'left', role = 'member', "
                "left_at = now() where space_id = :space and user_id = :member"
            ),
            {"space": space_id, "member": member_id},
        )
        if target.role == "owner":
            await connection.execute(
                text("""
                    update kernel.space_members set role = 'owner'
                    where space_id = :space and user_id = (
                        select user_id from kernel.space_members
                        where space_id = :space and status = 'accepted'
                        order by created_at, user_id limit 1
                    )
                """),
                {"space": space_id},
            )
