from __future__ import annotations

from datetime import date, time, timedelta
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator, model_validator
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from arga_tenancy import CURRENT_USER_SQL as ME
from travel import travel

Kind = Literal["activity", "transport", "meal", "accommodation", "free_time", "other"]
KINDS: tuple[Kind, ...] = ("activity", "transport", "meal", "accommodation", "free_time", "other")


class BlockIn(travel.BookingIn):
    id: UUID | None = None
    day: date | None = None
    kind: Kind = "activity"
    title: Annotated[str, Field(min_length=1, max_length=120)]
    starts_at: time | None = None
    ends_at: time | None = None
    place_id: str | None = None
    notes: Annotated[str | None, Field(max_length=2000)] = None

    @field_validator("title")
    @classmethod
    def tidy(cls, value: str) -> str:
        cleaned = " ".join(value.split())
        if not cleaned:
            raise ValueError("el título no puede estar vacío")
        return cleaned

    @model_validator(mode="after")
    def in_order(self) -> BlockIn:
        if self.starts_at and self.ends_at and self.ends_at < self.starts_at:
            raise ValueError("un bloque no puede acabar antes de empezar")
        return self


class Block(BaseModel):
    id: str
    day: date | None
    position: int
    kind: Kind
    title: str
    starts_at: time | None
    ends_at: time | None
    place: travel.Place | None
    visit_id: str | None
    notes: str | None
    mine: bool = True
    confirmation: str | None = None
    provider: str | None = None
    booking_url: str | None = None
    cost_eur: float | None = None
    paid_by: str | None = None


class Item(BaseModel):
    type: Literal["check_out", "leg", "check_in", "block"]
    stay: travel.Stay | None = None
    leg: travel.Leg | None = None
    block: Block | None = None


class Day(BaseModel):
    day: date
    number: int
    title: str | None = None
    sleeping: travel.Stay | None
    items: list[Item]


class Itinerary(BaseModel):
    trip_id: str
    title: str
    days: list[Day]
    unscheduled: list[Block]


BLOCK_COLUMNS = f"""
    b.id::text as id, b.day, b.position, b.kind, b.title, b.starts_at, b.ends_at,
    b.visit_id::text as visit_id, b.notes, b.user_id = {ME} as mine, b.place_id::text as place_id,
    b.confirmation, b.provider, b.booking_url,
    (select round(e.amount_eur * t.travellers, 2) from travel.travel_expense e
     join travel.travel_trip t on t.id = e.trip_id where e.block_id = b.id) as cost_eur,
    (select r.name from travel.travel_expense e join travel.travel_traveller r on r.id = e.paid_by
     where e.block_id = b.id) as paid_by,
    {travel._place_select("p", "p_")}
"""


def _block(row) -> Block:
    return Block(
        id=row.id,
        day=row.day,
        position=row.position,
        kind=row.kind,
        title=row.title,
        starts_at=row.starts_at,
        ends_at=row.ends_at,
        place=travel._joined_place(row, "p_") if row.place_id else None,
        visit_id=row.visit_id,
        notes=row.notes,
        mine=bool(row.mine),
        confirmation=row.confirmation,
        provider=row.provider,
        booking_url=row.booking_url,
        cost_eur=float(row.cost_eur) if row.cost_eur is not None else None,
        paid_by=row.paid_by,
    )


async def blocks(connection: AsyncConnection, trip_id: str) -> list[Block]:
    rows = (
        await connection.execute(
            text(f"""
                select {BLOCK_COLUMNS}
                from travel.travel_block b
                left join travel.travel_place p on p.id = b.place_id
                where b.trip_id = :trip
                order by b.day nulls last, b.position, b.created_at
            """),
            {"trip": trip_id},
        )
    ).all()
    return [_block(row) for row in rows]


