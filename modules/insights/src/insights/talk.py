from __future__ import annotations

import os
from datetime import datetime
from typing import Literal

import httpx
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from arga_tenancy import kernel_url, user_headers
from insights import insights
from insights.words import say

MODULE = "insights"
CAPABILITY = "claude.run"
HISTORY = 30


class NotFound(Exception):
    pass


class Message(BaseModel):
    id: str
    author: Literal["person", "insights"]
    body: str
    created_at: datetime


class Thread(BaseModel):
    id: str
    title: str
    insight_id: str | None
    waiting_since: datetime | None
    problem: str | None
    created_at: datetime
    updated_at: datetime


class ThreadOut(Thread):
    messages: list[Message]


class Say(BaseModel):
    text: str = Field(min_length=1, max_length=4000)


class Start(Say):
    insight_id: str | None = None


THREAD = (
    "id::text as id, title, insight_id::text as insight_id, waiting_since, problem, "
    "created_at, updated_at"
)


async def threads(connection: AsyncConnection, limit: int = 50) -> list[Thread]:
    rows = await connection.execute(
        text(
            f"select {THREAD} from insights.insights_thread order by updated_at desc limit :limit"
        ),
        {"limit": limit},
    )
    return [Thread.model_validate(dict(row._mapping)) for row in rows]


async def thread(connection: AsyncConnection, thread_id: str) -> ThreadOut:
    row = (
        await connection.execute(
            text(f"select {THREAD} from insights.insights_thread where id = cast(:id as uuid)"),
            {"id": thread_id},
        )
    ).one_or_none()
    if row is None:
        raise NotFound(thread_id)
    messages = await connection.execute(
        text("""
            select id::text as id, author, body, created_at from insights.insights_message
            where thread_id = cast(:id as uuid) order by created_at
        """),
        {"id": thread_id},
    )
    return ThreadOut(
        **dict(row._mapping),
        messages=[Message.model_validate(dict(one._mapping)) for one in messages],
    )


def title_of(text_: str) -> str:
    line = " ".join(text_.split())
    return line if len(line) <= 80 else line[:79].rstrip() + "…"


async def start(connection: AsyncConnection, wanted: Start) -> str:
    title = title_of(wanted.text)
    if wanted.insight_id:
        title = (await insights.one(connection, wanted.insight_id)).title
    thread_id = await connection.scalar(
        text("""
            insert into insights.insights_thread (title, insight_id)
            values (:title, cast(:insight as uuid)) returning id::text
        """),
        {"title": title, "insight": wanted.insight_id},
    )
    await add(connection, thread_id, "person", wanted.text)
    return thread_id


async def add(connection: AsyncConnection, thread_id: str, author: str, body: str) -> str:
    exists = await connection.scalar(
        text("select 1 from insights.insights_thread where id = cast(:thread as uuid)"),
        {"thread": thread_id},
    )
    if not exists:
        raise NotFound(thread_id)
    message_id = await connection.scalar(
        text("""
            insert into insights.insights_message (thread_id, author, body)
            values (cast(:thread as uuid), :author, :body) returning id::text
        """),
        {"thread": thread_id, "author": author, "body": body},
    )
    await connection.execute(
        text("""
            update insights.insights_thread
            set updated_at = now(), problem = null,
                waiting_since = case when :author = 'person' then now() else null end
            where id = cast(:thread as uuid)
        """),
        {"thread": thread_id, "author": author},
    )
    return message_id


async def remove(connection: AsyncConnection, thread_id: str) -> None:
    gone = await connection.execute(
        text("delete from insights.insights_thread where id = cast(:id as uuid)"), {"id": thread_id}
    )
    if not gone.rowcount:
        raise NotFound(thread_id)


LAST_RUN = text("""
    select payload->>'outcome' as outcome, payload->>'code' as code,
           payload->>'detail' as detail
    from insights.events
    where type = 'hub.run' and payload->>'key' like :key
      and ts >= :since
    order by ts desc limit 1
""")


def problem_of(outcome: str, code: str | None, detail: str | None, answered: bool) -> str | None:
    if outcome == "ok":
        return None if answered else say("chat.no_answer")
    if outcome == "rate_limited":
        return say("chat.rate_limited")
    if code == "not_granted":
        return say("chat.not_granted")
    reason = (detail or "").strip()
    return say("chat.failed_because", reason=reason) if reason else say("chat.failed")


