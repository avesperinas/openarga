from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from typing import Any

from pydantic import BaseModel, Field, model_validator
from sqlalchemy.ext.asyncio import AsyncConnection

from insights import clock, insights, passes, picks, pills, signals, talk, tastes
from insights.picks import Origin as PickOrigin
from insights.picks import PickIn

MODULE = "insights"
WRITE_ROLE = f"mod_{MODULE}"
READ_ROLE = f"mod_{MODULE}_read"
MAX_SIGNAL_DAYS = 62


def role_for_scopes(scopes: set[str]) -> str | None:
    if f"{MODULE}:write" in scopes:
        return WRITE_ROLE
    if f"{MODULE}:read" in scopes:
        return READ_ROLE
    return None


def _insight(one: insights.Insight) -> dict[str, Any]:
    return {
        "insight_id": one.id,
        "date": one.created_at.astimezone(clock.zone()).date().isoformat(),
        "kind": one.kind,
        "domain": one.domain,
        "topic": one.topic,
        "title": one.title,
        "body": one.body,
        "figures": [figure.model_dump() for figure in one.figures],
        "affects": one.affects,
        "action": one.action,
        **(
            {"proposals": [_proposal(n, p) for n, p in enumerate(one.proposals, 1)]}
            if one.proposals
            else {}
        ),
        "read": one.read_at is not None,
        "rating": one.rating,
    }


def _proposal(number: int, one: insights.Proposal) -> dict[str, Any]:
    return {"number": number, **one.model_dump()}


class GetProfile(BaseModel):
    pass


async def get_profile(connection: AsyncConnection, arguments: GetProfile) -> dict[str, Any]:
    found = await insights.profile(connection)
    return {
        "name": found.name,
        "about": found.about,
    }


class GetInsights(BaseModel):
    since: date | None = Field(
        default=None, description="Only those given since this day. Without it, the most recent."
    )
    limit: int = Field(default=30, ge=1, le=200, description="How many, at most.")


async def get_insights(connection: AsyncConnection, arguments: GetInsights) -> dict[str, Any]:
    since = (
        datetime.combine(arguments.since, time.min, tzinfo=clock.zone())
        if arguments.since
        else None
    )
    found = await insights.recent(connection, limit=arguments.limit, since=since)
    return {"insights": [_insight(one) for one in found]}


class GetSignals(BaseModel):
    since: date | None = Field(
        default=None, description="From which day. Without it, the seven days until `until`."
    )
    until: date | None = Field(default=None, description="Until which day. Without it, today.")


async def get_signals(connection: AsyncConnection, arguments: GetSignals) -> dict[str, Any]:
    until = arguments.until or clock.now().date()
    since = arguments.since or until - timedelta(days=6)
    if since > until:
        return {"signals": [], "note": "`since` is after `until`"}
    since = max(since, until - timedelta(days=MAX_SIGNAL_DAYS - 1))
    found = await signals.read(connection, since, until)
    return {
        "since": since.isoformat(),
        "until": until.isoformat(),
        "signals": [one.model_dump(mode="json") for one in found],
    }


class GetSeries(BaseModel):
    keys: list[str] = Field(
        default_factory=list,
        max_length=10,
        description=(
            "The keys of the figures (`vitals.weight`, `money.month_expense`). Empty: the list of "
            "every figure there is, with its last value, to choose from."
        ),
    )
    since: date | None = Field(
        default=None, description="From which day. Without it, 90 days back."
    )
    until: date | None = Field(default=None, description="Until which day. Without it, today.")


