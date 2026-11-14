from __future__ import annotations

import random
from datetime import date, datetime, time, timedelta
from typing import Any, Literal
from uuid import uuid4

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from arga_module import preferences
from insights import clock, insights, passes, picks, pills, talk, tastes

Kind = Literal["pill", "more", "picks", "profile"]

AHEAD = timedelta(minutes=25)
PILL_UNTIL = time(22, 30)
PICKS_FROM = time(17, 0)
PROFILE_FROM = time(10, 0)
AWAKE = (time(8, 0), time(22, 30))
LANGUAGE_DAY = 5
MORE_PER_DAY = 3
MAX_ATTEMPTS = passes.MAX_ATTEMPTS
WEB = ("WebFetch", "WebSearch")

LANGUAGE_NAMES = {
    "es": "Spanish from Spain",
    "en": "English",
    "de": "German",
    "fr": "French",
    "it": "Italian",
    "eu": "Basque",
}


def language() -> str:
    return preferences.current().locale


def written_in() -> str:
    return LANGUAGE_NAMES.get(language(), language())


def _week(day: date) -> str:
    year, week, _ = day.isocalendar()
    return f"{year}-W{week:02d}"


def due(now: datetime, settings: tastes.Settings, profiled: bool) -> list[tuple[Kind, str]]:
    local = now.astimezone(clock.zone())
    moment = local.time()
    out: list[tuple[Kind, str]] = []
    if settings.pill_on:
        hours, minutes = (int(part) for part in settings.pill_time.split(":"))
        start = (datetime.combine(local.date(), time(hours, minutes)) - AHEAD).time()
        if start <= moment <= PILL_UNTIL or (start > PILL_UNTIL and moment >= start):
            out.append(("pill", f"pill:{local.date().isoformat()}"))
    weekday = local.weekday()
    if (weekday == 4 and moment >= PICKS_FROM) or weekday in (5, 6):
        out.append(("picks", f"picks:{_week(local.date())}"))
    awake = AWAKE[0] <= moment <= AWAKE[1]
    if not profiled and awake:
        out.append(("profile", "profile:first"))
    elif weekday == 5 and moment >= PROFILE_FROM and awake:
        out.append(("profile", f"profile:{_week(local.date())}"))
    return out


RUN = text("select outcome, attempt from insights.insights_craft_run where key = :key")

SAVE = text("""
    insert into insights.insights_craft_run
        (kind, key, outcome, detail, attempt, origin, parent_id, branch, family_key)
    values (:kind, :key, :outcome, :detail, :attempt, :origin, cast(:parent as uuid), :branch,
            :family)
    on conflict (user_id, key) do update
    set outcome = excluded.outcome, detail = excluded.detail, attempt = excluded.attempt,
        family_key = coalesce(excluded.family_key, insights.insights_craft_run.family_key),
        asked_at = now()
    returning id::text as id
""")


async def next_attempt(connection: AsyncConnection, key: str) -> int | None:
    previous = (await connection.execute(RUN, {"key": key})).one_or_none()
    if previous is None:
        return 1
    if previous.outcome != "queued":
        return previous.attempt
    ended = (
        await connection.execute(pills.FINISHED, {"key": pills.asked_as(key, previous.attempt)})
    ).first()
    if ended is None or ended.outcome == "ok" or previous.attempt >= MAX_ATTEMPTS:
        return None
    return previous.attempt + 1


async def profiled(connection: AsyncConnection) -> bool:
    return bool(
        await connection.scalar(
            text("select count(*) from insights.insights_craft_run where kind = 'profile'")
        )
    )


def _head(profile: insights.Profile, today: str) -> list[str]:
    lines = [
        f"You are {profile.name}, inside arga, a person's personal system. Today is {today}. You "
        "read their data with arga's read tools and write only to Insights, with its tools.",
    ]
    if profile.about.strip():
        lines += ["", "What the person has told you about themselves:", profile.about.strip()]
    return lines


def _families(found: list[tastes.Family]) -> list[str]:
    return [
        f"- {one.key}: {one.name}, weight {one.weight} of 3"
        + (" (outside their comfort zone)" if one.outside else "")
        + f". {one.themes}"
        for one in found
    ]


