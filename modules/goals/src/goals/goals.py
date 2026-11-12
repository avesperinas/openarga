from __future__ import annotations

from datetime import date, timedelta
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from goals import metrics, tasks
from goals.common import Conflict, NotFound, enqueue, fold, is_uuid, today
from goals.progress import Check, DayState, Evaluation, GoalShape, evaluate, monday

Kind = Literal["periodic", "dated"]
Direction = Literal["at_least", "at_most"]
Period = Literal["day", "week"]
Status = Literal["active", "achieved", "missed", "abandoned"]

SEEDED: tuple[tuple[str, int], ...] = (
    ("Salud", 6),
    ("Dinero", 4),
    ("Aprender", 7),
    ("Deporte", 8),
)

HISTORY_DAYS = 400


class MetricRef(BaseModel):
    key: str
    label: str
    unit: str
    kind: Literal["level", "amount"]


class WeekDay(BaseModel):
    day: date
    state: DayState


class Goal(BaseModel):
    id: str
    title: str
    category_id: str | None
    category: str | None
    hue: int | None
    kind: Kind
    metric: MetricRef | None
    direction: Direction
    target: float | None
    period: Period | None
    days_per_week: int | None
    start_value: float | None
    start_on: date
    due_on: date | None
    status: Status
    closed_on: date | None
    closed_value: float | None
    note: str | None
    featured: bool
    position: int
    today_met: bool | None
    today_value: float | None
    today_manual: bool
    week: list[WeekDay]
    week_count: float | None
    week_target: float | None
    week_met: bool | None
    streak: int | None
    streak_unit: Literal["days", "weeks"] | None
    constancy: float | None
    current: float | None
    start: float | None
    expected: float | None
    pace: Literal["ahead", "on_track", "behind"] | None
    progress: float | None
    projection: float | None
    projection_reached: bool | None
    reached: bool | None
    last_day: date | None
    days_left: int | None


class DayPoint(BaseModel):
    day: date
    value: float | None
    met: bool | None
    manual: bool
    done: bool | None
    note: str | None


class GoalDetail(BaseModel):
    goal: Goal
    history: list[DayPoint]


SELECT = """
    select g.id::text as id, g.title, g.category_id::text as category_id, c.name as category,
           c.hue, g.kind, g.metric_key, g.metric_label, g.metric_unit, g.metric_kind,
           g.direction, g.target::float8 as target, g.period, g.days_per_week,
           g.start_value::float8 as start_value, g.start_on, g.due_on, g.status, g.closed_on,
           g.closed_value::float8 as closed_value, g.note, g.featured, g.position
    from goals.goals_goal g
    left join goals.goals_category c on c.id = g.category_id
"""
ORDER = " order by g.position, g.created_at"

CHECKS = text("""
    select goal_id::text as goal_id, day, done, value::float8 as value, note
    from goals.goals_goal_check
    where goal_id = any(cast(:ids as uuid[])) and day >= :since
""")


def stored(kind: str | None) -> str | None:
    return "level" if kind == "peak" else kind


def shape(row: Any, peaks: frozenset[str] = frozenset()) -> GoalShape:
    return GoalShape(
        kind=row.kind,
        start_on=row.start_on,
        direction=row.direction,
        target=row.target,
        period=row.period,
        days_per_week=row.days_per_week,
        due_on=row.due_on,
        start_value=row.start_value,
        metric_kind="peak" if row.metric_key in peaks else row.metric_kind,
    )


def _goal(row: Any, found: Evaluation) -> Goal:
    metric = (
        MetricRef(
            key=row.metric_key,
            label=row.metric_label or row.metric_key,
            unit=row.metric_unit or "count",
            kind=row.metric_kind,
        )
        if row.metric_key
        else None
    )
    return Goal(
        id=row.id,
        title=row.title,
        category_id=row.category_id,
        category=row.category,
        hue=row.hue,
        kind=row.kind,
        metric=metric,
        direction=row.direction,
        target=row.target,
        period=row.period,
        days_per_week=row.days_per_week,
        start_value=row.start_value,
        start_on=row.start_on,
        due_on=row.due_on,
        status=row.status,
        closed_on=row.closed_on,
        closed_value=row.closed_value,
        note=row.note,
        featured=row.featured,
        position=row.position,
        today_met=found.today_met,
        today_value=found.today_value,
        today_manual=found.today_manual,
        week=[WeekDay(day=day, state=state) for day, state in found.week],
        week_count=found.week_count,
        week_target=found.week_target,
        week_met=found.week_met,
        streak=found.streak,
        streak_unit=found.streak_unit,
        constancy=found.constancy,
        current=found.current,
        start=found.start,
        expected=found.expected,
        pace=found.pace,
        progress=found.progress,
        projection=found.projection,
        projection_reached=found.projection_reached,
        reached=found.reached,
        last_day=found.last_day,
        days_left=found.days_left,
    )


