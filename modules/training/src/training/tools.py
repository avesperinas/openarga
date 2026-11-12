from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from training import stats, training

MODULE = "training"
WRITE_ROLE = f"mod_{MODULE}"
READ_ROLE = f"mod_{MODULE}_read"


def role_for_scopes(scopes: set[str]) -> str | None:
    if f"{MODULE}:write" in scopes:
        return WRITE_ROLE
    if f"{MODULE}:read" in scopes:
        return READ_ROLE
    return None


DAY = r"^\d{4}-\d{2}-\d{2}$"
SINCE = "Desde este día, `AAAA-MM-DD`, incluido. Sin él, desde el principio."
UNTIL = "Hasta este día, `AAAA-MM-DD`, incluido. Sin él, hasta el final."


class FindExercises(BaseModel):
    query: str | None = Field(
        default=None,
        max_length=60,
        description=(
            "Parte del nombre del ejercicio o de la variante, p. ej. `banca`. "
            "Sin ella, el índice entero."
        ),
    )
    limit: int = Field(default=200, ge=1, le=1000, description="Cuántas variantes, como mucho.")


class GetSessions(BaseModel):
    since: str | None = Field(default=None, pattern=DAY, description=SINCE)
    until: str | None = Field(default=None, pattern=DAY, description=UNTIL)
    limit: int = Field(
        default=100,
        ge=1,
        le=1000,
        description="Cuántas sesiones devolver, de la más reciente. El total sale aparte.",
    )
    with_sets: bool = Field(
        default=False,
        description="Con `true`, cada sesión trae sus series. Sin él, solo el resumen.",
    )


class Summarise(BaseModel):
    by: Literal["year", "month", "week", "kind", "gym"] = Field(
        default="year", description="Cómo agrupar: por año, mes, semana, tipo de día o centro."
    )
    since: str | None = Field(default=None, pattern=DAY, description=SINCE)
    until: str | None = Field(default=None, pattern=DAY, description=UNTIL)


class GetProgress(BaseModel):
    variant_id: str = Field(
        min_length=36,
        max_length=36,
        description=(
            "La variante, tal cual la da `find_exercises`. La carga solo se compara dentro de una, "
            "y en un mismo centro."
        ),
    )
    since: str | None = Field(default=None, pattern=DAY, description=SINCE)
    until: str | None = Field(default=None, pattern=DAY, description=UNTIL)
    limit: int = Field(default=200, ge=1, le=1000, description="Cuántas sesiones hacia atrás.")


class GetMuscles(BaseModel):
    since: str | None = Field(default=None, pattern=DAY, description=SINCE)
    until: str | None = Field(default=None, pattern=DAY, description=UNTIL)


class GetActivities(BaseModel):
    since: str | None = Field(default=None, pattern=DAY, description=SINCE)
    until: str | None = Field(default=None, pattern=DAY, description=UNTIL)
    limit: int = Field(default=200, ge=1, le=1000, description="Cuántas actividades, como mucho.")


CATALOGUE = text("""
    select v.id            as variant_id,
           e.name          as exercise,
           v.name          as variant,
           v.implement,
           e.pattern,
           e.load_type,
           g.name          as gym,
           v.active,
           (select count(*) from training.training_session_exercise se
             where se.variant_id = v.id) as sessions,
           array(select distinct gg.name
                   from training.training_session_exercise se
                   join training.training_session s on s.id = se.session_id
                   join training.training_gym gg on gg.id = s.gym_id
                  where se.variant_id = v.id
                  order by gg.name) as gyms
    from training.training_variant v
    join training.training_exercise e on e.id = v.exercise_id
    left join training.training_gym g on g.id = v.gym_id
    where cast(:query as text) is null
       or e.name ilike '%' || cast(:query as text) || '%'
       or v.name ilike '%' || cast(:query as text) || '%'
    order by sessions desc, e.name, v.name
    limit :limit
""")

RANGE = """
      and s.day >= coalesce(cast(:since as date), date '0001-01-01')
      and s.day <= coalesce(cast(:until as date), date '9999-12-31')
"""