def _sources(found: list[tastes.Source], family: str) -> list[str]:
    mine = [one for one in found if one.family_key == family and not one.hidden]
    return [f"- {one.name} ({one.kind}, {one.language}): {one.url}" for one in mine] or [
        "(None: use serious sources.)"
    ]


def _answers(found: list[tastes.Question]) -> list[str]:
    return [
        f'- "{one.text}" → {tastes.said_answer(one)}' + (f" ({one.why})" if one.why else "")
        for one in found
    ]


def voice() -> list[str]:
    return [
        f"How to write: in {written_in()}, addressing the person informally, with rhythm and "
        "without stock phrases or filler. Numbers in that language's usual format. No Markdown "
        "in the texts.",
    ]


SUBSTANCE = [
    "Always with substance:",
    "- Talk about the world, never about the person or their figures: no steps, calories, "
    'spending, workouts or "today you did". Their data helps choose the topic; it is never '
    "the topic.",
    "- No self-help, life advice, generalities or worn-out topics. A concrete topic, with names, "
    "dates, places, mechanisms, figures about the world and, if there is one, a debate.",
    "- Rigour: do not invent figures, quotes or dates. What you tell must be in what you read "
    "with the web tools, or be well established knowledge. If something is disputed, say so.",
]


async def _pill_context(connection: AsyncConnection) -> dict[str, Any]:
    recent = await pills.recent(connection, limit=pills.SEEN_PILLS)
    since = clock.now().date() - timedelta(days=45)
    return {
        "traits": await tastes.traits(connection),
        "families": await tastes.families(connection),
        "sources": await tastes.sources(connection),
        "settings": await tastes.settings(connection),
        "recent": recent,
        "facts": await pills.facts(connection, since),
        "answers": await tastes.fresh_answers(connection),
        "picks": await picks.listed(connection, limit=80),
    }


