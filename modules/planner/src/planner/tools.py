from __future__ import annotations

from collections.abc import Awaitable, Callable
from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from typing import Any, Literal
from uuid import UUID
from zoneinfo import ZoneInfo

from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

import arga_recurrence as recurrence
from planner import calendar, feeds, hub, zones

MODULE = "planner"
WRITE_ROLE = f"mod_{MODULE}"
READ_ROLE = f"mod_{MODULE}_read"

Scope = Literal["this", "following", "all"]


def role_for_scopes(scopes: set[str]) -> str | None:
    if f"{MODULE}:write" in scopes:
        return WRITE_ROLE
    if f"{MODULE}:read" in scopes:
        return READ_ROLE
    return None


def _at(value: datetime | date, tz: str, all_day: bool) -> datetime | date:
    if all_day:
        return value.date() if isinstance(value, datetime) else value
    if not isinstance(value, datetime):
        value = datetime.combine(value, time(9))
    return value.replace(tzinfo=ZoneInfo(tz)) if value.tzinfo is None else value


def _occurrence(one: calendar.Occurrence, names: dict[str, str]) -> dict[str, Any]:
    out: dict[str, Any] = {
        "event_id": one.event_id,
        "title": one.title,
        "calendar": names.get(one.calendar_id, one.calendar_id),
        "all_day": one.all_day,
        "start": one.start,
        "end": one.end,
        "tz": one.tz,
    }
    for name in ("location", "notes", "url"):
        if getattr(one, name):
            out[name] = getattr(one, name)
    if one.original_start is not None:
        out["original_start"] = one.original_start
        out["repeat"] = one.repeat
    return out


def _event(one: calendar.Event, names: dict[str, str]) -> dict[str, Any]:
    out: dict[str, Any] = {
        "event_id": one.id,
        "title": one.title,
        "calendar": names.get(one.calendar_id, one.calendar_id),
        "all_day": one.all_day,
        "start": one.start,
        "end": one.end,
        "tz": one.tz,
        "status": one.status,
        "repeat": one.repeat,
    }
    for name in ("location", "notes", "url"):
        if getattr(one, name):
            out[name] = getattr(one, name)
    return out


async def _names(connection: AsyncConnection) -> dict[str, str]:
    return {one.id: one.name for one in await calendar.calendars(connection, create_default=False)}


async def _read(connection: AsyncConnection, found: list[calendar.Occurrence]) -> dict[str, Any]:
    layers = await calendar.calendars(connection, create_default=False)
    names = {one.id: one.name for one in layers}
    background = {one.id for one in layers if one.display == "background"}
    events = [_occurrence(one, names) for one in found if one.calendar_id not in background]
    backgrounds = [_occurrence(one, names) for one in found if one.calendar_id in background]
    out: dict[str, Any] = {"events": events, "count": len(events)}
    if backgrounds:
        out["backgrounds"] = backgrounds
    return out


async def _calendar_id(connection: AsyncConnection, wanted: str | None) -> str | None:
    if wanted is None:
        return None
    found = await calendar.calendars(connection, create_default=False)
    for one in found:
        if wanted == one.id or wanted.strip().casefold() == one.name.casefold():
            return one.id
    raise calendar.Invalid(
        f"there is no layer “{wanted}”; the ones there are: {', '.join(one.name for one in found)}"
    )


class GetCalendars(BaseModel):
    pass


def _layer(one: calendar.Calendar, names: dict[str, str]) -> dict[str, Any]:
    out: dict[str, Any] = {
        "id": one.id,
        "name": one.name,
        "tone": one.tone,
        "origin": one.origin,
        "visible": one.visible,
        "display": one.display,
    }
    if one.days_off_from:
        out["days_off_from"] = [names[i] for i in one.days_off_from if i in names]
    return out