COUNT_SESSIONS = text(f"""
    select count(*) as total,
           min(s.day) as first_day,
           max(s.day) as last_day
    from training.training_session s
    where s.ended_at is not null
    {RANGE}
""")

SESSIONS = text(
    """
    select s.id,
           s.day,
           d.name                 as day_name,
           d.kind,
           s.duration_seconds,
           g.name                 as gym,
           s.notes,
           r.number               as rotation,
           (select count(*)
              from training.training_session_exercise se
              join training.training_set_log l on l.session_exercise_id = se.id
             where se.session_id = s.id and l.completed)              as sets,
           (select coalesce(sum(l.reps * coalesce(l.weight, l.added_load, 0)), 0)
              from training.training_session_exercise se
              join training.training_set_log l on l.session_exercise_id = se.id
             where se.session_id = s.id and l.completed)              as volume
    from training.training_session s
    join training.training_plan_day d on d.id = s.plan_day_id and d.plan_version_id = s.plan_version_id
    join training.training_rotation r on r.id = s.rotation_id
    left join training.training_gym g on g.id = s.gym_id
    where s.ended_at is not null
"""
    + RANGE
    + """
    order by s.day desc, s.started_at desc
    limit :limit
"""
)

SUMMARY = {
    "year": "to_char(s.day, 'YYYY')",
    "month": "to_char(s.day, 'YYYY-MM')",
    "week": "to_char(s.day, 'IYYY-\"W\"IW')",
    "kind": "d.kind",
    "gym": "coalesce(g.name, 'sin centro')",
}


def summary_query(by: str) -> Any:
    return text(f"""
        select {SUMMARY[by]} as bucket,
               count(*) as sessions,
               coalesce(sum(s.duration_seconds), 0) as seconds,
               coalesce(sum((
                   select coalesce(sum(l.reps * coalesce(l.weight, l.added_load, 0)), 0)
                   from training.training_session_exercise se
                   join training.training_set_log l on l.session_exercise_id = se.id
                   where se.session_id = s.id and l.completed
               )), 0) as volume,
               min(s.day) as first_day,
               max(s.day) as last_day
        from training.training_session s
        join training.training_plan_day d
          on d.id = s.plan_day_id and d.plan_version_id = s.plan_version_id
        left join training.training_gym g on g.id = s.gym_id
        where s.ended_at is not null
        {RANGE}
        group by 1
        order by 1
    """)


ACTIVITIES = text("""
    select a.day, a.start_time, t.name as type, a.duration_seconds, a.notes
    from training.training_activity a
    join training.training_activity_type t on t.id = a.activity_type_id
    where a.day >= coalesce(cast(:since as date), date '0001-01-01')
      and a.day <= coalesce(cast(:until as date), date '9999-12-31')
    order by a.day desc, a.start_time desc
    limit :limit
""")

SETS_OF = text("""
    select se.session_id,
           e.name       as exercise,
           v.name       as variant,
           v.id         as variant_id,
           se.position,
           l.number,
           l.reps,
           l.weight,
           l.added_load
    from training.training_session_exercise se
    join training.training_variant v on v.id = se.variant_id
    join training.training_exercise e on e.id = v.exercise_id
    join training.training_set_log l on l.session_exercise_id = se.id
    where se.session_id = any(:sessions) and l.completed
    order by se.position, l.number
""")


def _number(value: Any) -> float | None:
    return None if value is None else float(value)


async def find_exercises(connection: AsyncConnection, arguments: FindExercises) -> dict[str, Any]:
    rows = (
        await connection.execute(CATALOGUE, {"query": arguments.query, "limit": arguments.limit})
    ).all()
    return {
        "variants": [
            {
                "variant_id": str(row.variant_id),
                "exercise": row.exercise,
                "variant": row.variant,
                "implement": row.implement,
                "pattern": row.pattern,
                "load_type": row.load_type,
                "gym": row.gym,
                "active": row.active,
                "sessions": row.sessions,
                "trained_at": list(row.gyms),
            }
            for row in rows
        ]
    }


