from __future__ import annotations

import json
from datetime import datetime, timedelta
from typing import Literal

from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

Kind = Literal["alert", "weekly"]
Domain = Literal["money", "body", "time", "leisure", "cross"]
Rating = Literal["useful", "known", "not_applicable"]

QUIET = timedelta(days=30)
CHANGED = 0.05

NAME = "Insights"


class NotFound(Exception):
    pass


class Repeated(Exception):
    pass


class Figure(BaseModel):
    label: str = Field(
        min_length=1,
        max_length=80,
        description="What is measured: `restaurant spending in September`.",
    )
    value: float = Field(description="The person's figure.")
    unit: str | None = Field(default=None, max_length=20, description="`€`, `kg`, `steps`, `h`.")
    baseline: float = Field(description="What is normal for them, what `value` is compared with.")
    baseline_label: str = Field(
        min_length=3,
        max_length=80,
        description=(
            "What that baseline is: `your 90-day average`, `your target`, `the goal's pace`."
        ),
    )


class Proposal(BaseModel):
    what: str = Field(
        min_length=10,
        max_length=200,
        description=(
            "What to do next week, concretely: `three dinners at home from Monday to Thursday`."
        ),
    )
    figure: Figure = Field(description="The figure it moves, with its baseline.")
    how: str = Field(
        min_length=5,
        max_length=200,
        description=(
            "How it is applied by asking an assistant: the app and what it does. `Shopping: add "
            "three dinners to the list`, `Planner: a 45 min block on Tuesday at 19:00`."
        ),
    )


PROPOSALS = (3, 7)


class InsightIn(BaseModel):
    kind: Kind = Field(
        default="alert",
        description="`alert` for a single piece of advice; `weekly` for the Sunday summary.",
    )
    domain: Domain = Field(
        description=(
            "Where it comes from: money, body, time and goals, leisure and travel, or `cross` if "
            "it crosses several."
        )
    )
    topic: str = Field(
        pattern=r"^[a-z0-9][a-z0-9._:-]{1,79}$",
        description=(
            "What it is about, to avoid repeating it: `money.spend:restaurants`, `vitals.weight`."
        ),
    )
    title: str = Field(min_length=1, max_length=120, description="What shows in the inbox.")
    body: str = Field(
        min_length=1,
        max_length=6000,
        description=(
            "The whole advice, in the second person and in paragraphs separated by a blank line. "
            "Brief: what you see, why it matters and what you would do."
        ),
    )
    figures: list[Figure] = Field(
        min_length=1,
        max_length=12,
        description=("The figures it rests on, the main one first, each with its baseline."),
    )
    affects: str = Field(
        min_length=3,
        max_length=300,
        description=(
            "Which goal or thing of the person it affects: "
            "`the goal of getting to 78 kg in December`."
        ),
    )
    action: str = Field(
        min_length=20,
        max_length=600,
        description="What to do, concrete and checkable: what, how much and when.",
    )
    proposals: list[Proposal] = Field(
        default_factory=list,
        max_length=PROPOSALS[1],
        description=(
            "Only in the Sunday summary, and always there: 3 to 7 proposals for next week, the "
            "most important first. They are applied when the person asks an assistant, never on "
            "their own."
        ),
    )


class Insight(InsightIn):
    id: str
    created_at: datetime
    read_at: datetime | None
    rating: Rating | None
    rated_at: datetime | None


class Profile(BaseModel):
    name: str
    about: str
    named: bool


class ProfileIn(BaseModel):
    name: str | None = Field(default=None, max_length=24)
    about: str = Field(default="", max_length=8000)


class RatingIn(BaseModel):
    rating: Rating | None


COLUMNS = (
    "id::text as id, kind, domain, topic, title, body, figures, affects, action, created_at, "
    "read_at, rating, rated_at, proposals"
)


def _insight(row) -> Insight:
    return Insight.model_validate(dict(row._mapping))