async def get_calendars(connection: AsyncConnection, arguments: GetCalendars) -> dict[str, Any]:
    layers = await calendar.calendars(connection, create_default=False)
    names = {one.id: one.name for one in layers}
    return {"calendars": [_layer(one, names) for one in layers]}


class GetEvents(BaseModel):
    start: datetime | date | None = Field(
        default=None,
        alias="from",
        description="From, included. A date is from its midnight. Required without `query`.",
    )
    end: datetime | date | None = Field(
        default=None,
        alias="to",
        description="To, excluded. A date is until its midnight. Required without `query`.",
    )
    query: str | None = Field(
        default=None,
        min_length=1,
        max_length=100,
        description="Words of the title, the place or the notes: searches every layer, between "
        "`from` and `to` if given.",
    )
    calendars: list[str] | None = Field(
        default=None, description="Layer ids or names. Without any, all. Not valid with `query`."
    )
    tz: str = Field(
        default_factory=zones.home_name,
        description="The zone of dates and times given without one. Without it, the person's.",
    )

    model_config = {"populate_by_name": True}


def _window(start: datetime | date, end: datetime | date, tz: str) -> tuple[datetime, datetime]:
    a = (
        _at(start, tz, False)
        if isinstance(start, datetime)
        else datetime.combine(start, time(), ZoneInfo(tz))
    )
    b = (
        _at(end, tz, False)
        if isinstance(end, datetime)
        else datetime.combine(end, time(), ZoneInfo(tz))
    )
    if a == b:
        b = a + timedelta(days=1)
    return a, b  # type: ignore[return-value]


async def get_events(connection: AsyncConnection, arguments: GetEvents) -> dict[str, Any]:
    if arguments.query is not None:
        if arguments.calendars:
            raise calendar.Invalid("`calendars` is not valid with `query`: every layer is searched")
        start = end = None
        if arguments.start is not None and arguments.end is not None:
            start, end = _window(arguments.start, arguments.end, arguments.tz)
        found = await calendar.search(connection, arguments.query, start, end)
        return await _read(connection, found)
    if arguments.start is None or arguments.end is None:
        raise calendar.Invalid("without `query`, `from` and `to` are needed")
    start, end = _window(arguments.start, arguments.end, arguments.tz)
    ids = None
    if arguments.calendars:
        ids = [await _calendar_id(connection, one) for one in arguments.calendars]
    found = await calendar.occurrences(connection, start, end, ids)  # type: ignore[arg-type]
    return await _read(connection, found)


