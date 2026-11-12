from __future__ import annotations

import datetime as dt
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator
from sqlalchemy.ext.asyncio import AsyncConnection

from arga_recurrence import Rule, to_rrule
from goals import goals, metrics, tasks
from goals.common import Conflict, is_uuid, today

MODULE = "goals"
WRITE_ROLE = f"mod_{MODULE}"
READ_ROLE = f"mod_{MODULE}_read"


def role_for_scopes(scopes: set[str]) -> str | None:
    if f"{MODULE}:write" in scopes:
        return WRITE_ROLE
    if f"{MODULE}:read" in scopes:
        return READ_ROLE
    return None


def _task(task: tasks.Task) -> dict[str, Any]:
    return {
        "task_id": task.id,
        "title": task.title,
        "category": task.category,
        "due_on": task.due_on.isoformat() if task.due_on else None,
        "due_time": task.due_time.strftime("%H:%M") if task.due_time else None,
        "status": task.status,
        "repeats": task.repeats,
        "notes": task.notes,
        "shared": task.space_id is not None,
        "done_on": task.done_at.date().isoformat() if task.done_at else None,
    }


class GetCategories(BaseModel):
    pass


async def get_categories(connection: AsyncConnection, arguments: GetCategories) -> dict[str, Any]:
    return {
        "categories": [
            {
                "name": one.name,
                "pending": one.pending,
                "overdue": one.overdue,
                "shared": one.space_id is not None,
            }
            for one in await tasks.categories(connection)
        ]
    }


class FindTasks(BaseModel):
    state: Literal["pending", "done"] = "pending"
    category: str | None = Field(default=None, max_length=40, description="Por su nombre.")
    query: str | None = Field(
        default=None, max_length=80, description="Texto a buscar en el título y las notas."
    )
    due_until: dt.date | None = Field(
        default=None,
        description="Solo las pendientes con fecha hasta este día, incluido. Hoy, para lo de hoy "
        "y lo vencido.",
    )
    limit: int = Field(default=100, ge=1, le=300)


async def find_tasks(connection: AsyncConnection, arguments: FindTasks) -> dict[str, Any]:
    category_id = None
    if arguments.category:
        category_id = (await tasks.find_category(connection, arguments.category)).id
    if arguments.state == "done":
        found = await tasks.done(connection, category_id, arguments.limit)
        if arguments.query:
            wanted = arguments.query.casefold()
            found = [one for one in found if wanted in one.title.casefold()]
    else:
        found = await tasks.pending(connection, category_id, arguments.due_until, arguments.query)
    return {"today": today().isoformat(), "tasks": [_task(one) for one in found[: arguments.limit]]}


