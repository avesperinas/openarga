from __future__ import annotations

import json
import random
import re
from datetime import date, datetime, timedelta
from typing import Any, Literal

from pydantic import BaseModel, Field, HttpUrl, field_validator
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from insights import clock, tastes
from insights.voice import PillAudio
from insights.words import say

Origin = Literal["daily", "surprise", "branch"]
Reaction = Literal["interested", "known", "other"]

WORDS_PER_MINUTE = (55, 115)
SEEN_PILLS = 150
SEEN_FACTS = 200
DAYS_CAP = 14.0
OUTSIDE_EVERY = 7


class NotFound(Exception):
    pass


class Invalid(Exception):
    pass


class Section(BaseModel):
    title: str = Field(min_length=2, max_length=100, description="The section's subheading.")
    text: str = Field(
        min_length=80,
        max_length=3000,
        description="The text, in paragraphs separated by a blank line. No Markdown.",
    )


class Branch(BaseModel):
    title: str = Field(
        min_length=3,
        max_length=120,
        description="A concrete subtopic that makes you want to know more.",
    )
    why: str = Field(min_length=5, max_length=200, description="Why it hooks, in one line.")


class SourceRef(BaseModel):
    title: str = Field(min_length=2, max_length=200, description="The name of what was read.")
    url: HttpUrl = Field(description="The address you really read, with https.")
    language: str = Field(default="es", pattern=r"^[a-z]{2}$")

    @field_validator("url")
    @classmethod
    def _https(cls, value: HttpUrl) -> HttpUrl:
        if value.scheme != "https":
            raise ValueError("the source needs https")
        return value


class Word(BaseModel):
    word: str = Field(min_length=1, max_length=60)
    meaning: str = Field(min_length=1, max_length=200)


class PillIn(BaseModel):
    run_key: str = Field(
        pattern=r"^(pill|more):[0-9A-Za-z:-]{3,60}$",
        description="The task key (`pill:2026-11-11`, `more:<id>`). It comes in the task.",
    )
    family_key: str = Field(
        pattern=r"^[a-z][a-z0-9_]{1,30}$", description="The topic (`history`), the task's."
    )
    topic: str = Field(
        min_length=2,
        max_length=120,
        description="The concrete subtopic, only its name: `The battle of Leuctra`.",
    )
    hook: str | None = Field(
        default=None,
        max_length=200,
        description=(
            "Only if the topic comes from their life, why today: `You are going to Lisbon in three "
            "weeks`. Never one of their figures."
        ),
    )
    language: str = Field(default="es", pattern=r"^[a-z]{2}$")
    headline: str = Field(min_length=5, max_length=160, description="The headline, with a hook.")
    lead: str = Field(
        min_length=20, max_length=800, description="The lead: the hook in two or three sentences."
    )
    sections: list[Section] = Field(
        min_length=3, max_length=5, description="3 to 5 sections with their subheading."
    )
    to_tell: str = Field(
        min_length=20,
        max_length=600,
        description="To tell: a true and surprising fact they could tell someone.",
    )
    to_think: str | None = Field(
        default=None, max_length=400, description="To think: an open question."
    )
    branches: list[Branch] = Field(
        min_length=3, max_length=3, description="Three branches to know more."
    )
    sources: list[SourceRef] = Field(
        min_length=1,
        max_length=6,
        description="What you read to write it, the main source first.",
    )
    glossary: list[Word] = Field(
        default_factory=list,
        max_length=20,
        description="Only if it is in another language: the hard words and what they mean.",
    )


class FactIn(BaseModel):
    family_key: str = Field(pattern=r"^[a-z][a-z0-9_]{1,30}$", description="Su tema.")
    text: str = Field(
        min_length=30,
        max_length=400,
        description="The fact, true and surprising, in one or two sentences with names and dates.",
    )
    detail: str | None = Field(
        default=None, max_length=1200, description="A bit more: why it is so, the context."
    )
    source: SourceRef