class CreateEvent(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    start: datetime | date = Field(
        description="Timed, `2026-10-06T19:00` (in `tz`) or with a zone. All day, a date."
    )
    end: datetime | date | None = Field(
        default=None,
        description="Timed, the end; without it, an hour later. All day, the last day "
        "included; without it, a single day.",
    )
    all_day: bool = False
    tz: str = Field(
        default_factory=zones.home_name,
        description="The event's zone: the one that decides daylight saving changes. "
        "Without it, the person's.",
    )
    calendar: str | None = Field(
        default=None,
        description="Layer id or name. Without any, the first of your own that is not a "
        "background.",
    )
    location: str | None = Field(default=None, max_length=300)
    notes: str | None = Field(default=None, max_length=8000)
    url: str | None = Field(default=None, max_length=2000)
    repeat: recurrence.Rule | None = Field(
        default=None,
        description="For a series. `until` is the last day included or a wall-clock time.",
    )


def _span(
    start: datetime | date, end: datetime | date | None, all_day: bool, tz: str
) -> tuple[datetime | date, datetime | date]:
    first = _at(start, tz, all_day)
    if all_day:
        last = _at(end, tz, True) if end is not None else first
        return first, last + timedelta(days=1)  # type: ignore[operator]
    last = _at(end, tz, False) if end is not None else first + timedelta(hours=1)  # type: ignore[operator]
    return first, last


async def create_event(connection: AsyncConnection, arguments: CreateEvent) -> dict[str, Any]:
    start, end = _span(arguments.start, arguments.end, arguments.all_day, arguments.tz)
    request = calendar.EventIn(
        calendar_id=await _calendar_id(connection, arguments.calendar),
        title=arguments.title,
        all_day=arguments.all_day,
        start=start,
        end=end,
        tz=arguments.tz,
        location=arguments.location,
        notes=arguments.notes,
        url=arguments.url,
        rrule=recurrence.to_rrule(arguments.repeat) if arguments.repeat else None,
    )
    created = await calendar.create(connection, request, source="tool")
    names = await _names(connection)
    out: dict[str, Any] = {"created": _event(created, names)}
    if not created.rrule:
        same = await calendar.duplicates(connection, created)
        if same:
            out["duplicates"] = [
                {
                    "event_id": one.event_id,
                    "title": one.title,
                    "calendar": names.get(one.calendar_id, one.calendar_id),
                }
                for one in same
            ]
    return out


class UpdateEvent(BaseModel):
    event_id: str
    scope: Scope = Field(
        default="all",
        description="In a series: `this` only `original_start`, `following` that one and the "
        "next ones, `all` all of them.",
    )
    original_start: str | None = Field(
        default=None, description="The occurrence to change, as `get_events` gives it."
    )
    title: str | None = Field(default=None, min_length=1, max_length=200)
    start: datetime | date | None = None
    end: datetime | date | None = None
    all_day: bool | None = None
    tz: str | None = None
    calendar: str | None = None
    location: str | None = Field(default=None, description="Empty removes it.")
    notes: str | None = Field(default=None, description="Empty removes it.")
    url: str | None = Field(default=None, description="Empty removes it.")
    repeat: recurrence.Rule | None = Field(default=None, description="The series' new repetition.")
    stop_repeating: bool = Field(default=False, description="Stops being a series.")


async def update_event(connection: AsyncConnection, arguments: UpdateEvent) -> dict[str, Any]:
    current = await calendar.event(connection, arguments.event_id)
    all_day = current.all_day if arguments.all_day is None else arguments.all_day
    tz = arguments.tz or current.tz
    changes: dict[str, Any] = {}
    given = arguments.model_fields_set
    if arguments.title is not None:
        changes["title"] = arguments.title
    if "all_day" in given:
        changes["all_day"] = all_day
    if "tz" in given:
        changes["tz"] = tz
    if arguments.start is not None:
        changes["start"] = _at(arguments.start, tz, all_day)
        if arguments.end is None and all_day:
            changes["end"] = changes["start"] + timedelta(days=1)
    if arguments.end is not None:
        end = _at(arguments.end, tz, all_day)
        changes["end"] = end + timedelta(days=1) if all_day else end  # type: ignore[operator]
    for name in ("location", "notes", "url"):
        if name in given:
            changes[name] = getattr(arguments, name) or None
    if arguments.calendar is not None:
        changes["calendar_id"] = await _calendar_id(connection, arguments.calendar)
    if arguments.repeat is not None:
        changes["rrule"] = recurrence.to_rrule(arguments.repeat)
    elif arguments.stop_repeating:
        changes["rrule"] = None
    patch = calendar.EventPatch.model_validate(changes)
    updated = await calendar.update(
        connection, arguments.event_id, patch, arguments.scope, arguments.original_start
    )
    return {"updated": _event(updated, await _names(connection))}


class CancelEvent(BaseModel):
    event_id: str
    scope: Scope = "all"
    original_start: str | None = None


async def cancel_event(connection: AsyncConnection, arguments: CancelEvent) -> dict[str, Any]:
    cancelled = await calendar.cancel(
        connection, arguments.event_id, arguments.scope, arguments.original_start
    )
    return {"cancelled": _event(cancelled, await _names(connection)), "scope": arguments.scope}


class CreateCalendar(BaseModel):
    name: str = Field(min_length=1, max_length=60)
    tone: int = Field(default=5, ge=1, le=10, description="One of the ten tones, from 1 to 10.")
    display: calendar.Display = Field(
        default="events",
        description="`events`, or `background` for a frame that takes no time, such as "
        "working hours or a trip.",
    )


async def create_calendar(connection: AsyncConnection, arguments: CreateCalendar) -> dict[str, Any]:
    names = await _names(connection)
    name = arguments.name.strip()
    if name.casefold() in {one.casefold() for one in names.values()}:
        raise calendar.Invalid(f"there is already a layer “{name}”")
    created = await calendar.create_calendar(
        connection, calendar.CalendarIn(name=name, tone=arguments.tone, display=arguments.display)
    )
    return {"created": _layer(created, await _names(connection))}


class SetDaysOff(BaseModel):
    calendar: str = Field(
        description="Id or name of your layer that takes the days off: the work one."
    )
    source: str = Field(
        description="Id or name of the layer whose all-day days it takes off: holidays, vacations."
    )
    off: bool = Field(default=True, description="`false` stops taking them off.")


async def set_days_off(connection: AsyncConnection, arguments: SetDaysOff) -> dict[str, Any]:
    layer = await calendar.calendar(
        connection, str(await _calendar_id(connection, arguments.calendar))
    )
    source = str(await _calendar_id(connection, arguments.source))
    ids = [one for one in layer.days_off_from if one != source]
    if arguments.off:
        ids.append(source)
    updated = await calendar.update_calendar(
        connection, layer.id, calendar.CalendarPatch(days_off_from=[UUID(one) for one in ids])
    )
    return {"updated": _layer(updated, await _names(connection))}


Transaction = Callable[[], AbstractAsyncContextManager[AsyncConnection]]


async def _writes(connection: AsyncConnection) -> None:
    await connection.execute(text("lock table planner.planner_calendar in row exclusive mode"))


class GetSources(BaseModel):
    provider: str | None = Field(
        default=None,
        pattern=r"^[a-z][a-z0-9_]{1,40}$",
        description="Without any, the catalog. With a source and `ask`, what that question "
        "can be answered with.",
    )
    ask: str | None = Field(default=None, pattern=r"^[a-z][a-z0-9_]{0,40}$")
    query: str | None = Field(
        default=None, max_length=60, description="What to search for, if the question is a search."
    )
    parent: str | None = Field(
        default=None,
        max_length=60,
        description="The answer to the question it depends on: the country of a region.",
    )


def _ask(one: dict[str, Any]) -> dict[str, Any]:
    out = {name: one.get(name) for name in ("key", "kind", "label") if one.get(name)}
    for name in ("depends_on", "default", "help", "none_label"):
        if one.get(name):
            out[name] = one[name]
    if one.get("optional"):
        out["optional"] = True
    if one.get("choices"):
        out["choices"] = one["choices"]
    if one.get("source"):
        out["search"] = True
    return out


async def get_sources(transaction: Transaction, arguments: GetSources) -> dict[str, Any]:
    if arguments.provider and arguments.ask:
        found = await hub.search(
            arguments.provider, arguments.ask, arguments.query, arguments.parent
        )
        out: dict[str, Any] = {"options": found.get("results") or []}
        if found.get("failed"):
            out["failed"] = found["failed"]
        return out
    if arguments.provider or arguments.ask:
        raise calendar.Invalid("a question's options are asked for with `provider` and `ask`")
    found = await hub.catalogue()
    async with transaction() as connection:
        layers = [
            one
            for one in await calendar.calendars(connection, create_default=False)
            if one.origin == "subscription"
        ]
    return {
        "sources": [
            {
                "provider": source["provider"],
                "title": source.get("title"),
                "subtitle": source.get("subtitle"),
                "tone": source.get("tone"),
                "many": source.get("many"),
                "asks": [_ask(one) for one in source.get("asks") or []],
                "subscribed": [
                    one.name
                    for one in layers
                    if one.subscription and one.subscription.provider == source["provider"]
                ],
            }
            for source in found.get("sources") or []
        ]
    }


class Subscribe(BaseModel):
    provider: str = Field(
        pattern=r"^[a-z][a-z0-9_]{1,40}$", description="The source, as `get_sources` gives it."
    )
    params: dict[str, Any] = Field(
        default_factory=dict,
        description="The answer to each of the source's questions, by its `key`: "
        '{"country": "ES", "region": "ES-NC"}. Search questions, with the `code` of the chosen '
        "one.",
    )
    name: str = Field(min_length=1, max_length=60, description="The name of its layer.")
    tone: int | None = Field(default=None, ge=1, le=10, description="Without any, the source's.")


async def subscribe(transaction: Transaction, arguments: Subscribe) -> dict[str, Any]:
    name = arguments.name.strip()
    async with transaction() as connection:
        await _writes(connection)
        if name.casefold() in {one.casefold() for one in (await _names(connection)).values()}:
            raise calendar.Invalid(f"there is already a layer “{name}”")
    tone = arguments.tone
    if tone is None:
        offered = {one["provider"]: one for one in (await hub.catalogue()).get("sources") or []}
        tone = int((offered.get(arguments.provider) or {}).get("tone") or 1)
    plugged = await hub.plug(
        arguments.provider, name, arguments.params, {"name": name, "tone": tone}
    )
    settings = plugged.get("settings") or {}
    async with transaction() as connection:
        existing = (
            await connection.scalar(
                text(
                    "select id from planner.planner_calendar"
                    " where connection_id = cast(:c as uuid) limit 1"
                ),
                {"c": plugged["connection"]},
            )
            if plugged.get("existing")
            else None
        )
        if existing:
            found = await calendar.calendar(connection, str(existing))
            return {"subscribed": _layer(found, await _names(connection)), "already": True}
        layer = await feeds.add_layer(
            connection,
            plugged["connection"],
            str(settings.get("name") or name),
            int(settings.get("tone") or tone),
        )
        created = await calendar.calendar(connection, layer)
        names = await _names(connection)
    return {
        "already": False,
        "subscribed": _layer(created, names),
        "note": "Lo suyo llega con la primera pasada, en un minuto.",
    }


class Unsubscribe(BaseModel):
    calendar: str = Field(description="Id or name of the subscribed layer to remove.")


async def unsubscribe(transaction: Transaction, arguments: Unsubscribe) -> dict[str, Any]:
    async with transaction() as connection:
        await _writes(connection)
        layer = await calendar.calendar(
            connection, str(await _calendar_id(connection, arguments.calendar))
        )
    if layer.origin != "subscription" or not layer.connection_id:
        raise calendar.Invalid(
            f"“{layer.name}” is not a subscription: a layer of your own is not removed"
        )
    await hub.unsubscribe(layer.connection_id)
    return {"unsubscribed": layer.name}


@dataclass(frozen=True)
class Tool:
    arguments: type[BaseModel]
    run: Callable[..., Awaitable[dict[str, Any]]]
    own_transactions: bool = False


TOOLS: dict[str, Tool] = {
    "get_calendars": Tool(GetCalendars, get_calendars),
    "get_events": Tool(GetEvents, get_events),
    "create_event": Tool(CreateEvent, create_event),
    "update_event": Tool(UpdateEvent, update_event),
    "cancel_event": Tool(CancelEvent, cancel_event),
    "create_calendar": Tool(CreateCalendar, create_calendar),
    "set_days_off": Tool(SetDaysOff, set_days_off),
    "get_sources": Tool(GetSources, get_sources, own_transactions=True),
    "subscribe": Tool(Subscribe, subscribe, own_transactions=True),
    "unsubscribe": Tool(Unsubscribe, unsubscribe, own_transactions=True),
}
