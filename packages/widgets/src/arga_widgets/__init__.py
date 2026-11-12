from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

State = Literal["ready", "empty", "error", "disconnected"]


class UnknownKind(ValueError):
    pass


class BadBody(ValueError):
    pass


class Body(BaseModel):
    model_config = ConfigDict(extra="forbid")

    detail: str | None = None


class Kpi(Body):
    value: float | str | None = None
    unit: str | None = None
    icon: str | None = None
    icon_hue: Annotated[int, Field(ge=1, le=8)] | None = None


class KpiDelta(Kpi):
    previous: float | None = None
    since: str | None = None
    good_when: Literal["up", "down", "neutral"] | None = None
    series: list[float] | None = None


class Chart(Kpi):
    series: list[float] | None = None


class Bars(Chart):
    labels: list[str] | None = None
    highlight: int | None = None


class Heatmap(Body):
    values: list[float] | None = None
    columns: int | None = None


class Progress(Body):
    value: float | None = None
    target: float | None = None
    unit: str | None = None
    label: str | None = None
    expected: float | None = None
    good_when: Literal["up", "down"] | None = None


class Ring(Progress):
    show: Literal["value", "percent"] | None = None


class Streak(Body):
    current: int | None = None
    best: int | None = None
    days: list[bool] | None = None
    label: str | None = None


class Stat(BaseModel):
    model_config = ConfigDict(extra="forbid")

    label: str
    value: float | str
    unit: str | None = None


class Stats(Body):
    stats: list[Stat] | None = None


class Row(BaseModel):
    model_config = ConfigDict(extra="forbid")

    label: str
    value: str
    tone: Literal["positive", "warning", "negative", "neutral"] | None = None


class Rows(Body):
    rows: list[Row] | None = None


class Entry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    start: str
    end: str | None = None
    all_day: bool | None = None
    title: str
    detail: str | None = None
    tone: Annotated[int, Field(ge=1, le=10)] | None = None


class Calendar(Body):
    marked: list[int] | None = None
    today: int | None = None
    entries: list[Entry] | None = None


class Agenda(Body):
    entries: list[Entry] | None = None


class Week(Body):
    entries: list[Entry] | None = None


class Event(BaseModel):
    model_config = ConfigDict(extra="forbid")

    at: str
    title: str
    detail: str | None = None


class UpNext(Body):
    events: list[Event] | None = None


class Action(BaseModel):
    model_config = ConfigDict(extra="forbid")

    label: str
    href: str
    icon: str | None = None


class Shortcuts(Body):
    actions: list[Action] | None = None


class TaskItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    title: str
    due: str | None = None
    overdue: bool | None = None
    done: bool | None = None
    detail: str | None = None
    hue: Annotated[int, Field(ge=1, le=8)] | None = None


class Tasks(Body):
    tasks: list[TaskItem] | None = None
    count: int | None = None
    checkable: bool | None = None


BODIES: dict[str, type[Body]] = {
    "kpi": Kpi,
    "kpi-delta": KpiDelta,
    "chart": Chart,
    "bars": Bars,
    "heatmap": Heatmap,
    "progress": Progress,
    "ring": Ring,
    "streak": Streak,
    "stats": Stats,
    "list": Rows,
    "calendar": Calendar,
    "upnext": UpNext,
    "shortcuts": Shortcuts,
    "agenda": Agenda,
    "week": Week,
    "tasks": Tasks,
}

REQUIRED: dict[str, tuple[str, ...]] = {
    "kpi": ("value",),
    "kpi-delta": ("value", "previous"),
    "chart": ("series",),
    "bars": ("series",),
    "heatmap": ("values",),
    "progress": ("value", "target"),
    "ring": ("value", "target"),
    "streak": ("current",),
    "stats": ("stats",),
    "list": ("rows",),
    "calendar": ("marked",),
    "upnext": ("events",),
    "shortcuts": ("actions",),
    "agenda": ("entries",),
    "week": ("entries",),
    "tasks": ("tasks",),
}

VERBS: dict[str, tuple[str, ...]] = {"tasks": ("complete", "reopen", "add")}


class Act(BaseModel):
    model_config = ConfigDict(extra="forbid")

    verb: Literal["complete", "reopen", "add"]
    id: Annotated[str, Field(min_length=1, max_length=200)]


def validate(kind: str, body: dict[str, Any], state: State = "ready") -> dict[str, Any]:
    model = BODIES.get(kind)
    if model is None:
        raise UnknownKind(f"'{kind}' no es un kind de la biblioteca: {', '.join(sorted(BODIES))}")

    try:
        model.model_validate(body)
    except ValidationError as error:
        raise BadBody(f"{kind}: {error}") from error

    if state == "ready":
        missing = [field for field in REQUIRED[kind] if body.get(field) is None]
        if missing:
            raise BadBody(
                f"{kind} con state 'ready' necesita {', '.join(missing)}. "
                "Si todavía no hay dato, el estado es 'empty'."
            )
    return body


def envelope(
    kind: str,
    state: State,
    body: dict[str, Any],
    uncertainty: dict[str, Any] | None = None,
) -> dict[str, Any]:
    sealed: dict[str, Any] = {
        "state": state,
        "updated_at": datetime.now(UTC).isoformat(),
        "body": validate(kind, body, state),
    }
    if uncertainty is not None:
        sealed["uncertainty"] = uncertainty
    return sealed


from arga_widgets.panel import BadPanel, Panel, panel, panels  # noqa: E402, F401