async def get_series(connection: AsyncConnection, arguments: GetSeries) -> dict[str, Any]:
    until = arguments.until or clock.now().date()
    since = arguments.since or until - timedelta(days=89)
    found = await signals.series(connection, until)
    if not arguments.keys:
        return {
            "metrics": [
                {
                    "key": one.key,
                    "label": one.label,
                    "unit": one.unit,
                    "kind": one.kind,
                    "domain": one.domain,
                    "last_day": max(one.points).isoformat(),
                    "last_value": one.points[max(one.points)],
                }
                for one in sorted(found, key=lambda one: one.key)
                if one.points
            ]
        }
    by_key = {one.key: one for one in found}
    out, missing = [], []
    for key in arguments.keys:
        one = by_key.get(key)
        if one is None:
            missing.append(key)
            continue
        out.append(
            {
                "key": one.key,
                "label": one.label,
                "unit": one.unit,
                "kind": one.kind,
                "points": [
                    {"day": day.isoformat(), "value": value}
                    for day, value in sorted(one.points.items())
                    if since <= day <= until
                ],
            }
        )
    answer: dict[str, Any] = {"series": out}
    if missing:
        answer["note"] = f"no figures with those keys: {', '.join(missing)}"
    return answer


class GetRuns(BaseModel):
    days: int = Field(
        default=14, ge=1, le=60, description="How many days back. Without it, fourteen."
    )


async def get_runs(connection: AsyncConnection, arguments: GetRuns) -> dict[str, Any]:
    found = await passes.recent(connection, arguments.days)
    return {
        "runs": [
            {
                "kind": one.kind,
                "key": one.key,
                "asked_at": one.asked_at.astimezone(clock.zone()).isoformat(timespec="minutes"),
                "state": one.state,
                "detail": one.detail,
                "attempt": one.attempt,
                "signals": one.signals,
                **({"ran_with": one.ran_with} if one.ran_with else {}),
                **({"fix": one.fix} if one.fix else {}),
            }
            for one in found
        ]
    }


class PublishInsight(insights.InsightIn):
    @model_validator(mode="after")
    def _proposals_only_in_the_week(self) -> PublishInsight:
        least, most = insights.PROPOSALS
        if self.kind == "weekly" and not least <= len(self.proposals) <= most:
            raise ValueError(
                f"the Sunday summary carries {least} to {most} proposals for next week in "
                f"`proposals`; it has {len(self.proposals)}"
            )
        if self.kind == "alert" and self.proposals:
            raise ValueError("a single alert carries no `proposals`: its proposal is `action`")
        return self


async def publish_insight(connection: AsyncConnection, arguments: PublishInsight) -> dict[str, Any]:
    try:
        published = await insights.publish(connection, arguments)
    except insights.Repeated as error:
        return {"published": None, "note": f"not published: {error}"}
    return {"published": _insight(published)}


class RateInsight(BaseModel):
    insight_id: str = Field(description="The `insight_id` that `get_insights` gives.")
    rating: insights.Rating | None = Field(
        description="`useful`, `known` or `not_applicable`; `null` to remove it."
    )


async def rate_insight(connection: AsyncConnection, arguments: RateInsight) -> dict[str, Any]:
    try:
        rated = await insights.rate(
            connection, arguments.insight_id, insights.RatingIn(rating=arguments.rating)
        )
    except insights.NotFound:
        return {"rated": None, "note": "no advice with that id"}
    return {"rated": _insight(rated)}


class Reply(BaseModel):
    thread_id: str = Field(description="The thread you were given in the task.")
    text: str = Field(
        min_length=1,
        max_length=12000,
        description="Your whole answer, in short paragraphs separated by a blank line.",
    )


async def reply(connection: AsyncConnection, arguments: Reply) -> dict[str, Any]:
    try:
        message_id = await talk.add(connection, arguments.thread_id, "insights", arguments.text)
    except talk.NotFound:
        return {"replied": None, "note": "no conversation with that id"}
    return {"replied": message_id}


class GetTastes(BaseModel):
    pass


