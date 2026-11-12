from __future__ import annotations

from datetime import date

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from arga_tenancy import CURRENT_USER_SQL as ME
from travel.travel.common import Conflict, NotFound, Source, Status, _clean_list
from travel.travel.models import Trip, TripIn
from travel.travel.read import trip
from travel.travel.sync import _sync_legs, _touch, _withdraw


async def find_duplicate(
    connection: AsyncConnection, title: str, starts_on: date, other_than: str | None = None
) -> str | None:
    return await connection.scalar(
        text("""
            select id::text from travel.travel_trip
            where lower(title) = lower(:title) and starts_on = :starts
              and (cast(:other as uuid) is null or id <> cast(:other as uuid))
        """),
        {"title": " ".join(title.split()), "starts": starts_on, "other": other_than},
    )


async def _check_unique(
    connection: AsyncConnection, title: str, starts_on: date, other_than: str | None = None
) -> None:
    found = await find_duplicate(connection, title, starts_on, other_than)
    if found:
        raise Conflict(
            f"ya hay un viaje «{' '.join(title.split())}» que empieza el {starts_on.isoformat()}",
            "DUPLICATE_TRIP",
            [{"trip_id": found}],
        )


def _summary_text(summary: str | None) -> str | None:
    cleaned = (summary or "").strip()
    return cleaned or None


async def create_trip(connection: AsyncConnection, request: TripIn, source: Source = "app") -> Trip:
    await _check_unique(connection, request.title, request.starts_on)
    trip_id = await connection.scalar(
        text("""
            insert into travel.travel_trip
                (title, starts_on, ends_on, travellers, companions, tags, notes, source, status,
                 budget_eur, summary)
            values (:title, :starts, :ends, :travellers, :companions, :tags, :notes, :source,
                    :status, :budget, :summary)
            returning id::text
        """),
        {
            "title": " ".join(request.title.split()),
            "starts": request.starts_on,
            "ends": request.ends_on,
            "travellers": request.travellers,
            "companions": _clean_list(request.companions),
            "tags": _clean_list(request.tags),
            "notes": request.notes,
            "source": source,
            "status": request.status or "confirmed",
            "budget": request.budget_eur,
            "summary": _summary_text(request.summary),
        },
    )
    await _touch(connection, trip_id)
    return await trip(connection, trip_id)


async def _outside(
    connection: AsyncConnection, trip_id: str, starts_on: date, ends_on: date
) -> list[dict]:
    rows = (
        await connection.execute(
            text("""
                select 'stay' as kind, s.id::text as id, p.name, s.arrives_on as since,
                       s.leaves_on as until
                from travel.travel_stay s join travel.travel_place p on p.id = s.place_id
                where s.trip_id = :id and (s.arrives_on < :starts or s.leaves_on > :ends)
                union all
                select 'visit', v.id::text, p.name, v.visited_on, v.visited_on
                from travel.travel_visit v join travel.travel_place p on p.id = v.place_id
                where v.trip_id = :id and (v.visited_on < :starts or v.visited_on > :ends)
                union all
                select 'leg', l.id::text, a.name || ' → ' || b.name, l.travelled_on,
                       l.travelled_on
                from travel.travel_leg l
                join travel.travel_place a on a.id = l.from_place_id
                join travel.travel_place b on b.id = l.to_place_id
                where l.trip_id = :id and (l.travelled_on < :starts or l.travelled_on > :ends)
                union all
                select 'block', b.id::text, b.title, b.day, b.day
                from travel.travel_block b
                where b.trip_id = :id and b.visit_id is null
                  and (b.day < :starts or b.day > :ends)
                order by since
            """),
            {"id": trip_id, "starts": starts_on, "ends": ends_on},
        )
    ).all()
    return [
        {
            "kind": row.kind,
            f"{row.kind}_id": row.id,
            "name": row.name,
            "from": row.since.isoformat(),
            "to": row.until.isoformat(),
        }
        for row in rows
    ]


SHIFT = [
    "update travel.travel_stay set arrives_on = arrives_on + cast(:days as int), "
    "leaves_on = leaves_on + cast(:days as int) where trip_id = :id",
    "update travel.travel_visit set visited_on = visited_on + cast(:days as int) "
    "where trip_id = :id",
    "update travel.travel_leg set travelled_on = travelled_on + cast(:days as int), "
    "arrives_on = arrives_on + cast(:days as int) where trip_id = :id",
    "update travel.travel_block set day = day + cast(:days as int) where trip_id = :id",
    "update travel.travel_day set day = day + cast(:days as int) where trip_id = :id",
]


