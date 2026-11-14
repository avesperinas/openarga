from __future__ import annotations

import json
import os
from datetime import date, datetime, timedelta
from typing import Any, Literal

import httpx
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from arga_tenancy import kernel_url, user_headers
from insights import clock, insights, signals, talk
from insights.words import say

MODULE = "insights"
CAPABILITY = "claude.run"
MORNING_FROM, MORNING_UNTIL = 7, 21
WEEKLY_FROM = 18
WEEKLY_UNTIL_MONDAY = 12
MAX_ATTEMPTS = 3
SEEN_DAYS = 14
TOLD_DAYS = 90

Kind = Literal["morning", "weekly"]


def _week_key(day: date) -> str:
    year, week, _ = day.isocalendar()
    return f"weekly:{year}-W{week:02d}"


def due(now: datetime) -> list[tuple[Kind, str]]:
    local = now.astimezone(clock.zone())
    out: list[tuple[Kind, str]] = []
    if MORNING_FROM <= local.hour < MORNING_UNTIL:
        out.append(("morning", f"morning:{local.date().isoformat()}"))
    if local.weekday() == 6 and local.hour >= WEEKLY_FROM:
        out.append(("weekly", _week_key(local.date())))
    if local.weekday() == 0 and local.hour < WEEKLY_UNTIL_MONDAY:
        out.append(("weekly", _week_key(local.date() - timedelta(days=1))))
    return out


def attempt_key(key: str, attempt: int) -> str:
    return key if attempt <= 1 else f"{key}#{attempt}"


ASKED_AS = "'insights:' || r.key || case when r.attempt > 1 then '#' || r.attempt else '' end"

RUN = text("select outcome, attempt from insights.insights_run where key = :key")

FINISHED = text("""
    select payload->>'outcome' as outcome, payload->>'detail' as detail,
           payload->>'code' as code, payload->>'ran_with' as ran_with
    from insights.events
    where type = 'hub.run' and payload->>'key' = :key
    order by ts desc limit 1
""")

SEEN = text(f"""
    select r.signal_ids from insights.insights_run r
    where r.kind = 'morning' and r.outcome = 'queued' and r.key <> :key
      and r.asked_at > now() - make_interval(days => :days)
      and exists (
          select 1 from insights.events e
          where e.type = 'hub.run' and e.payload->>'key' = {ASKED_AS}
            and e.payload->>'outcome' = 'ok'
      )
""")

SAVE = text("""
    insert into insights.insights_run (kind, key, outcome, detail, signal_ids, attempt)
    values (:kind, :key, :outcome, :detail, cast(:ids as jsonb), :attempt)
    on conflict (user_id, key) do update
    set outcome = excluded.outcome, detail = excluded.detail, signal_ids = excluded.signal_ids,
        attempt = excluded.attempt, asked_at = now()
""")


async def finished(connection: AsyncConnection, key: str, attempt: int) -> Any:
    asked_as = f"{MODULE}:{attempt_key(key, attempt)}"
    return (await connection.execute(FINISHED, {"key": asked_as})).one_or_none()


async def next_attempt(connection: AsyncConnection, key: str) -> int | None:
    previous = (await connection.execute(RUN, {"key": key})).one_or_none()
    if previous is None:
        return 1
    if previous.outcome != "queued":
        return previous.attempt
    ended = await finished(connection, key, previous.attempt)
    if ended is None or ended.outcome == "ok" or previous.attempt >= MAX_ATTEMPTS:
        return None
    return previous.attempt + 1


async def seen(connection: AsyncConnection, key: str) -> set[str]:
    rows = await connection.execute(SEEN, {"key": key, "days": SEEN_DAYS})
    return {one for row in rows for one in (row.signal_ids or [])}


async def save(
    connection: AsyncConnection,
    kind: Kind,
    key: str,
    outcome: str,
    found: list[signals.Signal],
    detail: str | None = None,
    attempt: int = 1,
) -> None:
    await connection.execute(
        SAVE,
        {
            "kind": kind,
            "key": key,
            "outcome": outcome,
            "detail": detail[:500] if detail else None,
            "ids": json.dumps([one.id for one in found]),
            "attempt": attempt,
        },
    )


RATINGS = {"useful": "it helped", "known": "they knew it", "not_applicable": "does not apply"}


def _told(given: list[insights.Insight]) -> list[str]:
    if not given:
        return ["(You have not told them anything yet.)"]
    return [
        f'- {one.created_at.astimezone(clock.zone()):%Y-%m-%d} · {one.topic} · "{one.title}" · '
        + (RATINGS[one.rating] if one.rating else "not rated")
        for one in given
    ]


def _signals(found: list[signals.Signal]) -> list[str]:
    return [f"- [{one.id}] {one.text}" for one in found] or ["(None.)"]


