from __future__ import annotations

from collections import defaultdict
from datetime import date
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy.ext.asyncio import AsyncConnection

import arga_contracts as contracts
from arga_contracts import records as write
from goals import goals, tasks

APP = "goals"
MADRID = ZoneInfo("Europe/Madrid")
ALL_DONE = 100_000
HISTORY_ROWS = 30
STATUS = {"active": "activa", "achieved": "lograda", "missed": "fallida", "abandoned": "abandonada"}
KIND = {"periodic": "periódica", "dated": "con fecha"}
PACE = {"ahead": "por delante", "on_track": "en camino", "behind": "por detrás"}


def _value(value: float | None, unit: str | None) -> str:
    if value is None:
        return ""
    return f"{write.trimmed(value)} {unit}".strip() if unit else write.trimmed(value)


def goal(found: goals.GoalDetail) -> dict[str, Any]:
    one = found.goal
    unit = one.metric.unit if one.metric else None
    properties: dict[str, Any] = {
        "estado": STATUS[one.status],
        "clase": KIND[one.kind],
        "desde": one.start_on.isoformat(),
    }
    for name, value in (
        ("categoria", one.category),
        ("cifra", one.metric.label if one.metric else None),
        ("objetivo", one.target),
        ("unidad", unit),
        ("hasta", one.due_on.isoformat() if one.due_on else None),
        ("actual", one.current),
        ("progreso", round(one.progress * 100) if one.progress is not None else None),
        ("racha", one.streak),
        ("ritmo", PACE[one.pace] if one.pace else None),
        ("esperado", round(one.expected, 2) if one.expected is not None else None),
        ("cerrada", one.closed_on.isoformat() if one.closed_on else None),
    ):
        if value is not None:
            properties[name] = value
    lead = []
    if one.kind == "dated" and one.due_on:
        lead.append(
            f"Llegar a {_value(one.target, unit)} para el {write.long_date(one.due_on)}"
            if one.target is not None
            else f"Para el {write.long_date(one.due_on)}"
        )
    elif one.period == "day":
        lead.append(f"{one.days_per_week} días a la semana")
    elif one.period == "week":
        lead.append(f"{_value(one.target, unit)} a la semana")
    if one.current is not None:
        lead.append(f"ahora {_value(one.current, unit)}")
    if one.pace:
        lead.append(PACE[one.pace])
    if one.streak:
        lead.append(f"racha de {one.streak} {'días' if one.streak_unit == 'days' else 'semanas'}")
    if one.status != "active" and one.closed_on:
        lead.append(f"{STATUS[one.status]} el {write.long_date(one.closed_on)}")
    rows = [
        [
            point.day.isoformat(),
            _value(point.value, unit),
            "sí" if point.met else ("no" if point.met is False else ""),
            point.note or "",
        ]
        for point in reversed(found.history[-HISTORY_ROWS:])
    ]
    return contracts.record(
        id=f"goal:{one.id}",
        title=one.title,
        kind="Meta",
        href=f"/goals/meta/{one.id}",
        folder="Metas",
        properties=properties,
        body=write.sections(
            (" · ".join(lead) + ".").capitalize() if lead else None,
            f"## Nota\n\n{one.note}" if one.note else None,
            "## Últimos días\n\n" + write.table(["Día", "Valor", "Cumplido", "Nota"], rows)
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
        title="Tareas pendientes",
        kind="Tareas",
        href="/goals/tareas",
        properties={"pendientes": len(found)},
        body=write.sections(*parts) or "Nada pendiente.",
    )


def days(found: list[tasks.Task]) -> list[dict[str, Any]]:
    by_day: dict[date, list[tasks.Task]] = defaultdict(list)
    for task in found:
        if task.done_at is not None:
            by_day[task.done_at.astimezone(MADRID).date()].append(task)
    return [
        contracts.record(
            id=f"day:{day.isoformat()}",
            title="Tareas",
            kind="Día",
            href="/goals/hechas",
            day=day,
            properties={"tareas_hechas": len(done)},
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