def _since(row: Any, at: date) -> date:
    return min(row.start_on - timedelta(days=7), monday(at) - timedelta(days=35))


async def _inputs(
    connection: AsyncConnection, rows: list[Any], at: date
) -> tuple[dict[str, dict[date, float]], dict[str, dict[date, Check]], dict[str, dict[date, Any]]]:
    values: dict[str, dict[date, float]] = {}
    by_key: dict[str, date] = {}
    for row in rows:
        if row.metric_key:
            since = _since(row, at)
            by_key[row.metric_key] = min(since, by_key.get(row.metric_key, since))
    series = await metrics.series_many(connection, by_key)
    for row in rows:
        values[row.id] = series.get(row.metric_key, {}) if row.metric_key else {}

    checks: dict[str, dict[date, Check]] = {row.id: {} for row in rows}
    raw: dict[str, dict[date, Any]] = {row.id: {} for row in rows}
    if rows:
        since = min(_since(row, at) for row in rows)
        found = await connection.execute(CHECKS, {"ids": [row.id for row in rows], "since": since})
        for check in found:
            checks[check.goal_id][check.day] = Check(done=check.done, value=check.value)
            raw[check.goal_id][check.day] = check
    return values, checks, raw


async def _read(connection: AsyncConnection, where: str, params: dict[str, Any]) -> list[Goal]:
    rows = (await connection.execute(text(SELECT + f" where {where}" + ORDER), params)).all()
    at = today()
    values, checks, _ = await _inputs(connection, rows, at)
    peaks = frozenset(one.key for one in await metrics.available(connection) if one.kind == "peak")
    return [
        _goal(row, evaluate(shape(row, peaks), values[row.id], checks[row.id], at)) for row in rows
    ]


async def active(connection: AsyncConnection, category_id: str | None = None) -> list[Goal]:
    where, params = "g.status = 'active'", {}
    if category_id:
        where += " and g.category_id = cast(:category as uuid)"
        params["category"] = category_id
    return await _read(connection, where, params)


async def closed(connection: AsyncConnection) -> list[Goal]:
    goals = await _read(connection, "g.status <> 'active'", {})
    return sorted(goals, key=lambda goal: goal.closed_on or goal.start_on, reverse=True)


async def one(connection: AsyncConnection, goal_id: str) -> Goal:
    if not is_uuid(goal_id):
        raise NotFound(f"meta {goal_id!r}")
    found = await _read(connection, "g.id = cast(:id as uuid)", {"id": goal_id})
    if not found:
        raise NotFound(f"meta {goal_id}")
    return found[0]


async def detail(connection: AsyncConnection, goal_id: str) -> GoalDetail:
    goal = await one(connection, goal_id)
    at = today()
    since = at - timedelta(days=HISTORY_DAYS)
    values = await metrics.series(connection, goal.metric.key, since) if goal.metric else {}
    raw = (await connection.execute(CHECKS, {"ids": [goal.id], "since": since})).all()
    checks = {row.day: row for row in raw}
    days = sorted(set(values) | set(checks))
    if goal.kind == "periodic":
        first = max(goal.start_on, since)
        days = [first + timedelta(days=n) for n in range((at - first).days + 1)]
    history: list[DayPoint] = []
    for day in days:
        check = checks.get(day)
        value = check.value if check is not None and check.value is not None else values.get(day)
        met: bool | None = None
        if goal.kind == "periodic" and goal.period == "day":
            if check is not None and check.done is not None:
                met = check.done
            elif value is not None and goal.target is not None:
                met = value >= goal.target if goal.direction == "at_least" else value <= goal.target
            else:
                met = False
        history.append(
            DayPoint(
                day=day,
                value=value,
                met=met,
                manual=check is not None,
                done=check.done if check is not None else None,
                note=check.note if check is not None else None,
            )
        )
    return GoalDetail(goal=goal, history=history)