def pill_brief(
    profile: insights.Profile,
    today: str,
    day: date,
    key: str,
    family: tastes.Family,
    context: dict[str, Any],
    *,
    origin: str = "daily",
    parent: pills.Pill | None = None,
    branch: str | None = None,
) -> str:
    settings: tastes.Settings = context["settings"]
    minutes = settings.pill_minutes
    least, most = minutes * pills.WORDS_PER_MINUTE[0], minutes * pills.WORDS_PER_MINUTE[1]
    target = (minutes * 75, minutes * 90)
    own = language()
    practice = own
    if (
        origin == "daily"
        and settings.pill_language
        and day.weekday() == LANGUAGE_DAY
        and settings.pill_language != own
    ):
        practice = settings.pill_language
    recent: list[pills.PillLine] = context["recent"]
    liked = [one.topic for one in recent if one.reaction == "interested"][:20]
    other = [one.topic for one in recent if one.reaction == "other"][:20]
    avoid = [
        one.label for one in context["traits"] if one.facet == "avoid" and one.status != "rejected"
    ]
    lines = [
        *_head(profile, today),
        "",
        "Today you do not advise: you write a pill, a few minutes of reading to learn something "
        "that truly interests them, like a good article in a serious popular science magazine.",
        "",
        f"Topic: {family.name} (`{family.key}`). What fits: {family.themes}.",
    ]
    if family.outside:
        lines.append(
            "This topic is meant to take them out of their comfort zone: it must be outside "
            "their usual interests and what they already liked. Choose something concrete and "
            "surprising and tell why it can hook them anyway (people, conflicts, how things work)."
        )
    if origin == "branch" and parent is not None and branch:
        lines += [
            "",
            f'It is a branch of the pill "{parent.headline}" ({parent.topic}): "{branch}". Go '
            "deeper on exactly that point. Do not repeat the basics of the previous one.",
        ]
    elif origin == "surprise":
        lines += ["", 'They asked for it just now with "Surprise me": make it truly surprising.']
    elif origin == "daily":
        lines += [
            "",
            "Before choosing, see whether something in their life calls for a topic (only if it "
            "is strong): a trip in the next 7 to 21 days (travel_get_trips), a subject they are "
            "studying (study_get_courses), a book they are reading or just finished "
            "(library_get_currently_reading, library_find_books), what they wrote about lately "
            "(notebook_get_digest). If so, use it within this topic or another of theirs with "
            "weight 2 or 3 (and then set that `family_key`), and say it in `hook` in one sentence, "
            "without their figures. If not, no `hook`.",
        ]
    lines += [
        "",
        "What you know of their tastes:",
        *tastes.described(context["traits"]),
        "",
        "Their topics and how much they interest them:",
        *_families(context["families"]),
    ]
    if avoid:
        lines += ["", f"They do not want you to talk about: {'; '.join(avoid)}."]
    lines += [
        "",
        "What they already read (do not repeat it or choose something almost the same):",
        *([f"- {one.topic}" for one in recent[:120]] or ["(Nothing yet.)"]),
    ]
    if liked:
        lines += ["", f"What interested them most: {'; '.join(liked)}."]
    if other:
        lines += ["", f"What they asked to swap for another topic: {'; '.join(other)}."]
    if context["answers"]:
        lines += ["", "What they answered you recently:", *_answers(context["answers"])]
    lines += [
        "",
        "Their trusted sources for this topic (use them if they fit; if not, other serious ones):",
        *_sources(context["sources"], family.key),
        "",
        *SUBSTANCE,
        "",
        "How you make it:",
        f"1. Choose a concrete, surprising subtopic with substance for {minutes} minutes.",
        "2. Really read about it: open with web_fetch the Wikipedia article that covers it best "
        "(in their language and, if more complete, in English) and at least one other serious "
        "source. If needed, search with web_search.",
        f"3. Write the reading (a lead and 3 to 5 sections with their subheadings) in about "
        f"{target[0]} to {target[1]} words; it is refused under {least} or over {most}. Start "
        "with a hook, explain with concrete examples, and close with why it matters today. On "
        "political topics, the ideas honestly and their main criticisms.",
        '4. "To tell" (`to_tell`): a true and surprising fact they could tell someone. "To '
        'think" (`to_think`): an open question. Three branches (`branches`): concrete subtopics '
        "that make them want to go on, each with why it hooks.",
        f'5. Publish it with insights_publish_pill: `run_key` "{key}", `family_key` the topic\'s, '
        "`topic` the subtopic, and in `sources` what you really read, with its address.",
        '6. Then insights_publish_picks with the `pill_id` it returns and `origin` "pill": 2 to 5 '
        "things to follow this topic, in formats they like (books that exist, preferably with an "
        "edition in their language; a podcast or an episode; a documentary or a film if there "
        "is one). Each with why for this person, with their own things. Insights checks them in "
        "a catalogue: what does not exist does not show.",
    ]
    if practice != own:
        level = settings.pill_level or "B1"
        lines += [
            "",
            f"Today it is in {LANGUAGE_NAMES.get(practice, practice)}, for practice, at level "
            f"{level}: clear sentences, that level's vocabulary and the hard parts explained. In "
            f'`language` "{practice}", and in `glossary` 8 to 15 hard words with their meaning '
            f"in {written_in()}. The facts of the day, in {written_in()}.",
        ]
    if origin == "daily":
        recent_facts = [one.text for one in context["facts"]][:60]
        lines += [
            "",
            f'7. The facts of the day with insights_publish_facts, `day` "{day.isoformat()}": 5 '
            "facts, spread over their topics with most weight (and one from another), true and "
            "surprising, each with a name, a date or a concrete figure, a bit more in `detail`, "
            "and the source you read to check it. None that everyone has heard already. Do not "
            "repeat those of these days:",
            *([f"- {one}" for one in recent_facts] or ["(None yet.)"]),
            "",
            "8. If something about their tastes cannot be deduced and would help you get it "
            "right, you can leave them a question with insights_ask_question (at most one, "
            "answered with one tap, with its why). Save what they answered above as a taste with "
            "insights_note_taste.",
        ]
    lines += ["", *voice()]
    return "\n".join(lines)


