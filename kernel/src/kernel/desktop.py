from __future__ import annotations

import json
from datetime import datetime
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field, ValidationError, model_validator
from sqlalchemy import text

from arga_tenancy import CURRENT_USER_SQL, require_person
from kernel.db import engine
from kernel.subject import SUBJECT_HEADER, subject_of
from kernel.ui import BREAKPOINTS, FALLBACK_SIZE, SIZE_PATTERN, SIZES, Breakpoint
from kernel.widgets import BY_ID, KERNEL

router = APIRouter(tags=["ui"])

Device = Literal["mobile", "desktop"]
DEVICES: tuple[Device, ...] = ("mobile", "desktop")

Column = Annotated[int, Field(ge=0, le=11)]
Row = Annotated[int, Field(ge=0, le=499)]
Cell = tuple[Column, Row]
Placements = dict[Breakpoint, dict[str, dict[str, Cell]]]


class DeskItem(BaseModel):
    instance_id: str = Field(min_length=1, max_length=128)
    source: str
    widget: str
    size: Annotated[str, Field(pattern=SIZE_PATTERN)]
    option: str | None = Field(default=None, max_length=200)


class DeskPage(BaseModel):
    id: str = Field(min_length=1, max_length=64)
    items: list[DeskItem] = []


class Desktop(BaseModel):
    pages: list[DeskPage]
    placements: Placements = {}
    updated_at: datetime | None = None
    default: bool = False


class DesktopWrite(BaseModel):
    pages: list[DeskPage]
    placements: Placements = {}
    updated_at: datetime | None = None

    @model_validator(mode="after")
    def one_of_each(self) -> DesktopWrite:
        pages = [page.id for page in self.pages]
        if len(pages) != len(set(pages)):
            raise ValueError("two screens share an id")
        instances = [item.instance_id for page in self.pages for item in page.items]
        if len(instances) != len(set(instances)):
            raise ValueError("two widgets share an instance_id")
        return self


DEFAULT: tuple[tuple[str, tuple[tuple[str, str], ...]], ...] = (
    ("hoy", (("events", "2x2"), ("entities", "2x2"), ("events_trend", "4x2"))),
    (
        "actividad",
        (("events_by_weekday", "4x2"), ("activity", "4x2"), ("entities_by_volume", "4x2")),
    ),
    ("sistema", (("version", "2x2"),)),
)


Starting = tuple[tuple[str, tuple[tuple[str, str, str, str | None], ...]], ...]

STARTING: dict[Device, Starting] = {
    "mobile": (
        (
            "hoy",
            (
                ("panel", "day", "4x4", None),
                ("goals", "overdue", "2x1", None),
                ("planner", "upnext", "2x1", None),
                ("goals", "upcoming", "4x2", None),
                ("planner", "week", "4x2", None),
            ),
        ),
        (
            "salud",
            (
                ("vitals", "readiness", "2x2", None),
                ("vitals", "sleep_score", "2x2", None),
                ("macros", "macros_today", "4x2", None),
                ("macros", "log", "2x1", None),
                ("vitals", "steps_today", "2x1", None),
                ("training", "next", "4x1", None),
                ("panel", "health", "4x4", None),
                ("vitals", "weight", "2x2", None),
                ("training", "week", "2x2", None),
            ),
        ),
        (
            "dinero",
            (
                ("money", "networth", "4x2", None),
                ("money", "liquid", "2x1", None),
                ("money", "emergency", "2x1", None),
                ("panel", "money", "4x4", None),
            ),
        ),
        (
            "mas",
            (
                ("shopping", "list", "4x2", None),
                ("study", "upnext", "2x2", None),
                ("travel", "next_trip", "4x2", None),
                ("outings", "weekend", "2x2", None),
                ("library", "reading", "2x2", None),
                ("insights", "latest", "4x2", None),
            ),
        ),
    ),
    "desktop": (
        (
            "hoy",
            (
                ("panel", "day", "4x6", None),
                ("planner", "week", "4x2", None),
                ("goals", "upcoming", "4x4", None),
                ("goals", "overdue", "2x2", None),
                ("goals", "goal", "2x2", None),
            ),
        ),
        (
            "salud",
            (
                ("panel", "health", "4x6", None),
                ("macros", "today", "2x2", None),
                ("macros", "log", "2x1", None),
                ("vitals", "sleep_week", "4x2", None),
                ("vitals", "steps_today", "2x1", None),
                ("macros", "macros_today", "4x2", None),
                ("vitals", "weight", "4x2", None),
                ("macros", "week_short", "4x2", None),
                ("vitals", "training_week", "4x2", None),
            ),
        ),
        (
            "dinero",
            (
                ("panel", "money", "4x6", None),
                ("money", "networth", "4x2", None),
                ("money", "expense", "4x2", None),
                ("money", "liquid", "2x1", None),
                ("money", "emergency", "2x1", None),
                ("money", "cash", "2x1", None),
                ("money", "shared", "2x1", None),
                ("money", "basic", "4x2", None),
            ),
        ),
        (
            "mas",
            (
                ("panel", "home", "4x6", None),
                ("panel", "leisure", "4x6", None),
                ("panel", "work", "4x6", None),
            ),
        ),
    ),
}

