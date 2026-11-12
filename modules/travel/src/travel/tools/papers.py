from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncConnection

from travel import (
    documents,
)
from travel.tools.reading import GetTrip, _pick


async def get_trip_documents(connection: AsyncConnection, arguments: GetTrip) -> dict[str, Any]:
    picked = await _pick(connection, arguments.trip_id, arguments.title)
    if "trip" not in picked:
        return picked
    found = await documents.documents(connection, picked["trip"].id)
    return {
        "trip_id": picked["trip"].id,
        "documents": [
            {
                "name": one.name,
                "content_type": one.content_type,
                "size_kb": round(one.size / 1024),
                "for": {"type": one.link.type, "title": one.link.title} if one.link else None,
            }
            for one in found
        ],
    }
