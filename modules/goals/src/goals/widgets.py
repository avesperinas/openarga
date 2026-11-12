from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncConnection

from arga_widgets import envelope
from goals import goals, tasks
from goals.common import today

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


def _plural(count: int, one: str, many: str) -> str:
    return f"{count} {one if count == 1 else many}"


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
        detail = (
            f"mañana, {_plural(len(tomorrow), 'tarea', 'tareas')}"
            if tomorrow
            else "nada para hoy ni para mañana"
        )
        return envelope(KIND, "empty", {"detail": f"Nada para hoy · {detail}"})
    return _ready(found)


async def upcoming(connection: AsyncConnection) -> dict:
    found = await tasks.pending(connection, until=today() + timedelta(days=AHEAD_DAYS))
    if not found:
        return envelope(KIND, "empty", {"detail": f"nada en los próximos {AHEAD_DAYS} días"})
    return _ready(found)


async def overdue(connection: AsyncConnection) -> dict:
    now = today()
    found = [
        task
        for task in await tasks.pending(connection, until=now - timedelta(days=1))
        if task.status == "overdue"
    ]
    if not found:
        return envelope(KIND, "empty", {"detail": "nada vencido"})
    return _ready(found)


PACE_TONE = {"ahead": "positive", "on_track": "neutral", "behind": "negative"}
PACE_WORD = {"ahead": "por delante", "on_track": "en ritmo", "behind": "por detrás"}


def _figure(value: float | None, unit: str | None) -> str:
    if value is None:
        return "—"
    decimals = 1 if unit == "kg" or (abs(value) < 100 and not float(value).is_integer()) else 0
    text = f"{value:,.{decimals}f}".replace(",", " ").replace(".", ",").replace(" ", ".")
    word = {"EUR": "€", "steps": "pasos", "count": "", "percent": "%", "points": "pts"}.get(
        unit or "", unit or ""
    )
    return f"{text} {word}".strip()


async def goals_today(connection: AsyncConnection) -> dict:
    daily = [
        goal
        for goal in await goals.active(connection)
        if goal.kind == "periodic" and goal.period == "day"
    ]
    if not daily:
        return envelope(KIND, "empty", {"detail": "Sin metas de cada día · ponte una en KPIs"})
    items = []
    for goal in daily:
        item: dict = {"id": goal.id, "title": goal.title, "done": bool(goal.today_met)}
        detail = (
            f"racha de {goal.streak} {'semanas' if goal.streak_unit == 'weeks' else 'días'}"
            if goal.streak
            else f"{int(goal.week_count or 0)} de {int(goal.week_target or 7)} esta semana"
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
        return envelope("list", "empty", {"detail": "Sin metas con fecha"})
    rows = []
    for goal in dated[:ROWS]:
        unit = goal.metric.unit if goal.metric else None
        if goal.target is None:
            rows.append({"label": goal.title, "value": "hito", "tone": "neutral"})
            continue
        word = PACE_WORD.get(goal.pace or "", "sin datos")
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
        return envelope("progress", "empty", {"detail": "Marca una meta como destacada en KPIs"})
    goal = found[0]
    if goal.kind == "periodic":
        return envelope(
            "progress",
            "ready",
            {
                "value": goal.week_count or 0,
                "target": goal.week_target or 7,
                "unit": goal.metric.unit if goal.period == "week" and goal.metric else None,
                "label": f"{goal.title} · esta semana",
            },
        )
    if goal.target is None or goal.current is None or goal.start is None:
        return envelope("progress", "empty", {"detail": f"{goal.title} · sin datos todavía"})
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
            "label": f"{goal.title} · {_figure(goal.current, unit)} "
            f"de {_figure(goal.target, unit)}",
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
            raise tasks.NotFound("no hay ninguna categoría donde apuntarlo")
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
