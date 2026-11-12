from __future__ import annotations

import json
from datetime import date, datetime, time
from typing import Any

import httpx
from pydantic import BaseModel, Field, ValidationError
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from macros import intake
from macros.common import MADRID, Conflict, NotFound, Unavailable, is_uuid, today


class TemplateIn(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    items: list[intake.ItemIn] = Field(min_length=1, max_length=intake.MAX_ITEMS)
    said: str | None = Field(default=None, max_length=1000)
    daily_at: time | None = None


class Template(BaseModel):
    id: str
    name: str
    items: list[dict[str, Any]]
    said: str | None
    daily_at: time | None


SAVE = text("""
    insert into macros.macros_template (name, items, said, daily_at)
    values (:name, cast(:items as jsonb), :said, :daily_at)
    on conflict (user_id, lower(btrim(name))) do update
       set items = excluded.items, said = excluded.said, daily_at = excluded.daily_at
    returning id
""")

ALL = text(
    "select id, name, items, said, daily_at from macros.macros_template order by lower(name)"
)

BY_ID = text("""
    select id, name, items, said, daily_at from macros.macros_template where id = cast(:id as uuid)
""")

BY_NAME = text("""
    select id, name, items, said, daily_at from macros.macros_template
     where lower(btrim(name)) = lower(btrim(:name))
""")

DELETE = text("delete from macros.macros_template where id = cast(:id as uuid) returning id")

DAILY_DUE = text("""
    select t.id, t.name, t.items, t.said, t.daily_at from macros.macros_template t
     where t.daily_at is not null
       and not exists (
           select 1 from macros.macros_template_run r where r.template_id = t.id and r.day = :day
       )
""")

RAN = text("""
    insert into macros.macros_template_run (template_id, day, entry_id)
    values (cast(:template as uuid), :day, cast(:entry as uuid))
    on conflict do nothing
""")

ENTRY_ITEMS = text("""
    select kind, food_id, recipe_id, name, quantity, unit, estimated
    from macros.macros_item where entry_id = cast(:id as uuid) order by position
""")


def _template(row: Any) -> Template:
    return Template(
        id=str(row.id), name=row.name, items=row.items, said=row.said, daily_at=row.daily_at
    )


async def save(connection: AsyncConnection, request: TemplateIn) -> Template:
    items = [one.model_dump(exclude_defaults=True) for one in request.items]
    found = await connection.scalar(
        SAVE,
        {
            "name": request.name.strip(),
            "items": json.dumps(items),
            "said": (request.said or "").strip() or None,
            "daily_at": request.daily_at,
        },
    )
    return await read(connection, str(found))


ITEMS_OF = text("""
    select i.kind, i.food_id, i.recipe_id, i.name, i.quantity, i.unit, i.estimated, i.nutrients,
           i.portion
    from macros.macros_item i join macros.macros_entry e on e.id = i.entry_id
    where i.entry_id = any(cast(:ids as uuid[]))
    order by e.eaten_at, i.position
""")


async def _as_items(connection: AsyncConnection, entry_ids: list[str]) -> list[intake.ItemIn]:
    items = []
    for row in (await connection.execute(ITEMS_OF, {"ids": entry_ids})).all():
        one: dict[str, Any] = {"kind": row.kind, "quantity": float(row.quantity), "unit": row.unit}
        if row.kind == "food":
            one["food_id"] = str(row.food_id)
            if row.portion and row.unit == "unit":
                one["portion"] = row.portion
        elif row.kind == "recipe":
            one["recipe_id"] = str(row.recipe_id)
        elif row.kind == "quick":
            one["name"] = row.name
            said = {
                key: value
                for key, value in (row.nutrients or {}).items()
                if key in ("protein", "carbs", "fat")
            }
            if said:
                one["quick"] = said
        if row.estimated:
            one["estimated"] = True
        items.append(intake.ItemIn.model_validate(one))
    return items


async def from_entry(
    connection: AsyncConnection, entry_id: str, name: str, daily_at: time | None
) -> Template:
    entry = await intake.one(connection, entry_id)
    items = await _as_items(connection, [entry_id])
    return await save(
        connection, TemplateIn(name=name, items=items, said=entry.said, daily_at=daily_at)
    )


async def from_meal(
    connection: AsyncConnection, day: date, meal: str, name: str, daily_at: time | None
) -> Template:
    found = await intake.in_meal(connection, day, meal)
    if not found:
        raise NotFound("nada apuntado en esa comida")
    items = await _as_items(connection, [entry.id for entry in found])
    if len(items) > intake.MAX_ITEMS:
        raise Conflict(f"un menú lleva hasta {intake.MAX_ITEMS} cosas")
    return await save(connection, TemplateIn(name=name, items=items, daily_at=daily_at))


async def all_of(connection: AsyncConnection) -> list[Template]:
    return [_template(row) for row in (await connection.execute(ALL)).all()]


async def read(connection: AsyncConnection, template_id: str) -> Template:
    row = (
        (await connection.execute(BY_ID, {"id": template_id})).first()
        if is_uuid(template_id)
        else None
    )
    if row is None:
        raise NotFound(f"la plantilla {template_id}")
    return _template(row)


async def find(connection: AsyncConnection, wanted: str) -> Template:
    if is_uuid(wanted):
        return await read(connection, wanted)
    row = (await connection.execute(BY_NAME, {"name": wanted})).first()
    if row is None:
        known = ", ".join(one.name for one in await all_of(connection)) or "ninguna"
        raise NotFound(f"la plantilla «{wanted}» (hay: {known})")
    return _template(row)


async def remove(connection: AsyncConnection, template_id: str) -> None:
    if (await connection.execute(DELETE, {"id": template_id})).first() is None:
        raise NotFound(f"la plantilla {template_id}")


async def use(
    connection: AsyncConnection,
    client: httpx.AsyncClient,
    template: Template,
    eaten_at: datetime | None = None,
    planned: bool = False,
    origin: str = "app",
) -> intake.Entry:
    try:
        items = [intake.ItemIn.model_validate(one) for one in template.items]
    except ValidationError as error:
        raise Conflict(f"la plantilla «{template.name}» ya no se puede apuntar: {error}") from error
    request = intake.EntryIn(eaten_at=eaten_at, said=template.said, items=items, planned=planned)
    return await intake.log(connection, client, request, origin)  # type: ignore[arg-type]


async def materialise(connection: AsyncConnection, client: httpx.AsyncClient) -> int:
    day = today()
    created = 0
    for row in (await connection.execute(DAILY_DUE, {"day": day})).all():
        template = _template(row)
        moment = datetime.combine(day, template.daily_at or time(), MADRID)
        try:
            async with connection.begin_nested():
                entry = await use(connection, client, template, moment, planned=True)
                await connection.execute(
                    RAN, {"template": template.id, "day": day, "entry": entry.id}
                )
        except (Conflict, NotFound, Unavailable):
            continue
        created += 1
    return created
