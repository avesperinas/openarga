from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, Field, model_validator
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from arga_tenancy import CURRENT_USER_SQL as ME
from travel import geo
from travel.travel.common import NotFound

PlaceCategory = Literal[
    "restaurant",
    "nightlife",
    "cafe",
    "market",
    "beach",
    "nature",
    "viewpoint",
    "culture",
    "castle",
    "town",
    "shopping",
    "parking",
    "lodging",
    "other",
]

CATEGORY_OF_KIND: dict[str, str] = {
    **dict.fromkeys(
        ("city", "town", "village", "hamlet", "suburb", "neighbourhood", "quarter", "municipality"),
        "town",
    ),
    **dict.fromkeys(("beach", "bay", "cove"), "beach"),
    **dict.fromkeys(
        (
            "peak",
            "mountain",
            "park",
            "nature_reserve",
            "forest",
            "wood",
            "natural",
            "cave_entrance",
            "waterfall",
            "lake",
            "island",
            "national_park",
            "protected_area",
            "garden",
        ),
        "nature",
    ),
    **dict.fromkeys(
        (
            "museum",
            "gallery",
            "attraction",
            "monument",
            "memorial",
            "artwork",
            "theatre",
            "place_of_worship",
            "church",
            "cathedral",
            "monastery",
            "arts_centre",
            "historic",
        ),
        "culture",
    ),
    **dict.fromkeys(
        ("castle", "ruins", "archaeological_site", "fort", "fortress", "city_wall", "tower"),
        "castle",
    ),
    "viewpoint": "viewpoint",
    **dict.fromkeys(("restaurant", "fast_food", "food_court"), "restaurant"),
    **dict.fromkeys(("cafe", "bakery", "ice_cream", "pastry"), "cafe"),
    **dict.fromkeys(("bar", "pub", "nightclub", "biergarten", "wine_bar"), "nightlife"),
    "marketplace": "market",
    **dict.fromkeys(("mall", "shop", "department_store", "supermarket", "boutique"), "shopping"),
    **dict.fromkeys(("parking", "parking_space", "parking_entrance"), "parking"),
    **dict.fromkeys(
        ("hotel", "hostel", "guest_house", "apartment", "motel", "camp_site", "chalet"), "lodging"
    ),
}


def category_of(kind: str | None) -> str | None:
    return CATEGORY_OF_KIND.get((kind or "").lower())


class PlaceIn(BaseModel):
    name: Annotated[str, Field(min_length=1, max_length=120)]
    display_name: Annotated[str | None, Field(max_length=300)] = None
    lat: Annotated[float | None, Field(ge=-90, le=90)] = None
    lon: Annotated[float | None, Field(ge=-180, le=180)] = None
    kind: Annotated[str | None, Field(max_length=40)] = None
    osm_type: Literal["node", "way", "relation"] | None = None
    osm_id: int | None = None
    country_code: Annotated[str | None, Field(max_length=2)] = None
    region_code: Annotated[str | None, Field(max_length=20)] = None
    category: PlaceCategory | None = None

    @model_validator(mode="after")
    def whole(self) -> PlaceIn:
        if (self.lat is None) != (self.lon is None):
            raise ValueError("un lugar lleva latitud y longitud, o ninguna de las dos")
        if (self.osm_type is None) != (self.osm_id is None):
            raise ValueError("el id de OpenStreetMap va con su tipo: node, way o relation")
        return self


class Place(BaseModel):
    id: str
    name: str
    display_name: str | None
    lat: float | None
    lon: float | None
    country_code: str | None
    region_code: str | None
    country: str | None
    region: str | None
    kind: str | None
    category: PlaceCategory | None = None


PLACE_COLUMNS = "id::text, name, display_name, lat, lon, country_code, region_code, kind, category"


def _place(row) -> Place:
    known = geo.names()
    return Place(
        id=row.id,
        name=row.name,
        display_name=row.display_name,
        lat=row.lat,
        lon=row.lon,
        country_code=row.country_code,
        region_code=row.region_code,
        country=known.get(row.country_code) if row.country_code else None,
        region=known.get(row.region_code) if row.region_code else None,
        kind=row.kind,
        category=row.category,
    )


async def save_place(connection: AsyncConnection, place: PlaceIn) -> Place:
    if place.osm_id is not None:
        found = (
            await connection.execute(
                text(
                    f"select {PLACE_COLUMNS} from travel.travel_place "
                    f"where osm_type = :type and osm_id = :id and user_id = {ME}"
                ),
                {"type": place.osm_type, "id": place.osm_id},
            )
        ).one_or_none()
        if found is not None:
            if place.category and found.category != place.category:
                return await set_category(connection, found.id, place.category)
            return _place(found)
    country, region = geo.locate(place.lat, place.lon, place.country_code, place.region_code)
    row = (
        await connection.execute(
            text(f"""
                insert into travel.travel_place
                    (name, display_name, lat, lon, country_code, region_code, kind, osm_type,
                     osm_id, category)
                values (:name, :display, :lat, :lon, :country, :region, :kind, :osm_type, :osm_id,
                        :category)
                returning {PLACE_COLUMNS}
            """),
            {
                "name": " ".join(place.name.split()),
                "display": place.display_name,
                "lat": place.lat,
                "lon": place.lon,
                "country": country,
                "region": region,
                "kind": place.kind,
                "category": place.category or category_of(place.kind),
                "osm_type": place.osm_type,
                "osm_id": place.osm_id,
            },
        )
    ).one()
    return _place(row)


async def places(connection: AsyncConnection, query: str | None = None) -> list[Place]:
    rows = (
        await connection.execute(
            text(f"""
                select p.id::text as id, p.name, p.display_name, p.lat, p.lon, p.country_code,
                       p.region_code, p.kind, p.category
                from travel.travel_place p
                left join lateral (
                    select count(*) as uses from (
                        select place_id from travel.travel_stay where place_id = p.id
                        union all select place_id from travel.travel_visit where place_id = p.id
                        union all select place_id from travel.travel_other_place
                            where place_id = p.id
                    ) u
                ) used on true
                where p.user_id = {ME}
                  and (cast(:query as text) is null or p.name ilike :like
                       or p.display_name ilike :like)
                order by used.uses desc, p.name
                limit 50
            """),
            {"query": query, "like": f"%{query}%" if query else None},
        )
    ).all()
    return [_place(row) for row in rows]


async def set_category(connection: AsyncConnection, place_id: str, category: str | None) -> Place:
    updated = await connection.execute(
        text("update travel.travel_place set category = :category where id = :id"),
        {"id": place_id, "category": category},
    )
    if updated.rowcount == 0:
        raise NotFound(f"lugar {place_id}")
    return await place_by_id(connection, place_id)


async def place_by_id(connection: AsyncConnection, place_id: str) -> Place:
    row = (
        await connection.execute(
            text(f"select {PLACE_COLUMNS} from travel.travel_place where id = :id"),
            {"id": place_id},
        )
    ).one_or_none()
    if row is None:
        raise NotFound(f"lugar {place_id}")
    return _place(row)