async def update_trip(
    connection: AsyncConnection,
    trip_id: str,
    request: TripIn,
    keep_group_total: bool = False,
    shift: bool = False,
) -> Trip:
    current = (
        await connection.execute(
            text("select travellers, starts_on from travel.travel_trip where id = :id"),
            {"id": trip_id},
        )
    ).one_or_none()
    if current is None:
        raise NotFound(f"viaje {trip_id}")
    before = current.travellers
    await _check_unique(connection, request.title, request.starts_on, trip_id)
    moved = (request.starts_on - current.starts_on).days
    if shift and moved:
        for statement in SHIFT:
            await connection.execute(text(statement), {"id": trip_id, "days": moved})
    outside = await _outside(connection, trip_id, request.starts_on, request.ends_on)
    if outside:
        raise Conflict(
            "hay cosas del viaje fuera de esas fechas: cámbialas antes",
            "DATE_OUT_OF_RANGE",
            outside,
        )
    await connection.execute(
        text("""
            update travel.travel_trip
            set title = :title, starts_on = :starts, ends_on = :ends, travellers = :travellers,
                companions = :companions, tags = :tags, notes = :notes,
                status = coalesce(:status, status),
                budget_eur = case when :budget_given then cast(:budget as numeric)
                                  else budget_eur end,
                summary = case when :summary_given then cast(:summary as text) else summary end
            where id = :id
        """),
        {
            "id": trip_id,
            "title": " ".join(request.title.split()),
            "starts": request.starts_on,
            "ends": request.ends_on,
            "travellers": request.travellers,
            "companions": _clean_list(request.companions),
            "tags": _clean_list(request.tags),
            "notes": request.notes,
            "status": request.status,
            "budget_given": "budget_eur" in request.model_fields_set,
            "budget": request.budget_eur,
            "summary_given": "summary" in request.model_fields_set,
            "summary": _summary_text(request.summary),
        },
    )
    if request.travellers != before:
        await connection.execute(
            text("""
                update travel.travel_expense
                set amount_eur = round(total_eur / :after, 2)
                where trip_id = :id and total_eur is not null
                  and abs(total_eur - amount_eur * :before) <= 0.01 * :before
            """),
            {"id": trip_id, "before": before, "after": request.travellers},
        )
    if keep_group_total and request.travellers != before:
        await connection.execute(
            text("""
                update travel.travel_expense
                set amount_eur = round(amount_eur * :before / :after, 2)
                where trip_id = :id and total_eur is null
            """),
            {"id": trip_id, "before": before, "after": request.travellers},
        )
    await _touch(connection, trip_id)
    return await trip(connection, trip_id)


async def delete_trip(connection: AsyncConnection, trip_id: str) -> None:
    shared_by_other = await connection.scalar(
        text(
            f"select space_id is not null and user_id <> {ME} "
            "from travel.travel_trip where id = :id"
        ),
        {"id": trip_id},
    )
    if shared_by_other:
        raise Conflict("este viaje lo compartió otra persona: solo ella lo borra", "NOT_OWNER")
    gone = (
        await connection.execute(
            text(
                "delete from travel.travel_trip where id = :id returning title, starts_on, ends_on"
            ),
            {"id": trip_id},
        )
    ).one_or_none()
    if gone is None:
        raise NotFound(f"viaje {trip_id}")
    await _withdraw(connection, trip_id, gone.title, gone.starts_on, gone.ends_on)
    await _sync_legs(connection, trip_id, [])


async def set_status(connection: AsyncConnection, trip_id: str, status: Status) -> Trip:
    updated = await connection.execute(
        text("update travel.travel_trip set status = :status where id = :id"),
        {"id": trip_id, "status": status},
    )
    if updated.rowcount == 0:
        raise NotFound(f"viaje {trip_id}")
    await _touch(connection, trip_id)
    return await trip(connection, trip_id)


async def archive_trip(connection: AsyncConnection, trip_id: str, archived: bool) -> Trip:
    updated = await connection.execute(
        text("""
            update travel.travel_trip
            set archived_at = case when :archived then coalesce(archived_at, now()) end,
                updated_at = now()
            where id = :id
        """),
        {"id": trip_id, "archived": archived},
    )
    if updated.rowcount == 0:
        raise NotFound(f"viaje {trip_id}")
    return await trip(connection, trip_id)
