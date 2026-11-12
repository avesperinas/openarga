from __future__ import annotations

from typing import Annotated, Literal

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field, ValidationError
from sqlalchemy import text

from arga_tenancy import require_person
from kernel.db import engine
from kernel.subject import SUBJECT_HEADER, subject_of
from kernel.widgets import BY_ID, CATALOGUE, KERNEL, KINDS, LIST_LIKE, RENDERERS

router = APIRouter(tags=["ui"])

Breakpoint = Literal["mobile", "tablet", "desktop"]
BREAKPOINTS: tuple[Breakpoint, ...] = ("mobile", "tablet", "desktop")

SIZES: tuple[str, ...] = ("1x1", "2x1", "4x1", "1x2", "2x2", "2x4", "4x2", "4x4", "4x6")
SIZE_PATTERN = r"^(1x1|2x1|4x1|1x2|2x2|2x4|4x2|4x4|4x6)$"
SPAN_BY_SIZE: dict[str, tuple[int, int]] = {
    "1x1": (1, 1),
    "2x1": (2, 1),
    "4x1": (4, 1),
    "1x2": (1, 2),
    "2x2": (2, 2),
    "2x4": (2, 4),
    "4x2": (4, 2),
    "4x4": (4, 4),
    "4x6": (4, 6),
}
FALLBACK_SIZE = "2x2"


MODULE_WIDGETS = text("""
    select m.id as module,
           w.value->>'id' as id,
           w.value->>'title' as title,
           w.value->>'kind' as kind,
           w.value->'sizes' as sizes,
           w.value->>'endpoint' as endpoint,
           coalesce((w.value->>'refresh')::int, 0) as refresh,
           w.value->>'link' as link,
           w.value->'option' as option,
           (m.manifest->'ui'->>'hue')::int as hue
    from kernel.modules m
    cross join lateral jsonb_array_elements(m.manifest->'ui'->'widgets') as w
    where m.enabled
    order by m.id, w.value->>'id'
""")

READ_PREFS = text("select prefs from kernel.ui_preferences where subject = :subject")

WRITE_PREFS = text("""
    insert into kernel.ui_preferences (subject, prefs, updated_at)
    values (:subject, cast(:prefs as jsonb), now())
    on conflict (subject) do update
    set prefs = excluded.prefs, updated_at = now()
""")


WallpaperId = Annotated[str, Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")]
AppId = Annotated[str, Field(pattern=r"^[a-z][a-z0-9_]{1,30}$")]
AppBackground = Annotated[str, Field(pattern=r"^(app|plain|hue-[1-8])$")]
AppName = Annotated[str, Field(min_length=1, max_length=24, pattern=r"^[^\x00-\x1f\x7f]+$")]


Area = Literal["day", "money", "health", "work", "home", "leisure", "mind"]


class HomePanels(BaseModel):
    order: Annotated[list[Area], Field(max_length=7)] = []
    hidden: Annotated[list[Area], Field(max_length=7)] = []
    placed: Annotated[list[Literal["mobile", "desktop"]], Field(max_length=2)] = []


class Preferences(BaseModel):
    glass_opacity: Annotated[float, Field(ge=0.35, le=1.0)] = 0.55
    theme: Literal["system", "light", "dark"] = "system"
    wallpaper: WallpaperId = "marea"
    app_wallpapers: Annotated[dict[AppId, WallpaperId], Field(max_length=32)] = {}
    app_backgrounds: Annotated[dict[AppId, AppBackground], Field(max_length=32)] = {}
    app_names: Literal["standard", "arga", "greek", "custom"] = "standard"
    custom_app_names: Annotated[dict[AppId, AppName], Field(max_length=64)] = {}
    icon_style: Literal["solid", "ink", "paper"] = "solid"
    home_panels: HomePanels = HomePanels()


@router.get("/ui/preferences")
async def read_preferences(
    subject: Annotated[str | None, Header(alias=SUBJECT_HEADER)] = None,
) -> Preferences:
    who = subject_of(subject)
    async with engine().connect() as connection:
        stored = await connection.scalar(READ_PREFS, {"subject": who})

    try:
        return Preferences.model_validate(stored or {})
    except ValidationError:
        return Preferences()


@router.put("/ui/preferences")
async def write_preferences(
    preferences: Preferences,
    subject: Annotated[str | None, Header(alias=SUBJECT_HEADER)] = None,
) -> Preferences:
    require_person()
    who = subject_of(subject)
    async with engine().begin() as connection:
        await connection.execute(
            WRITE_PREFS, {"subject": who, "prefs": preferences.model_dump_json()}
        )
    return preferences


class CatalogueEntry(BaseModel):
    source: str
    id: str
    title: str
    hue: int
    kind: str
    shape: str
    sizes: list[str]
    endpoint: str
    refresh: int = 0
    link: str | None = None
    option: dict[str, str] | None = None


@router.get("/ui/widgets")
async def widget_catalogue() -> list[CatalogueEntry]:
    catalogue = [
        CatalogueEntry(
            source=KERNEL,
            id=widget.id,
            title=widget.title,
            hue=widget.hue,
            kind=widget.kind,
            shape=widget.shape,
            sizes=list(widget.sizes),
            endpoint=f"/api/kernel/widgets/{widget.id}",
        )
        for widget in CATALOGUE
    ]

    async with engine().connect() as connection:
        rows = (await connection.execute(MODULE_WIDGETS)).all()

    catalogue.extend(
        CatalogueEntry(
            source=row.module,
            id=row.id,
            title=row.title,
            hue=row.hue or 1,
            kind=row.kind if row.kind in KINDS else "kpi",
            shape="list" if row.kind in LIST_LIKE else "number",
            sizes=list(row.sizes or []),
            endpoint=row.endpoint,
            refresh=row.refresh,
            link=row.link,
            option=row.option if isinstance(row.option, dict) else None,
        )
        for row in rows
    )
    return catalogue


@router.get("/widgets/{widget_id}")
async def widget_data(widget_id: str) -> dict:
    if widget_id not in BY_ID:
        raise HTTPException(status_code=404, detail=f"the kernel has no widget '{widget_id}'")
    async with engine().connect() as connection:
        return await RENDERERS[widget_id](connection)
