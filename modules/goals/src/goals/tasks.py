from __future__ import annotations

from datetime import date, datetime, time, timedelta
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from arga_agenda import KEY, dated, uid
from arga_recurrence import describe, next_occurrence, parse, to_rrule
from goals import figures
from goals.common import (
    MADRID,
    TZ,
    Conflict,
    NotFound,
    enqueue,
    fold,
    is_uuid,
    me,
    now,
    today,
)

Status = Literal["overdue", "today", "upcoming", "someday", "done"]

SEEDED: tuple[tuple[str, int], ...] = (("Trabajo", 1), ("Casa", 2), ("Personal", 5))


class Category(BaseModel):
    id: str
    name: str
    hue: int
    position: int
    space_id: str | None
    pending: int
    overdue: int
    goals: int = 0


class Task(BaseModel):
    id: str
    category_id: str
    category: str
    hue: int
    title: str
    notes: str | None
    due_on: date | None
    due_time: time | None
    rule: str | None
    repeats: str | None
    status: Status
    done_at: datetime | None
    done_by_me: bool | None
    space_id: str | None


def _name(value: str) -> str:
    value = " ".join(value.split())
    if not value:
        raise ValueError("el nombre no puede ir vacío")
    return value


class CategoryIn(BaseModel):
    name: str = Field(min_length=1, max_length=40)
    hue: int = Field(default=1, ge=1, le=8)

    _clean = field_validator("name")(_name)


class CategoryPatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=40)
    hue: int | None = Field(default=None, ge=1, le=8)

    @field_validator("name")
    @classmethod
    def _clean(cls, value: str | None) -> str | None:
        return None if value is None else _name(value)


class OrderIn(BaseModel):
    ids: list[str] = Field(min_length=1, max_length=200)


class SpaceIn(BaseModel):
    space_id: str | None = None


CATEGORIES = text("""
    select c.id::text as id, c.name, c.hue, c.position, c.space_id::text as space_id,
           count(t.id) filter (where t.done_at is null) as pending,
           count(t.id) filter (where t.done_at is null and t.due_on < :today) as overdue,
           (select count(*) from goals.goals_goal g
            where g.category_id = c.id and g.status = 'active') as goals
    from goals.goals_category c
    left join goals.goals_task t on t.category_id = c.id
    group by c.id
    order by c.position, c.created_at
""")


async def seed(connection: AsyncConnection) -> None:
    first = await connection.scalar(
        text(
            "insert into goals.goals_person default values "
            "on conflict (user_id) do nothing returning user_id"
        )
    )
    if first is None:
        return
    for position, (name, hue) in enumerate(SEEDED, start=1):
        await connection.execute(
            text(
                "insert into goals.goals_category (name, hue, position) "
                "values (:name, :hue, :position)"
            ),
            {"name": name, "hue": hue, "position": position},
        )


async def categories(connection: AsyncConnection) -> list[Category]:
    rows = await connection.execute(CATEGORIES, {"today": today()})
    return [Category(**row._mapping) for row in rows]


async def category(connection: AsyncConnection, category_id: str) -> Category:
    for one in await categories(connection):
        if one.id == category_id:
            return one
    raise NotFound(f"categoría {category_id}")


async def find_category(connection: AsyncConnection, name: str) -> Category:
    all_of_them = await categories(connection)
    wanted = fold(name)
    for one in all_of_them:
        if fold(one.name) == wanted:
            return one
    known = ", ".join(one.name for one in all_of_them) or "ninguna"
    raise NotFound(f"no hay una categoría '{name}'. Las que hay: {known}")


async def create_category(connection: AsyncConnection, body: CategoryIn) -> Category:
    taken = {fold(one.name) for one in await categories(connection)}
    if fold(body.name) in taken:
        raise Conflict(f"ya tienes una categoría '{body.name}'")
    new = await connection.scalar(
        text("""
            insert into goals.goals_category (name, hue, position)
            values (:name, :hue,
                    (select coalesce(max(position), 0) + 1 from goals.goals_category))
            returning id::text
        """),
        {"name": body.name, "hue": body.hue},
    )
    return await category(connection, new)