class FactsIn(BaseModel):
    day: date = Field(description="The day of the facts: the task's.")
    facts: list[FactIn] = Field(min_length=3, max_length=7, description="De 3 a 7 datos.")


class Pill(BaseModel):
    id: str
    day: date
    origin: Origin
    run_key: str | None
    parent_id: str | None
    depth: int
    family_key: str
    topic: str
    hook: str | None
    language: str
    minutes: int
    headline: str
    lead: str
    sections: list[dict[str, Any]]
    to_tell: str
    to_think: str | None
    branches: list[dict[str, Any]]
    sources: list[dict[str, Any]]
    glossary: list[dict[str, Any]]
    reaction: Reaction | None
    read_at: datetime | None
    created_at: datetime
    audio: PillAudio | None = None


class PillLine(BaseModel):
    id: str
    day: date
    origin: Origin
    family_key: str
    topic: str
    headline: str
    minutes: int
    reaction: Reaction | None
    read_at: datetime | None
    parent_id: str | None


class Fact(BaseModel):
    id: str
    day: date
    family_key: str
    text: str
    detail: str | None
    source: dict[str, Any]
    reaction: Literal["interested", "known"] | None
    created_at: datetime


PILL_COLUMNS = (
    "id::text as id, day, origin, run_key, parent_id::text as parent_id, depth, family_key, "
    "topic, hook, language, minutes, headline, lead, sections, to_tell, to_think, branches, "
    "sources, glossary, reaction, read_at, created_at, "
    "(select jsonb_build_object('duration', a.duration, 'timeline', a.timeline) "
    "from insights.insights_pill_audio a where a.pill_id = insights_pill.id) as audio"
)
LINE_COLUMNS = (
    "id::text as id, day, origin, family_key, topic, headline, minutes, reaction, read_at, "
    "parent_id::text as parent_id"
)
FACT_COLUMNS = "id::text as id, day, family_key, text, detail, source, reaction, created_at"


def words(found: PillIn) -> int:
    body = " ".join([found.lead, *(one.text for one in found.sections)])
    return len(re.findall(r"\w+", body))


class Ask(BaseModel):
    id: str
    kind: str
    key: str
    origin: Origin | None
    parent_id: str | None
    branch: str | None
    family_key: str | None
    asked_at: datetime
    state: str = "waiting"
    detail: str | None = None
    pill_id: str | None = None


ASK_COLUMNS = (
    "id::text as id, kind, key, origin, parent_id::text as parent_id, branch, family_key, "
    "asked_at, outcome, detail, attempt"
)

FINISHED = text("""
    select payload->>'outcome' as outcome, payload->>'detail' as detail,
           payload->>'code' as code
    from insights.events
    where type = 'hub.run' and payload->>'key' = :key
    order by ts desc limit 1
""")


def asked_as(key: str, attempt: int) -> str:
    return f"insights:{key}" if attempt <= 1 else f"insights:{key}#{attempt}"


async def ask_state(connection: AsyncConnection, row: Any) -> Ask:
    found = Ask(
        id=row.id,
        kind=row.kind,
        key=row.key,
        origin=row.origin,
        parent_id=row.parent_id,
        branch=row.branch,
        family_key=row.family_key,
        asked_at=row.asked_at,
    )
    if row.kind in ("pill", "more"):
        pill = await connection.scalar(
            text(
                "select id::text from insights.insights_pill where run_key = :key "
                "order by created_at limit 1"
            ),
            {"key": row.key},
        )
        if pill:
            found.state, found.pill_id = "ready", pill
            return found
    if row.outcome == "refused":
        found.state, found.detail = "refused", row.detail
        return found
    if row.outcome == "quiet":
        found.state = "ready"
        return found
    done = (await connection.execute(FINISHED, {"key": asked_as(row.key, row.attempt)})).first()
    if done is None:
        return found
    if done.outcome == "ok":
        found.state = "ready" if row.kind not in ("pill", "more") else "failed"
        found.detail = None if found.state == "ready" else say("pill.not_published")
        return found
    found.state, found.detail = "failed", done.detail or done.outcome
    return found


