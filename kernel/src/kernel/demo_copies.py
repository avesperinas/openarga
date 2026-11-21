from __future__ import annotations

import os
import re
from datetime import datetime, timedelta
from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from sqlalchemy import text

from kernel.db import engine

router = APIRouter(tags=["demo"])

COPY_SUBJECT = re.compile(r"^demo-[a-z0-9]{6,16}-[a-z]+$")


def _on(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in ("1", "true", "yes")


def copies_on() -> bool:
    return _on("OPENARGA_DEMO") and _on("OPENARGA_DEMO_COPIES")


def _minutes(name: str, default: int) -> int:
    raw = os.environ.get(name, "").strip()
    return int(raw) if raw.isdigit() and int(raw) > 0 else default


def lifetime() -> timedelta:
    return timedelta(minutes=_minutes("OPENARGA_DEMO_COPY_MINUTES", 120))


def active_window() -> timedelta:
    return timedelta(minutes=_minutes("OPENARGA_DEMO_IDLE_MINUTES", 30))


def is_copy_subject(subject: str) -> bool:
    return copies_on() and COPY_SUBJECT.match(subject) is not None


CLAIM = text("""
    update kernel.demo_copies set status = 'claimed', claimed_at = now()
    where tag = (
        select tag from kernel.demo_copies
        where status = 'ready'
        order by locale = :locale desc, created_at
        limit 1
        for update skip locked
    )
    returning tag, locale, claimed_at
""")
WAKE = text("""
    update kernel.users set last_seen_at = now()
    where subject like 'demo-' || :tag || '-%'
""")


class ClaimIn(BaseModel):
    locale: Literal["en", "es"]


class ClaimOut(BaseModel):
    tag: str
    locale: str
    until: datetime


@router.post("/internal/demo/claim")
async def claim(body: ClaimIn) -> ClaimOut:
    if not copies_on():
        raise HTTPException(status_code=404, detail="this instance does not hand out demo copies")
    async with engine().begin() as connection:
        row = (await connection.execute(CLAIM, {"locale": body.locale})).first()
        if row is None:
            raise HTTPException(status_code=409, detail="no demo copy is free right now")
        await connection.execute(WAKE, {"tag": row.tag})
    return ClaimOut(tag=row.tag, locale=row.locale, until=row.claimed_at + lifetime())
