from __future__ import annotations

from collections.abc import Iterable
from datetime import date

from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from training import stats


class Record(BaseModel):
    variant_id: str
    range: str
    reps: int
    load: float
    previous: float


class Worked(BaseModel):
    muscle: str
    name: str
    sets: float


class Outcome(BaseModel):
    session_id: str
    muscles: list[Worked]
    records: list[Record]


HEAD = text("select day, gym_id, ended_at from training.training_session where id = :id")

WORKED = text("""
    select em.muscle_id as muscle, m.name, sum(em.contribution) as sets
    from training.training_session_exercise se
    join training.training_set_log l on l.session_exercise_id = se.id and l.completed
    join training.training_variant v on v.id = se.variant_id
    join training.training_exercise_muscle em on em.exercise_id = v.exercise_id
    join training.training_muscle m on m.id = em.muscle_id
    where se.session_id = :id
    group by em.muscle_id, m.name
    order by sets desc, m.name
""")


class NotFound(Exception):
    pass


def new_records(
    today: Iterable[tuple[int, float]], before: Iterable[tuple[int, float]]
) -> list[tuple[str, int, float, float]]:
    earlier = list(before)
    out: list[tuple[str, int, float, float]] = []
    for label, low, high in stats.RANGES:
        inside = [(reps, load) for reps, load in today if low <= reps <= high]
        previous = [load for reps, load in earlier if low <= reps <= high]
        if not inside or not previous:
            continue
        reps, load = max(inside, key=lambda pair: (pair[1], pair[0]))
        if load > max(previous):
            out.append((label, reps, load, max(previous)))
    return out


def _sets(analysis: stats.Analysis, entry_id: str) -> list[tuple[int, float]]:
    return [
        (logged.reps, float(logged.weight or logged.added_load or 0))
        for logged in analysis.entries[entry_id].sets
        if logged.completed and logged.reps and (logged.weight or logged.added_load)
    ]


def records_of(analysis: stats.Analysis, session_id: str, day: date) -> list[Record]:
    points = {point.id: point for serie in analysis.series for point in serie.points}
    out: list[Record] = []
    for entry in analysis.entries.values():
        if entry.session_id != session_id:
            continue
        point = points.get(entry.id)
        if point is None or not point.counted:
            continue
        before = [
            pair
            for other in points.values()
            if other.counted
            and (other.variant_id, other.gym_id) == (entry.variant_id, entry.gym_id)
            and other.day < day
            for pair in _sets(analysis, other.id)
        ]
        out.extend(
            Record(variant_id=entry.variant_id, range=label, reps=reps, load=load, previous=prev)
            for label, reps, load, prev in new_records(_sets(analysis, entry.id), before)
        )
    return out


async def read(connection: AsyncConnection, session_id: str) -> Outcome:
    head = (await connection.execute(HEAD, {"id": session_id})).one_or_none()
    if head is None:
        raise NotFound(session_id)
    muscles = [
        Worked(muscle=row.muscle, name=row.name, sets=float(row.sets))
        for row in (await connection.execute(WORKED, {"id": session_id})).all()
    ]
    records = []
    if head.ended_at is not None:
        analysis = await stats.analyse(connection, head.day)
        records = records_of(analysis, session_id, head.day)
    return Outcome(session_id=session_id, muscles=muscles, records=records)
