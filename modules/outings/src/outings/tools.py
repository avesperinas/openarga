from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import date
from typing import Annotated, Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from arga_tenancy import SPACES_GUC, format_spaces
from outings import agenda, by_hand, explore, foryou, hub, spaces, wishes
from outings.common import Conflict, NotFound

MODULE = "outings"
WRITE_ROLE = f"mod_{MODULE}"
READ_ROLE = f"mod_{MODULE}_read"


def role_for_scopes(scopes: set[str]) -> str | None:
    if f"{MODULE}:write" in scopes:
        return WRITE_ROLE
    if f"{MODULE}:read" in scopes:
        return READ_ROLE
    return None


def _event(one: agenda.Event, full: bool = False) -> dict[str, Any]:
    out: dict[str, Any] = {
        "event_id": one.id,
        "title": one.title,
        "starts_on": one.starts_on.isoformat(),
        "ends_on": one.ends_on.isoformat(),
        "time": one.time,
        "venue": one.venue,
        "town": one.town,
        "category": one.category,
        "summary": one.summary,
        "in_calendar": one.in_calendar,
        "saved_as_wish": one.wish_id,
    }
    if one.programme:
        out["programme"] = one.programme
    if one.highlight:
        out["highlight"] = True
    if full:
        out["links"] = [link.model_dump() for link in one.links]
    return out


def _wish(one: wishes.Wish) -> dict[str, Any]:
    return {
        "wish_id": one.id,
        "kind": one.kind,
        "name": one.name,
        "text": one.body,
        "place": one.place.model_dump(exclude_none=True) if one.place else None,
        "dates": (
            {"from": one.starts_on.isoformat(), "to": (one.ends_on or one.starts_on).isoformat()}
            if one.starts_on
            else None
        ),
        "has_photo": one.has_photo,
        "done_on": one.done_at.date().isoformat() if one.done_at else None,
        "shared": one.space_id is not None,
        "mine": one.mine,
    }


class GetEvent(BaseModel):
    event_id: str


async def get_event(connection: AsyncConnection, arguments: GetEvent) -> dict[str, Any]:
    return _event(await agenda.event(connection, arguments.event_id), full=True)


class GetWishes(BaseModel):
    kind: wishes.Kind | None = None
    query: Annotated[str, Field(max_length=100)] | None = Field(
        default=None, description="Part of the name, the text or the place."
    )
    include_archived: bool = Field(default=False, description="Also the done ones (the Archive).")


async def get_wishes(connection: AsyncConnection, arguments: GetWishes) -> dict[str, Any]:
    archived = None if arguments.include_archived else False
    found = await wishes.wishes(connection, arguments.kind, archived, arguments.query)
    return {"wishes": [_wish(one) for one in found]}


class FindPlace(BaseModel):
    query: Annotated[str, Field(min_length=2, max_length=120)] = Field(
        description="The place's name, with its town or country if it could be confused."
    )


async def find_place(_connection: AsyncConnection, arguments: FindPlace) -> dict[str, Any]:
    found = await hub.search(arguments.query)
    return {
        "candidates": [
            wishes.place_of(one).model_dump(exclude_none=True)
            for one in found.get("candidates", [])
        ],
        "failed": found.get("failed", []),
    }


class AddWish(BaseModel):
    kind: wishes.Kind
    name: Annotated[str, Field(min_length=1, max_length=120)]
    text: Annotated[str, Field(max_length=4000)] | None = None
    place: wishes.Place | None = Field(
        default=None,
        description='A find_place candidate as is, or only {"name": ...} if it cannot be located.',
    )


async def add_wish(connection: AsyncConnection, arguments: AddWish) -> dict[str, Any]:
    created = await wishes.add(
        connection,
        wishes.WishIn(
            kind=arguments.kind, name=arguments.name, body=arguments.text, place=arguments.place
        ),
        source="tool",
    )
    return _wish(created)


class SaveEvent(BaseModel):
    event_id: str


async def save_event(connection: AsyncConnection, arguments: SaveEvent) -> dict[str, Any]:
    created = await agenda.save(connection, arguments.event_id, source="tool")
    return _wish(await wishes.wish(connection, created))


class SendToCalendar(BaseModel):
    event_id: str
    on: bool = Field(default=True, description="false takes it out of Planner.")