BAR = [
    "The bar (if it does not pass, it is not published; insights_publish_insight refuses what "
    "lacks it):",
    "1. Quote one of their figures and its baseline (their average, their band, their pace, "
    "their goal), not a general rule. In `figures`, the main one first.",
    "2. Say what it affects: one of their goals, something in their profile or a consequence "
    "with a date.",
    "3. Propose a concrete and checkable action: what, how much and when.",
    "4. Do not repeat advice from the last 30 days on the same topic unless the figure changed. "
    'What they rated "they knew it", only with something they do not know; what "does not '
    'apply", do not come back to it.',
]


def voice() -> list[str]:
    from insights.craft import written_in

    return [
        f"How to write: in {written_in()}, informally, direct and brief, without cheering. The "
        "body in short paragraphs separated by a blank line, without Markdown or headings: what "
        "you see, why it matters and what you would do. Numbers in that language's usual format. "
        "Do not diagnose: on health, say what you see in their figures and when it is worth "
        "asking a doctor.",
        "You only write to Insights, with insights_publish_insight. Do not use insights_reply: "
        "there is no conversation here. If a piece of data is not there, do not invent it.",
    ]


def _head(profile: insights.Profile, today: str) -> list[str]:
    lines = [
        f"You are {profile.name}, a person's adviser inside arga, their personal system. Today "
        f"is {today}. You look at all their data at once with arga's read tools (figures, money "
        "movements, workouts, food, goals, agenda, notes) and write to them what you see that "
        "matters.",
    ]
    if profile.about.strip():
        lines += ["", "What the person has told you about themselves:", profile.about.strip()]
    else:
        lines += [
            "",
            "They have told you nothing about themselves: advise with what their data says.",
        ]
    return lines


def morning_brief(
    profile: insights.Profile,
    fresh: list[signals.Signal],
    standing: list[signals.Signal],
    given: list[insights.Insight],
    today: str,
) -> str:
    lines = [
        *_head(profile, today),
        "",
        "This is your morning look. Insights has already measured, without a model, what falls "
        "outside their usual:",
        "",
        "New signals:",
        *_signals(fresh),
        "",
        "Signals still standing that were there other mornings (only if they change something):",
        *_signals(standing),
        "",
        "What you told them in the last 90 days, with their rating:",
        *_told(given),
        "",
        "What you do:",
        "1. Look closely at each new signal with the read tools: where it comes from, whether it "
        "is a badly logged figure, what explains it and which other figures move with it. "
        "insights_get_series gives you any figure over any range.",
        "2. Cross them: what is worth most is what no app sees alone.",
        '3. Publish with insights_publish_insight, kind "alert", at most two pieces of advice, '
        "only what passes the bar. A stable and short `topic` (the figure's key, "
        "`vitals.weight`, or `money.spend:restaurants`): it is what avoids repeating yourself.",
        "4. If nothing passes the bar, publish nothing. Staying quiet is normal.",
        "",
        *BAR,
        "",
        *voice(),
    ]
    return "\n".join(lines)


def weekly_brief(
    profile: insights.Profile,
    week: list[signals.Signal],
    given: list[insights.Insight],
    today: str,
    monday: date,
    sunday: date,
    key: str,
) -> str:
    topic = "week:" + key.split(":", 1)[1].lower()
    lines = [
        *_head(profile, today),
        "",
        f"Time for the summary of their week, from Monday {monday:%d/%m} to Sunday {sunday:%d/%m}.",
        "",
        "The week's signals, measured without a model:",
        *_signals(week),
        "",
        "What you told them in the last 90 days, with their rating:",
        *_told(given),
        "",
        "What you do:",
        "1. Go over the week by area with the read tools: money (Money, Career), body (Vitals, "
        "Macros, Training), time and goals (Planner, Goals, Notebook) and leisure and travel "
        "(Library, Travel, Outings). In each, what moved against their usual, with figures. If an "
        "area has nothing, say it in one line or leave it out.",
        '2. Publish exactly one with insights_publish_insight: kind "weekly", domain "cross", '
        f'topic "{topic}", a short title that says the main thing of the week. In the body, one '
        "paragraph per area. In `figures`, the three to six figures that matter most, each with "
        "its baseline. In `affects`, the goal or part of their profile that weighs most this "
        "week. In `action`, the proposal that matters most, in one sentence.",
        "3. In `proposals`, 3 to 7 proposals for next week, the most important first. Each "
        "concrete and checkable (`what`: what, how much and when), with the figure it moves and "
        "its baseline (`figure`), and in `how` how it is applied: the app and what an assistant "
        "would do with its tools when the person asks (`Planner: a 45 min block on Tuesday at "
        "19:00`). You apply none: you only propose them. No filler proposals: if the week gives "
        "no more, three.",
        "4. This one is always published, even if the week was quiet: then say that, with the "
        "figures that show it.",
        "",
        *BAR[:4],
        "",
        *voice(),
    ]
    return "\n".join(lines)


def timeout() -> float:
    return float(os.environ.get("HUB_TIMEOUT_SECONDS", "30"))


def transport() -> httpx.AsyncBaseTransport | None:
    return None