async def find(connection: AsyncConnection, title: str) -> Goal:
    wanted = fold(title)
    for pool in (await active(connection), await closed(connection)):
        exact = [goal for goal in pool if fold(goal.title) == wanted]
        if len(exact) == 1:
            return exact[0]
        partial = [goal for goal in pool if wanted in fold(goal.title)]
        if len(partial) == 1:
            return partial[0]
        if len(exact) > 1 or len(partial) > 1:
            names = ", ".join(goal.title for goal in (exact or partial))
            raise Conflict(f"hay varias metas que se llaman así: {names}. Usa su id")
    raise NotFound(f"no hay una meta '{title}'")


async def counts(connection: AsyncConnection) -> dict[str, int]:
    rows = await connection.execute(
        text(
            "select category_id::text as id, count(*) as n from goals.goals_goal "
            "where status = 'active' and category_id is not null group by category_id"
        )
    )
    return {row.id: row.n for row in rows}


async def seed(connection: AsyncConnection) -> None:
    await tasks.seed(connection)
    first = await connection.scalar(
        text(
            "update goals.goals_person set goals_seeded_at = now() "
            "where goals_seeded_at is null returning user_id"
        )
    )
    if first is None:
        return
    rows = await connection.execute(
        text("select name, position from goals.goals_category where space_id is null")
    )
    existing = rows.all()
    taken = {fold(row.name) for row in existing}
    position = max((row.position for row in existing), default=0)
    for name, hue in SEEDED:
        if fold(name) in taken:
            continue
        position += 1
        await connection.execute(
            text(
                "insert into goals.goals_category (name, hue, position) "
                "values (:name, :hue, :position)"
            ),
            {"name": name, "hue": hue, "position": position},
        )


def _title(value: str) -> str:
    value = " ".join(value.split())
    if not value:
        raise ValueError("la meta necesita un título")
    return value


class GoalIn(BaseModel):
    title: str = Field(min_length=1, max_length=120)
    category_id: str | None = None
    kind: Kind
    metric_key: str | None = Field(default=None, max_length=160)
    direction: Direction = "at_least"
    target: float | None = Field(default=None, allow_inf_nan=False)
    period: Period | None = None
    days_per_week: int | None = Field(default=None, ge=1, le=7)
    start_value: float | None = Field(default=None, allow_inf_nan=False)
    start_on: date | None = None
    due_on: date | None = None
    note: str | None = Field(default=None, max_length=2000)
    featured: bool = False

    _clean = field_validator("title")(_title)


class GoalPatch(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=120)
    category_id: str | None = None
    metric_key: str | None = Field(default=None, max_length=160)
    direction: Direction | None = None
    target: float | None = Field(default=None, allow_inf_nan=False)
    period: Period | None = None
    days_per_week: int | None = Field(default=None, ge=1, le=7)
    start_value: float | None = Field(default=None, allow_inf_nan=False)
    start_on: date | None = None
    due_on: date | None = None
    note: str | None = Field(default=None, max_length=2000)
    featured: bool | None = None

    @field_validator("title")
    @classmethod
    def _clean(cls, value: str | None) -> str | None:
        return None if value is None else _title(value)


def _check_shape(fields: dict[str, Any]) -> None:
    kind = fields["kind"]
    if kind == "periodic":
        if fields["due_on"] is not None:
            raise Conflict("una meta periódica no tiene fecha límite: se cumple cada día o semana")
        if fields["period"] is None:
            raise Conflict("una meta periódica es de cada día (period: day) o de la semana (week)")
        if fields["period"] == "day" and fields["days_per_week"] is None:
            fields["days_per_week"] = 7
        if fields["period"] == "week":
            fields["days_per_week"] = None
            if fields["target"] is None:
                raise Conflict("una meta de total semanal necesita el total (target)")
    else:
        if fields["due_on"] is None:
            raise Conflict("una meta con fecha necesita su fecha límite (due_on)")
        if fields["period"] is not None or fields["days_per_week"] is not None:
            raise Conflict("una meta con fecha no se repite: quita period y days_per_week")
        if fields["due_on"] <= fields["start_on"]:
            raise Conflict("la fecha límite tiene que ser después del punto de partida")
    if fields["metric_key"] and fields["kind"] == "periodic" and fields["target"] is None:
        raise Conflict(
            "una meta periódica atada a una cifra necesita la condición (target): "
            "«8.000 pasos» es la cifra pasos con target 8000"
        )