async def one_ask(connection: AsyncConnection, ask_id: str) -> Ask:
    row = (
        await connection.execute(
            text(
                f"select {ASK_COLUMNS} from insights.insights_craft_run where id = cast(:id as uuid)"
            ),
            {"id": ask_id},
        )
    ).first()
    if row is None:
        raise NotFound(ask_id)
    return await ask_state(connection, row)


async def ask_by_key(connection: AsyncConnection, key: str) -> Ask | None:
    row = (
        await connection.execute(
            text(f"select {ASK_COLUMNS} from insights.insights_craft_run where key = :key"),
            {"key": key},
        )
    ).first()
    return await ask_state(connection, row) if row else None


async def recent_asks(connection: AsyncConnection, days: int = 14) -> list[Ask]:
    rows = (
        await connection.execute(
            text(f"""
                select {ASK_COLUMNS} from insights.insights_craft_run
                where asked_at > now() - make_interval(days => :days)
                order by asked_at desc
            """),
            {"days": days},
        )
    ).all()
    return [await ask_state(connection, row) for row in rows]


async def publish(connection: AsyncConnection, wanted: PillIn, now: datetime) -> Pill:
    run = (
        await connection.execute(
            text(f"select {ASK_COLUMNS} from insights.insights_craft_run where key = :key"),
            {"key": wanted.run_key},
        )
    ).first()
    if run is None:
        raise Invalid(f"no task with key '{wanted.run_key}'")
    already = await connection.scalar(
        text("select id::text from insights.insights_pill where run_key = :key"),
        {"key": wanted.run_key},
    )
    if already:
        raise Invalid("that task already has its pill published")
    if wanted.family_key not in {one.key for one in await tastes.families(connection)}:
        raise Invalid(f"'{wanted.family_key}' is not one of their topics")
    settings = await tastes.settings(connection)
    minutes = settings.pill_minutes
    least, most = (minutes * WORDS_PER_MINUTE[0], minutes * WORDS_PER_MINUTE[1])
    counted = words(wanted)
    if counted < least or counted > most:
        raise Invalid(
            f"the reading has {counted} words and {minutes} minutes take {least} to {most} "
            "(lead and sections)"
        )
    repeated = await connection.scalar(
        text("""
            select topic from insights.insights_pill
            where lower(topic) = lower(:topic) and created_at > :since limit 1
        """),
        {"topic": wanted.topic.strip(), "since": now - timedelta(days=365)},
    )
    if repeated:
        raise Invalid(
            f"you already told them about '{repeated}' this year: choose another subtopic"
        )
    parent_id, depth = None, 0
    origin = run.origin or "daily"
    if run.parent_id:
        parent_depth = await connection.scalar(
            text("select depth from insights.insights_pill where id = cast(:id as uuid)"),
            {"id": run.parent_id},
        )
        if parent_depth is not None:
            parent_id, depth = run.parent_id, parent_depth + 1
    row = (
        await connection.execute(
            text(f"""
                insert into insights.insights_pill
                    (day, origin, run_key, parent_id, depth, family_key, topic, hook, language,
                     minutes, headline, lead, sections, to_tell, to_think, branches, sources,
                     glossary)
                values (:day, :origin, :run_key, cast(:parent as uuid), :depth, :family_key,
                        :topic, :hook, :language, :minutes, :headline, :lead,
                        cast(:sections as jsonb), :to_tell, :to_think, cast(:branches as jsonb),
                        cast(:sources as jsonb), cast(:glossary as jsonb))
                returning {PILL_COLUMNS}
            """),
            {
                "day": now.astimezone(clock.zone()).date(),
                "origin": origin,
                "run_key": wanted.run_key,
                "parent": parent_id,
                "depth": depth,
                "family_key": wanted.family_key,
                "topic": wanted.topic.strip(),
                "hook": wanted.hook,
                "language": wanted.language,
                "minutes": minutes,
                "headline": wanted.headline.strip(),
                "lead": wanted.lead.strip(),
                "sections": json.dumps([one.model_dump() for one in wanted.sections]),
                "to_tell": wanted.to_tell.strip(),
                "to_think": wanted.to_think,
                "branches": json.dumps([one.model_dump() for one in wanted.branches]),
                "sources": json.dumps([one.model_dump(mode="json") for one in wanted.sources]),
                "glossary": json.dumps([one.model_dump() for one in wanted.glossary]),
            },
        )
    ).one()
    return Pill.model_validate(dict(row._mapping))