PANEL_APPS: dict[str, tuple[str, ...]] = {
    "day": ("planner", "goals"),
    "money": ("money",),
    "health": ("vitals", "training", "macros"),
    "work": ("study",),
    "home": ("shopping", "recipes"),
    "leisure": ("travel", "outings", "library"),
    "mind": ("notebook", "insights"),
}

AVAILABLE = text("""
    select m.id as module, w.value->>'id' as id
    from kernel.modules m
    cross join lateral jsonb_array_elements(m.manifest->'ui'->'widgets') as w
    where m.enabled
""")


async def available(connection: Any) -> set[tuple[str, str]]:
    return {(row.module, row.id) for row in await connection.execute(AVAILABLE)}


def _present(source: str, widget: str, option: str | None, installed: set[tuple[str, str]]) -> bool:
    if source != "panel":
        return (source, widget) in installed
    apps = {module for module, _ in installed}
    if option:
        return option.split(".", 1)[0] in apps
    return any(app in apps for app in PANEL_APPS.get(widget, ()))


def default_desktop(
    installed: set[tuple[str, str]] | None = None, device: Device = "mobile"
) -> Desktop:
    have = installed or set()
    pages = [
        DeskPage(
            id=name,
            items=[
                DeskItem(
                    instance_id="-".join(
                        part
                        for part in ("por-defecto", device, name, source, widget, option)
                        if part
                    ),
                    source=source,
                    widget=widget,
                    size=size,
                    option=option,
                )
                for source, widget, size, option in placed
                if _present(source, widget, option, have)
            ],
        )
        for name, placed in STARTING[device]
    ]
    pages = [page for page in pages if page.items]
    if pages:
        return Desktop(pages=pages, default=True)
    return Desktop(
        pages=[
            DeskPage(
                id=name,
                items=[
                    DeskItem(
                        instance_id=f"por-defecto-{name}-{widget}",
                        source="kernel",
                        widget=widget,
                        size=size,
                    )
                    for widget, size in placed
                ],
            )
            for name, placed in DEFAULT
        ],
        default=True,
    )


def tolerated_desktop(pages: Any, placements: Any) -> tuple[list[DeskPage], Placements]:
    kept: list[DeskPage] = []
    seen: set[str] = set()
    for raw in pages or []:
        if not isinstance(raw, dict) or not isinstance(raw.get("id"), str) or not raw["id"]:
            continue
        items: list[DeskItem] = []
        for entry in raw.get("items") or []:
            if not isinstance(entry, dict):
                continue
            candidate = {**entry, "size": entry.get("size")}
            if candidate["size"] not in SIZES:
                candidate["size"] = FALLBACK_SIZE
            try:
                item = DeskItem.model_validate(candidate)
            except ValidationError:
                continue
            if item.instance_id in seen or (item.source == KERNEL and item.widget not in BY_ID):
                continue
            seen.add(item.instance_id)
            items.append(item)
        kept.append(DeskPage(id=raw["id"], items=items))
    return kept, pruned(kept, placements)


