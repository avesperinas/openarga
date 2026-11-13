from __future__ import annotations

import asyncio
import io
from dataclasses import dataclass
from datetime import date, datetime
from typing import Annotated, Any, Literal

from pydantic import BaseModel, Field, field_validator
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from arga_tenancy import CURRENT_USER_SQL as ME
from outings.common import Conflict, NotFound, zone

Kind = Literal["eat", "plan", "getaway", "trip"]
PHOTO_LIMIT = 8 * 1024 * 1024
PHOTO_SIDE = 1600
THUMB_SIDE = 360


def _clean(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = " ".join(value.split())
    return cleaned or None


class Place(BaseModel):
    name: Annotated[str, Field(min_length=1, max_length=200)]
    detail: Annotated[str, Field(max_length=300)] | None = None
    town: Annotated[str, Field(max_length=120)] | None = None
    country: Annotated[str, Field(max_length=120)] | None = None
    country_code: Annotated[str, Field(pattern=r"^[A-Za-z]{2}$")] | None = None
    lat: Annotated[float, Field(ge=-90, le=90)] | None = None
    lon: Annotated[float, Field(ge=-180, le=180)] | None = None
    osm_ref: Annotated[str, Field(pattern=r"^(node|way|relation)/[0-9]+$")] | None = None

    @field_validator("name", "detail", "town", "country")
    @classmethod
    def _tidy(cls, value: str | None) -> str | None:
        return _clean(value)

    @field_validator("country_code")
    @classmethod
    def _upper(cls, value: str | None) -> str | None:
        return value.upper() if value else None


def place_of(candidate: dict[str, Any]) -> Place:
    name = str(candidate.get("name") or "").strip()
    display = str(candidate.get("display_name") or "")
    parts = [part.strip() for part in display.split(",") if part.strip()]
    words = [part for part in parts if part != name and not part.replace(" ", "").isdigit()]
    town = candidate.get("town") or (words[0] if len(words) >= 3 else None)
    country = candidate.get("country") or (words[-1] if words else None)
    detail = ", ".join(words[:2]) if words else None
    osm_type, osm_id = candidate.get("osm_type"), candidate.get("osm_id")
    return Place(
        name=name or display or "?",
        detail=detail,
        town=town,
        country=country,
        country_code=candidate.get("country_code"),
        lat=candidate.get("lat"),
        lon=candidate.get("lon"),
        osm_ref=f"{osm_type}/{osm_id}"
        if osm_type in ("node", "way", "relation") and osm_id
        else None,
    )


class WishIn(BaseModel):
    kind: Kind
    name: Annotated[str, Field(min_length=1, max_length=120)]
    body: Annotated[str, Field(max_length=4000)] | None = None
    place: Place | None = None

    @field_validator("name")
    @classmethod
    def _name(cls, value: str) -> str:
        cleaned = _clean(value)
        if not cleaned:
            raise ValueError("the name cannot be empty")
        return cleaned

    @field_validator("body")
    @classmethod
    def _body(cls, value: str | None) -> str | None:
        return value.strip() or None if value is not None else None


class WishPatch(BaseModel):
    kind: Kind | None = None
    name: Annotated[str, Field(min_length=1, max_length=120)] | None = None
    body: Annotated[str, Field(max_length=4000)] | None = None
    place: Place | None = None

    @field_validator("name")
    @classmethod
    def _name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = _clean(value)
        if not cleaned:
            raise ValueError("the name cannot be empty")
        return cleaned

    @field_validator("body")
    @classmethod
    def _body(cls, value: str | None) -> str | None:
        return value.strip() or None if value is not None else None


class PhotoCredit(BaseModel):
    author: str | None
    license: str | None
    page: str


class Wish(BaseModel):
    id: str
    kind: Kind
    name: str
    body: str | None
    place: Place | None
    has_photo: bool
    photo_version: str | None
    photo_credit: PhotoCredit | None = None
    done_at: datetime | None
    event_id: str | None = None
    starts_on: date | None = None
    ends_on: date | None = None
    source: str
    created_at: datetime
    updated_at: datetime
    space_id: str | None = None
    mine: bool = True


COLUMNS = f"""
    w.id::text as id, w.kind, w.name, w.body, w.place_name, w.place_detail, w.place_town,
    w.place_country, w.place_country_code, w.lat, w.lon, w.osm_ref, w.done_at, w.source,
    w.event_id::text as event_id, w.starts_on, w.ends_on,
    w.created_at, w.updated_at, w.space_id::text as space_id, w.user_id = {ME} as mine,
    p.updated_at as photo_at, p.credit_author, p.credit_license, p.credit_page
"""
FROM = "from outings.outings_wish w left join outings.outings_photo p on p.wish_id = w.id"


def _wish(row: Any) -> Wish:
    place = None
    if row.place_name:
        place = Place(
            name=row.place_name,
            detail=row.place_detail,
            town=row.place_town,
            country=row.place_country,
            country_code=row.place_country_code,
            lat=row.lat,
            lon=row.lon,
            osm_ref=row.osm_ref,
        )
    return Wish(
        id=row.id,
        kind=row.kind,
        name=row.name,
        body=row.body,
        place=place,
        has_photo=row.photo_at is not None,
        photo_version=str(int(row.photo_at.timestamp())) if row.photo_at else None,
        photo_credit=PhotoCredit(
            author=row.credit_author, license=row.credit_license, page=row.credit_page
        )
        if row.credit_page
        else None,
        done_at=row.done_at,
        event_id=row.event_id,
        starts_on=row.starts_on,
        ends_on=row.ends_on,
        source=row.source,
        created_at=row.created_at,
        updated_at=row.updated_at,
        space_id=row.space_id,
        mine=bool(row.mine),
    )


async def wishes(
    connection: AsyncConnection,
    kind: str | None = None,
    archived: bool | None = False,
    query: str | None = None,
) -> list[Wish]:
    where = ["true"]
    params: dict[str, Any] = {}
    if kind:
        where.append("w.kind = :kind")
        params["kind"] = kind
    if archived is True:
        where.append("w.done_at is not null")
    elif archived is False:
        where.append("w.done_at is null")
    if query:
        where.append(
            "(w.name ilike :query or coalesce(w.body, '') ilike :query "
            "or coalesce(w.place_name, '') ilike :query or coalesce(w.place_town, '') ilike :query)"
        )
        params["query"] = f"%{query.strip()}%"
    order = "w.done_at desc" if archived is True else "w.created_at desc"
    rows = await connection.execute(
        text(f"select {COLUMNS} {FROM} where {' and '.join(where)} order by {order}, w.id"), params
    )
    return [_wish(row) for row in rows]


async def wish(connection: AsyncConnection, wish_id: str) -> Wish:
    row = (
        await connection.execute(
            text(f"select {COLUMNS} {FROM} where w.id = cast(:id as uuid)"), {"id": wish_id}
        )
    ).one_or_none()
    if row is None:
        raise NotFound(f"wish {wish_id}")
    return _wish(row)


def _place_params(place: Place | None) -> dict[str, Any]:
    return {
        "place_name": place.name if place else None,
        "place_detail": place.detail if place else None,
        "place_town": place.town if place else None,
        "place_country": place.country if place else None,
        "place_country_code": place.country_code if place else None,
        "lat": place.lat if place and place.lon is not None else None,
        "lon": place.lon if place and place.lat is not None else None,
        "osm_ref": place.osm_ref if place else None,
    }


INSERT = text("""
    insert into outings.outings_wish
        (kind, name, body, place_name, place_detail, place_town, place_country,
         place_country_code, lat, lon, osm_ref, source)
    values (:kind, :name, :body, :place_name, :place_detail, :place_town, :place_country,
            :place_country_code, :lat, :lon, :osm_ref, :source)
    returning id::text
""")


async def add(connection: AsyncConnection, request: WishIn, source: str = "app") -> Wish:
    created = await connection.scalar(
        INSERT,
        {
            "kind": request.kind,
            "name": request.name,
            "body": request.body,
            "source": source,
            **_place_params(request.place),
        },
    )
    return await wish(connection, created)


async def update(connection: AsyncConnection, wish_id: str, patch: WishPatch) -> Wish:
    sent = patch.model_fields_set
    sets: list[str] = []
    params: dict[str, Any] = {"id": wish_id}
    for field in ("kind", "name"):
        if field in sent and getattr(patch, field) is not None:
            sets.append(f"{field} = :{field}")
            params[field] = getattr(patch, field)
    if "body" in sent:
        sets.append("body = :body")
        params["body"] = patch.body
    if "place" in sent:
        place = _place_params(patch.place)
        sets.extend(f"{column} = :{column}" for column in place)
        params.update(place)
        sets.append("place_photo_at = null")
    if not sets:
        return await wish(connection, wish_id)
    updated = await connection.execute(
        text(
            f"update outings.outings_wish set {', '.join(sets)}, updated_at = now() "
            "where id = cast(:id as uuid)"
        ),
        params,
    )
    if updated.rowcount == 0:
        raise NotFound(f"wish {wish_id}")
    return await wish(connection, wish_id)


async def mark_done(connection: AsyncConnection, wish_id: str) -> Wish:
    updated = await connection.execute(
        text("""
            update outings.outings_wish
            set done_at = coalesce(done_at, now()), updated_at = now()
            where id = cast(:id as uuid)
        """),
        {"id": wish_id},
    )
    if updated.rowcount == 0:
        raise NotFound(f"wish {wish_id}")
    return await wish(connection, wish_id)


async def restore(connection: AsyncConnection, wish_id: str) -> Wish:
    updated = await connection.execute(
        text("""
            update outings.outings_wish set done_at = null, updated_at = now()
            where id = cast(:id as uuid)
        """),
        {"id": wish_id},
    )
    if updated.rowcount == 0:
        raise NotFound(f"wish {wish_id}")
    return await wish(connection, wish_id)


async def remove(connection: AsyncConnection, wish_id: str, name: str | None = None) -> Wish:
    found = await wish(connection, wish_id)
    if name is not None and name.strip() != found.name:
        raise Conflict(f"that wish is called “{found.name}”", "NAME_MISMATCH")
    if found.space_id is not None and not found.mine:
        raise Conflict("someone else shared this wish: only they can delete it", "NOT_OWNER")
    await connection.execute(
        text("delete from outings.outings_wish where id = cast(:id as uuid)"), {"id": wish_id}
    )
    return found


def _shrink(content: bytes) -> tuple[bytes, str, bytes]:
    from PIL import Image, ImageOps, UnidentifiedImageError

    try:
        with Image.open(io.BytesIO(content)) as opened:
            image = ImageOps.exif_transpose(opened)
            image.load()
    except (UnidentifiedImageError, OSError) as error:
        raise Conflict("that is not a readable photo", "INVALID_PHOTO") from error

    def encode(side: int) -> bytes:
        copy = image.copy()
        copy.thumbnail((side, side))
        if copy.mode not in ("RGB", "L"):
            background = Image.new("RGB", copy.size, (255, 255, 255))
            background.paste(copy, mask=copy.getchannel("A") if "A" in copy.getbands() else None)
            copy = background
        out = io.BytesIO()
        copy.save(out, "JPEG", quality=84, optimize=True, progressive=True)
        return out.getvalue()

    return encode(PHOTO_SIDE), "image/jpeg", encode(THUMB_SIDE)


@dataclass(frozen=True)
class Shrunk:
    content: bytes
    kind: str
    thumb: bytes


async def shrink(content: bytes) -> Shrunk:
    if not content:
        raise Conflict("the photo arrived empty", "INVALID_PHOTO")
    if len(content) > PHOTO_LIMIT:
        raise Conflict("la foto pasa de 8 MB", "PHOTO_TOO_LARGE")
    return Shrunk(*await asyncio.to_thread(_shrink, content))


async def set_photo(
    connection: AsyncConnection, wish_id: str, shrunk: Shrunk, credit: PhotoCredit | None = None
) -> Wish:
    await wish(connection, wish_id)
    photo, kind, thumb = shrunk.content, shrunk.kind, shrunk.thumb
    await connection.execute(
        text("""
            insert into outings.outings_photo
                (wish_id, content, content_type, thumb, credit_author, credit_license, credit_page,
                 space_id)
            values (cast(:id as uuid), :content, :kind, :thumb, :author, :license, :page,
                    (select space_id from outings.outings_wish where id = cast(:id as uuid)))
            on conflict (wish_id) do update
            set content = excluded.content, content_type = excluded.content_type,
                thumb = excluded.thumb, credit_author = excluded.credit_author,
                credit_license = excluded.credit_license, credit_page = excluded.credit_page,
                updated_at = clock_timestamp()
        """),
        {
            "id": wish_id,
            "content": photo,
            "kind": kind,
            "thumb": thumb,
            "author": credit.author[:200] if credit and credit.author else None,
            "license": credit.license[:80] if credit and credit.license else None,
            "page": credit.page if credit else None,
        },
    )
    await connection.execute(
        text("update outings.outings_wish set updated_at = now() where id = cast(:id as uuid)"),
        {"id": wish_id},
    )
    return await wish(connection, wish_id)


async def remove_photo(connection: AsyncConnection, wish_id: str) -> Wish:
    await wish(connection, wish_id)
    await connection.execute(
        text("delete from outings.outings_photo where wish_id = cast(:id as uuid)"),
        {"id": wish_id},
    )
    return await wish(connection, wish_id)


async def photo(
    connection: AsyncConnection, wish_id: str, thumb: bool = False
) -> tuple[bytes, str]:
    row = (
        await connection.execute(
            text(
                "select content, content_type, thumb from outings.outings_photo "
                "where wish_id = cast(:id as uuid)"
            ),
            {"id": wish_id},
        )
    ).one_or_none()
    if row is None:
        raise NotFound(f"photo of wish {wish_id}")
    if thumb:
        return bytes(row.thumb), "image/jpeg"
    return bytes(row.content), row.content_type


async def share(connection: AsyncConnection, wish_id: str, space_id: str | None) -> Wish:
    found = await wish(connection, wish_id)
    if not found.mine:
        raise Conflict("only whoever noted the wish can share or unshare it", "NOT_OWNER")
    if found.space_id == space_id:
        return found
    owner = f", user_id = {ME}" if space_id is None else ""
    await connection.execute(
        text(
            f"update outings.outings_photo set space_id = cast(:space as uuid){owner} "
            "where wish_id = cast(:id as uuid)"
        ),
        {"id": wish_id, "space": space_id},
    )
    await connection.execute(
        text(
            "update outings.outings_wish set space_id = cast(:space as uuid), updated_at = now() "
            "where id = cast(:id as uuid)"
        ),
        {"id": wish_id, "space": space_id},
    )
    return await wish(connection, wish_id)


def done_day(found: Wish) -> date | None:
    return found.done_at.astimezone(zone()).date() if found.done_at else None
