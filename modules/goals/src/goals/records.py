from __future__ import annotations

from collections import defaultdict
from datetime import date
from typing import Any

from sqlalchemy.ext.asyncio import AsyncConnection

import arga_contracts as contracts
from arga_contracts import records as write
from goals import goals, tasks
from goals.common import zone

APP = "goals"
ALL_DONE = 100_000
HISTORY_ROWS = 30
PACE = {"ahead": "ahead", "on_track": "on track", "behind": "behind"}


def _value(value: float | None, unit: str | None) -> str:
    if value is None:
        return ""
    return f"{write.trimmed(value)} {unit}".strip() if unit else write.trimmed(value)


def goal(found: goals.GoalDetail) -> dict[str, Any]:
    one = found.goal
    unit = one.metric.unit if one.metric else None
    properties: dict[str, Any] = {
        "status": one.status,
        "kind": one.kind,
        "since": one.start_on.isoformat(),
    }
    for name, value in (
        ("category", one.category),
        ("metric", one.metric.label if one.metric else None),
        ("target", one.target),
        ("unit", unit),
        ("due", one.due_on.isoformat() if one.due_on else None),
        ("current", one.current),
        ("progress", round(one.progress * 100) if one.progress is not None else None),
        ("streak", one.streak),
        ("pace", one.pace),
        ("expected", round(one.expected, 2) if one.expected is not None else None),
        ("closed", one.closed_on.isoformat() if one.closed_on else None),
    ):
        if value is not None:
            properties[name] = value
    lead = []
    if one.kind == "dated" and one.due_on:
        lead.append(
            f"Reach {_value(one.target, unit)} by {write.long_date(one.due_on)}"
            if one.target is not None
            else f"By {write.long_date(one.due_on)}"
        )
    elif one.period == "day":
        lead.append(f"{one.days_per_week} days a week")
    elif one.period == "week":
        lead.append(f"{_value(one.target, unit)} a week")
    if one.current is not None:
        lead.append(f"now {_value(one.current, unit)}")
    if one.pace:
        lead.append(PACE[one.pace])
    if one.streak:
        lead.append(f"streak of {one.streak} {'days' if one.streak_unit == 'days' else 'weeks'}")
    if one.status != "active" and one.closed_on:
        lead.append(f"{one.status} on {write.long_date(one.closed_on)}")
    rows = [
        [
            point.day.isoformat(),
            _value(point.value, unit),
            "yes" if point.met else ("no" if point.met is False else ""),
            point.note or "",
        ]
        for point in reversed(found.history[-HISTORY_ROWS:])
    ]
    return contracts.record(
        id=f"goal:{one.id}",
        title=one.title,
        kind="Goal",
        href=f"/goals/goal/{one.id}",
        folder="Goals",
        properties=properties,
        body=write.sections(
            (" · ".join(lead) + ".").capitalize() if lead else None,
            f"## Note\n\n{one.note}" if one.note else None,
            "## Last days\n\n" + write.table(["Day", "Value", "Met", "Note"], rows)
            if rows
            else None,
        ),
    )


def pending(found: list[tasks.Task]) -> dict[str, Any]:
    by_category: dict[str, list[tasks.Task]] = defaultdict(list)
    for task in found:
        by_category[task.category].append(task)
    parts = []
    for category, inside in by_category.items():
        lines = "\n".join(
            f"- [ ] {task.title}"
            + (f" · {task.due_on.isoformat()}" if task.due_on else "")
            + (f" · {task.repeats}" if task.repeats else "")
            for task in inside
        )
        parts.append(f"### {category}\n\n{lines}")
    return contracts.record(
        id="pending",
        title="Pending tasks",
        kind="Tasks",
        href="/goals/tasks",
        properties={"pending": len(found)},
        body=write.sections(*parts) or "Nothing pending.",
    )


def days(found: list[tasks.Task]) -> list[dict[str, Any]]:
    by_day: dict[date, list[tasks.Task]] = defaultdict(list)
    for task in found:
        if task.done_at is not None:
            by_day[task.done_at.astimezone(zone()).date()].append(task)
    return [
        contracts.record(
            id=f"day:{day.isoformat()}",
            title="Tasks",
            kind="Day",
            href="/goals/done",
            day=day,
            properties={"tasks_done": len(done)},
            body="\n".join(
                f"- [x] {task.title} · {task.category}"
                for task in sorted(done, key=lambda one: one.done_at)
            ),
        )
        for day, done in sorted(by_day.items())
    ]


async def build(connection: AsyncConnection) -> list[dict[str, Any]]:
    found = [
        goal(await goals.detail(connection, one.id))
        for one in await goals.active(connection) + await goals.closed(connection)
    ]
    found.append(pending(await tasks.pending(connection)))
    found.extend(days(await tasks.done(connection, limit=ALL_DONE)))
    return found
