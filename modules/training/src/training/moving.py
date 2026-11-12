from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncConnection

import arga_contracts as contracts
from arga_agenda import KEY
from training import activities, agenda, training


async def move(connection: AsyncConnection, asked: contracts.AgendaMove) -> dict[str, Any]:
    module, kind, object_id = asked.uid.split(":", 2)
    if module != "training" or kind not in ("session", "activity"):
        raise training.NotFound(asked.uid)
    if asked.all_day:
        raise training.Conflict("en Training todo lleva hora")
    if kind == "activity":
        moved = await activities.move(connection, object_id, asked.start, asked.end)
        return contracts.agenda_moved(agenda.activity_payload(moved)[KEY])
    await training.change_times(
        connection, object_id, training.Times(started_at=asked.start, ended_at=asked.end)
    )
    row = await agenda.session_row(connection, object_id)
    return contracts.agenda_moved(agenda.payload(row)[KEY])