async def publish_facts(connection: AsyncConnection, wanted: FactsIn) -> list[Fact]:
    known = {one.key for one in await tastes.families(connection)}
    seen = {
        re.sub(r"\W+", " ", value.lower()).strip()
        for value in (
            await connection.scalars(
                text("select text from insights.insights_fact order by created_at desc limit :n"),
                {"n": SEEN_FACTS},
            )
        )
    }
    out = []
    for one in wanted.facts:
        if one.family_key not in known:
            raise Invalid(f"'{one.family_key}' is not one of their topics")
        plain = re.sub(r"\W+", " ", one.text.lower()).strip()
        if plain in seen:
            continue
        seen.add(plain)
        row = (
            await connection.execute(
                text(f"""
                    insert into insights.insights_fact (day, family_key, text, detail, source)
                    values (:day, :family, :text, :detail, cast(:source as jsonb))
                    returning {FACT_COLUMNS}
                """),
                {
                    "day": wanted.day,
                    "family": one.family_key,
                    "text": one.text.strip(),
                    "detail": one.detail,
                    "source": json.dumps(one.source.model_dump(mode="json")),
                },
            )
        ).one()
        out.append(Fact.model_validate(dict(row._mapping)))
    return out


async def one(connection: AsyncConnection, pill_id: str) -> Pill:
    row = (
        await connection.execute(
            text(f"select {PILL_COLUMNS} from insights.insights_pill where id = cast(:id as uuid)"),
            {"id": pill_id},
        )
    ).first()
    if row is None:
        raise NotFound(pill_id)
    return Pill.model_validate(dict(row._mapping))


async def daily(connection: AsyncConnection, day: date) -> Pill | None:
    row = (
        await connection.execute(
            text(f"""
                select {PILL_COLUMNS} from insights.insights_pill
                where day = :day and origin = 'daily' order by created_at desc limit 1
            """),
            {"day": day},
        )
    ).first()
    return Pill.model_validate(dict(row._mapping)) if row else None


async def recent(connection: AsyncConnection, limit: int = 60) -> list[PillLine]:
    rows = await connection.execute(
        text(
            f"select {LINE_COLUMNS} from insights.insights_pill order by created_at desc limit :limit"
        ),
        {"limit": limit},
    )
    return [PillLine.model_validate(dict(row._mapping)) for row in rows]


async def children(connection: AsyncConnection, pill_id: str) -> list[PillLine]:
    rows = await connection.execute(
        text(f"""
            select {LINE_COLUMNS} from insights.insights_pill
            where parent_id = cast(:id as uuid) order by created_at
        """),
        {"id": pill_id},
    )
    return [PillLine.model_validate(dict(row._mapping)) for row in rows]


async def mark_read(connection: AsyncConnection, pill_id: str) -> Pill:
    await connection.execute(
        text(
            "update insights.insights_pill set read_at = coalesce(read_at, now()) "
            "where id = cast(:id as uuid)"
        ),
        {"id": pill_id},
    )
    return await one(connection, pill_id)