async def _metric(connection: AsyncConnection, key: str | None) -> metrics.Metric | None:
    if not key:
        return None
    found = await metrics.find(connection, key)
    if found is None:
        raise NotFound(
            f"no ha llegado nunca la cifra '{key}'. Las que hay salen en list_metrics o en el "
            f"selector de la app"
        )
    return found


async def _category(connection: AsyncConnection, category_id: str | None) -> None:
    if category_id is None:
        return
    if not is_uuid(category_id):
        raise NotFound(f"categoría {category_id!r}")
    found = await connection.scalar(
        text("select 1 from goals.goals_category where id = cast(:id as uuid)"),
        {"id": category_id},
    )
    if not found:
        raise NotFound(f"categoría {category_id}")


async def _starting_value(
    connection: AsyncConnection, metric: metrics.Metric | None, fields: dict[str, Any]
) -> float | None:
    if fields["start_value"] is not None or fields["kind"] != "dated" or metric is None:
        return fields["start_value"]
    if metric.kind == "amount":
        return 0.0
    if fields["start_on"] > today():
        return None
    if metric.kind == "peak":
        history = await metrics.series(connection, metric.key, date(1970, 1, 1))
        before = [value for day, value in history.items() if day < fields["start_on"]]
        best = max if fields["direction"] == "at_least" else min
        return best(before) if before else None
    history = await metrics.series(connection, metric.key, fields["start_on"] - timedelta(days=90))
    before = [day for day in history if day <= fields["start_on"]]
    if before:
        return history[max(before)]
    return metric.last_value if metric.last_day <= fields["start_on"] else None


async def _unfeature_others(connection: AsyncConnection, goal_id: str) -> None:
    await connection.execute(
        text(
            "update goals.goals_goal set featured = false "
            "where featured and id <> cast(:id as uuid)"
        ),
        {"id": goal_id},
    )


INSERT = text("""
    insert into goals.goals_goal
        (category_id, title, kind, metric_key, metric_label, metric_unit, metric_kind, direction,
         target, period, days_per_week, start_value, start_on, due_on, note, featured, position)
    values (cast(:category_id as uuid), :title, :kind, :metric_key, :metric_label, :metric_unit,
            :metric_kind, :direction, :target, :period, :days_per_week, :start_value, :start_on,
            :due_on, :note, :featured,
            (select coalesce(max(position), 0) + 1 from goals.goals_goal))
    returning id::text
""")


async def create(connection: AsyncConnection, body: GoalIn) -> Goal:
    await seed(connection)
    fields = body.model_dump()
    fields["start_on"] = fields["start_on"] or today()
    fields["note"] = (fields["note"] or "").strip() or None
    _check_shape(fields)
    await _category(connection, fields["category_id"])
    metric = await _metric(connection, fields["metric_key"])
    fields["start_value"] = await _starting_value(connection, metric, fields)
    goal_id = await connection.scalar(
        INSERT,
        {
            **fields,
            "metric_label": metric.label if metric else None,
            "metric_unit": metric.unit if metric else None,
            "metric_kind": stored(metric.kind) if metric else None,
        },
    )
    if body.featured:
        await _unfeature_others(connection, goal_id)
    created = await one(connection, goal_id)
    await _publish(connection, created, "created")
    return created


class PastGoalIn(BaseModel):
    title: str = Field(min_length=1, max_length=120)
    category_id: str | None = None
    start_on: date
    due_on: date
    outcome: Literal["achieved", "missed", "abandoned"]
    closed_on: date | None = None
    target: float | None = Field(default=None, allow_inf_nan=False)
    start_value: float | None = Field(default=None, allow_inf_nan=False)
    closed_value: float | None = Field(default=None, allow_inf_nan=False)
    direction: Direction = "at_least"
    note: str | None = Field(default=None, max_length=2000)

    _clean = field_validator("title")(_title)


INSERT_PAST = text("""
    insert into goals.goals_goal
        (category_id, title, kind, direction, target, start_value, start_on, due_on, status,
         closed_on, closed_value, note, position)
    values (cast(:category_id as uuid), :title, 'dated', :direction, :target, :start_value,
            :start_on, :due_on, :outcome, :closed_on, :closed_value, :note,
            (select coalesce(max(position), 0) + 1 from goals.goals_goal))
    returning id::text
""")


