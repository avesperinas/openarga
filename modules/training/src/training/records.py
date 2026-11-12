from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

import arga_contracts as contracts
from arga_contracts import records as write
from training import links

APP = "training"
IMPLEMENTS = {
    "barbell": "barbell",
    "dumbbell": "dumbbells",
    "smith": "Smith machine",
    "machine": "machine",
    "cable": "cable",
    "bodyweight": "bodyweight",
}
LAST_TIMES = 10

VARIANTS = text("""
    select v.id, v.name as variant, v.implement, v.active, e.name as exercise,
           coalesce(array_agg(m.name order by em.contribution desc, m.name)
                    filter (where m.name is not null), '{}') as muscles
    from training.training_variant v
    join training.training_exercise e on e.id = v.exercise_id
    left join training.training_exercise_muscle em on em.exercise_id = e.id
    left join training.training_muscle m on m.id = em.muscle_id
    group by v.id, v.name, v.implement, v.active, e.name
""")

SESSIONS = text("""
    select s.id, s.day, s.started_at, s.duration_seconds, s.notes, d.name as plan_day,
           g.name as gym
    from training.training_session s
    join training.training_plan_day d on d.id = s.plan_day_id
    left join training.training_gym g on g.id = s.gym_id
    where s.ended_at is not null
""")

SETS = text("""
    select se.session_id, se.variant_id, se.position, l.number, l.reps, l.weight, l.added_load,
           l.rir
    from training.training_session_exercise se
    join training.training_session s on s.id = se.session_id and s.ended_at is not null
    join training.training_set_log l on l.session_exercise_id = se.id and l.completed
    order by se.session_id, se.position, l.number
""")

ACTIVITIES = text("""
    select a.day, a.duration_seconds, a.notes, t.name
    from training.training_activity a
    join training.training_activity_type t on t.id = a.activity_type_id
""")


@dataclass
class Set:
    number: int
    reps: int
    kg: float | None

    @property
    def shown(self) -> str:
        return f"{self.reps} × {write.trimmed(self.kg)} kg" if self.kg else f"{self.reps} reps"

    @property
    def volume(self) -> float:
        return self.reps * (self.kg or 0)


@dataclass
class Done:
    variant_id: str
    position: int
    sets: list[Set] = field(default_factory=list)


def _kg(weight: Any, added: Any) -> float | None:
    if weight is None and added is None:
        return None
    return float(weight or 0) + float(added or 0)


def _minutes(seconds: int | None) -> int | None:
    return None if seconds is None else round(seconds / 60)


def _session_title(row: Any) -> str:
    return f"{row.day.isoformat()} {row.plan_day}"


async def build(connection: AsyncConnection) -> list[dict[str, Any]]:
    variants = {str(row.id): row for row in (await connection.execute(VARIANTS)).all()}
    names = {key: links.label(row.exercise, row.variant) for key, row in variants.items()}
    sessions = {str(row.id): row for row in (await connection.execute(SESSIONS)).all()}
    done: dict[str, dict[str, Done]] = defaultdict(dict)
    for row in (await connection.execute(SETS)).all():
        session_id, variant_id = str(row.session_id), str(row.variant_id)
        one = done[session_id].setdefault(variant_id, Done(variant_id, row.position))
        one.sets.append(Set(row.number, row.reps, _kg(row.weight, row.added_load)))

    found: list[dict[str, Any]] = []
    history: dict[str, list[tuple[date, str, Done]]] = defaultdict(list)
    for session_id, row in sessions.items():
        exercises = sorted(done[session_id].values(), key=lambda one: one.position)
        for one in exercises:
            history[one.variant_id].append((row.day, session_id, one))
        found.append(session(row, exercises, names))
    for variant_id, row in variants.items():
        found.append(exercise(variant_id, row, names[variant_id], history[variant_id], sessions))
    found.extend(await days(connection, sessions, done))
    return found


