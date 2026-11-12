from __future__ import annotations

import asyncio
import base64
import binascii
import io
from dataclasses import dataclass

from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from travel import hub, travel

LIMIT = 12 * 1024 * 1024
SIDE = 1600
THUMB_SIDE = 480
PER_PASS = 3


class Credit(BaseModel):
    author: str | None
    license: str | None
    page: str


def _open(content: bytes):
    from PIL import Image, ImageOps, UnidentifiedImageError

    try:
        with Image.open(io.BytesIO(content)) as opened:
            image = ImageOps.exif_transpose(opened)
            image.load()
    except (UnidentifiedImageError, OSError) as error:
        raise travel.Conflict("eso no es una foto que se pueda leer", "INVALID_PHOTO") from error
    if image.mode not in ("RGB", "L"):
        from PIL import Image as Img

        background = Img.new("RGB", image.size, (255, 255, 255))
        background.paste(image, mask=image.getchannel("A") if "A" in image.getbands() else None)
        image = background
    return image


def _jpeg(image, side: int) -> bytes:
    copy = image.copy()
    copy.thumbnail((side, side))
    out = io.BytesIO()
    copy.convert("RGB").save(out, "JPEG", quality=84, optimize=True, progressive=True)
    return out.getvalue()


def icon(content: bytes, side: int) -> bytes:
    from PIL import ImageOps

    image = _open(content)
    square = ImageOps.fit(image, (side, side), centering=(0.5, 0.5))
    out = io.BytesIO()
    square.convert("RGB").save(out, "PNG", optimize=True)
    return out.getvalue()


@dataclass(frozen=True)
class Prepared:
    content: bytes
    thumb: bytes


def _prepare(content: bytes) -> Prepared:
    image = _open(content)
    return Prepared(_jpeg(image, SIDE), _jpeg(image, THUMB_SIDE))


async def prepare(content: bytes) -> Prepared:
    if not content:
        raise travel.Conflict("la foto llegó vacía", "INVALID_PHOTO")
    if len(content) > LIMIT:
        raise travel.Conflict("la foto pasa de 12 MB", "PHOTO_TOO_LARGE")
    return await asyncio.to_thread(_prepare, content)


async def set_cover(
    connection: AsyncConnection, trip_id: str, cover: Prepared, credit: Credit | None = None
) -> travel.Trip:
    await travel.trip(connection, trip_id)
    await connection.execute(
        text("""
            insert into travel.travel_cover
                (trip_id, content, content_type, thumb, credit_author, credit_license,
                 credit_page, space_id)
            values (cast(:id as uuid), :content, 'image/jpeg', :thumb, :author, :license, :page,
                    (select space_id from travel.travel_trip where id = cast(:id as uuid)))
            on conflict (trip_id) do update
            set content = excluded.content, content_type = excluded.content_type,
                thumb = excluded.thumb, credit_author = excluded.credit_author,
                credit_license = excluded.credit_license, credit_page = excluded.credit_page,
                updated_at = clock_timestamp()
        """),
        {
            "id": trip_id,
            "content": cover.content,
            "thumb": cover.thumb,
            "author": credit.author if credit else None,
            "license": credit.license if credit else None,
            "page": credit.page if credit else None,
        },
    )
    await travel._touch(connection, trip_id)
    return await travel.trip(connection, trip_id)


async def remove_cover(connection: AsyncConnection, trip_id: str) -> travel.Trip:
    await connection.execute(
        text("delete from travel.travel_cover where trip_id = cast(:id as uuid)"), {"id": trip_id}
    )
    await connection.execute(
        text(
            "update travel.travel_trip set cover_looked_at = coalesce(cover_looked_at, now()) "
            "where id = cast(:id as uuid)"
        ),
        {"id": trip_id},
    )
    await travel._touch(connection, trip_id)
    return await travel.trip(connection, trip_id)


async def content(connection: AsyncConnection, trip_id: str, size: str = "full") -> bytes:
    column = "thumb" if size == "thumb" else "content"
    found = await connection.scalar(
        text(f"select {column} from travel.travel_cover where trip_id = cast(:id as uuid)"),
        {"id": trip_id},
    )
    if found is None:
        raise travel.NotFound(f"portada del viaje {trip_id}")
    return bytes(found)


PENDING = text("""
    select t.id::text as id, t.title
    from travel.travel_trip t
    where t.cover_looked_at is null and t.archived_at is null
      and not exists (select 1 from travel.travel_cover c where c.trip_id = t.id)
    order by t.starts_on desc
    limit :limit
""")


def _destination(trip: travel.Trip) -> dict | None:
    stays = sorted(trip.stays, key=lambda one: -one.nights)
    place = stays[0].place if stays else (trip.visits[0].place if trip.visits else None)
    if place is None:
        return None
    body: dict = {"name": place.name, "place": place.display_name or place.name}
    if place.lat is not None and place.lon is not None:
        body |= {"lat": place.lat, "lon": place.lon}
    return body


async def fill(connection: AsyncConnection, limit: int = PER_PASS) -> int:
    placed = 0
    for row in (await connection.execute(PENDING, {"limit": limit})).all():
        found = await travel.trip(connection, row.id)
        asked = _destination(found)
        if asked is None:
            continue
        answer = await hub.place_photo(asked)
        if answer.get("failed"):
            break
        photo = answer.get("photo")
        if photo:
            try:
                await set_cover(
                    connection,
                    row.id,
                    await prepare(base64.b64decode(photo["content"], validate=True)),
                    Credit(
                        author=photo.get("author"),
                        license=photo.get("license"),
                        page=photo["page"],
                    ),
                )
                placed += 1
            except (KeyError, ValueError, binascii.Error, travel.Conflict):
                pass
        await connection.execute(
            text("update travel.travel_trip set cover_looked_at = now() where id = :id"),
            {"id": row.id},
        )
    return placed