class AddTask(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    category: str = Field(
        min_length=1, max_length=40, description="El nombre de una categoría que ya existe."
    )
    due_on: dt.date | None = Field(default=None, description="Sin fecha si no se dice.")
    due_time: dt.time | None = Field(default=None, description="Solo si se dice una hora.")
    notes: str | None = Field(default=None, max_length=4000)
    repeat: Rule | None = Field(
        default=None,
        description="Si se repite. Necesita due_on, que es la primera vez. Al marcarla hecha nace "
        "la siguiente.",
    )


async def add_task(connection: AsyncConnection, arguments: AddTask) -> dict[str, Any]:
    await tasks.seed(connection)
    category = await tasks.find_category(connection, arguments.category)
    created = await tasks.create(
        connection,
        tasks.TaskIn(
            category_id=category.id,
            title=arguments.title,
            notes=arguments.notes,
            due_on=arguments.due_on,
            due_time=arguments.due_time,
            rule=to_rrule(arguments.repeat) if arguments.repeat else None,
        ),
    )
    return _task(created)


class UpdateTask(BaseModel):
    task_id: str
    title: str | None = Field(default=None, min_length=1, max_length=200)
    category: str | None = Field(default=None, max_length=40)
    due_on: dt.date | None = None
    due_time: dt.time | None = None
    notes: str | None = Field(default=None, max_length=4000)
    repeat: Rule | None = None

    @model_validator(mode="after")
    def _uuid(self) -> UpdateTask:
        if not is_uuid(self.task_id):
            raise ValueError("task_id es el id que devuelven find_tasks o add_task")
        return self


async def update_task(connection: AsyncConnection, arguments: UpdateTask) -> dict[str, Any]:
    given = arguments.model_fields_set
    patch: dict[str, Any] = {}
    if arguments.title is not None:
        patch["title"] = arguments.title
    if arguments.category:
        patch["category_id"] = (await tasks.find_category(connection, arguments.category)).id
    for field in ("due_on", "due_time", "notes"):
        if field in given:
            patch[field] = getattr(arguments, field)
    if "repeat" in given:
        patch["rule"] = to_rrule(arguments.repeat) if arguments.repeat else None
    changed = await tasks.update(connection, arguments.task_id, tasks.TaskPatch(**patch))
    return _task(changed)


class CompleteTask(BaseModel):
    task_id: str

    @model_validator(mode="after")
    def _uuid(self) -> CompleteTask:
        if not is_uuid(self.task_id):
            raise ValueError("task_id es el id que devuelven find_tasks o add_task")
        return self


async def complete_task(connection: AsyncConnection, arguments: CompleteTask) -> dict[str, Any]:
    result = await tasks.complete(connection, arguments.task_id)
    return {"done": _task(result.task), "next": _task(result.next) if result.next else None}


class AddCategory(BaseModel):
    name: str = Field(min_length=1, max_length=40)
    hue: int | None = Field(
        default=None,
        ge=1,
        le=8,
        description="Uno de los ocho tonos de arga. Sin él, el siguiente libre.",
    )


async def add_category(connection: AsyncConnection, arguments: AddCategory) -> dict[str, Any]:
    await tasks.seed(connection)
    existing = await tasks.categories(connection)
    used = {one.hue for one in existing}
    hue = arguments.hue or next((h for h in range(1, 9) if h not in used), len(existing) % 8 + 1)
    created = await tasks.create_category(
        connection, tasks.CategoryIn(name=arguments.name, hue=hue)
    )
    return {"name": created.name, "hue": created.hue}


def _goal(goal: goals.Goal) -> dict[str, Any]:
    said: dict[str, Any] = {
        "goal_id": goal.id,
        "title": goal.title,
        "category": goal.category,
        "kind": goal.kind,
        "status": goal.status,
        "metric": goal.metric.model_dump() if goal.metric else None,
        "direction": goal.direction,
        "target": goal.target,
        "note": goal.note,
        "featured": goal.featured,
    }
    if goal.kind == "periodic":
        said |= {
            "period": goal.period,
            "days_per_week": goal.days_per_week,
            "today_met": goal.today_met,
            "today_marked_by_hand": goal.today_manual,
            "this_week": {"done": goal.week_count, "of": goal.week_target, "met": goal.week_met},
            "streak": goal.streak,
            "streak_unit": goal.streak_unit,
            "constancy_4_weeks": round(goal.constancy, 3) if goal.constancy is not None else None,
        }
    else:
        said |= {
            "start_on": goal.start_on.isoformat(),
            "due_on": goal.due_on.isoformat() if goal.due_on else None,
            "days_left": goal.days_left,
            "start": goal.start,
            "current": goal.current,
            "last_data_on": goal.last_day.isoformat() if goal.last_day else None,
            "expected_today": goal.expected,
            "pace": goal.pace,
            "progress": round(goal.progress, 3) if goal.progress is not None else None,
            "projection": goal.projection,
            "projection_reached": goal.projection_reached,
        }
    if goal.status != "active":
        said |= {
            "closed_on": goal.closed_on.isoformat() if goal.closed_on else None,
            "closed_value": goal.closed_value,
        }
    return said


def _goal_id(value: str) -> str:
    if not is_uuid(value):
        raise ValueError("goal_id es el id que devuelven get_goals o create_goal")
    return value


async def _category_id(connection: AsyncConnection, name: str | None) -> str | None:
    if not name:
        return None
    return (await tasks.find_category(connection, name)).id


class GetGoals(BaseModel):
    state: Literal["active", "closed"] = "active"
    category: str | None = Field(default=None, max_length=40, description="Por su nombre.")


async def get_goals(connection: AsyncConnection, arguments: GetGoals) -> dict[str, Any]:
    if arguments.state == "closed":
        found = await goals.closed(connection)
    else:
        found = await goals.active(connection, await _category_id(connection, arguments.category))
    if arguments.category and arguments.state == "closed":
        wanted = arguments.category.casefold()
        found = [one for one in found if (one.category or "").casefold() == wanted]
    return {"today": today().isoformat(), "goals": [_goal(one) for one in found]}


class GetGoal(BaseModel):
    goal_id: str

    _check = field_validator("goal_id")(_goal_id)


async def get_goal(connection: AsyncConnection, arguments: GetGoal) -> dict[str, Any]:
    found = await goals.detail(connection, arguments.goal_id)
    history = [
        {
            "day": point.day.isoformat(),
            "value": point.value,
            "met": point.met,
            "by_hand": point.manual,
            "note": point.note,
        }
        for point in found.history
        if point.value is not None or point.manual or point.met
    ]
    return {"goal": _goal(found.goal), "history": history[-120:]}


class ListMetrics(BaseModel):
    query: str | None = Field(
        default=None, max_length=60, description="Texto a buscar en el nombre o la clave."
    )


async def list_metrics(connection: AsyncConnection, arguments: ListMetrics) -> dict[str, Any]:
    found = await metrics.available(connection)
    if arguments.query:
        wanted = arguments.query.casefold()
        found = [one for one in found if wanted in f"{one.label} {one.key}".casefold()]
    return {
        "metrics": [
            {
                "key": one.key,
                "label": one.label,
                "unit": one.unit,
                "kind": one.kind,
                "last_day": one.last_day.isoformat(),
                "last_value": one.last_value,
            }
            for one in found
        ]
    }


class CreateGoal(BaseModel):
    title: str = Field(min_length=1, max_length=120)
    kind: Literal["periodic", "dated"] = Field(
        description="periodic: se cumple cada día o cada semana. dated: llegar a algo en una fecha."
    )
    category: str | None = Field(default=None, max_length=40, description="Por su nombre.")
    metric_key: str | None = Field(
        default=None,
        max_length=160,
        description="La clave de una cifra de list_metrics. Sin ella, se apunta a mano.",
    )
    direction: Literal["at_least", "at_most"] = "at_least"
    target: float | None = Field(
        default=None,
        description="Periódica: la condición de cada día («8000» pasos) o el total semanal. Con "
        "fecha: la cifra a la que llegar. Nulo en una periódica que solo se marca o en un hito.",
    )
    period: Literal["day", "week"] | None = Field(
        default=None, description="Solo periódicas: day (días por semana) o week (total semanal)."
    )
    days_per_week: int | None = Field(default=None, ge=1, le=7, description="7 es diaria.")
    start_value: float | None = Field(
        default=None,
        description="Solo con fecha y a mano. Con cifra no se dice: es lo que valía la cifra el "
        "día que empieza, y lo pone KPIs.",
    )
    start_on: dt.date | None = Field(default=None, description="Por defecto, hoy.")
    due_on: dt.date | None = Field(default=None, description="Solo con fecha: la fecha límite.")
    note: str | None = Field(default=None, max_length=2000)
    featured: bool = Field(default=False, description="Sale en el widget «Meta destacada».")


STARTS_ITSELF = (
    "con cifra, el punto de partida no se dice: es lo que valía la cifra el día que empieza la "
    "meta (start_on), y lo pone KPIs. Quita start_value"
)


async def create_goal(connection: AsyncConnection, arguments: CreateGoal) -> dict[str, Any]:
    if arguments.metric_key and arguments.start_value is not None:
        raise Conflict(STARTS_ITSELF)
    await goals.seed(connection)
    fields = arguments.model_dump(exclude={"category"})
    created = await goals.create(
        connection,
        goals.GoalIn(**fields, category_id=await _category_id(connection, arguments.category)),
    )
    return _goal(created)


class UpdateGoal(BaseModel):
    goal_id: str
    title: str | None = Field(default=None, min_length=1, max_length=120)
    category: str | None = Field(default=None, max_length=40)
    metric_key: str | None = Field(default=None, max_length=160)
    direction: Literal["at_least", "at_most"] | None = None
    target: float | None = None
    period: Literal["day", "week"] | None = None
    days_per_week: int | None = Field(default=None, ge=1, le=7)
    start_value: float | None = None
    start_on: dt.date | None = None
    due_on: dt.date | None = None
    note: str | None = Field(default=None, max_length=2000)
    featured: bool | None = None

    _check = field_validator("goal_id")(_goal_id)


async def update_goal(connection: AsyncConnection, arguments: UpdateGoal) -> dict[str, Any]:
    given = arguments.model_fields_set - {"goal_id"}
    if "start_value" in given and arguments.start_value is not None:
        metric = (
            arguments.metric_key
            if "metric_key" in given
            else (await goals.one(connection, arguments.goal_id)).metric
        )
        if metric:
            raise Conflict(STARTS_ITSELF)
    patch: dict[str, Any] = {name: getattr(arguments, name) for name in given if name != "category"}
    if "category" in given:
        patch["category_id"] = await _category_id(connection, arguments.category)
    changed = await goals.update(connection, arguments.goal_id, goals.GoalPatch(**patch))
    return _goal(changed)


class CheckGoal(BaseModel):
    goal_id: str
    day: dt.date | None = Field(default=None, description="Por defecto, hoy.")
    done: bool | None = Field(
        default=None,
        description="Periódica diaria: hecho o no ese día. Hito: true lo da por cumplido.",
    )
    value: float | None = Field(
        default=None,
        description="La cifra de ese día: dónde vas en una con fecha, o cuánto en un total "
        "semanal.",
    )
    note: str | None = Field(default=None, max_length=500)

    _check = field_validator("goal_id")(_goal_id)


async def check_goal(connection: AsyncConnection, arguments: CheckGoal) -> dict[str, Any]:
    marked = await goals.check(
        connection,
        arguments.goal_id,
        goals.CheckIn(
            day=arguments.day, done=arguments.done, value=arguments.value, note=arguments.note
        ),
    )
    return _goal(marked)


class CloseGoal(BaseModel):
    goal_id: str
    outcome: Literal["achieved", "abandoned", "reopen"] = Field(
        description="achieved: cumplida antes de tiempo. abandoned: se deja. reopen: vuelve a "
        "estar activa."
    )

    _check = field_validator("goal_id")(_goal_id)


async def close_goal(connection: AsyncConnection, arguments: CloseGoal) -> dict[str, Any]:
    if arguments.outcome == "reopen":
        return _goal(await goals.reopen(connection, arguments.goal_id))
    return _goal(await goals.close(connection, arguments.goal_id, arguments.outcome))


class RecordPastGoal(BaseModel):
    title: str = Field(min_length=1, max_length=120)
    category: str | None = Field(default=None, description="El nombre de una categoría.")
    start_on: dt.date = Field(description="Cuándo te lo propusiste.")
    due_on: dt.date = Field(description="Para cuándo era.")
    outcome: Literal["achieved", "missed", "abandoned"]
    closed_on: dt.date | None = Field(default=None, description="Por defecto, su fecha límite.")
    target: float | None = Field(default=None, description="La cifra a la que había que llegar.")
    start_value: float | None = None
    closed_value: float | None = Field(default=None, description="La cifra en la que se quedó.")
    direction: Literal["at_least", "at_most"] = "at_least"
    note: str | None = Field(default=None, max_length=2000)


async def record_past_goal(
    connection: AsyncConnection, arguments: RecordPastGoal
) -> dict[str, Any]:
    fields = arguments.model_dump(exclude={"category"})
    fields["category_id"] = await _category_id(connection, arguments.category)
    return _goal(await goals.record_past(connection, goals.PastGoalIn(**fields)))


class DeleteGoal(BaseModel):
    goal_id: str
    title: str = Field(
        min_length=1, max_length=120, description="El título exacto de la meta, para confirmar."
    )

    _check = field_validator("goal_id")(_goal_id)


async def delete_goal(connection: AsyncConnection, arguments: DeleteGoal) -> dict[str, Any]:
    goal = await goals.one(connection, arguments.goal_id)
    if goal.title != arguments.title.strip():
        raise Conflict(
            f"el título no coincide: la meta se llama '{goal.title}'. No se ha borrado nada"
        )
    await goals.remove(connection, arguments.goal_id)
    return {"deleted": goal.title}


@dataclass(frozen=True)
class Tool:
    arguments: type[BaseModel]
    run: Callable[..., Awaitable[dict[str, Any]]]


TOOLS: dict[str, Tool] = {
    "get_categories": Tool(GetCategories, get_categories),
    "find_tasks": Tool(FindTasks, find_tasks),
    "add_task": Tool(AddTask, add_task),
    "update_task": Tool(UpdateTask, update_task),
    "complete_task": Tool(CompleteTask, complete_task),
    "add_category": Tool(AddCategory, add_category),
    "get_goals": Tool(GetGoals, get_goals),
    "get_goal": Tool(GetGoal, get_goal),
    "list_metrics": Tool(ListMetrics, list_metrics),
    "create_goal": Tool(CreateGoal, create_goal),
    "update_goal": Tool(UpdateGoal, update_goal),
    "check_goal": Tool(CheckGoal, check_goal),
    "close_goal": Tool(CloseGoal, close_goal),
    "record_past_goal": Tool(RecordPastGoal, record_past_goal),
    "delete_goal": Tool(DeleteGoal, delete_goal),
}