async def profile(connection: AsyncConnection) -> Profile:
    row = (
        await connection.execute(text("select name, about from insights.insights_profile"))
    ).first()
    name = (row.name or "").strip() if row else ""
    return Profile(name=name or NAME, about=row.about if row else "", named=bool(name))


async def save_profile(connection: AsyncConnection, wanted: ProfileIn) -> Profile:
    name = (wanted.name or "").strip() or None
    await connection.execute(
        text("""
            insert into insights.insights_profile (name, about) values (:name, :about)
            on conflict (user_id) do update
            set name = excluded.name, about = excluded.about, updated_at = now()
        """),
        {"name": name, "about": wanted.about},
    )
    return await profile(connection)


async def publish(connection: AsyncConnection, insight: InsightIn) -> Insight:
    if insight.kind == "alert":
        await _not_repeated(connection, insight)
    row = (
        await connection.execute(
            text(f"""
                insert into insights.insights_insight
                    (kind, domain, topic, title, body, figures, affects, action, proposals)
                values (:kind, :domain, :topic, :title, :body, cast(:figures as jsonb), :affects,
                        :action, cast(:proposals as jsonb))
                returning {COLUMNS}
            """),
            {
                **insight.model_dump(exclude={"figures", "proposals"}),
                "figures": json.dumps([one.model_dump() for one in insight.figures]),
                "proposals": json.dumps([one.model_dump() for one in insight.proposals]),
            },
        )
    ).one()
    return _insight(row)


async def _not_repeated(connection: AsyncConnection, insight: InsightIn) -> None:
    last = (
        await connection.execute(
            text("""
                select figures, created_at from insights.insights_insight
                where kind = 'alert' and topic = :topic
                  and created_at > now() - make_interval(days => :days)
                order by created_at desc limit 1
            """),
            {"topic": insight.topic, "days": QUIET.days},
        )
    ).first()
    if last is None:
        return
    before = float(last.figures[0]["value"])
    now = insight.figures[0].value
    moved = abs(now - before) > CHANGED * max(abs(before), 1e-9)
    if not moved:
        raise Repeated(
            f"you already gave advice on '{insight.topic}' on {last.created_at:%Y-%m-%d} with the "
            f"same figure ({before:g}); only come back if the figure changes more than "
            f"{CHANGED:.0%}"
        )


async def recent(
    connection: AsyncConnection, *, limit: int = 50, since: datetime | None = None
) -> list[Insight]:
    rows = await connection.execute(
        text(f"""
            select {COLUMNS} from insights.insights_insight
            where cast(:since as timestamptz) is null or created_at >= cast(:since as timestamptz)
            order by created_at desc limit :limit
        """),
        {"limit": limit, "since": since},
    )
    return [_insight(row) for row in rows]


async def one(connection: AsyncConnection, insight_id: str) -> Insight:
    row = (
        await connection.execute(
            text(f"select {COLUMNS} from insights.insights_insight where id = cast(:id as uuid)"),
            {"id": insight_id},
        )
    ).first()
    if row is None:
        raise NotFound(insight_id)
    return _insight(row)


async def mark_read(connection: AsyncConnection, insight_id: str) -> Insight:
    await connection.execute(
        text("""
            update insights.insights_insight set read_at = coalesce(read_at, now())
            where id = cast(:id as uuid)
        """),
        {"id": insight_id},
    )
    return await one(connection, insight_id)


async def rate(connection: AsyncConnection, insight_id: str, wanted: RatingIn) -> Insight:
    await connection.execute(
        text("""
            update insights.insights_insight
            set rating = cast(:rating as text),
                rated_at = case when cast(:rating as text) is null then null else now() end,
                read_at = coalesce(read_at, now())
            where id = cast(:id as uuid)
        """),
        {"id": insight_id, "rating": wanted.rating},
    )
    return await one(connection, insight_id)


async def unread(connection: AsyncConnection) -> int:
    return await connection.scalar(
        text("select count(*) from insights.insights_insight where read_at is null")
    )