async def update_category(
    connection: AsyncConnection, category_id: str, body: CategoryPatch
) -> Category:
    current = await category(connection, category_id)
    if body.name is not None and fold(body.name) != fold(current.name):
        taken = {fold(one.name) for one in await categories(connection) if one.id != category_id}
        if fold(body.name) in taken:
            raise Conflict(f"ya tienes una categoría '{body.name}'")
    await connection.execute(
        text(
            "update goals.goals_category set name = :name, hue = :hue where id = cast(:id as uuid)"
        ),
        {
            "id": category_id,
            "name": body.name if body.name is not None else current.name,
            "hue": body.hue if body.hue is not None else current.hue,
        },
    )
    renamed = await category(connection, category_id)
    if renamed.name != current.name:
        for task_id in await _dated_pending(
            connection, "category_id = cast(:id as uuid)", category_id
        ):
            await publish(connection, await one(connection, task_id))
    return renamed


async def order(connection: AsyncConnection, body: OrderIn) -> list[Category]:
    known = {one.id for one in await categories(connection)}
    if set(body.ids) != known or len(body.ids) != len(known):
        raise Conflict("el orden tiene que llevar todas tus categorías, una vez cada una")
    for position, category_id in enumerate(body.ids, start=1):
        await connection.execute(
            text(
                "update goals.goals_category set position = :position where id = cast(:id as uuid)"
            ),
            {"id": category_id, "position": position},
        )
    return await categories(connection)


async def remove_category(connection: AsyncConnection, category_id: str) -> None:
    await category(connection, category_id)
    for task_id in await _dated_pending(connection, "category_id = cast(:id as uuid)", category_id):
        await publish(connection, await one(connection, task_id), gone=True)
    await connection.execute(
        text("delete from goals.goals_category where id = cast(:id as uuid)"),
        {"id": category_id},
    )


async def share_category(
    connection: AsyncConnection, category_id: str, space_id: str | None
) -> Category:
    await category(connection, category_id)
    await connection.execute(
        text(
            "update goals.goals_task set space_id = cast(:space as uuid) "
            "where category_id = cast(:id as uuid)"
        ),
        {"id": category_id, "space": space_id},
    )
    await connection.execute(
        text(
            "update goals.goals_category set space_id = cast(:space as uuid) "
            "where id = cast(:id as uuid)"
        ),
        {"id": category_id, "space": space_id},
    )
    return await category(connection, category_id)


def status(
    due_on: date | None, due_time: time | None, done_at: datetime | None, at: datetime
) -> Status:
    if done_at is not None:
        return "done"
    if due_on is None:
        return "someday"
    day = at.date()
    if due_on < day:
        return "overdue"
    if due_on == day:
        if due_time is not None and due_time < at.time().replace(tzinfo=None):
            return "overdue"
        return "today"
    return "upcoming"


def repeats(rule: str | None) -> str | None:
    return describe(parse(rule)) if rule else None


SELECT = """
    select t.id::text as id, t.category_id::text as category_id, c.name as category, c.hue,
           t.title, t.notes, t.due_on, t.due_time, t.rule, t.series_on, t.done_at,
           t.done_by::text as done_by, t.space_id::text as space_id
    from goals.goals_task t
    join goals.goals_category c on c.id = t.category_id
"""

ONE = text(SELECT + " where t.id = cast(:id as uuid)")


def _task(row: Any, at: datetime) -> Task:
    return Task(
        id=row.id,
        category_id=row.category_id,
        category=row.category,
        hue=row.hue,
        title=row.title,
        notes=row.notes,
        due_on=row.due_on,
        due_time=row.due_time,
        rule=row.rule,
        repeats=repeats(row.rule),
        status=status(row.due_on, row.due_time, row.done_at, at),
        done_at=row.done_at,
        done_by_me=None if row.done_by is None else row.done_by == me(),
        space_id=row.space_id,
    )


async def one(connection: AsyncConnection, task_id: str) -> Task:
    row = (await connection.execute(ONE, {"id": task_id})).first()
    if row is None:
        raise NotFound(f"tarea {task_id}")
    return _task(row, now())


async def pending(
    connection: AsyncConnection,
    category_id: str | None = None,
    until: date | None = None,
    query: str | None = None,
) -> list[Task]:
    where = ["t.done_at is null"]
    params: dict[str, Any] = {}
    if category_id:
        where.append("t.category_id = cast(:category as uuid)")
        params["category"] = category_id
    if until:
        where.append("t.due_on <= :until")
        params["until"] = until
    rows = await connection.execute(
        text(
            SELECT
            + f" where {' and '.join(where)} "
            + "order by t.due_on nulls last, t.due_time nulls first, c.position, t.created_at"
        ),
        params,
    )
    at = now()
    found = [_task(row, at) for row in rows]
    if query:
        wanted = fold(query)
        found = [task for task in found if wanted in fold(f"{task.title} {task.notes or ''}")]
    return found