def picks_brief(profile: insights.Profile, today: str, context: dict[str, Any]) -> str:
    lines = [
        *_head(profile, today),
        "",
        'Time for "For you this week": 3 to 5 recommendations for the weekend and the coming '
        "days, tied to this person and not to a topic.",
        "",
        "What you know of their tastes:",
        *tastes.described(context["traits"]),
        "",
        "What you already recommended, with what they did:",
        *picks.described(context["picks"]),
        "",
        "What you do:",
        "1. Look at their reading with the Library tools (what they read, what they finished, "
        "their notes per book, what they abandoned), what they study (Study), where they go "
        "(Travel), what interests them (Outings) and what they write about (Notebook). If they "
        "finished a book these days, the next one that would suit them is the best "
        "recommendation there is.",
        "2. Choose 3 to 5, in different formats according to their tastes (book, podcast or "
        "episode, film, series or documentary), at least one a little outside their usual. "
        "Things that exist, with the exact title (that of the edition in their language if "
        "there is one) and their authorship.",
        '3. Publish with insights_publish_picks, `origin` "weekly". In `why`, why for this '
        'person, with their own things ("You gave a 5 to...", "You are going to..."). In '
        "`because`, the traits you lean on. Insights checks them in a catalogue and tells you "
        "what it did not publish: if one fails, try another.",
        "4. If they finished a book, you can ask what they thought of it with "
        "insights_ask_question (one, with its why).",
        "",
        "None of their figures in what you write: here you do not advise.",
        "",
        *voice(),
    ]
    return "\n".join(lines)


def profile_brief(profile: insights.Profile, today: str, context: dict[str, Any]) -> str:
    first = not context["traits"]
    lines = [
        *_head(profile, today),
        "",
        "Time to know them better: what they like, how, and what they are living now. What you "
        'propose they will see on the "You" screen of Insights, with its evidence, and they '
        "will confirm or dismiss it.",
        "",
        "What you already know (do not repeat it; do not propose again what was dismissed):",
        *tastes.described(context["traits"]),
    ]
    rejected = [one.label for one in context["traits"] if one.status == "rejected"]
    if rejected:
        lines += [f"Dismissed by the person: {'; '.join(rejected)}."]
    if context["answers"]:
        lines += [
            "",
            "What they answered you and you have not saved yet:",
            *_answers(context["answers"]),
        ]
    lines += [
        "",
        "What you do:",
        "1. Go through their apps with the read tools: Library (genres, authors, notes, what "
        "they abandoned), Study (what they study and the languages), Travel (trips done and "
        "coming, ideas), Outings (what interests them and what they mute, their wishes), "
        "Notebook (what they write about, their folders), Training and Vitals (which sport they "
        "do), Career (what they work on), Planner (what they do each week).",
        f"2. Propose {'up to 15' if first else 'up to 6'} traits with insights_propose_trait, "
        'each concrete and with its evidence in one line ("Library: 6 science fiction novels, '
        'average 4.2"). Facets: `topic` (a topic), `genre`, `format`, `creator` (an author, a '
        "podcast), `work` (a work that marked them), `style` (how they like to be told things), "
        "`avoid`, `context` (what they live now: a master's, a trip, a language), `language`. "
        "Few and certain beats many and vague.",
        "3. What they answered you, save it with insights_note_taste: they already said it, it "
        "needs no confirmation.",
        "4. If something important cannot be deduced, leave them a question with "
        "insights_ask_question (at most one, answered with one tap, with its why). If you "
        "proposed a trait with little evidence, it can be `confirm` with its `trait_id`.",
        "",
        "Nothing else: no advice and no pills in this pass.",
        "",
        *voice(),
    ]
    return "\n".join(lines)


async def save(
    connection: AsyncConnection,
    kind: Kind,
    key: str,
    outcome: str,
    *,
    detail: str | None = None,
    attempt: int = 1,
    origin: str | None = None,
    parent_id: str | None = None,
    branch: str | None = None,
    family: str | None = None,
) -> str:
    return await connection.scalar(
        SAVE,
        {
            "kind": kind,
            "key": key,
            "outcome": outcome,
            "detail": detail[:500] if detail else None,
            "attempt": attempt,
            "origin": origin,
            "parent": parent_id,
            "branch": branch,
            "family": family,
        },
    )