def _range(arguments: Any) -> dict[str, Any]:
    return {
        "since": date.fromisoformat(arguments.since) if arguments.since else None,
        "until": date.fromisoformat(arguments.until) if arguments.until else None,
    }


async def get_sessions(connection: AsyncConnection, arguments: GetSessions) -> dict[str, Any]:
    window = _range(arguments)
    counted = (await connection.execute(COUNT_SESSIONS, window)).one()
    rows = (await connection.execute(SESSIONS, {**window, "limit": arguments.limit})).all()
    sessions = {
        str(row.id): {
            "session_id": str(row.id),
            "day": row.day.isoformat(),
            "name": row.day_name,
            "kind": row.kind,
            "rotation": row.rotation,
            "duration_minutes": None
            if row.duration_seconds is None
            else round(row.duration_seconds / 60),
            "gym": row.gym,
            "notes": row.notes,
            "sets": row.sets,
            "volume_kg": _number(row.volume),
        }
        for row in rows
    }

    if arguments.with_sets and sessions:
        for entry in sessions.values():
            entry["exercises"] = []
        detail = (
            await connection.execute(SETS_OF, {"sessions": [str(key) for key in sessions]})
        ).all()
        for row in detail:
            session = sessions[str(row.session_id)]
            exercises: list[dict[str, Any]] = session["exercises"]
            if not exercises or exercises[-1]["variant_id"] != str(row.variant_id):
                exercises.append(
                    {
                        "exercise": row.exercise,
                        "variant": row.variant,
                        "variant_id": str(row.variant_id),
                        "sets": [],
                    }
                )
            exercises[-1]["sets"].append(
                {
                    "number": row.number,
                    "reps": row.reps,
                    "weight_kg": _number(row.weight),
                    "added_load_kg": _number(row.added_load),
                }
            )

    return {
        "total": counted.total,
        "returned": len(sessions),
        "first_day": counted.first_day.isoformat() if counted.first_day else None,
        "last_day": counted.last_day.isoformat() if counted.last_day else None,
        "sessions": list(sessions.values()),
    }


async def summarise_training(connection: AsyncConnection, arguments: Summarise) -> dict[str, Any]:
    window = _range(arguments)
    rows = (await connection.execute(summary_query(arguments.by), window)).all()
    return {
        "by": arguments.by,
        "total_sessions": sum(row.sessions for row in rows),
        "buckets": [
            {
                "bucket": row.bucket,
                "sessions": row.sessions,
                "hours": round(row.seconds / 3600, 1),
                "volume_kg": _number(row.volume),
                "first_day": row.first_day.isoformat(),
                "last_day": row.last_day.isoformat(),
            }
            for row in rows
        ],
    }


async def get_activities(connection: AsyncConnection, arguments: GetActivities) -> dict[str, Any]:
    rows = (
        await connection.execute(ACTIVITIES, {**_range(arguments), "limit": arguments.limit})
    ).all()
    by_type: dict[str, int] = {}
    for row in rows:
        by_type[row.type] = by_type.get(row.type, 0) + 1
    return {
        "total": len(rows),
        "by_type": by_type,
        "activities": [
            {
                "day": row.day.isoformat(),
                "start": row.start_time.strftime("%H:%M"),
                "type": row.type,
                "minutes": None
                if row.duration_seconds is None
                else round(row.duration_seconds / 60),
                "notes": row.notes,
            }
            for row in rows
        ],
    }


REASONS = {
    "high": "muy por encima de las sesiones de alrededor en esa máquina",
    "low": "muy por debajo de las sesiones de alrededor en esa máquina",
    "excluded": "apartado a mano",
}


def _today() -> date:
    return training.local_day(datetime.now(UTC))