async def send_to_calendar(
    connection: AsyncConnection, arguments: SendToCalendar
) -> dict[str, Any]:
    return _event(await agenda.to_calendar(connection, arguments.event_id, arguments.on))


class UpdateWish(BaseModel):
    wish_id: str
    kind: wishes.Kind | None = None
    name: Annotated[str, Field(min_length=1, max_length=120)] | None = None
    text: Annotated[str, Field(max_length=4000)] | None = None
    place: wishes.Place | None = None


async def update_wish(connection: AsyncConnection, arguments: UpdateWish) -> dict[str, Any]:
    sent = arguments.model_fields_set - {"wish_id"}
    if not sent:
        raise Conflict("nothing to change was sent", "INVALID")
    fields = {
        "kind": arguments.kind,
        "name": arguments.name,
        "body": arguments.text,
        "place": arguments.place,
    }
    renamed = {"text": "body"}
    patch = wishes.WishPatch(
        **{renamed.get(key, key): fields[renamed.get(key, key)] for key in sent}
    )
    return _wish(await wishes.update(connection, arguments.wish_id, patch))


class WishId(BaseModel):
    wish_id: str


async def mark_wish_done(connection: AsyncConnection, arguments: WishId) -> dict[str, Any]:
    return _wish(await wishes.mark_done(connection, arguments.wish_id))


async def restore_wish(connection: AsyncConnection, arguments: WishId) -> dict[str, Any]:
    return _wish(await wishes.restore(connection, arguments.wish_id))


class DeleteWish(BaseModel):
    wish_id: str
    name: Annotated[str, Field(min_length=1, max_length=120)] = Field(
        description="The wish's exact name: if it does not match, nothing is deleted."
    )


async def delete_wish(connection: AsyncConnection, arguments: DeleteWish) -> dict[str, Any]:
    gone = await wishes.remove(connection, arguments.wish_id, arguments.name)
    return {"deleted": gone.id, "name": gone.name}


class ShareWish(BaseModel):
    wish_id: str
    space: Annotated[str, Field(min_length=1, max_length=80)] | None = Field(
        description="The name of the OpenArga space to share it with, or null to make it only "
        "yours again."
    )


async def share_wish(connection: AsyncConnection, arguments: ShareWish) -> dict[str, Any]:
    space_id = None
    if arguments.space is not None:
        try:
            mine = await spaces.of_caller()
        except spaces.Unavailable as error:
            raise Conflict(f"cannot read your spaces: {error}", "UNAVAILABLE") from error
        wanted = arguments.space.strip().casefold()
        match = [one for one in mine if one["name"].strip().casefold() == wanted]
        if not match:
            names = ", ".join(f"“{one['name']}”" for one in mine) or "none"
            raise Conflict(
                f"you are in no space called “{arguments.space}”; yours: {names}",
                "NOT_FOUND",
            )
        space_id = match[0]["id"]
        ids = tuple(UUID(one["id"]) for one in mine)
        await connection.execute(
            text("select set_config(:guc, :spaces, true)"),
            {"guc": SPACES_GUC, "spaces": "{" + format_spaces(ids) + "}"},
        )
    return _wish(await wishes.share(connection, arguments.wish_id, space_id))


class AddEvents(BaseModel):
    events: Annotated[list[by_hand.EventIn], Field(min_length=1, max_length=60)]


async def add_events(connection: AsyncConnection, arguments: AddEvents) -> dict[str, Any]:
    found = await by_hand.add(connection, arguments.events)
    counts: dict[str, int] = {}
    for one in found:
        counts[one.outcome] = counts.get(one.outcome, 0) + 1
    return {"summary": counts, "events": [one.model_dump(exclude_none=True) for one in found]}


