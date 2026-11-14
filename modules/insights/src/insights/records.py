from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

import arga_contracts as contracts
from arga_contracts import records as write
from insights import clock, pills, tastes
from insights.insights import COLUMNS, Insight

KIND = "Week summary"
FOLDER = "Weeks"

WEEKLY = text(
    f"select {COLUMNS} from insights.insights_insight where kind = 'weekly' order by created_at"
)


def week_of(created_at: datetime) -> date:
    day = created_at.astimezone(clock.zone()).date()
    if day.weekday() == 0:
        day -= timedelta(days=1)
    return day - timedelta(days=day.weekday())


def week_key(monday: date) -> str:
    year, week, _ = monday.isocalendar()
    return f"{year}-W{week:02d}"


def _figure(figure: Any) -> str:
    unit = f" {figure.unit}" if figure.unit else ""
    return (
        f"{write.trimmed(figure.value)}{unit}, against {write.trimmed(figure.baseline)}{unit} "
        f"({figure.baseline_label})"
    )


def body(insight: Insight) -> str:
    proposals = "\n".join(
        f"{n}. {one.what}: {_figure(one.figure)}. {one.how}."
        for n, one in enumerate(insight.proposals, start=1)
    )
    return write.sections(
        f"**{insight.title}**",
        insight.body,
        f"## Proposals for next week\n\n{proposals}" if proposals else None,
    )


def record(insight: Insight) -> dict[str, Any]:
    monday = week_of(insight.created_at)
    key = week_key(monday)
    return contracts.record(
        id=f"week-{key}",
        title=f"Week of {write.long_date(monday)}",
        kind=KIND,
        href=f"/insights/insight/{insight.id}",
        folder=FOLDER,
        properties={"week": key, "proposals": len(insight.proposals)},
        body=body(insight),
    )


PILL_KIND = "Pill"
PILL_FOLDER = "Pills"


def pill_body(pill: pills.Pill, facts: list[pills.Fact]) -> str:
    sections = "\n\n".join(
        f"## {one.get('title', '')}\n\n{one.get('text', '')}" for one in pill.sections
    )
    sources = "\n".join(f"- [{one.get('title')}]({one.get('url')})" for one in pill.sources)
    said = "\n".join(f"- {one.text}" for one in facts)
    return write.sections(
        f"*{pill.lead}*",
        sections,
        f"> **To tell.** {pill.to_tell}",
        f"**To think.** {pill.to_think}" if pill.to_think else None,
        f"## Facts of the day\n\n{said}" if said else None,
        f"## Sources\n\n{sources}" if sources else None,
    )


def pill_record(pill: pills.Pill, family: str, facts: list[pills.Fact]) -> dict[str, Any]:
    return contracts.record(
        id=f"pill-{pill.id}",
        title=pill.headline[:200],
        kind=PILL_KIND,
        href=f"/insights/pill/{pill.id}",
        folder=PILL_FOLDER,
        properties={"topic": family, "subtopic": pill.topic, "day": pill.day.isoformat()},
        body=pill_body(pill, facts),
    )


async def _pills(connection: AsyncConnection) -> list[dict[str, Any]]:
    names = {one.key: one.name for one in await tastes.families(connection)}
    rows = await connection.execute(
        text(f"select {pills.PILL_COLUMNS} from insights.insights_pill order by created_at")
    )
    found = [pills.Pill.model_validate(dict(row._mapping)) for row in rows]
    if not found:
        return []
    by_day: dict[date, list[pills.Fact]] = {}
    for fact in await pills.facts(connection, min(one.day for one in found)):
        by_day.setdefault(fact.day, []).append(fact)
    return [
        pill_record(
            one,
            names.get(one.family_key, one.family_key),
            by_day.get(one.day, []) if one.origin == "daily" else [],
        )
        for one in found
    ]


async def build(connection: AsyncConnection) -> list[dict[str, Any]]:
    weekly = [
        Insight.model_validate(dict(row._mapping)) for row in await connection.execute(WEEKLY)
    ]
    by_week: dict[str, dict[str, Any]] = {}
    for insight in weekly:
        one = record(insight)
        by_week[one["id"]] = one
    return [*by_week.values(), *await _pills(connection)]
