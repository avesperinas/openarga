from __future__ import annotations

from collections import defaultdict
from datetime import date
from typing import Any

from sqlalchemy.ext.asyncio import AsyncConnection

import arga_contracts as contracts
from arga_contracts import records as write
from outings import wishes
from outings.words import say

APP = "outings"


def _id(found: wishes.Wish) -> str:
    return f"wish:{found.id}"


def _where(place: wishes.Place) -> str:
    parts = [place.name] + [
        part for part in (place.town, place.country) if part and part != place.name
    ]
    return ", ".join(parts)


def ficha(found: wishes.Wish) -> dict[str, Any]:
    done = wishes.done_day(found)
    properties: dict[str, Any] = {
        "kind": say(f"kind.{found.kind}").lower(),
        "status": say("record.done" if done else "record.pending"),
    }
    if found.place:
        properties["place"] = _where(found.place)
        if found.place.lat is not None and found.place.lon is not None:
            properties["coordinates"] = f"{found.place.lat:.5f}, {found.place.lon:.5f}"
    if done:
        properties["done"] = done.isoformat()
    first = " · ".join(
        part
        for part in (
            f"**{say(f'kind.{found.kind}')}**",
            _where(found.place) if found.place else None,
        )
        if part
    )
    return contracts.record(
        id=_id(found),
        title=found.name,
        kind=say("record.wish"),
        href=f"/outings/wishes/{found.id}",
        folder=say("record.wishes"),
        properties=properties,
        body=write.sections(
            first,
            found.body,
            say("record.done_on", date=done.isoformat()) if done else None,
        ),
    )


def days(found: list[wishes.Wish]) -> list[dict[str, Any]]:
    lines: dict[date, list[str]] = defaultdict(list)
    for one in sorted(found, key=lambda each: each.name.casefold()):
        done = wishes.done_day(one)
        if done is not None:
            lines[done].append(f"- {say('record.did', link=write.link(APP, _id(one), one.name))}")
    return [
        contracts.record(
            id=f"day:{day.isoformat()}",
            title=say("record.wishes"),
            kind=say("record.day"),
            href="/outings/wishes",
            day=day,
            body="\n".join(said),
        )
        for day, said in sorted(lines.items())
    ]


async def build(connection: AsyncConnection) -> list[dict[str, Any]]:
    found = await wishes.wishes(connection, archived=None)
    return [ficha(one) for one in found] + days(found)