def pruned(pages: list[DeskPage], placements: Any) -> Placements:
    present = {page.id: {item.instance_id for item in page.items} for page in pages}
    result: Placements = {}
    if not isinstance(placements, dict):
        return result
    for breakpoint in BREAKPOINTS:
        by_page = placements.get(breakpoint)
        if not isinstance(by_page, dict):
            continue
        cells: dict[str, dict[str, Cell]] = {}
        for page_id, by_item in by_page.items():
            if page_id not in present or not isinstance(by_item, dict):
                continue
            kept = {}
            for instance_id, cell in by_item.items():
                if instance_id not in present[page_id]:
                    continue
                if (
                    isinstance(cell, list | tuple)
                    and len(cell) == 2
                    and all(isinstance(n, int) and not isinstance(n, bool) for n in cell)
                    and 0 <= cell[0] <= 11
                    and 0 <= cell[1] <= 499
                ):
                    kept[instance_id] = (cell[0], cell[1])
            if kept:
                cells[page_id] = kept
        if cells:
            result[breakpoint] = cells
    return result


READ_DEVICE_DESKTOPS = text(f"""
    select device, pages, placements, updated_at
    from kernel.ui_device_desktops
    where user_id = {CURRENT_USER_SQL}
""")

WRITE_DEVICE_DESKTOP = text("""
    insert into kernel.ui_device_desktops (device, pages, placements, updated_at)
    values (:device, cast(:pages as jsonb), cast(:placements as jsonb), now())
    on conflict (user_id, device) do update
    set pages = excluded.pages, placements = excluded.placements, updated_at = now()
    where ui_device_desktops.updated_at
        = coalesce(cast(:expected as timestamptz), ui_device_desktops.updated_at)
    returning updated_at
""")

CURRENT_DEVICE_DESKTOP = text(f"""
    select updated_at from kernel.ui_device_desktops
    where user_id = {CURRENT_USER_SQL} and device = :device
""")


class Desktops(BaseModel):
    mobile: Desktop
    desktop: Desktop


@router.get("/ui/desktops")
async def read_desktops(
    subject: Annotated[str | None, Header(alias=SUBJECT_HEADER)] = None,
) -> Desktops:
    subject_of(subject)
    async with engine().connect() as connection:
        rows = {row.device: row for row in (await connection.execute(READ_DEVICE_DESKTOPS)).all()}
        installed = None if len(rows) == len(DEVICES) else await available(connection)

    desktops: dict[str, Desktop] = {}
    for device in DEVICES:
        stored = rows.get(device)
        if stored is None:
            desktops[device] = default_desktop(installed, device)
            continue
        pages, placements = tolerated_desktop(stored.pages, stored.placements)
        desktops[device] = Desktop(pages=pages, placements=placements, updated_at=stored.updated_at)
    return Desktops(**desktops)


@router.get("/ui/desktops/starting")
async def read_starting_desktops(
    subject: Annotated[str | None, Header(alias=SUBJECT_HEADER)] = None,
) -> Desktops:
    subject_of(subject)
    async with engine().connect() as connection:
        installed = await available(connection)
    return Desktops(**{device: default_desktop(installed, device) for device in DEVICES})


@router.put("/ui/desktops/{device}")
async def write_device_desktop(
    device: Device,
    desktop: DesktopWrite,
    subject: Annotated[str | None, Header(alias=SUBJECT_HEADER)] = None,
) -> Desktop:
    require_person()
    subject_of(subject)
    placements = pruned(desktop.pages, json.loads(json.dumps(desktop.placements)))
    parameters = {
        "device": device,
        "pages": json.dumps([page.model_dump() for page in desktop.pages]),
        "placements": json.dumps(placements),
        "expected": desktop.updated_at,
    }

    async with engine().begin() as connection:
        written = await connection.scalar(WRITE_DEVICE_DESKTOP, parameters)
        if written is None:
            current = await connection.scalar(CURRENT_DEVICE_DESKTOP, {"device": device})
            raise HTTPException(
                status_code=409,
                detail=(
                    f"the {device} desktop changed somewhere else at {current}; read it again "
                    f"before writing, or the other device's edit is lost"
                ),
            )

    return Desktop(pages=desktop.pages, placements=placements, updated_at=written)