async def record_past(connection: AsyncConnection, body: PastGoalIn) -> Goal:
    await seed(connection)
    fields = body.model_dump()
    if fields["due_on"] <= fields["start_on"]:
        raise Conflict("la fecha límite tiene que ser después del punto de partida")
    fields["closed_on"] = fields["closed_on"] or fields["due_on"]
    if fields["closed_on"] < fields["start_on"]:
        raise Conflict("no pudo cerrarse antes de empezar")
    if fields["closed_on"] > today():
        raise Conflict("una meta pasada se cerró hoy o antes: si sigue abierta, créala normal")
    fields["note"] = (fields["note"] or "").strip() or None
    await _category(connection, fields["category_id"])
    goal_id = await connection.scalar(INSERT_PAST, fields)
    return await one(connection, goal_id)


async def update(connection: AsyncConnection, goal_id: str, body: GoalPatch) -> Goal:
    current = await one(connection, goal_id)
    given = body.model_fields_set
    fields: dict[str, Any] = {
        "kind": current.kind,
        "title": current.title,
        "category_id": current.category_id,
        "metric_key": current.metric.key if current.metric else None,
        "direction": current.direction,
        "target": current.target,
        "period": current.period,
        "days_per_week": current.days_per_week,
        "start_value": current.start_value,
        "start_on": current.start_on,
        "due_on": current.due_on,
        "note": current.note,
        "featured": current.featured,
    }
    for name in given:
        value = getattr(body, name)
        if name in {"title", "featured", "direction"} and value is None:
            continue
        fields[name] = value
    fields["note"] = (fields["note"] or "").strip() or None
    _check_shape(fields)
    await _category(connection, fields["category_id"])

    metric_changed = "metric_key" in given and fields["metric_key"] != (
        current.metric.key if current.metric else None
    )
    label = current.metric.label if current.metric else None
    unit = current.metric.unit if current.metric else None
    kind = current.metric.kind if current.metric else None
    if metric_changed:
        metric = await _metric(connection, fields["metric_key"])
        label, unit, kind = (
            (metric.label, metric.unit, stored(metric.kind)) if metric else (None, None, None)
        )
    elif fields["metric_key"]:
        metric = await metrics.find(connection, fields["metric_key"])
    else:
        metric = None
    moved = metric_changed or fields["start_on"] != current.start_on
    if moved and "start_value" not in given:
        fields["start_value"] = None
    if fields["start_value"] is None:
        fields["start_value"] = await _starting_value(connection, metric, fields)

    await connection.execute(
        text("""
            update goals.goals_goal
            set title = :title, category_id = cast(:category_id as uuid), metric_key = :metric_key,
                metric_label = :metric_label, metric_unit = :metric_unit,
                metric_kind = :metric_kind, direction = :direction, target = :target,
                period = :period, days_per_week = :days_per_week, start_value = :start_value,
                start_on = :start_on, due_on = :due_on, note = :note, featured = :featured,
                updated_at = now()
            where id = cast(:id as uuid)
        """),
        {
            **{name: value for name, value in fields.items() if name != "kind"},
            "id": goal_id,
            "metric_label": label,
            "metric_unit": unit,
            "metric_kind": kind,
        },
    )
    if fields["featured"]:
        await _unfeature_others(connection, goal_id)
    return await one(connection, goal_id)


async def remove(connection: AsyncConnection, goal_id: str) -> None:
    await one(connection, goal_id)
    await connection.execute(
        text("delete from goals.goals_goal where id = cast(:id as uuid)"), {"id": goal_id}
    )


class OrderIn(BaseModel):
    ids: list[str] = Field(min_length=1, max_length=300)


async def order(connection: AsyncConnection, body: OrderIn) -> list[Goal]:
    known = {goal.id for goal in await active(connection)}
    if set(body.ids) != known or len(body.ids) != len(known):
        raise Conflict("el orden tiene que llevar todas tus metas activas, una vez cada una")
    for position, goal_id in enumerate(body.ids, start=1):
        await connection.execute(
            text("update goals.goals_goal set position = :p where id = cast(:id as uuid)"),
            {"id": goal_id, "p": position},
        )
    return await active(connection)


class CheckIn(BaseModel):
    day: date | None = None
    done: bool | None = None
    value: float | None = Field(default=None, allow_inf_nan=False)
    note: str | None = Field(default=None, max_length=500)

    @model_validator(mode="after")
    def _something(self) -> CheckIn:
        if self.done is None and self.value is None:
            raise ValueError("di si se hizo (done) o apunta un valor (value)")
        return self