async def react(connection: AsyncConnection, pill_id: str, reaction: Reaction | None) -> Pill:
    await connection.execute(
        text("""
            update insights.insights_pill set reaction = cast(:reaction as text),
                   read_at = coalesce(read_at, now())
            where id = cast(:id as uuid)
        """),
        {"id": pill_id, "reaction": reaction},
    )
    return await one(connection, pill_id)


async def facts(connection: AsyncConnection, since: date) -> list[Fact]:
    rows = await connection.execute(
        text(f"""
            select {FACT_COLUMNS} from insights.insights_fact
            where day >= :since order by day desc, created_at
        """),
        {"since": since},
    )
    return [Fact.model_validate(dict(row._mapping)) for row in rows]


async def react_fact(
    connection: AsyncConnection, fact_id: str, reaction: Literal["interested", "known"] | None
) -> Fact:
    row = (
        await connection.execute(
            text(f"""
                update insights.insights_fact set reaction = cast(:reaction as text)
                where id = cast(:id as uuid) returning {FACT_COLUMNS}
            """),
            {"id": fact_id, "reaction": reaction},
        )
    ).first()
    if row is None:
        raise NotFound(fact_id)
    return Fact.model_validate(dict(row._mapping))


def streak(days: set[date], today: date) -> int:
    day = today if today in days else today - timedelta(days=1)
    count, since_forgiven = 0, 7
    for _ in range(400):
        if day in days:
            count += 1
            since_forgiven += 1
        elif since_forgiven >= 7 and count > 0:
            since_forgiven = 0
        else:
            break
        day -= timedelta(days=1)
    return count


async def read_days(connection: AsyncConnection) -> set[date]:
    rows = await connection.scalars(
        text("""
            select distinct (read_at at time zone :zone)::date from insights.insights_pill
            where read_at is not null and read_at > now() - interval '400 days'
        """),
        {"zone": clock.zone().key},
    )
    return set(rows)


class Taken(BaseModel):
    family_key: str
    created_at: datetime
    reaction: Reaction | None


async def history(connection: AsyncConnection) -> list[Taken]:
    rows = await connection.execute(
        text("""
            select family_key, created_at, reaction from insights.insights_pill
            order by created_at desc limit :n
        """),
        {"n": SEEN_PILLS},
    )
    return [Taken.model_validate(dict(row._mapping)) for row in rows]


def choose(
    families: list[tastes.Family],
    taken: list[Taken],
    now: datetime,
    rng: random.Random,
    avoid: set[str] | None = None,
) -> tastes.Family:
    avoid = avoid or set()
    alive = [one for one in families if one.weight > 0 and one.key not in avoid]
    if not alive:
        alive = [one for one in families if one.key not in avoid] or families
    inside = [one for one in alive if not one.outside]
    outside = [one for one in alive if one.outside]
    if outside and inside:
        keys = {one.key for one in outside}
        since = next(
            (index for index, one in enumerate(taken) if one.family_key in keys), len(taken)
        )
        every = OUTSIDE_EVERY if max(one.weight for one in outside) >= 2 else OUTSIDE_EVERY * 2
        if since >= every - 1:
            return outside[0]
    pool = inside or alive
    best, best_score = pool[0], float("-inf")
    for family in pool:
        mine = [one for one in taken if one.family_key == family.key]
        days = (
            min((now - mine[0].created_at).total_seconds() / 86400, DAYS_CAP) if mine else DAYS_CAP
        )
        liked = sum(1 for one in mine if one.reaction == "interested")
        other = sum(1 for one in mine if one.reaction == "other")
        known = sum(1 for one in mine if one.reaction == "known")
        score = (
            (days + 0.5)
            * family.weight
            * max(0.2, 1 + 0.15 * liked - 0.12 * other - 0.04 * known)
            * (0.85 + rng.random() * 0.3)
        )
        if score > best_score:
            best, best_score = family, score
    return best