async def ask(key: str, prompt: str, tools: tuple[str, ...] = ()) -> dict[str, Any]:
    body: dict[str, Any] = {"key": key, "prompt": prompt, "wait_for_room": True}
    if tools:
        body["tools"] = list(tools)
    try:
        async with httpx.AsyncClient(transport=transport()) as client:
            response = await client.post(
                f"{kernel_url()}/internal/capabilities/{CAPABILITY}",
                json=body,
                headers={**user_headers(), "x-arga-module": MODULE},
                timeout=timeout(),
            )
    except httpx.HTTPError as error:
        return {"outcome": "error", "detail": f"Hub does not answer ({type(error).__name__})"}
    if response.status_code != 200:
        return {"outcome": "error", "detail": f"Hub answers {response.status_code}"}
    return response.json()


NOT_GRANTED = "Insights is not allowed to use your AI: allow it in Hub."


def refused_detail(answer: dict[str, Any]) -> str | None:
    if answer.get("outcome") in ("queued", "running") or answer.get("repeated"):
        return None
    if answer.get("code") == "not_granted":
        return NOT_GRANTED
    return str(answer.get("detail") or "Hub did not note the pass.")


def week_of(key: str) -> tuple[date, date]:
    year, week = key.split(":", 1)[1].split("-W")
    monday = date.fromisocalendar(int(year), int(week), 1)
    return monday, monday + timedelta(days=6)


async def run(connection: AsyncConnection, kind: Kind, key: str, now: datetime) -> str | None:
    attempt = await next_attempt(connection, key)
    if attempt is None:
        return None
    local = now.astimezone(clock.zone())
    today = local.date()
    profile = await insights.profile(connection)
    given = await insights.recent(connection, limit=60, since=now - timedelta(days=TOLD_DAYS))
    said_today = talk.said_day(local)
    if kind == "morning":
        found = await signals.read(connection, today - timedelta(days=1), today)
        before = await seen(connection, key)
        fresh = [one for one in found if one.id not in before]
        if not fresh:
            await save(connection, kind, key, "quiet", found, attempt=attempt)
            return "quiet"
        standing = [one for one in found if one.id in before]
        prompt = morning_brief(profile, fresh, standing, given, said_today)
    else:
        monday, sunday = week_of(key)
        found = await signals.read(connection, monday, min(sunday, today))
        prompt = weekly_brief(profile, found, given, said_today, monday, sunday, key)
    answer = await ask(attempt_key(key, attempt), prompt)
    problem = refused_detail(answer)
    if problem:
        await save(connection, kind, key, "refused", found, problem, attempt=attempt)
        return "refused"
    await save(connection, kind, key, "queued", found, attempt=attempt)
    return "queued"


LAST_RUNS = text("""
    select distinct on (kind) kind, key, outcome, detail, attempt,
           jsonb_array_length(signal_ids) as signals, asked_at
    from insights.insights_run
    order by kind, asked_at desc
""")

RECENT_RUNS = text("""
    select kind, key, outcome, detail, attempt, jsonb_array_length(signal_ids) as signals, asked_at
    from insights.insights_run
    where asked_at > now() - make_interval(days => :days)
    order by asked_at desc
""")

FIXES = ("no_room", "no_account", "not_granted", "rate_limited")


def fix_for(code: str | None) -> str | None:
    return say(f"run.fix.{code}") if code in FIXES else None


class LastRun(BaseModel):
    kind: Kind
    key: str
    asked_at: datetime
    signals: int
    state: str
    detail: str | None
    attempt: int = 1
    ran_with: str | None = None
    fix: str | None = None


async def _told_run(connection: AsyncConnection, row: Any) -> LastRun:
    state, detail, ran_with, fix = row.outcome, row.detail, None, None
    if row.outcome == "queued":
        done = await finished(connection, row.key, row.attempt)
        state = done.outcome if done else "waiting"
        detail = done.detail if done else None
        ran_with = done.ran_with if done else None
        if done and done.outcome != "ok":
            fix = fix_for(done.code or done.outcome)
            if fix is None:
                fix = (
                    say("run.retry", attempt=row.attempt, attempts=MAX_ATTEMPTS)
                    if row.attempt < MAX_ATTEMPTS
                    else say("run.gave_up")
                )
    elif row.outcome == "refused":
        fix = fix_for("not_granted") if row.detail == NOT_GRANTED else None
    return LastRun(
        kind=row.kind,
        key=row.key,
        asked_at=row.asked_at,
        signals=row.signals,
        state=state,
        detail=detail,
        attempt=row.attempt,
        ran_with=ran_with,
        fix=fix,
    )


async def last(connection: AsyncConnection) -> list[LastRun]:
    return [await _told_run(connection, row) for row in await connection.execute(LAST_RUNS)]


async def recent(connection: AsyncConnection, days: int = 14) -> list[LastRun]:
    rows = (await connection.execute(RECENT_RUNS, {"days": days})).all()
    return [await _told_run(connection, row) for row in rows]