async def done(
    connection: AsyncConnection, category_id: str | None = None, limit: int = 100
) -> list[Task]:
    where = "t.done_at is not null"
    params: dict[str, Any] = {"limit": limit}
    if category_id:
        where += " and t.category_id = cast(:category as uuid)"
        params["category"] = category_id
    rows = await connection.execute(
        text(SELECT + f" where {where} order by t.done_at desc limit :limit"), params
    )
    at = now()
    return [_task(row, at) for row in rows]


async def _dated_pending(connection: AsyncConnection, where: str, value: str) -> list[str]:
    ids = await connection.scalars(
        text(
            f"select id::text from goals.goals_task "
            f"where done_at is null and due_on is not null and {where}"
        ),
        {"id": value},
    )
    return list(ids.all())


async def publish(
    connection: AsyncConnection,
    task: Task,
    *,
    gone: bool = False,
    was_on: date | None = None,
) -> None:
    day = task.due_on or was_on
    if day is None:
        return
    cancelled = gone or task.done_at is not None or task.due_on is None
    if task.due_time is not None and task.due_on is not None:
        start: str = datetime.combine(task.due_on, task.due_time, MADRID).isoformat()
        end, all_day = start, False
    else:
        start, end, all_day = day.isoformat(), (day + timedelta(days=1)).isoformat(), True
    agenda = dated(
        uid=uid("goals", "task", task.id),
        title=task.title,
        start=start,
        end=end,
        all_day=all_day,
        tz=TZ,
        status="cancelled" if cancelled else "confirmed",
        href=f"/goals/tarea/{task.id}",
    )
    await enqueue(
        connection,
        "task",
        {
            "task_id": task.id,
            "category_id": task.category_id,
            "title": task.title,
            "due_on": task.due_on,
            "done": task.done_at is not None,
            KEY: agenda,
        },
    )


class TaskIn(BaseModel):
    category_id: str
    title: str = Field(min_length=1, max_length=200)
    notes: str | None = Field(default=None, max_length=4000)
    due_on: date | None = None
    due_time: time | None = None
    rule: str | None = Field(default=None, max_length=300)


class TaskPatch(BaseModel):
    category_id: str | None = None
    title: str | None = Field(default=None, min_length=1, max_length=200)
    notes: str | None = Field(default=None, max_length=4000)
    due_on: date | None = None
    due_time: time | None = None
    rule: str | None = Field(default=None, max_length=300)


def _clean_title(value: str) -> str:
    value = " ".join(value.split())
    if not value:
        raise Conflict("la tarea necesita un título")
    return value


def _normal_rule(rule: str | None) -> str | None:
    if not rule:
        return None
    try:
        return to_rrule(parse(rule))
    except ValueError as error:
        raise Conflict(f"esa repetición no se entiende: {error}") from error


def _check_shape(due_on: date | None, due_time: time | None, rule: str | None) -> None:
    if due_time is not None and due_on is None:
        raise Conflict("una hora va con su día: pon también la fecha")
    if rule is not None and due_on is None:
        raise Conflict("una tarea que se repite necesita la fecha de la primera vez")


async def _space_of(connection: AsyncConnection, category_id: str) -> str | None:
    if not is_uuid(category_id):
        raise NotFound(f"categoría {category_id!r}")
    found = (
        await connection.execute(
            text(
                "select space_id::text as space_id from goals.goals_category "
                "where id = cast(:id as uuid)"
            ),
            {"id": category_id},
        )
    ).first()
    if found is None:
        raise NotFound(f"categoría {category_id}")
    return found.space_id


INSERT = text("""
    insert into goals.goals_task
        (category_id, title, notes, due_on, due_time, rule, series_on, previous_id, space_id)
    values (cast(:category as uuid), :title, :notes, :due_on, :due_time, :rule, :series_on,
            cast(:previous as uuid), cast(:space as uuid))
    returning id::text
""")


async def create(connection: AsyncConnection, body: TaskIn) -> Task:
    rule = _normal_rule(body.rule)
    _check_shape(body.due_on, body.due_time, rule)
    space = await _space_of(connection, body.category_id)
    task_id = await connection.scalar(
        INSERT,
        {
            "category": body.category_id,
            "title": _clean_title(body.title),
            "notes": (body.notes or "").strip() or None,
            "due_on": body.due_on,
            "due_time": body.due_time,
            "rule": rule,
            "series_on": body.due_on if rule else None,
            "previous": None,
            "space": space,
        },
    )
    created = await one(connection, task_id)
    await publish(connection, created)
    return created