async def check(connection: AsyncConnection, goal_id: str, body: CheckIn) -> Goal:
    goal = await one(connection, goal_id)
    if goal.status != "active":
        raise Conflict("esta meta está cerrada: reábrela para apuntar en ella")
    day = body.day or today()
    if day > today():
        raise Conflict("no se apunta un día que todavía no ha llegado")
    if day < goal.start_on:
        raise Conflict(f"la meta empieza el {goal.start_on:%d/%m/%Y}")
    if goal.kind == "dated" and goal.target is None:
        if body.done:
            return await close(connection, goal_id, "achieved")
        raise Conflict("un hito se da por hecho con done: true")
    if goal.kind == "dated" and body.value is None:
        raise Conflict("en una meta con fecha se apunta la cifra en la que vas (value)")
    if goal.period == "week" and body.value is None:
        raise Conflict("en una meta de total semanal se apunta cuánto se hizo ese día (value)")
    await connection.execute(
        text("""
            insert into goals.goals_goal_check (goal_id, day, done, value, note)
            values (cast(:goal as uuid), :day, :done, :value, :note)
            on conflict (goal_id, day) do update
            set done = excluded.done, value = excluded.value, note = excluded.note,
                created_at = now()
        """),
        {
            "goal": goal_id,
            "day": day,
            "done": body.done,
            "value": body.value,
            "note": (body.note or "").strip() or None,
        },
    )
    await settle(connection, [goal_id])
    return await one(connection, goal_id)


async def uncheck(connection: AsyncConnection, goal_id: str, day: date) -> Goal:
    await one(connection, goal_id)
    await connection.execute(
        text(
            "delete from goals.goals_goal_check where goal_id = cast(:goal as uuid) and day = :day"
        ),
        {"goal": goal_id, "day": day},
    )
    return await one(connection, goal_id)


CLOSE = text("""
    update goals.goals_goal
    set status = :status, closed_on = :on, closed_value = :value, featured = false,
        updated_at = now()
    where id = cast(:id as uuid)
""")


async def close(
    connection: AsyncConnection, goal_id: str, outcome: Literal["achieved", "abandoned"]
) -> Goal:
    goal = await one(connection, goal_id)
    if goal.status != "active":
        raise Conflict("esta meta ya está cerrada")
    await connection.execute(
        CLOSE, {"id": goal_id, "status": outcome, "on": today(), "value": goal.current}
    )
    closed_goal = await one(connection, goal_id)
    await _publish(connection, closed_goal, outcome)
    return closed_goal


async def reopen(connection: AsyncConnection, goal_id: str) -> Goal:
    goal = await one(connection, goal_id)
    if goal.status == "active":
        raise Conflict("esta meta no está cerrada")
    if goal.kind == "dated" and goal.due_on is not None and goal.due_on < today():
        raise Conflict("su fecha ya pasó: cambia la fecha límite para reabrirla")
    await connection.execute(
        text("""
            update goals.goals_goal
            set status = 'active', closed_on = null, closed_value = null, updated_at = now()
            where id = cast(:id as uuid)
        """),
        {"id": goal_id},
    )
    return await one(connection, goal_id)


async def settle(connection: AsyncConnection, ids: list[str] | None = None) -> list[Goal]:
    where, params = "g.status = 'active' and g.kind = 'dated'", {}
    if ids is not None:
        where += " and g.id = any(cast(:ids as uuid[]))"
        params["ids"] = ids
    finished: list[Goal] = []
    at = today()
    for goal in await _read(connection, where, params):
        if goal.target is not None and goal.reached:
            outcome = "achieved"
        elif goal.due_on is not None and goal.due_on < at:
            outcome = "missed"
        else:
            continue
        await connection.execute(
            CLOSE,
            {
                "id": goal.id,
                "status": outcome,
                "on": min(at, goal.due_on) if outcome == "missed" and goal.due_on else at,
                "value": goal.current,
            },
        )
        done = await one(connection, goal.id)
        await _publish(connection, done, outcome)
        finished.append(done)
    return finished


async def _publish(connection: AsyncConnection, goal: Goal, what: str) -> None:
    await enqueue(
        connection,
        "goal",
        {
            "goal_id": goal.id,
            "what": what,
            "title": goal.title,
            "kind": goal.kind,
            "category": goal.category,
            "metric_key": goal.metric.key if goal.metric else None,
            "target": goal.target,
            "due_on": goal.due_on,
            "status": goal.status,
            "closed_value": goal.closed_value,
        },
    )