async def itinerary(connection: AsyncConnection, trip_id: str) -> Itinerary:
    found = await travel.trip(connection, trip_id)
    every = await blocks(connection, trip_id)
    titles = await day_titles(connection, trip_id)
    days: list[Day] = []
    for offset in range(found.days):
        day = found.starts_on + timedelta(days=offset)
        items = [Item(type="check_out", stay=s) for s in found.stays if s.leaves_on == day]
        items += [Item(type="leg", leg=leg) for leg in found.legs if leg.travelled_on == day]
        items += [Item(type="check_in", stay=s) for s in found.stays if s.arrives_on == day]
        items += [Item(type="block", block=b) for b in every if b.day == day]
        sleeping = next((s for s in found.stays if s.arrives_on <= day < s.leaves_on), None)
        days.append(
            Day(
                day=day,
                number=offset + 1,
                title=titles.get(day),
                sleeping=sleeping,
                items=by_the_clock(items),
            )
        )
    return Itinerary(
        trip_id=found.id,
        title=found.title,
        days=days,
        unscheduled=[b for b in every if b.day is None],
    )


def starts(item: Item) -> time | None:
    if item.type == "check_out" and item.stay:
        return item.stay.check_out_at
    if item.type == "check_in" and item.stay:
        return item.stay.check_in_at
    if item.type == "leg" and item.leg:
        return item.leg.departs_at
    return item.block.starts_at if item.block else None


def by_the_clock(items: list[Item]) -> list[Item]:
    keyed = []
    last = time.min
    for index, item in enumerate(items):
        at = starts(item)
        if at is not None:
            last = at
        keyed.append((at or last, at is None, index, item))
    return [item for *_, item in sorted(keyed, key=lambda one: one[:3])]


async def day_titles(connection: AsyncConnection, trip_id: str) -> dict[date, str]:
    rows = (
        await connection.execute(
            text("select day, title from travel.travel_day where trip_id = :trip"),
            {"trip": trip_id},
        )
    ).all()
    return {row.day: row.title for row in rows}


async def set_day_title(
    connection: AsyncConnection, trip_id: str, day: date, title: str | None
) -> Itinerary:
    await travel._check_dates(connection, trip_id, day)
    cleaned = " ".join((title or "").split())
    if len(cleaned) > 80:
        raise travel.Conflict("el título de un día tiene como mucho 80 caracteres", "TOO_LONG")
    await connection.execute(
        text("delete from travel.travel_day where trip_id = :trip and day = :day"),
        {"trip": trip_id, "day": day},
    )
    if cleaned:
        await connection.execute(
            text("insert into travel.travel_day (trip_id, day, title) values (:trip, :day, :t)"),
            {"trip": trip_id, "day": day, "t": cleaned},
        )
    await travel._touch(connection, trip_id)
    return await itinerary(connection, trip_id)


async def _row(connection: AsyncConnection, block_id: str):
    row = (
        await connection.execute(
            text("""
                select id::text as id, trip_id::text as trip_id, day, position, kind, place_id::text
                       as place_id, visit_id::text as visit_id, notes
                from travel.travel_block where id = :id
            """),
            {"id": block_id},
        )
    ).one_or_none()
    if row is None:
        raise travel.NotFound(f"bloque {block_id}")
    return row


async def trip_of(connection: AsyncConnection, block_id: str) -> str:
    return (await _row(connection, block_id)).trip_id


async def _order(connection: AsyncConnection, trip_id: str, day: date | None) -> list[str]:
    return list(
        (
            await connection.execute(
                text("""
                    select id::text from travel.travel_block
                    where trip_id = :trip and day is not distinct from :day
                    order by position, created_at
                """),
                {"trip": trip_id, "day": day},
            )
        ).scalars()
    )


async def _renumber(connection: AsyncConnection, ids: list[str]) -> None:
    for index, block_id in enumerate(ids):
        await connection.execute(
            text("update travel.travel_block set position = :pos where id = :id"),
            {"id": block_id, "pos": index},
        )


