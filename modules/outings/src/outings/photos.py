from __future__ import annotations

import base64
import binascii
from datetime import UTC, datetime

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from outings import hub, wishes

KINDS = ("getaway", "trip")
PER_PASS = 3
FINDER = datetime(2026, 10, 3, 16, 20, tzinfo=UTC)

PENDING = text("""
    select w.id::text as id, w.name, w.place_name, w.osm_ref, w.lat, w.lon
    from outings.outings_wish w
    where w.kind in ('getaway', 'trip') and w.done_at is null and w.place_name is not null
      and (w.place_photo_at is null
           or (w.place_photo_none is not false and w.place_photo_at < :finder))
      and not exists (select 1 from outings.outings_photo p where p.wish_id = w.id)
    order by w.created_at
    limit :limit
""")

LOOKED = text("""
    update outings.outings_wish set place_photo_at = now(), place_photo_none = :none
    where id = cast(:id as uuid)
""")


def asked(row) -> dict:
    body = {"name": row.name, "place": row.place_name}
    if row.osm_ref:
        body["osm_ref"] = row.osm_ref
    if row.lat is not None and row.lon is not None:
        body |= {"lat": row.lat, "lon": row.lon}
    return body


async def fill(connection: AsyncConnection, limit: int = PER_PASS) -> int:
    rows = (await connection.execute(PENDING, {"limit": limit, "finder": FINDER})).all()
    placed = 0
    for row in rows:
        try:
            answer = await hub.place_photo(asked(row))
        except hub.Refused:
            break
        found = answer.get("photo")
        none = True
        if found:
            try:
                content = base64.b64decode(found["content"], validate=True)
                credit = wishes.PhotoCredit(
                    author=found.get("author"), license=found.get("license"), page=found["page"]
                )
                await wishes.set_photo(connection, row.id, await wishes.shrink(content), credit)
                placed += 1
                none = False
            except (KeyError, ValueError, binascii.Error, wishes.Conflict):
                pass
        await connection.execute(LOOKED, {"id": row.id, "none": none})
    return placed