async def get_progress(connection: AsyncConnection, arguments: GetProgress) -> dict[str, Any]:
    analysis = await stats.analyse(connection, _today())
    name = analysis.names.get(arguments.variant_id)
    if name is None:
        return {"variant": None, "best_sets": [], "note": "esa variante no existe en tu catálogo"}

    window = _range(arguments)
    since, until = window["since"] or date.min, window["until"] or date.max
    series = [serie for serie in analysis.series if serie.variant_id == arguments.variant_id]
    starts = {serie.since for serie in series if serie.start in ("mark", "detected")}
    points = sorted(
        (point for serie in series for point in serie.points if since <= point.day <= until),
        key=lambda point: point.day,
        reverse=True,
    )[: arguments.limit]
    counted = [point for point in points if point.counted]
    best = max(counted, key=lambda point: point.e1rm, default=None)
    machines: dict[str | None, list] = {}
    for point in sorted(points, key=lambda point: point.day):
        machines.setdefault(point.gym_id, []).append(point)

    def e1rm(point) -> float:
        return round(point.e1rm, 1)

    return {
        "variant": {
            "variant_id": arguments.variant_id,
            "exercise": name.exercise,
            "variant": name.variant,
            "implement": name.implement,
            "min_increment_kg": name.min_increment,
            "load_includes_bodyweight": name.load_type != "external",
        },
        "sessions": len(points),
        "best": None
        if best is None
        else {
            "day": best.day.isoformat(),
            "gym": analysis.gym(best.gym_id),
            "reps": best.reps,
            "load_kg": round(best.load, 2),
            "e1rm_kg": e1rm(best),
        },
        "by_gym": [
            {
                "gym": analysis.gym(gym_id),
                "sessions": len(found),
                "first_day": found[0].day.isoformat(),
                "last_day": found[-1].day.isoformat(),
                "best_e1rm_kg": max((e1rm(p) for p in found if p.counted), default=None),
            }
            for gym_id, found in machines.items()
        ],
        "best_sets": [
            {
                "day": point.day.isoformat(),
                "gym": analysis.gym(point.gym_id),
                "reps": point.reps,
                "load_kg": round(point.load, 2),
                "e1rm_kg": e1rm(point),
                "e1rm_reliable": point.reps <= 10,
                "counts": point.counted,
                "why_not": None if point.counted else REASONS[point.status],
                "machine_changed": point.day in starts,
            }
            for point in points
        ],
    }


async def get_muscles(connection: AsyncConnection, arguments: GetMuscles) -> dict[str, Any]:
    today = _today()
    analysis = await stats.analyse(connection, today)
    window = _range(arguments)
    first = await connection.scalar(stats.FIRST_DAY)
    since = window["since"] or first or today
    until = min(window["until"] or today, today)
    volume = {
        row.muscle: int(row.sets)
        for row in (await connection.execute(stats.VOLUME, {"since": since, "until": until})).all()
    }
    muscles = []
    for row in (await connection.execute(stats.MUSCLES)).all():
        measured = stats.muscle_strength(analysis, row.id, since, until)
        used: dict[str, int] = {}
        days = []
        for entry in analysis.entries.values():
            if entry.muscle == row.id and since <= entry.day <= until:
                days.append(entry.day)
                label = analysis.names[entry.variant_id].label
                used[label] = used.get(label, 0) + 1
        muscles.append(
            {
                "muscle": row.id,
                "name": row.name,
                "strength_change_pct": measured.delta if measured else None,
                "sets_per_week": stats.per_week(volume.get(row.id, 0), since, until),
                "last_day": max(days).isoformat() if days else None,
                "exercises": [
                    {"exercise": label, "sessions": count}
                    for label, count in sorted(used.items(), key=lambda item: -item[1])
                ],
            }
        )
    return {
        "since": since.isoformat(),
        "until": until.isoformat(),
        "bodyweight_kg": analysis.bodyweight,
        "muscles": muscles,
    }


@dataclass(frozen=True)
class Tool:
    arguments: type[BaseModel]
    run: Callable[[AsyncConnection, Any], Awaitable[dict[str, Any]]]


TOOLS: dict[str, Tool] = {
    "find_exercises": Tool(FindExercises, find_exercises),
    "get_sessions": Tool(GetSessions, get_sessions),
    "get_progress": Tool(GetProgress, get_progress),
    "summarise_training": Tool(Summarise, summarise_training),
    "get_activities": Tool(GetActivities, get_activities),
    "get_muscles": Tool(GetMuscles, get_muscles),
}