async def _slot(
    connection: AsyncConnection, trip_id: str, day: date | None, at: time | None
) -> int:
    order = await _order(connection, trip_id, day)
    if at is None or day is None:
        return len(order)
    earlier = await connection.scalar(
        text("""
            select count(*) from travel.travel_block
            where trip_id = :trip and day = :day and starts_at is not null and starts_at <= :at
        """),
        {"trip": trip_id, "day": day, "at": at},
    )
    return int(earlier or 0)


async def _sync_visit(connection: AsyncConnection, trip_id: str, block_id: str) -> None:
    row = (
        await connection.execute(
            text("""
                select kind, day, place_id::text as place_id, visit_id::text as visit_id, notes
                from travel.travel_block where id = :id
            """),
            {"id": block_id},
        )
    ).one()
    wants = row.kind == "activity" and row.place_id is not None
    if not wants:
        if row.visit_id:
            await connection.execute(
                text("update travel.travel_block set visit_id = null where id = :id"),
                {"id": block_id},
            )
            await connection.execute(
                text("delete from travel.travel_visit where id = :id"), {"id": row.visit_id}
            )
        return
    stay = await travel.stay_covering(connection, trip_id, row.day)
    if row.visit_id:
        await connection.execute(
            text("""
                update travel.travel_visit
                set place_id = :place, visited_on = :day, stay_id = :stay
                where id = :id
            """),
            {"id": row.visit_id, "place": row.place_id, "day": row.day, "stay": stay},
        )
        return
    visit_id = await connection.scalar(
        text("""
            insert into travel.travel_visit (trip_id, place_id, stay_id, visited_on)
            values (:trip, :place, :stay, :day)
            returning id::text
        """),
        {"trip": trip_id, "place": row.place_id, "stay": stay, "day": row.day},
    )
    await connection.execute(
        text("update travel.travel_block set visit_id = :visit where id = :id"),
        {"id": block_id, "visit": visit_id},
    )


async def _same_visit(
    connection: AsyncConnection, trip_id: str, day: date | None, place_id: str | None
) -> str | None:
    if day is None or place_id is None:
        return None
    return await connection.scalar(
        text("""
            select id::text from travel.travel_block
            where trip_id = :trip and day = :day and place_id = :place and kind = 'activity'
            order by starts_at nulls last, created_at
            limit 1
        """),
        {"trip": trip_id, "day": day, "place": place_id},
    )


async def add_block(connection: AsyncConnection, trip_id: str, request: BlockIn) -> Itinerary:
    if request.id is not None:
        exists = await connection.scalar(
            text("select 1 from travel.travel_block where id = :id"), {"id": request.id}
        )
        if exists:
            return await itinerary(connection, trip_id)
    await travel._check_dates(connection, trip_id, request.day)
    if request.place_id:
        await travel.place_by_id(connection, request.place_id)
    if request.kind == "activity":
        twin = await _same_visit(connection, trip_id, request.day, request.place_id)
        if twin is not None:
            return await _complete(connection, trip_id, twin, request)
    position = await _slot(connection, trip_id, request.day, request.starts_at)
    await connection.execute(
        text("""
            update travel.travel_block set position = position + 1
            where trip_id = :trip and day is not distinct from :day and position >= :pos
        """),
        {"trip": trip_id, "day": request.day, "pos": position},
    )
    block_id = await connection.scalar(
        text("""
            insert into travel.travel_block
                (id, trip_id, day, position, kind, title, starts_at, ends_at, place_id, notes)
            values (coalesce(cast(:id as uuid), gen_random_uuid()), :trip, :day, :pos, :kind,
                    :title, :starts, :ends, cast(:place as uuid), :notes)
            returning id::text
        """),
        {
            "id": str(request.id) if request.id else None,
            "trip": trip_id,
            "day": request.day,
            "pos": position,
            "kind": request.kind,
            "title": request.title,
            "starts": request.starts_at,
            "ends": request.ends_at,
            "place": request.place_id,
            "notes": request.notes,
        },
    )
    await _sync_visit(connection, trip_id, block_id)
    await travel._booked(connection, trip_id, "block", block_id, request)
    await travel._touch(connection, trip_id)
    return await itinerary(connection, trip_id)


