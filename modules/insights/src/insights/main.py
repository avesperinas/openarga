from __future__ import annotations

from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Literal
from uuid import UUID
from zoneinfo import ZoneInfo

from fastapi import HTTPException, Query, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncConnection

from arga_module.service import Service
from insights import (
    craft,
    hub,
    insights,
    passes,
    picks,
    pills,
    publisher,
    signals,
    talk,
    tastes,
    tools,
    voice,
    widgets,
)
from insights import panel as home_panel

MODULE_ID = "insights"
MADRID = ZoneInfo("Europe/Madrid")

service = Service(
    MODULE_ID,
    "Insights",
    tools=tools.TOOLS,
    role_for_scopes=tools.role_for_scopes,
    widgets=widgets.RENDERERS,
    panel=home_panel.build,
    errors={
        insights.NotFound: 404,
        talk.NotFound: 404,
        tastes.NotFound: 404,
        pills.NotFound: 404,
        picks.NotFound: 404,
        voice.NoAudio: 404,
        tastes.Refused: 409,
        picks.Conflict: 409,
        craft.TooMany: 429,
    },
    publisher=publisher.PUBLISHER,
    ui_dist=Path(__file__).resolve().parents[2] / "ui" / "dist",
)
app = service.app
as_role = service.as_role
_app = service.edit


@app.get("/badge")
async def badge() -> dict:
    async with service.as_reader() as connection:
        pill = await pills.daily(connection, datetime.now(MADRID).date())
        waiting = await tastes.current_question(connection)
        count = await insights.unread(connection)
        count += int(pill is not None and pill.read_at is None) + int(waiting is not None)
        return {"count": count}


@app.get("/profile")
async def read_profile() -> insights.Profile:
    return await _app(insights.profile)


@app.put("/profile")
async def save_profile(request: insights.ProfileIn) -> insights.Profile:
    return await _app(insights.save_profile, request)


@app.get("/insights")
async def list_insights(limit: int = Query(default=50, ge=1, le=200)) -> list[insights.Insight]:

    async def found(connection: AsyncConnection) -> list[insights.Insight]:
        return await insights.recent(connection, limit=limit)

    return await _app(found)


@app.get("/insights/{insight_id}")
async def read_insight(insight_id: UUID) -> insights.Insight:
    return await _app(insights.one, str(insight_id))


@app.post("/insights/{insight_id}/read")
async def mark_read(insight_id: UUID) -> insights.Insight:
    return await _app(insights.mark_read, str(insight_id))


@app.put("/insights/{insight_id}/rating")
async def rate_insight(insight_id: UUID, request: insights.RatingIn) -> insights.Insight:
    return await _app(insights.rate, str(insight_id), request)


@app.get("/signals")
async def list_signals(days: int = Query(default=7, ge=1, le=31)) -> list[signals.Signal]:
    today = datetime.now(MADRID).date()

    async def found(connection: AsyncConnection) -> list[signals.Signal]:
        return await signals.read(connection, today - timedelta(days=days - 1), today)

    async with service.as_reader() as connection:
        return await found(connection)


@app.get("/runs")
async def list_runs() -> list[passes.LastRun]:
    async with service.as_reader() as connection:
        return await passes.last(connection)


async def _brief(connection: AsyncConnection, thread_id: str) -> str:
    conversation = await talk.thread(connection, thread_id)
    about = (
        await insights.one(connection, conversation.insight_id) if conversation.insight_id else None
    )
    today = talk.said_day(datetime.now(MADRID))
    found = tastes.described(await tastes.traits(connection))
    return talk.brief(await insights.profile(connection), conversation, about, today, found)


async def _ask(thread_id: str, key: str) -> talk.ThreadOut:
    prompt = await _app(_brief, thread_id)
    problem = await talk.ask(key, prompt)
    if problem:
        await _app(talk.failed, thread_id, problem)
    return await _app(talk.thread, thread_id)


async def _settled(connection: AsyncConnection, thread_id: str) -> talk.ThreadOut:
    await talk.settle(connection, thread_id)
    return await talk.thread(connection, thread_id)


@app.get("/threads")
async def list_threads() -> list[talk.Thread]:

    async def listed(connection: AsyncConnection) -> list[talk.Thread]:
        for one in await talk.threads(connection):
            if one.waiting_since is not None:
                await talk.settle(connection, one.id)
        return await talk.threads(connection)

    return await _app(listed)


@app.post("/threads", status_code=201)
async def start_thread(request: talk.Start) -> talk.ThreadOut:

    async def begin(connection: AsyncConnection) -> tuple[str, str]:
        thread_id = await talk.start(connection, request)
        last = (await talk.thread(connection, thread_id)).messages[-1].id
        return thread_id, last

    thread_id, message_id = await _app(begin)
    return await _ask(thread_id, f"thread:{message_id}")


@app.get("/threads/{thread_id}")
async def read_thread(thread_id: UUID) -> talk.ThreadOut:
    return await _app(_settled, str(thread_id))


@app.delete("/threads/{thread_id}", status_code=204)
async def delete_thread(thread_id: UUID) -> Response:
    await _app(talk.remove, str(thread_id))
    return Response(status_code=204)