async def get_tastes(connection: AsyncConnection, arguments: GetTastes) -> dict[str, Any]:
    found = await tastes.everything(connection)
    pending = await tastes.current_question(connection)
    return {
        "traits": [
            {
                "trait_id": one.id,
                "facet": one.facet,
                "label": one.label,
                "stance": one.stance,
                "source": one.source,
                "status": one.status,
                **({"evidence": one.evidence} if one.evidence else {}),
            }
            for one in found.traits
        ],
        "families": [one.model_dump() for one in found.families],
        "settings": found.settings.model_dump(mode="json", exclude={"started_at"}),
        "onboarding": {
            "done": found.onboarding.done,
            "answered": found.onboarding.answered,
            "total": found.onboarding.total,
        },
        **({"pending_question": pending.text} if pending else {}),
    }


class GetPills(BaseModel):
    limit: int = Field(default=30, ge=1, le=150, description="How many, newest first.")


async def get_pills(connection: AsyncConnection, arguments: GetPills) -> dict[str, Any]:
    found = await pills.recent(connection, limit=arguments.limit)
    return {
        "pills": [
            {
                "pill_id": one.id,
                "day": one.day.isoformat(),
                "origin": one.origin,
                "family_key": one.family_key,
                "topic": one.topic,
                "headline": one.headline,
                "read": one.read_at is not None,
                "reaction": one.reaction,
            }
            for one in found
        ]
    }


class GetFacts(BaseModel):
    days: int = Field(default=14, ge=1, le=90, description="How many days back.")


async def get_facts(connection: AsyncConnection, arguments: GetFacts) -> dict[str, Any]:
    since = clock.now().date() - timedelta(days=arguments.days - 1)
    found = await pills.facts(connection, since)
    return {
        "facts": [
            {
                "day": one.day.isoformat(),
                "family_key": one.family_key,
                "text": one.text,
                "reaction": one.reaction,
            }
            for one in found
        ]
    }


class GetLibrary(BaseModel):
    states: list[picks.State] = Field(
        default_factory=list,
        description="`new`, `saved`, `doing`, `done`, `dismissed`. Empty: all.",
    )


async def get_library(connection: AsyncConnection, arguments: GetLibrary) -> dict[str, Any]:
    found = await picks.listed(connection, states=list(arguments.states) or None)
    return {
        "picks": [
            {
                "pick_id": one.id,
                "kind": one.kind,
                "title": one.title,
                "creators": one.creators,
                "year": one.year,
                "state": one.state,
                "why": one.why,
                **({"rating": one.rating} if one.rating is not None else {}),
                **({"more_like": one.more_like} if one.more_like is not None else {}),
                **({"note": one.note} if one.note else {}),
            }
            for one in found
        ]
    }


class PublishPill(pills.PillIn):
    pass


async def publish_pill(connection: AsyncConnection, arguments: PublishPill) -> dict[str, Any]:
    try:
        published = await pills.publish(connection, arguments, clock.now())
    except pills.Invalid as error:
        return {"published": None, "note": f"not published: {error}"}
    return {
        "published": {
            "pill_id": published.id,
            "headline": published.headline,
            "family_key": published.family_key,
        }
    }


class PublishFacts(pills.FactsIn):
    pass


async def publish_facts(connection: AsyncConnection, arguments: PublishFacts) -> dict[str, Any]:
    try:
        published = await pills.publish_facts(connection, arguments)
    except pills.Invalid as error:
        return {"published": [], "note": f"not published: {error}"}
    skipped = len(arguments.facts) - len(published)
    return {
        "published": len(published),
        **({"note": f"{skipped} were already given and are not repeated"} if skipped else {}),
    }


class PublishPicks(BaseModel):
    origin: PickOrigin = Field(
        description="`pill` (with `pill_id`), `weekly` (For you this week), `event` or `chat`."
    )
    pill_id: str | None = Field(default=None, description="The pill they go with.")
    picks: list[PickIn] = Field(min_length=1, max_length=8)