class FindEvents(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    query: Annotated[str, Field(max_length=100)] | None = Field(
        default=None,
        description="Words to look for in the title, the venue, the town or the programme.",
    )
    when: explore.When = Field(
        default="quarter",
        description="weekend, week (7 days), month (30), quarter (three months) or year.",
    )
    zone: explore.Zone | None = Field(
        default=None,
        description="near (the home area's core towns) or region (the rest). Without it, all.",
    )
    date_from: date | None = Field(
        default=None, alias="from", description="From this day, with `to`: instead of `when`."
    )
    date_to: date | None = Field(default=None, alias="to", description="Until this day.")
    category: agenda.Category | None = None
    town: Annotated[str, Field(max_length=80)] | None = Field(
        default=None, description="Only what is on in this town."
    )
    best_first: bool = Field(
        default=False,
        description="Best first (the near area, the big things, what interests) instead of by "
        "date.",
    )
    limit: Annotated[int, Field(ge=1, le=100)] = 60
    for_you: bool = Field(
        default=False,
        description="Only what the person may like in the next 45 days, each with its reason "
        "(an interest, something big in the near area, a wish nearby). Ignores the other filters.",
    )


async def find_events(connection: AsyncConnection, arguments: FindEvents) -> dict[str, Any]:
    if arguments.for_you:
        picked = await foryou.picks(connection)
        return {
            "total": len(picked),
            "events": [
                {**_event(one.event), "zone": one.event.zone, "why": one.reasons}
                for one in picked[: arguments.limit]
            ],
        }
    dated = arguments.date_from is not None and arguments.date_to is not None
    found = await explore.search(
        connection,
        arguments.query,
        arguments.when,
        first=arguments.date_from if dated else None,
        last=arguments.date_to if dated else None,
        town=arguments.town,
        zone=arguments.zone,
        category=arguments.category,
        sort="best" if arguments.best_first else "date",
        limit=arguments.limit,
    )
    return {
        "from": found.first.isoformat(),
        "to": found.last.isoformat(),
        "total": found.total,
        "events": [{**_event(one), "zone": one.zone} for one in found.events],
    }


class NoArguments(BaseModel):
    pass


async def get_agenda_brief(connection: AsyncConnection, _arguments: NoArguments) -> dict[str, Any]:
    return {"brief": await by_hand.brief(connection)}


class HideEvents(BaseModel):
    event_ids: Annotated[list[UUID], Field(min_length=1, max_length=100)]


async def hide_events(connection: AsyncConnection, arguments: HideEvents) -> dict[str, Any]:
    hidden, missing = [], []
    for event_id in map(str, arguments.event_ids):
        try:
            await explore.dismiss(connection, event_id)
            hidden.append(event_id)
        except NotFound:
            missing.append(event_id)
    return {"hidden": len(hidden), "not_found": missing}


class Interest(BaseModel):
    kind: Literal["like", "mute"] = Field(
        description="like: it interests you and goes up in Explore; mute: it shows nowhere."
    )
    term: Annotated[str, Field(min_length=2, max_length=80)] = Field(
        description="A word or a name: jazz, a venue, a festival."
    )


async def add_interest(connection: AsyncConnection, arguments: Interest) -> dict[str, Any]:
    found = await explore.add_interest(
        connection, explore.InterestIn(kind=arguments.kind, term=arguments.term)
    )
    return found.model_dump()


async def remove_interest(connection: AsyncConnection, arguments: Interest) -> dict[str, Any]:
    folded = agenda.fold(arguments.term)
    for one in await explore.interests(connection):
        if one.kind == arguments.kind and agenda.fold(one.term) == folded:
            return {"removed": (await explore.remove_interest(connection, one.id)).model_dump()}
    raise Conflict(f"there is no {arguments.kind} “{arguments.term}”", "NOT_FOUND")


@dataclass(frozen=True)
class Tool:
    arguments: type[BaseModel]
    run: Callable[[AsyncConnection, Any], Awaitable[Any]]


TOOLS: dict[str, Tool] = {
    "get_event": Tool(GetEvent, get_event),
    "get_wishes": Tool(GetWishes, get_wishes),
    "find_place": Tool(FindPlace, find_place),
    "add_wish": Tool(AddWish, add_wish),
    "save_event": Tool(SaveEvent, save_event),
    "send_to_calendar": Tool(SendToCalendar, send_to_calendar),
    "update_wish": Tool(UpdateWish, update_wish),
    "mark_wish_done": Tool(WishId, mark_wish_done),
    "restore_wish": Tool(WishId, restore_wish),
    "delete_wish": Tool(DeleteWish, delete_wish),
    "share_wish": Tool(ShareWish, share_wish),
    "add_events": Tool(AddEvents, add_events),
    "find_events": Tool(FindEvents, find_events),
    "get_agenda_brief": Tool(NoArguments, get_agenda_brief),
    "hide_events": Tool(HideEvents, hide_events),
    "add_interest": Tool(Interest, add_interest),
    "remove_interest": Tool(Interest, remove_interest),
}