@app.post("/threads/{thread_id}/messages", status_code=201)
async def say(thread_id: UUID, request: talk.Say) -> talk.ThreadOut:
    message_id = await _app(talk.add, str(thread_id), "person", request.text)
    return await _ask(str(thread_id), f"thread:{message_id}")


@app.post("/threads/{thread_id}/retry")
async def retry(thread_id: UUID) -> talk.ThreadOut:

    async def again(connection: AsyncConnection) -> str:
        conversation = await talk.thread(connection, str(thread_id))
        last = conversation.messages[-1]
        if last.author != "person":
            raise HTTPException(status_code=409, detail="already answered")
        await talk.add_waiting(connection, str(thread_id))
        return last.id

    message_id = await _app(again)
    stamp = datetime.now(MADRID).strftime("%Y%m%d%H%M%S")
    return await _ask(str(thread_id), f"thread:{message_id}:again:{stamp}")


class Today(BaseModel):
    day: date
    pill: pills.Pill | None
    asked: pills.Ask | None
    facts: list[pills.Fact]
    picks: list[picks.Pick]
    question: tastes.Question | None
    onboarding: tastes.Onboarding
    settings: tastes.Settings
    streak: int
    unread: int
    latest: insights.Insight | None
    waiting: list[pills.Ask]


async def _today(connection: AsyncConnection) -> Today:
    now = datetime.now(MADRID)
    day = now.date()
    await tastes.ensure_defaults(connection)
    pill = await pills.daily(connection, day)
    asked = None if pill else await pills.ask_by_key(connection, f"pill:{day.isoformat()}")
    recent = await insights.recent(connection, limit=1)
    waiting = [
        one
        for one in await pills.recent_asks(connection, days=1)
        if one.kind == "more" and one.state == "waiting"
    ]
    return Today(
        day=day,
        pill=pill,
        asked=asked,
        facts=await pills.facts(connection, day),
        picks=await picks.listed(connection, pill_id=pill.id) if pill else [],
        question=await tastes.current_question(connection),
        onboarding=await tastes.onboarding(connection),
        settings=await tastes.settings(connection),
        streak=pills.streak(await pills.read_days(connection), day),
        unread=await insights.unread(connection),
        latest=recent[0] if recent else None,
        waiting=waiting,
    )


@app.get("/today")
async def today() -> Today:
    return await _app(_today)


class PillOut(BaseModel):
    pill: pills.Pill
    picks: list[picks.Pick]
    children: list[pills.PillLine]
    parent: pills.PillLine | None


async def _pill_out(connection: AsyncConnection, pill_id: str) -> PillOut:
    found = await pills.one(connection, pill_id)
    parent = None
    if found.parent_id:
        lines = [one for one in await pills.recent(connection, 400) if one.id == found.parent_id]
        parent = lines[0] if lines else None
    return PillOut(
        pill=found,
        picks=await picks.listed(connection, pill_id=pill_id),
        children=await pills.children(connection, pill_id),
        parent=parent,
    )


@app.get("/pills")
async def list_pills(limit: int = Query(default=60, ge=1, le=200)) -> list[pills.PillLine]:
    async def found(connection: AsyncConnection) -> list[pills.PillLine]:
        return await pills.recent(connection, limit=limit)

    return await _app(found)


@app.get("/pills/{pill_id}")
async def read_pill(pill_id: UUID) -> PillOut:
    return await _app(_pill_out, str(pill_id))


@app.post("/pills/{pill_id}/read")
async def read_it(pill_id: UUID) -> pills.Pill:
    return await _app(pills.mark_read, str(pill_id))


class PillReaction(BaseModel):
    reaction: pills.Reaction | None


def byte_range(header: str | None, size: int) -> tuple[int, int] | None:
    if not header or not header.startswith("bytes=") or "," in header:
        return None
    first, _, last = header.removeprefix("bytes=").strip().partition("-")
    try:
        if not first:
            start, end = max(0, size - int(last)), size - 1
        else:
            start, end = int(first), min(int(last), size - 1) if last else size - 1
    except ValueError:
        return None
    if start > end or start >= size:
        raise HTTPException(status_code=416, headers={"content-range": f"bytes */{size}"})
    return start, end


@app.api_route("/pills/{pill_id}/audio", methods=["GET", "HEAD"])
async def pill_audio(pill_id: UUID, request: Request) -> Response:
    content, kind = await _app(voice.content, str(pill_id))
    size = len(content)
    headers = {"accept-ranges": "bytes", "cache-control": "private, max-age=604800"}
    wanted = byte_range(request.headers.get("range"), size)
    if wanted is None:
        return Response(content=content, media_type=kind, headers=headers)
    start, end = wanted
    headers["content-range"] = f"bytes {start}-{end}/{size}"
    return Response(
        content=content[start : end + 1], status_code=206, media_type=kind, headers=headers
    )


@app.put("/pills/{pill_id}/reaction")
async def react_pill(pill_id: UUID, request: PillReaction) -> pills.Pill:
    return await _app(pills.react, str(pill_id), request.reaction)