async def _complete(
    connection: AsyncConnection, trip_id: str, block_id: str, request: BlockIn
) -> Itinerary:
    current = (
        await connection.execute(
            text("""
                select title, starts_at, ends_at, notes, confirmation, provider, booking_url
                from travel.travel_block where id = :id
            """),
            {"id": block_id},
        )
    ).one()
    given = request.model_fields_set
    merged = BlockIn(
        day=request.day,
        kind="activity",
        title=request.title,
        starts_at=request.starts_at if "starts_at" in given else current.starts_at,
        ends_at=request.ends_at if "ends_at" in given else current.ends_at,
        place_id=request.place_id,
        notes=request.notes if request.notes else current.notes,
        **{
            key: getattr(request, key)
            for key in ("confirmation", "provider", "booking_url", "cost_eur")
            if key in given
        },
    )
    return await update_block(connection, trip_id, block_id, merged)


async def update_block(
    connection: AsyncConnection, trip_id: str, block_id: str, request: BlockIn
) -> Itinerary:
    current = await _row(connection, block_id)
    if current.trip_id != trip_id:
        raise travel.NotFound(f"bloque {block_id}")
    await travel._check_dates(connection, trip_id, request.day)
    if request.place_id:
        await travel.place_by_id(connection, request.place_id)
    moved = current.day != request.day
    await connection.execute(
        text("""
            update travel.travel_block
            set day = :day, kind = :kind, title = :title, starts_at = :starts, ends_at = :ends,
                place_id = cast(:place as uuid), notes = :notes, updated_at = now(),
                position = case when :moved then 1000000 else position end
            where id = :id
        """),
        {
            "id": block_id,
            "day": request.day,
            "kind": request.kind,
            "title": request.title,
            "starts": request.starts_at,
            "ends": request.ends_at,
            "place": request.place_id,
            "notes": request.notes,
            "moved": moved,
        },
    )
    if moved:
        await _renumber(connection, await _order(connection, trip_id, current.day))
        await _renumber(connection, await _order(connection, trip_id, request.day))
    await _sync_visit(connection, trip_id, block_id)
    await travel._booked(connection, trip_id, "block", block_id, request)
    await travel._touch(connection, trip_id)
    return await itinerary(connection, trip_id)


async def move_block(
    connection: AsyncConnection, trip_id: str, block_id: str, day: date | None, position: int
) -> Itinerary:
    current = await _row(connection, block_id)
    if current.trip_id != trip_id:
        raise travel.NotFound(f"bloque {block_id}")
    await travel._check_dates(connection, trip_id, day)
    target = [one for one in await _order(connection, trip_id, day) if one != block_id]
    target.insert(max(0, min(position, len(target))), block_id)
    await connection.execute(
        text("update travel.travel_block set day = :day, updated_at = now() where id = :id"),
        {"id": block_id, "day": day},
    )
    await _renumber(connection, target)
    if current.day != day:
        await _renumber(connection, await _order(connection, trip_id, current.day))
    await _sync_visit(connection, trip_id, block_id)
    await travel._touch(connection, trip_id)
    return await itinerary(connection, trip_id)


async def remove_block(connection: AsyncConnection, trip_id: str, block_id: str) -> Itinerary:
    current = await _row(connection, block_id)
    if current.trip_id != trip_id:
        raise travel.NotFound(f"bloque {block_id}")
    if current.visit_id:
        await connection.execute(
            text("delete from travel.travel_visit where id = :id"), {"id": current.visit_id}
        )
    else:
        await connection.execute(
            text("delete from travel.travel_block where id = :id"), {"id": block_id}
        )
    await _renumber(connection, await _order(connection, trip_id, current.day))
    await travel._touch(connection, trip_id)
    return await itinerary(connection, trip_id)