async def settle(connection: AsyncConnection, thread_id: str) -> None:
    conversation = await thread(connection, thread_id)
    if conversation.waiting_since is None or not conversation.messages:
        return
    asked = [one for one in conversation.messages if one.author == "person"]
    if not asked:
        return
    last = asked[-1]
    run = (
        await connection.execute(
            LAST_RUN,
            {"key": f"{MODULE}:thread:{last.id}%", "since": conversation.waiting_since},
        )
    ).one_or_none()
    if run is None:
        return
    answered = any(
        one.author == "insights" and one.created_at >= last.created_at
        for one in conversation.messages
    )
    problem = problem_of(run.outcome, run.code, run.detail, answered)
    if problem:
        await failed(connection, thread_id, problem)


async def add_waiting(connection: AsyncConnection, thread_id: str) -> None:
    await connection.execute(
        text("""
            update insights.insights_thread set waiting_since = now(), problem = null
            where id = cast(:thread as uuid)
        """),
        {"thread": thread_id},
    )


async def failed(connection: AsyncConnection, thread_id: str, problem: str) -> None:
    await connection.execute(
        text("""
            update insights.insights_thread set waiting_since = null, problem = :problem
            where id = cast(:thread as uuid)
        """),
        {"thread": thread_id, "problem": problem[:500]},
    )


def brief(
    profile: insights.Profile,
    conversation: ThreadOut,
    about: insights.Insight | None,
    today: str,
    tastes: list[str] | None = None,
) -> str:
    lines = [
        f"You are {profile.name}, a person's adviser inside arga, their personal system. Today "
        f"is {today}. They write to you in the {profile.name} app and you answer through the "
        f'insights_reply tool, with thread_id "{conversation.id}". Call it only once, at the '
        "end, with your whole answer. What does not go through insights_reply they will not see.",
        "",
        "How you answer:",
        "- With their data, not with generalities. Before answering, look at what you need with "
        "arga's read tools (figures, money movements, workouts, food, goals, Notebook notes) and "
        "quote the figures: theirs against their own baseline (their average, their goal, their "
        "pace).",
        f"- Direct and brief, in {craft_language()}, informally. No filler or cheering. In "
        "Markdown: short paragraphs, **bold** for the figure that matters, lists if you "
        "enumerate and a small table only if it compares several figures. No headings.",
        "- If you propose something, make it concrete and checkable: what, how much and when.",
        "- If a piece of data is not there, say so and say how to get it; do not invent it.",
        "- Do not diagnose: on health, say what you see in their figures and when it is worth "
        "asking a doctor.",
        "- You can only write to Insights. If they ask you to note something in another app, "
        "tell them how to do it.",
        '- If they tell you something about their tastes ("I loved it", "no football"), '
        "note it with insights_note_taste. If they ask for recommendations, publish them with "
        'insights_publish_picks (`origin` "chat"), which checks them in a catalogue, and tell '
        "them in your answer which ones came out: they will be in their Library.",
    ]
    if profile.about.strip():
        lines += ["", "What the person has told you about themselves:", profile.about.strip()]
    if tastes:
        lines += ["", "What you know of their tastes:", *tastes]
    if about is not None:
        figures = "; ".join(
            f"{one.label}: {one.value:g}{' ' + one.unit if one.unit else ''} against "
            f"{one.baseline:g} ({one.baseline_label})"
            for one in about.figures
        )
        lines += [
            "",
            f"This conversation answers advice you gave them on {about.created_at:%Y-%m-%d}:",
            f'"{about.title}". {about.body}',
            f"Figures: {figures}. What it affects: {about.affects}. What you proposed: "
            f"{about.action}",
        ]
    lines += ["", "The conversation so far (the last message is the one to answer):"]
    for message in conversation.messages[-HISTORY:]:
        who = "Person" if message.author == "person" else profile.name
        lines.append(f"[{who}] {message.body}")
    return "\n".join(lines)


def craft_language() -> str:
    from insights.craft import written_in

    return written_in()


def said_day(moment: datetime) -> str:
    return f"{moment:%A} {moment.day} {moment:%B} {moment.year}"


def timeout() -> float:
    return float(os.environ.get("HUB_TIMEOUT_SECONDS", "30"))


def transport() -> httpx.AsyncBaseTransport | None:
    return None


async def ask(key: str, prompt: str) -> str | None:
    try:
        async with httpx.AsyncClient(transport=transport()) as client:
            response = await client.post(
                f"{kernel_url()}/internal/capabilities/{CAPABILITY}",
                json={"key": key, "prompt": prompt},
                headers={**user_headers(), "x-arga-module": MODULE},
                timeout=timeout(),
            )
    except httpx.HTTPError as error:
        return say("chat.hub_silent", error=type(error).__name__)
    if response.status_code != 200:
        return say("chat.hub_refused", status=response.status_code)
    answer = response.json()
    if answer.get("outcome") in ("queued", "running") or answer.get("repeated"):
        return None
    if answer.get("code") == "not_granted":
        return say("chat.not_granted")
    return answer.get("detail") or say("chat.not_noted")