class MoreIn(BaseModel):
    origin: Literal["surprise", "branch"]
    parent_id: UUID | None = None
    branch: str | None = Field(default=None, max_length=200)


@app.post("/pills/more", status_code=201)
async def ask_more(request: MoreIn) -> pills.Ask:

    async def asked(connection: AsyncConnection) -> pills.Ask:
        return await craft.more(
            connection,
            datetime.now(MADRID),
            origin=request.origin,
            parent_id=str(request.parent_id) if request.parent_id else None,
            branch=request.branch,
        )

    return await _app(asked)


@app.get("/asks/{ask_id}")
async def read_ask(ask_id: UUID) -> pills.Ask:
    return await _app(pills.one_ask, str(ask_id))


@app.get("/facts")
async def list_facts(days: int = Query(default=14, ge=1, le=120)) -> list[pills.Fact]:
    since = datetime.now(MADRID).date() - timedelta(days=days - 1)

    async def found(connection: AsyncConnection) -> list[pills.Fact]:
        return await pills.facts(connection, since)

    return await _app(found)


class FactReaction(BaseModel):
    reaction: Literal["interested", "known"] | None


@app.put("/facts/{fact_id}/reaction")
async def react_fact(fact_id: UUID, request: FactReaction) -> pills.Fact:
    return await _app(pills.react_fact, str(fact_id), request.reaction)


@app.get("/tastes")
async def read_tastes() -> tastes.Tastes:
    async def found(connection: AsyncConnection) -> tastes.Tastes:
        await tastes.ensure_defaults(connection)
        return await tastes.everything(connection)

    return await _app(found)


@app.put("/settings")
async def save_settings(request: tastes.SettingsIn) -> tastes.Settings:
    return await _app(tastes.save_settings, request)


@app.post("/traits", status_code=201)
async def add_trait(request: tastes.TraitIn) -> tastes.Trait:
    return await _app(tastes.add_trait, request)


@app.put("/traits/{trait_id}")
async def change_trait(trait_id: UUID, request: tastes.TraitChange) -> tastes.Trait:
    return await _app(tastes.change_trait, str(trait_id), request)


@app.delete("/traits/{trait_id}", status_code=204)
async def forget_trait(trait_id: UUID) -> Response:
    await _app(tastes.forget_trait, str(trait_id))
    return Response(status_code=204)


@app.get("/onboarding")
async def read_onboarding() -> tastes.Onboarding:
    async def found(connection: AsyncConnection) -> tastes.Onboarding:
        await tastes.ensure_defaults(connection)
        return await tastes.onboarding(connection)

    return await _app(found)


class StartAnswer(BaseModel):
    answer: tastes.Answer | None = None


@app.post("/onboarding/{bank_key}")
async def answer_start(bank_key: str, request: StartAnswer) -> tastes.Onboarding:
    return await _app(tastes.answer_start, bank_key, request.answer)


@app.post("/questions/{question_id}/answer")
async def answer_question(question_id: UUID, request: StartAnswer) -> tastes.Question:
    return await _app(tastes.answer_question, str(question_id), request.answer)


@app.put("/families/{key}")
async def change_family(key: str, request: tastes.FamilyChange) -> tastes.Family:
    return await _app(tastes.change_family, key, request)


@app.post("/families", status_code=201)
async def add_family(request: tastes.FamilyIn) -> tastes.Family:
    return await _app(tastes.add_family, request)


@app.post("/sources", status_code=201)
async def add_source(request: tastes.SourceIn) -> tastes.Source:
    return await _app(tastes.add_source, request)


@app.put("/sources/{source_id}")
async def change_source(source_id: UUID, request: tastes.SourceChange) -> tastes.Source:
    return await _app(tastes.change_source, str(source_id), request)


STATES = Query(default=[])


@app.get("/picks")
async def list_picks(state: list[picks.State] = STATES) -> list[picks.Pick]:
    async def found(connection: AsyncConnection) -> list[picks.Pick]:
        return await picks.listed(connection, states=list(state) or None)

    return await _app(found)


@app.put("/picks/{pick_id}")
async def change_pick(pick_id: UUID, request: picks.PickChange) -> picks.Pick:
    return await _app(picks.change, str(pick_id), request)


@app.get("/picks/{pick_id}/cover")
async def pick_cover(pick_id: UUID) -> Response:
    content, kind = await _app(picks.cover, str(pick_id))
    return Response(
        content=content, media_type=kind, headers={"cache-control": "private, max-age=604800"}
    )


@app.post("/picks/{pick_id}/save")
async def save_pick(pick_id: UUID) -> picks.Pick:
    found = await _app(picks.one_pick, str(pick_id))
    if found.kind != "book":
        return await _app(picks.change, str(pick_id), picks.PickChange(state="saved"))
    body = await _app(picks.want_body, str(pick_id))
    try:
        await hub.want_book(body)
    except hub.Unavailable as error:
        await _app(picks.change, str(pick_id), picks.PickChange(state="saved"))
        raise HTTPException(
            status_code=502, detail=f"saved here, but not in your reading list: {error}"
        ) from error
    return await _app(picks.mark_sent, str(pick_id), "library")


service.serve_ui()
