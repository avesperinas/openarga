from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Annotated

from pydantic import BaseModel, Field, field_validator, model_validator
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from arga_tenancy import CURRENT_USER_SQL as ME
from travel import itinerary, travel


class IdeaIn(BaseModel):
    title: Annotated[str, Field(min_length=1, max_length=120)]
    notes: Annotated[str | None, Field(max_length=4000)] = None
    budget_eur: Annotated[Decimal | None, Field(ge=0, le=Decimal("99999999"), decimal_places=2)] = (
        None
    )
    days_min: Annotated[int | None, Field(ge=1, le=365)] = None
    days_max: Annotated[int | None, Field(ge=1, le=365)] = None
    months: Annotated[list[Annotated[int, Field(ge=1, le=12)]], Field(max_length=12)] = []
    tags: Annotated[list[Annotated[str, Field(max_length=40)]], Field(max_length=20)] = []

    @field_validator("title")
    @classmethod
    def tidy(cls, value: str) -> str:
        cleaned = " ".join(value.split())
        if not cleaned:
            raise ValueError("el título no puede estar vacío")
        return cleaned

    @model_validator(mode="after")
    def in_order(self) -> IdeaIn:
        if self.days_min and self.days_max and self.days_max < self.days_min:
            raise ValueError("los días como mucho no pueden ser menos que como poco")
        self.months = sorted(set(self.months))
        return self


class IdeaPlace(BaseModel):
    id: str
    place: travel.Place
    note: str | None


class IdeaTrip(BaseModel):
    id: str
    title: str
    starts_on: date
    phase: travel.Phase


class Idea(BaseModel):
    id: str
    title: str
    notes: str | None
    budget_eur: float | None
    days_min: int | None
    days_max: int | None
    months: list[int]
    tags: list[str]
    archived: bool
    places: list[IdeaPlace]
    trips: list[IdeaTrip]
    countries: list[str]
    space_id: str | None = None
    mine: bool = True


COLUMNS = f"""
    id::text as id, title, notes, budget_eur, days_min, days_max, months, tags,
    archived_at is not null as archived, space_id::text as space_id, user_id = {ME} as mine
"""


async def _places(connection: AsyncConnection, ids: list[str]):
    return (
        await connection.execute(
            text(f"""
                select ip.id::text as id, ip.idea_id::text as idea_id, ip.note,
                       {travel._place_select("p", "p_")}
                from travel.travel_idea_place ip
                join travel.travel_place p on p.id = ip.place_id
                where ip.idea_id::text = any(:ids)
                order by ip.position, p.name
            """),
            {"ids": ids},
        )
    ).all()


async def ideas(connection: AsyncConnection, idea_id: str | None = None) -> list[Idea]:
    where = "where id = :id" if idea_id else ""
    rows = (
        await connection.execute(
            text(
                f"select {COLUMNS} from travel.travel_idea {where} order by archived_at nulls "
                "first, created_at desc"
            ),
            {"id": idea_id} if idea_id else {},
        )
    ).all()
    if not rows:
        return []
    ids = [row.id for row in rows]
    places = await _places(connection, ids)
    trips = (
        await connection.execute(
            text("""
                select id::text as id, idea_id::text as idea_id, title, status, starts_on, ends_on
                from travel.travel_trip where idea_id::text = any(:ids) order by starts_on
            """),
            {"ids": ids},
        )
    ).all()
    found = []
    for row in rows:
        mine_places = [
            IdeaPlace(id=one.id, place=travel._joined_place(one, "p_"), note=one.note)
            for one in places
            if one.idea_id == row.id
        ]
        countries: list[str] = []
        for one in mine_places:
            code = one.place.country_code
            if code and code not in countries:
                countries.append(code)
        found.append(
            Idea(
                id=row.id,
                title=row.title,
                notes=row.notes,
                budget_eur=float(row.budget_eur) if row.budget_eur is not None else None,
                days_min=row.days_min,
                days_max=row.days_max,
                months=list(row.months),
                tags=list(row.tags),
                archived=row.archived,
                places=mine_places,
                trips=[
                    IdeaTrip(
                        id=one.id,
                        title=one.title,
                        starts_on=one.starts_on,
                        phase=travel.phase_of(one.status, one.starts_on, one.ends_on),
                    )
                    for one in trips
                    if one.idea_id == row.id
                ],
                countries=countries,
                space_id=row.space_id,
                mine=bool(row.mine),
            )
        )
    return found