ORPHAN_VISITS = text(f"""
    select v.id::text as id, v.trip_id::text as trip_id, v.visited_on, p.name, v.note
    from travel.travel_visit v
    join travel.travel_place p on p.id = v.place_id
    where v.user_id = {ME}
      and not exists (select 1 from travel.travel_block b where b.visit_id = v.id)
    order by v.trip_id, v.visited_on nulls last, p.name
""")


async def ensure_blocks(connection: AsyncConnection, trip_id: str | None = None) -> int:
    rows = (await connection.execute(ORPHAN_VISITS)).all()
    made = 0
    for row in rows:
        if trip_id is not None and row.trip_id != trip_id:
            continue
        place_id = await connection.scalar(
            text("select place_id::text from travel.travel_visit where id = :id"), {"id": row.id}
        )
        if await _same_visit(connection, row.trip_id, row.visited_on, place_id):
            await connection.execute(
                text("delete from travel.travel_visit where id = :id"), {"id": row.id}
            )
            continue
        position = len(await _order(connection, row.trip_id, row.visited_on))
        await connection.execute(
            text("""
                insert into travel.travel_block
                    (trip_id, day, position, kind, title, place_id, visit_id, notes, space_id)
                select v.trip_id, v.visited_on, :pos, 'activity', :title, v.place_id, v.id,
                       :notes, v.space_id
                from travel.travel_visit v where v.id = :visit
            """),
            {
                "visit": row.id,
                "pos": position,
                "title": row.name[:120],
                "notes": row.note,
            },
        )
        made += 1
    if trip_id is not None:
        await merge_twins(connection, trip_id)
    return made


async def merge_twins(connection: AsyncConnection, trip_id: str) -> int:
    groups = (
        await connection.execute(
            text("""
                select day, place_id, array_agg(id::text order by starts_at nulls last,
                                                created_at) as ids
                from travel.travel_block
                where trip_id = :trip and kind = 'activity' and day is not null
                  and place_id is not null
                group by day, place_id having count(*) > 1
            """),
            {"trip": trip_id},
        )
    ).all()
    merged = 0
    for group in groups:
        keep, *others = group.ids
        for other in others:
            costs = await connection.scalar(
                text("""
                    select count(*) from travel.travel_expense
                    where block_id = cast(:a as uuid) or block_id = cast(:b as uuid)
                """),
                {"a": keep, "b": other},
            )
            if costs and costs > 1:
                continue
            await connection.execute(
                text("""
                    update travel.travel_block k set
                        notes = coalesce(k.notes, o.notes),
                        starts_at = coalesce(k.starts_at, o.starts_at),
                        ends_at = coalesce(k.ends_at, o.ends_at),
                        confirmation = coalesce(k.confirmation, o.confirmation),
                        provider = coalesce(k.provider, o.provider),
                        booking_url = coalesce(k.booking_url, o.booking_url),
                        updated_at = now()
                    from travel.travel_block o
                    where k.id = cast(:keep as uuid) and o.id = cast(:other as uuid)
                """),
                {"keep": keep, "other": other},
            )
            for table in ("travel_expense", "travel_document"):
                await connection.execute(
                    text(
                        f"update travel.{table} set block_id = cast(:keep as uuid) "
                        "where block_id = cast(:other as uuid)"
                    ),
                    {"keep": keep, "other": other},
                )
            visit = await connection.scalar(
                text("select visit_id::text from travel.travel_block where id = :id"),
                {"id": other},
            )
            if visit:
                await connection.execute(
                    text("delete from travel.travel_visit where id = :id"), {"id": visit}
                )
            else:
                await connection.execute(
                    text("delete from travel.travel_block where id = :id"), {"id": other}
                )
            merged += 1
        await _renumber(connection, await _order(connection, trip_id, group.day))
    return merged