def session(row: Any, exercises: list[Done], names: dict[str, str]) -> dict[str, Any]:
    sets = sum(len(one.sets) for one in exercises)
    volume = sum(item.volume for one in exercises for item in one.sets)
    minutes = _minutes(row.duration_seconds)
    parts = []
    for one in exercises:
        shown = write.link(APP, one.variant_id, names.get(one.variant_id, "Exercise"))
        series = ", ".join(item.shown for item in one.sets)
        parts.append(f"- {shown}: {series}")
    lead = [f"{row.plan_day}, {write.weekday(row.day)} {write.long_date(row.day)}"]
    if minutes is not None:
        lead.append(f"{minutes} min")
    lead.append(f"{sets} sets")
    if volume:
        lead.append(f"{write.number(volume)} kg lifted")
    if row.gym:
        lead.append(row.gym)
    properties: dict[str, Any] = {
        "date": row.day.isoformat(),
        "plan_day": row.plan_day,
        "sets": sets,
        "volume_kg": round(volume),
    }
    if minutes is not None:
        properties["duration_min"] = minutes
    if row.gym:
        properties["gym"] = row.gym
    return contracts.record(
        id=f"session:{row.id}",
        title=_session_title(row),
        kind="Session",
        href=f"/training/session/{row.id}",
        folder=f"Sessions/{row.day.year}",
        properties=properties,
        body=write.sections(
            " · ".join(lead) + ".",
            "## Exercises\n\n" + "\n".join(parts) if parts else None,
            f"## Notes\n\n{row.notes}" if row.notes else None,
        ),
    )


def exercise(
    variant_id: str,
    row: Any,
    name: str,
    times: list[tuple[date, str, Done]],
    sessions: dict[str, Any],
) -> dict[str, Any]:
    times = sorted(times, key=lambda one: one[0])
    heaviest = max(
        ((day, item) for day, _, one in times for item in one.sets if item.kg),
        key=lambda pair: (pair[1].kg, pair[1].reps),
        default=None,
    )
    properties: dict[str, Any] = {
        "exercise": row.exercise,
        "implement": IMPLEMENTS.get(row.implement, row.implement),
        "muscles": list(row.muscles),
        "times": len(times),
        "active": row.active,
    }
    if times:
        properties["last_time"] = times[-1][0].isoformat()
    if heaviest is not None:
        properties["best_weight_kg"] = heaviest[1].kg
    last = []
    for _day, session_id, one in reversed(times[-LAST_TIMES:]):
        shown = write.link(APP, f"session:{session_id}", _session_title(sessions[session_id]))
        last.append(f"- {shown}: " + ", ".join(item.shown for item in one.sets))
    lead = f"{row.exercise} with {IMPLEMENTS.get(row.implement, row.implement)}"
    if row.muscles:
        lead += " · " + ", ".join(row.muscles)
    best = None
    if heaviest is not None:
        best = f"Heaviest: {heaviest[1].shown}, on {write.long_date(heaviest[0])}."
    return contracts.record(
        id=variant_id,
        title=name,
        kind="Exercise",
        href=f"/training/stats?variant={variant_id}",
        folder="Exercises",
        properties=properties,
        body=write.sections(
            lead + ".",
            best,
            f"## Latest times\n\n{chr(10).join(last)}" if last else "Not done yet.",
            None if row.active else "*No longer in use.*",
        ),
    )


async def days(
    connection: AsyncConnection, sessions: dict[str, Any], done: dict[str, dict[str, Done]]
) -> list[dict[str, Any]]:
    lines: dict[date, list[str]] = defaultdict(list)
    minutes: dict[date, int] = defaultdict(int)
    series: dict[date, int] = defaultdict(int)
    for session_id, row in sorted(sessions.items(), key=lambda pair: pair[1].started_at):
        count = sum(len(one.sets) for one in done[session_id].values())
        took = _minutes(row.duration_seconds)
        shown = write.link(APP, f"session:{session_id}", row.plan_day)
        lines[row.day].append(
            f"- Workout: {shown}" + (f" · {took} min" if took else "") + f" · {count} sets"
        )
        minutes[row.day] += took or 0
        series[row.day] += count
    for row in (await connection.execute(ACTIVITIES)).all():
        took = _minutes(row.duration_seconds)
        lines[row.day].append(
            f"- {row.name}"
            + (f" · {took} min" if took else "")
            + (f" · {row.notes}" if row.notes else "")
        )
        minutes[row.day] += took or 0
    found = []
    for day, told in sorted(lines.items()):
        properties: dict[str, Any] = {}
        if minutes[day]:
            properties["training_min"] = minutes[day]
        if series[day]:
            properties["sets"] = series[day]
        found.append(
            contracts.record(
                id=f"day:{day.isoformat()}",
                title="Training",
                kind="Day",
                href="/training/calendar",
                day=day,
                properties=properties,
                body="\n".join(told),
            )
        )
    return found