async def idea(connection: AsyncConnection, idea_id: str) -> Idea:
    found = await ideas(connection, idea_id)
    if not found:
        raise travel.NotFound(f"idea {idea_id}")
    return found[0]


def _values(request: IdeaIn) -> dict:
    return {
        "title": request.title,
        "notes": request.notes,
        "budget": request.budget_eur,
        "days_min": request.days_min,
        "days_max": request.days_max,
        "months": request.months,
        "tags": travel._clean_list(request.tags),
    }


SPREAD = [
    """
    update travel.travel_idea_place c set space_id = i.space_id
    from travel.travel_idea i
    where i.id = :id and c.idea_id = i.id and c.space_id is distinct from i.space_id
    """,
    """
    update travel.travel_place p set space_id = i.space_id
    from travel.travel_idea i
    where i.id = :id and i.space_id is not null and p.space_id is null
      and p.id in (select place_id from travel.travel_idea_place where idea_id = :id)
    """,
]


async def _touch(connection: AsyncConnection, idea_id: str) -> None:
    updated = await connection.execute(
        text("update travel.travel_idea set updated_at = now() where id = :id"), {"id": idea_id}
    )
    if updated.rowcount == 0:
        raise travel.NotFound(f"idea {idea_id}")
    for statement in SPREAD:
        await connection.execute(text(statement), {"id": idea_id})


async def create_idea(
    connection: AsyncConnection, request: IdeaIn, source: travel.Source = "app"
) -> Idea:
    idea_id = await connection.scalar(
        text("""
            insert into travel.travel_idea
                (title, notes, budget_eur, days_min, days_max, months, tags, source)
            values (:title, :notes, :budget, :days_min, :days_max, :months, :tags, :source)
            returning id::text
        """),
        {**_values(request), "source": source},
    )
    return await idea(connection, idea_id)


async def update_idea(connection: AsyncConnection, idea_id: str, request: IdeaIn) -> Idea:
    updated = await connection.execute(
        text("""
            update travel.travel_idea
            set title = :title, notes = :notes, budget_eur = :budget, days_min = :days_min,
                days_max = :days_max, months = :months, tags = :tags
            where id = :id
        """),
        {**_values(request), "id": idea_id},
    )
    if updated.rowcount == 0:
        raise travel.NotFound(f"idea {idea_id}")
    await _touch(connection, idea_id)
    return await idea(connection, idea_id)


async def archive_idea(connection: AsyncConnection, idea_id: str, archived: bool) -> Idea:
    updated = await connection.execute(
        text("""
            update travel.travel_idea
            set archived_at = case when :archived then coalesce(archived_at, now()) end
            where id = :id
        """),
        {"id": idea_id, "archived": archived},
    )
    if updated.rowcount == 0:
        raise travel.NotFound(f"idea {idea_id}")
    return await idea(connection, idea_id)


async def delete_idea(connection: AsyncConnection, idea_id: str) -> None:
    found = await idea(connection, idea_id)
    if not found.mine:
        raise travel.Conflict(
            "esta idea la compartió otra persona: solo ella la borra", "NOT_OWNER"
        )
    await connection.execute(text("delete from travel.travel_idea where id = :id"), {"id": idea_id})