async def publish_picks(connection: AsyncConnection, arguments: PublishPicks) -> dict[str, Any]:
    if arguments.origin == "pill" and not arguments.pill_id:
        return {"published": [], "note": "with `origin` `pill` goes the `pill_id`"}
    try:
        published, notes = await picks.publish(
            connection, arguments.picks, arguments.origin, arguments.pill_id
        )
    except picks.NotFound:
        return {"published": [], "note": "no pill with that id"}
    return {
        "published": [
            {"pick_id": one.id, "kind": one.kind, "title": one.title, "verified": one.verified}
            for one in published
        ],
        **({"not_published": notes} if notes else {}),
    }


class AskQuestion(tastes.QuestionIn):
    pass


async def ask_question(connection: AsyncConnection, arguments: AskQuestion) -> dict[str, Any]:
    try:
        asked = await tastes.ask(connection, arguments, clock.now())
    except (tastes.Refused, tastes.NotFound) as error:
        return {"asked": None, "note": f"not left: {error}"}
    return {"asked": {"question_id": asked.id, "text": asked.text}}


class ProposeTrait(BaseModel):
    facet: tastes.Facet = Field(description="What kind of trait it is.")
    label: str = Field(
        min_length=2, max_length=120, description="Concrete: `Long epic fantasy, in sagas`."
    )
    stance: int = Field(default=1, ge=-2, le=2, description="De −2 (no quiere) a +2 (le encanta).")
    evidence: str = Field(
        min_length=5,
        max_length=300,
        description="What supports it, with its app: `Library: 6 novels, average 4.2`.",
    )


async def propose_trait(connection: AsyncConnection, arguments: ProposeTrait) -> dict[str, Any]:
    found, what = await tastes.remember(
        connection,
        arguments.facet,
        arguments.label,
        arguments.stance,
        "seen",
        evidence=arguments.evidence,
        confirmed=False,
    )
    notes = {
        "rejected": "the person dismissed it: it does not come back",
        "kept": "it was already confirmed; the evidence is saved",
    }
    return {
        "trait": {"trait_id": found.id, "label": found.label, "status": found.status},
        **({"note": notes[what]} if what in notes else {}),
    }


class NoteTaste(BaseModel):
    facet: tastes.Facet
    label: str = Field(min_length=2, max_length=120)
    stance: int = Field(default=1, ge=-2, le=2)
    evidence: str | None = Field(
        default=None, max_length=300, description="What they said, in one line."
    )


async def note_taste(connection: AsyncConnection, arguments: NoteTaste) -> dict[str, Any]:
    found, _ = await tastes.remember(
        connection,
        arguments.facet,
        arguments.label,
        arguments.stance,
        "said",
        evidence=arguments.evidence,
        confirmed=True,
    )
    return {"trait": {"trait_id": found.id, "label": found.label, "status": found.status}}


@dataclass(frozen=True)
class Tool:
    arguments: type[BaseModel]
    run: Callable[..., Awaitable[dict[str, Any]]]


TOOLS: dict[str, Tool] = {
    "get_profile": Tool(GetProfile, get_profile),
    "get_insights": Tool(GetInsights, get_insights),
    "get_signals": Tool(GetSignals, get_signals),
    "get_series": Tool(GetSeries, get_series),
    "get_runs": Tool(GetRuns, get_runs),
    "publish_insight": Tool(PublishInsight, publish_insight),
    "rate_insight": Tool(RateInsight, rate_insight),
    "reply": Tool(Reply, reply),
    "get_tastes": Tool(GetTastes, get_tastes),
    "get_pills": Tool(GetPills, get_pills),
    "get_facts": Tool(GetFacts, get_facts),
    "get_library": Tool(GetLibrary, get_library),
    "publish_pill": Tool(PublishPill, publish_pill),
    "publish_facts": Tool(PublishFacts, publish_facts),
    "publish_picks": Tool(PublishPicks, publish_picks),
    "ask_question": Tool(AskQuestion, ask_question),
    "propose_trait": Tool(ProposeTrait, propose_trait),
    "note_taste": Tool(NoteTaste, note_taste),
}