async def update(connection: AsyncConnection, task_id: str, body: TaskPatch) -> Task:
    current = await one(connection, task_id)
    given = body.model_fields_set
    category_id = body.category_id if body.category_id else current.category_id
    due_on = body.due_on if "due_on" in given else current.due_on
    due_time = body.due_time if "due_time" in given else current.due_time
    rule = _normal_rule(body.rule) if "rule" in given else current.rule
    _check_shape(due_on, due_time, rule)
    series = await connection.scalar(
        text("select series_on from goals.goals_task where id = cast(:id as uuid)"),
        {"id": task_id},
    )
    if rule is None:
        series = None
    elif rule != current.rule or due_on != current.due_on or series is None:
        series = due_on
    notes = body.notes if "notes" in given else current.notes
    await connection.execute(
        text("""
            update goals.goals_task
            set category_id = cast(:category as uuid), title = :title, notes = :notes,
                due_on = :due_on, due_time = :due_time, rule = :rule, series_on = :series_on,
                space_id = cast(:space as uuid), updated_at = now()
            where id = cast(:id as uuid)
        """),
        {
            "id": task_id,
            "category": category_id,
            "title": _clean_title(body.title) if body.title is not None else current.title,
            "notes": (notes or "").strip() or None,
            "due_on": due_on,
            "due_time": due_time,
            "rule": rule,
            "series_on": series,
            "space": await _space_of(connection, category_id),
        },
    )
    changed = await one(connection, task_id)
    await publish(connection, changed, was_on=current.due_on)
    return changed


async def remove(connection: AsyncConnection, task_id: str) -> None:
    current = await one(connection, task_id)
    await publish(connection, current, gone=True)
    await connection.execute(
        text("delete from goals.goals_task where id = cast(:id as uuid)"), {"id": task_id}
    )


class Completed(BaseModel):
    task: Task
    next: Task | None


async def complete(connection: AsyncConnection, task_id: str) -> Completed:
    current = await one(connection, task_id)
    if current.done_at is not None:
        raise Conflict("esta tarea ya está hecha")
    await connection.execute(
        text("""
            update goals.goals_task
            set done_at = now(), done_by = cast(:me as uuid), updated_at = now()
            where id = cast(:id as uuid)
        """),
        {"id": task_id, "me": me()},
    )
    finished = await one(connection, task_id)
    await publish(connection, finished)
    await figures.publish_day(connection, today())

    following = None
    if current.rule and current.due_on:
        series_on = await connection.scalar(
            text("select series_on from goals.goals_task where id = cast(:id as uuid)"),
            {"id": task_id},
        )
        day = next_occurrence(
            parse(current.rule), series_on or current.due_on, current.due_on + timedelta(days=1)
        )
        if day is not None:
            next_id = await connection.scalar(
                INSERT,
                {
                    "category": current.category_id,
                    "title": current.title,
                    "notes": current.notes,
                    "due_on": day,
                    "due_time": current.due_time,
                    "rule": current.rule,
                    "series_on": series_on or current.due_on,
                    "previous": task_id,
                    "space": current.space_id,
                },
            )
            following = await one(connection, next_id)
            await publish(connection, following)
    return Completed(task=finished, next=following)


async def undo(connection: AsyncConnection, task_id: str) -> Task:
    current = await one(connection, task_id)
    if current.done_at is None:
        raise Conflict("esta tarea no está hecha: no hay nada que deshacer")
    following = (
        await connection.execute(
            text(SELECT + " where t.previous_id = cast(:id as uuid)"), {"id": task_id}
        )
    ).first()
    if following is not None:
        if following.done_at is not None:
            raise Conflict("la siguiente de esta serie ya está hecha: deshaz esa primero")
        await publish(connection, _task(following, now()), gone=True)
        await connection.execute(
            text("delete from goals.goals_task where id = cast(:id as uuid)"),
            {"id": following.id},
        )
    await connection.execute(
        text("""
            update goals.goals_task set done_at = null, done_by = null, updated_at = now()
            where id = cast(:id as uuid)
        """),
        {"id": task_id},
    )
    back = await one(connection, task_id)
    await publish(connection, back)
    if current.done_at is not None and current.done_by_me:
        await figures.publish_day(connection, current.done_at.astimezone(MADRID).date())
    return back