async def _send(
    connection: AsyncConnection,
    kind: Kind,
    key: str,
    attempt: int,
    prompt: str,
    tools: tuple[str, ...],
    **extra: Any,
) -> str:
    answer = await passes.ask(passes.attempt_key(key, attempt), prompt, tools)
    problem = passes.refused_detail(answer)
    if problem:
        await save(connection, kind, key, "refused", detail=problem, attempt=attempt, **extra)
        return "refused"
    await save(connection, kind, key, "queued", attempt=attempt, **extra)
    return "queued"


async def run(
    connection: AsyncConnection,
    kind: Kind,
    key: str,
    now: datetime,
    rng: random.Random | None = None,
) -> str | None:
    attempt = await next_attempt(connection, key)
    if attempt is None:
        return None
    local = now.astimezone(clock.zone())
    today = talk.said_day(local)
    profile = await insights.profile(connection)
    await tastes.ensure_defaults(connection)
    context = await _pill_context(connection)
    if kind == "pill":
        if await pills.daily(connection, local.date()) is not None:
            await save(connection, kind, key, "quiet", attempt=attempt, origin="daily")
            return "quiet"
        family = pills.choose(
            context["families"], await pills.history(connection), now, rng or random.Random()
        )
        prompt = pill_brief(profile, today, local.date(), key, family, context)
        outcome = await _send(
            connection, kind, key, attempt, prompt, WEB, origin="daily", family=family.key
        )
    elif kind == "picks":
        prompt = picks_brief(profile, today, context)
        outcome = await _send(connection, kind, key, attempt, prompt, ())
    else:
        prompt = profile_brief(profile, today, context)
        outcome = await _send(connection, kind, key, attempt, prompt, ())
    if outcome == "queued" and context["answers"]:
        await tastes.mark_seen(connection, [one.id for one in context["answers"] if one.id])
    return outcome


class TooMany(Exception):
    pass


async def more(
    connection: AsyncConnection,
    now: datetime,
    *,
    origin: Literal["surprise", "branch"],
    parent_id: str | None = None,
    branch: str | None = None,
    rng: random.Random | None = None,
) -> pills.Ask:
    local = now.astimezone(clock.zone())
    asked_today = await connection.scalar(
        text("""
            select count(*) from insights.insights_craft_run
            where kind = 'more' and outcome = 'queued'
              and (asked_at at time zone :zone)::date = :day
        """),
        {"day": local.date(), "zone": clock.zone().key},
    )
    if asked_today >= MORE_PER_DAY:
        raise TooMany(f"You already asked for {MORE_PER_DAY} today: there are more tomorrow.")
    parent = await pills.one(connection, parent_id) if parent_id else None
    if origin == "branch" and (parent is None or not branch):
        raise pills.NotFound(parent_id or "")
    await tastes.ensure_defaults(connection)
    context = await _pill_context(connection)
    family_list: list[tastes.Family] = context["families"]
    if origin == "branch" and parent is not None:
        family = next((one for one in family_list if one.key == parent.family_key), family_list[0])
    else:
        avoid = {parent.family_key} if parent is not None else set()
        family = pills.choose(
            family_list, await pills.history(connection), now, rng or random.Random(), avoid
        )
    key = f"more:{local:%Y%m%d}-{uuid4().hex[:12]}"
    profile = await insights.profile(connection)
    prompt = pill_brief(
        profile,
        talk.said_day(local),
        local.date(),
        key,
        family,
        context,
        origin=origin,
        parent=parent,
        branch=branch,
    )
    await _send(
        connection,
        "more",
        key,
        1,
        prompt,
        WEB,
        origin=origin,
        parent_id=parent.id if parent else None,
        branch=branch,
        family=family.key,
    )
    found = await pills.ask_by_key(connection, key)
    assert found is not None
    return found
