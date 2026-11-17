from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncConnection

from arga_widgets import envelope
from goals import goals, tasks
from goals.common import number, plural, t, today

KIND = "tasks"
ROWS = 14
AHEAD_DAYS = 7


def _due(task: tasks.Task) -> str | None:
    if task.due_on is None:
        return None
    if task.due_time is None:
        return task.due_on.isoformat()
    return datetime.combine(task.due_on, task.due_time).isoformat()


def _item(task: tasks.Task) -> dict:
    item: dict = {"id": task.id, "title": task.title}
    due = _due(task)
    if due:
        item["due"] = due
    if task.status == "overdue":
        item["overdue"] = True
    if task.category:
        item["detail"] = task.category
    if 1 <= task.hue <= 8:
        item["hue"] = task.hue
    return item


def _ready(found: list[tasks.Task]) -> dict:
    return envelope(
        KIND,
        "ready",
        {"tasks": [_item(task) for task in found[:ROWS]], "count": len(found), "checkable": True},
    )


async def for_today(connection: AsyncConnection) -> dict:
    now = today()
    found = await tasks.pending(connection, until=now)
    if not found:
        tomorrow = await tasks.pending(connection, until=now + timedelta(days=1))
        detail = plural("widget.tomorrow", len(tomorrow)) if tomorrow else t("widget.nothing_soon")
        return envelope(KIND, "empty", {"detail": t("widget.nothing_today", detail=detail)})
    return _ready(found)


async def upcoming(connection: AsyncConnection) -> dict:
    found = await tasks.pending(connection, until=today() + timedelta(days=AHEAD_DAYS))
    if not found:
        return envelope(KIND, "empty", {"detail": t("widget.nothing_ahead", days=AHEAD_DAYS)})
    return _ready(found)


async def overdue(connection: AsyncConnection) -> dict:
    now = today()
    found = [
        task
        for task in await tasks.pending(connection, until=now - timedelta(days=1))
        if task.status == "overdue"
    ]
    if not found:
        return envelope(KIND, "empty", {"detail": t("widget.nothing_overdue")})
    return _ready(found)


PACE_TONE = {"ahead": "positive", "on_track": "neutral", "behind": "negative"}


def _figure(value: float | None, unit: str | None) -> str:
    if value is None:
        return "—"
    decimals = 1 if unit == "kg" or (abs(value) < 100 and not float(value).is_integer()) else 0
    word = {"EUR": "€", "count": "", "percent": "%"}.get(unit or "")
    if word is None:
        word = t(f"unit.{unit}") if unit in ("steps", "points") else unit or ""
    return f"{number(value, decimals)} {word}".strip()


async def goals_today(connection: AsyncConnection) -> dict:
    daily = [
        goal
        for goal in await goals.active(connection)
        if goal.kind == "periodic" and goal.period == "day"
    ]
    if not daily:
        return envelope(KIND, "empty", {"detail": t("widget.no_daily")})
    items = []
    for goal in daily:
        item: dict = {"id": goal.id, "title": goal.title, "done": bool(goal.today_met)}
        detail = (
            plural(f"widget.streak_{goal.streak_unit or 'days'}", goal.streak)
            if goal.streak
            else t(
                "widget.this_week",
                count=int(goal.week_count or 0),
                target=int(goal.week_target or 7),
            )
        )
        item["detail"] = detail
        if goal.hue and 1 <= goal.hue <= 8:
            item["hue"] = goal.hue
        items.append(item)
    items.sort(key=lambda item: item["done"])
    pending = sum(1 for item in items if not item["done"])
    return envelope(
        KIND,
        "ready",
        {"tasks": items[:ROWS], "count": pending, "checkable": True},
    )


async def goals_list(connection: AsyncConnection) -> dict:
    dated = sorted(
        (goal for goal in await goals.active(connection) if goal.kind == "dated"),
        key=lambda goal: goal.due_on or goal.start_on,
    )
    if not dated:
        return envelope("list", "empty", {"detail": t("widget.no_dated")})
    rows = []
    for goal in dated[:ROWS]:
        unit = goal.metric.unit if goal.metric else None
        if goal.target is None:
            rows.append({"label": goal.title, "value": t("widget.milestone"), "tone": "neutral"})
            continue
        word = t(f"pace.{goal.pace}") if goal.pace else t("widget.no_data")
        rows.append(
            {
                "label": goal.title,
                "value": f"{_figure(goal.current, unit)} · {word}",
                "tone": PACE_TONE.get(goal.pace or "", "neutral"),
            }
        )
    return envelope("list", "ready", {"rows": rows})


async def featured(connection: AsyncConnection) -> dict:
    found = [goal for goal in await goals.active(connection) if goal.featured]
    if not found:
        return envelope("progress", "empty", {"detail": t("widget.no_featured")})
    goal = found[0]
    if goal.kind == "periodic":
        return envelope(
            "progress",
            "ready",
            {
                "value": goal.week_count or 0,
                "target": goal.week_target or 7,
                "unit": goal.metric.unit if goal.period == "week" and goal.metric else None,
                "label": t("widget.featured_week", title=goal.title),
            },
        )
    if goal.target is None or goal.current is None or goal.start is None:
        return envelope(
            "progress", "empty", {"detail": t("widget.featured_empty", title=goal.title)}
        )
    whole = abs(goal.target - goal.start) or 1.0
    done = max(0.0, (goal.current - goal.start) * (1 if goal.target >= goal.start else -1))
    expected = abs(goal.expected - goal.start) if goal.expected is not None else None
    unit = goal.metric.unit if goal.metric else None
    return envelope(
        "progress",
        "ready",
        {
            "value": round(done, 2),
            "target": round(whole, 2),
            "expected": round(expected, 2) if expected is not None else None,
            "label": t(
                "widget.featured_of",
                title=goal.title,
                current=_figure(goal.current, unit),
                target=_figure(goal.target, unit),
            ),
        },
    )


RENDERERS = {
    "today": for_today,
    "upcoming": upcoming,
    "overdue": overdue,
    "goals_today": goals_today,
    "goals": goals_list,
    "goal": featured,
}


ACTING = {"today", "upcoming", "overdue", "goals_today"}


async def act(connection: AsyncConnection, widget_id: str, verb: str, item_id: str) -> None:
    if verb == "add":
        await tasks.seed(connection)
        found = await tasks.categories(connection)
        if not found:
            raise tasks.NotFound("there is no category to put it in")
        await tasks.create(
            connection,
            tasks.TaskIn(category_id=found[0].id, title=item_id[:200], due_on=tasks.today()),
        )
        return
    if widget_id == "goals_today":
        await goals.check(connection, item_id, goals.CheckIn(done=verb == "complete"))
    elif verb == "complete":
        await tasks.complete(connection, item_id)
    else:
        await tasks.undo(connection, item_id)