async def add_place(
    connection: AsyncConnection, idea_id: str, place_id: str, note: str | None = None
) -> Idea:
    await idea(connection, idea_id)
    await travel.place_by_id(connection, place_id)
    await connection.execute(
        text("""
            insert into travel.travel_idea_place (idea_id, place_id, position, note)
            values (:idea, :place,
                    (select coalesce(max(position) + 1, 0) from travel.travel_idea_place
                     where idea_id = :idea), :note)
            on conflict (idea_id, place_id) do update
                set note = coalesce(excluded.note, travel_idea_place.note)
        """),
        {"idea": idea_id, "place": place_id, "note": note},
    )
    await _touch(connection, idea_id)
    return await idea(connection, idea_id)


async def remove_place(connection: AsyncConnection, idea_id: str, idea_place_id: str) -> Idea:
    deleted = await connection.execute(
        text("delete from travel.travel_idea_place where id = :id and idea_id = :idea"),
        {"id": idea_place_id, "idea": idea_id},
    )
    if deleted.rowcount == 0:
        raise travel.NotFound(f"destino {idea_place_id}")
    await _touch(connection, idea_id)
    return await idea(connection, idea_id)


async def plan_idea(
    connection: AsyncConnection,
    idea_id: str,
    starts_on: date,
    ends_on: date,
    title: str | None = None,
    travellers: int = 1,
) -> travel.Trip:
    found = await idea(connection, idea_id)
    request = travel.TripIn(
        title=title or found.title,
        starts_on=starts_on,
        ends_on=ends_on,
        travellers=travellers,
        tags=found.tags,
        notes=found.notes,
        status="plan",
        budget_eur=Decimal(str(found.budget_eur)) if found.budget_eur is not None else None,
    )
    trip = await travel.create_trip(connection, request)
    await connection.execute(
        text(
            "update travel.travel_trip set idea_id = :idea, space_id = cast(:space as uuid) "
            "where id = :trip"
        ),
        {"idea": idea_id, "trip": trip.id, "space": found.space_id},
    )
    for destination in found.places:
        await itinerary.add_block(
            connection,
            trip.id,
            itinerary.BlockIn(title=destination.place.name, place_id=destination.place.id),
        )
    await travel._touch(connection, trip.id)
    return await travel.trip(connection, trip.id)


async def share_idea(connection: AsyncConnection, idea_id: str, space_id: str | None) -> Idea:
    found = await idea(connection, idea_id)
    if not found.mine:
        raise travel.Conflict(
            "solo quien creó la idea la comparte o deja de compartirla", "NOT_OWNER"
        )
    if found.space_id == space_id:
        return found
    if found.space_id is not None:
        await connection.execute(
            text(
                f"update travel.travel_idea_place set space_id = null, user_id = {ME} "
                "where idea_id = :id"
            ),
            {"id": idea_id},
        )
        foreign = (
            await connection.execute(
                text(f"""
                    select ip.id::text as idea_place_id, p.name, p.display_name, p.lat, p.lon,
                           p.country_code, p.region_code, p.kind, p.osm_type, p.osm_id,
                           p.category
                    from travel.travel_idea_place ip
                    join travel.travel_place p on p.id = ip.place_id
                    where ip.idea_id = :id and p.user_id <> {ME}
                """),
                {"id": idea_id},
            )
        ).all()
        for row in foreign:
            mine = await travel.save_place(
                connection,
                travel.PlaceIn(
                    name=row.name,
                    display_name=row.display_name,
                    lat=row.lat,
                    lon=row.lon,
                    country_code=row.country_code,
                    region_code=row.region_code,
                    kind=row.kind,
                    osm_type=row.osm_type,
                    osm_id=row.osm_id,
                    category=row.category,
                ),
            )
            await connection.execute(
                text("update travel.travel_idea_place set place_id = :new where id = :id"),
                {"id": row.idea_place_id, "new": mine.id},
            )
    await connection.execute(
        text("update travel.travel_idea set space_id = cast(:space as uuid) where id = :id"),
        {"id": idea_id, "space": space_id},
    )
    await _touch(connection, idea_id)
    return await idea(connection, idea_id)
