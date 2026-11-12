from __future__ import annotations

import hashlib
import json
import unicodedata
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from typing import Any, Literal
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, Field, field_validator, model_validator
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

import arga_recurrence as recurrence
from arga_agenda import dated, uid
from planner import apps, feeds

Scope = Literal["this", "following", "all"]
Source = Literal["app", "tool"]
Display = Literal["events", "background"]

DEFAULT_CALENDAR = "Personal"
MAX_WINDOW_DAYS = 400


class NotFound(LookupError):
    pass


class Invalid(ValueError):
    pass


class Subscription(BaseModel):
    provider: str | None = None
    updated_at: datetime | None = None
    failing: bool = False
    detail: str | None = None
    paused: bool = False


class Calendar(BaseModel):
    id: str
    name: str
    tone: int
    origin: str
    visible: bool
    position: int
    display: Display = "events"
    connection_id: str | None = None
    app: str | None = None
    movable: bool = False
    subscription: Subscription | None = None
    days_off_from: list[str] = []


class CalendarIn(BaseModel):
    name: str = Field(min_length=1, max_length=60)
    tone: int = Field(ge=1, le=10)
    display: Display = "events"
    days_off_from: list[UUID] = Field(default=[], max_length=20)

    @field_validator("name")
    @classmethod
    def _name(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("el nombre no puede ir vacío")
        return value


class CalendarPatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=60)
    tone: int | None = Field(default=None, ge=1, le=10)
    visible: bool | None = None
    display: Display | None = None
    days_off_from: list[UUID] | None = Field(default=None, max_length=20)


CALENDAR_COLUMNS = (
    "id::text, name, tone, origin, visible, position, display, connection_id::text, app, "
    "days_off_from::text[] as days_off_from"
)


async def ensure_default(connection: AsyncConnection) -> None:
    found = await connection.scalar(
        text("select 1 from planner.planner_calendar where origin = 'own' limit 1")
    )
    if not found:
        await connection.execute(
            text(
                "insert into planner.planner_calendar (name, tone, position) values (:name, 1, 0)"
            ),
            {"name": DEFAULT_CALENDAR},
        )


async def calendars(
    connection: AsyncConnection, *, create_default: bool = True, subscriptions: bool = True
) -> list[Calendar]:
    if create_default:
        await ensure_default(connection)
    rows = (
        await connection.execute(
            text(
                f"select {CALENDAR_COLUMNS} from planner.planner_calendar "
                "order by origin, position, created_at"
            )
        )
    ).mappings()
    found = [Calendar(**row) for row in rows]
    if not any(one.connection_id for one in found):
        return found
    if not subscriptions:
        gone = await feeds.removed(connection)
        return [one for one in found if one.connection_id not in gone]
    known = await feeds.statuses(connection)
    out = []
    for one in found:
        if one.connection_id:
            status = known.get(one.connection_id)
            if status is not None and status.removed:
                continue
            one.subscription = Subscription(
                provider=status.provider if status else None,
                updated_at=status.updated_at if status else None,
                failing=status.failing if status else False,
                detail=status.detail if status else None,
                paused=status.paused if status else False,
            )
        out.append(one)
    return out


async def calendar(connection: AsyncConnection, calendar_id: str) -> Calendar:
    row = (
        (
            await connection.execute(
                text(f"select {CALENDAR_COLUMNS} from planner.planner_calendar where id = :id"),
                {"id": calendar_id},
            )
        )
        .mappings()
        .first()
    )
    if row is None:
        raise NotFound(f"capa {calendar_id}")
    return Calendar(**row)


async def _days_off_from(
    connection: AsyncConnection, calendar_id: str | None, wanted: list[UUID]
) -> list[str]:
    ids = list(dict.fromkeys(str(one) for one in wanted))
    if calendar_id in ids:
        raise Invalid("una capa no libra sus propios días")
    if not ids:
        return []
    found = set(
        await connection.scalars(
            text(
                "select id::text from planner.planner_calendar where id = any(cast(:ids as uuid[]))"
            ),
            {"ids": ids},
        )
    )
    missing = [one for one in ids if one not in found]
    if missing:
        raise NotFound(f"capa {missing[0]}")
    return ids


async def create_calendar(connection: AsyncConnection, request: CalendarIn) -> Calendar:
    days_off = await _days_off_from(connection, None, request.days_off_from)
    row = (
        await connection.execute(
            text(
                "insert into planner.planner_calendar (name, tone, display, days_off_from, position) "
                "values (:name, :tone, :display, cast(:days_off as uuid[]), "
                "coalesce((select max(position) + 1 "
                "from planner.planner_calendar where origin = 'own'), 0)) returning id::text"
            ),
            {
                "name": request.name,
                "tone": request.tone,
                "display": request.display,
                "days_off": days_off,
            },
        )
    ).scalar_one()
    return await calendar(connection, row)


async def update_calendar(
    connection: AsyncConnection, calendar_id: str, patch: CalendarPatch
) -> Calendar:
    current = await calendar(connection, calendar_id)
    fields = patch.model_dump(exclude_none=True)
    if "name" in fields:
        fields["name"] = fields["name"].strip()
    if "days_off_from" in fields:
        if current.origin != "own" and patch.days_off_from:
            raise Invalid("solo una capa tuya libra días")
        fields["days_off_from"] = await _days_off_from(
            connection, calendar_id, patch.days_off_from or []
        )
    if fields:
        sets = ", ".join(
            "days_off_from = cast(:days_off_from as uuid[])"
            if name == "days_off_from"
            else f"{name} = :{name}"
            for name in fields
        )
        await connection.execute(
            text(f"update planner.planner_calendar set {sets} where id = :id"),
            {**fields, "id": calendar_id},
        )
    return await calendar(connection, calendar_id)


async def reorder_calendars(connection: AsyncConnection, ids: list[str]) -> list[Calendar]:
    for position, calendar_id in enumerate(ids):
        await connection.execute(
            text("update planner.planner_calendar set position = :p where id = :id"),
            {"p": position, "id": calendar_id},
        )
    return await calendars(connection)


def _zone(tz: str) -> ZoneInfo:
    try:
        return ZoneInfo(tz)
    except (ZoneInfoNotFoundError, ValueError) as error:
        raise Invalid(f"{tz!r} no es una zona IANA, como Europe/Madrid") from error


def _parse_when(value: Any, all_day: bool) -> Any:
    if not isinstance(value, str):
        return value
    try:
        if all_day:
            return date.fromisoformat(value[:10])
        return datetime.fromisoformat(value)
    except ValueError as error:
        raise ValueError(f"{value!r} no es {'una fecha' if all_day else 'una hora'}") from error


def _rule_text(value: str | None) -> str | None:
    if value is None:
        return None
    value = value.strip().removeprefix("RRULE:")
    if not value:
        return None
    try:
        return recurrence.to_rrule(recurrence.parse(value))
    except ValueError as error:
        raise ValueError(f"la repetición no se entiende: {error}") from error


class EventIn(BaseModel):
    calendar_id: str | None = None
    title: str = Field(min_length=1, max_length=200)
    all_day: bool = False
    start: datetime | date
    end: datetime | date
    tz: str = Field(min_length=1, max_length=64)
    location: str | None = Field(default=None, max_length=300)
    notes: str | None = Field(default=None, max_length=8000)
    url: str | None = Field(default=None, max_length=2000)
    rrule: str | None = None

    @model_validator(mode="before")
    @classmethod
    def _dates_follow_all_day(cls, data: Any) -> Any:
        if isinstance(data, dict):
            all_day = bool(data.get("all_day", False))
            data = {
                **data,
                **{k: _parse_when(data[k], all_day) for k in ("start", "end") if k in data},
            }
        return data

    @field_validator("title")
    @classmethod
    def _title(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("el título no puede ir vacío")
        return value

    @field_validator("location", "notes", "url")
    @classmethod
    def _blank_is_none(cls, value: str | None) -> str | None:
        return value.strip() or None if value is not None else None

    @field_validator("rrule")
    @classmethod
    def _rule(cls, value: str | None) -> str | None:
        return _rule_text(value)


class EventPatch(BaseModel):
    calendar_id: str | None = None
    title: str | None = Field(default=None, min_length=1, max_length=200)
    all_day: bool | None = None
    start: datetime | date | None = None
    end: datetime | date | None = None
    tz: str | None = Field(default=None, min_length=1, max_length=64)
    location: str | None = Field(default=None, max_length=300)
    notes: str | None = Field(default=None, max_length=8000)
    url: str | None = Field(default=None, max_length=2000)
    rrule: str | None = None

    @model_validator(mode="before")
    @classmethod
    def _dates(cls, data: Any) -> Any:
        if isinstance(data, dict) and ("start" in data or "end" in data):
            all_day = data.get("all_day")
            if all_day is None:
                sample = data.get("start") or data.get("end")
                all_day = isinstance(sample, str) and len(sample) == 10
            data = {
                **data,
                **{
                    k: _parse_when(data[k], bool(all_day))
                    for k in ("start", "end")
                    if data.get(k) is not None
                },
            }
        return data

    @field_validator("title")
    @classmethod
    def _title(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        if not value:
            raise ValueError("el título no puede ir vacío")
        return value

    @field_validator("location", "notes", "url")
    @classmethod
    def _blank_is_none(cls, value: str | None) -> str | None:
        return value.strip() or None if value is not None else None

    @field_validator("rrule")
    @classmethod
    def _rule(cls, value: str | None) -> str | None:
        return _rule_text(value)


class Event(BaseModel):
    id: str
    calendar_id: str
    title: str
    all_day: bool
    start: str
    end: str
    tz: str
    location: str | None
    notes: str | None
    url: str | None
    rrule: str | None
    repeat: str | None
    status: str
    source: str


class Occurrence(BaseModel):
    id: str
    event_id: str
    calendar_id: str
    title: str
    all_day: bool
    start: str
    end: str
    tz: str
    location: str | None
    notes: str | None
    url: str | None
    status: str
    original_start: str | None = None
    rrule: str | None = None
    repeat: str | None = None
    moved: bool = False
    href: str | None = None


EVENT_COLUMNS = (
    "id::text, calendar_id::text, title, all_day, start_at, end_at, start_date, end_date, tz, "
    "location, notes, url, rrule, status, source"
)


@dataclass
class Row:
    id: str
    calendar_id: str
    title: str
    all_day: bool
    start_at: datetime | None
    end_at: datetime | None
    start_date: date | None
    end_date: date | None
    tz: str
    location: str | None
    notes: str | None
    url: str | None
    rrule: str | None
    status: str
    source: str

    @property
    def zone(self) -> ZoneInfo:
        return ZoneInfo(self.tz)

    @property
    def start(self) -> datetime | date:
        return self.start_date if self.all_day else self.start_at.astimezone(self.zone)  # type: ignore[union-attr,return-value]

    @property
    def end(self) -> datetime | date:
        return self.end_date if self.all_day else self.end_at.astimezone(self.zone)  # type: ignore[union-attr,return-value]

    @property
    def wall_start(self) -> datetime | date:
        if self.all_day:
            return self.start_date  # type: ignore[return-value]
        return self.start_at.astimezone(self.zone).replace(tzinfo=None)  # type: ignore[union-attr]

    @property
    def duration(self) -> timedelta:
        if self.all_day:
            return self.end_date - self.start_date  # type: ignore[operator]
        return self.end_at - self.start_at  # type: ignore[operator]

    @property
    def rule(self) -> recurrence.Rule | None:
        return recurrence.parse(self.rrule) if self.rrule else None


def _iso(value: datetime | date) -> str:
    return value.isoformat()


def phrase(rrule: str | None) -> str | None:
    return recurrence.describe(recurrence.parse(rrule)) if rrule else None


def _event(row: Row) -> Event:
    return Event(
        id=row.id,
        calendar_id=row.calendar_id,
        title=row.title,
        all_day=row.all_day,
        start=_iso(row.start),
        end=_iso(row.end),
        tz=row.tz,
        location=row.location,
        notes=row.notes,
        url=row.url,
        rrule=row.rrule,
        repeat=phrase(row.rrule),
        status=row.status,
        source=row.source,
    )


async def _row(connection: AsyncConnection, event_id: str) -> Row:
    if event_id.startswith("feed:"):
        raise Invalid("lo suscrito no se edita: se puede ocultar en la app")
    try:
        UUID(event_id)
    except ValueError as error:
        raise NotFound(f"evento {event_id}") from error
    found = (
        (
            await connection.execute(
                text(f"select {EVENT_COLUMNS} from planner.planner_event where id = :id"),
                {"id": event_id},
            )
        )
        .mappings()
        .first()
    )
    if found is None:
        raise NotFound(f"evento {event_id}")
    return Row(**found)


async def event(connection: AsyncConnection, event_id: str) -> Event:
    return _event(await _row(connection, event_id))


async def _own_calendar(connection: AsyncConnection, calendar_id: str | None) -> str:
    await ensure_default(connection)
    if calendar_id is None:
        return (
            await connection.execute(
                text(
                    "select id::text from planner.planner_calendar where origin = 'own' "
                    "order by display = 'background', position, created_at limit 1"
                )
            )
        ).scalar_one()
    found = await calendar(connection, calendar_id)
    if found.origin != "own":
        raise Invalid("lo suscrito no se edita: elige una capa propia")
    return found.id


def _timing(all_day: bool, start: datetime | date, end: datetime | date, tz: str) -> dict[str, Any]:
    _zone(tz)
    if all_day:
        if isinstance(start, datetime) or isinstance(end, datetime):
            raise Invalid("de todo el día, inicio y fin son fechas")
        if end <= start:
            raise Invalid(
                "de todo el día, el fin es el día siguiente al último: va después del inicio"
            )
        return {"start_at": None, "end_at": None, "start_date": start, "end_date": end}
    if not isinstance(start, datetime) or not isinstance(end, datetime):
        raise Invalid("con hora, inicio y fin son horas")
    if start.tzinfo is None or end.tzinfo is None:
        raise Invalid("con hora, inicio y fin van con su zona")
    if end < start:
        raise Invalid("el fin va después del inicio")
    return {"start_at": start, "end_at": end, "start_date": None, "end_date": None}


def _check_rule(rrule: str | None, start: datetime | date) -> None:
    if rrule is None:
        return
    rule = recurrence.parse(rrule)
    wall = start if not isinstance(start, datetime) else start.replace(tzinfo=None)
    first = recurrence.next_occurrence(rule, wall, wall)
    if first is None:
        raise Invalid("la repetición acaba antes de empezar")


async def create(connection: AsyncConnection, request: EventIn, source: Source = "app") -> Event:
    calendar_id = await _own_calendar(connection, request.calendar_id)
    timing = _timing(request.all_day, request.start, request.end, request.tz)
    start_wall = (
        request.start.astimezone(_zone(request.tz))
        if isinstance(request.start, datetime)
        else request.start
    )
    _check_rule(request.rrule, start_wall)
    event_id = (
        await connection.execute(
            text(
                "insert into planner.planner_event (calendar_id, title, all_day, start_at, end_at, "
                "start_date, end_date, tz, location, notes, url, rrule, source) values ("
                ":calendar_id, :title, :all_day, :start_at, :end_at, :start_date, :end_date, :tz, "
                ":location, :notes, :url, :rrule, :source) returning id::text"
            ),
            {
                "calendar_id": calendar_id,
                "title": request.title,
                "all_day": request.all_day,
                **timing,
                "tz": request.tz,
                "location": request.location,
                "notes": request.notes,
                "url": request.url,
                "rrule": request.rrule,
                "source": source,
            },
        )
    ).scalar_one()
    row = await _row(connection, event_id)
    await publish(connection, row, "created")
    return _event(row)


@dataclass
class Override:
    id: str
    event_id: str
    original_start: datetime
    cancelled: bool
    start_at: datetime | None
    end_at: datetime | None
    start_date: date | None
    end_date: date | None
    title: str | None
    location: str | None
    notes: str | None
    url: str | None


OVERRIDE_COLUMNS = (
    "id::text, event_id::text, original_start, cancelled, start_at, end_at, start_date, "
    "end_date, title, location, notes, url"
)


async def _overrides(
    connection: AsyncConnection, event_ids: list[str]
) -> dict[str, list[Override]]:
    if not event_ids:
        return {}
    rows = (
        await connection.execute(
            text(
                f"select {OVERRIDE_COLUMNS} from planner.planner_override "
                "where event_id = any(cast(:ids as uuid[]))"
            ),
            {"ids": event_ids},
        )
    ).mappings()
    out: dict[str, list[Override]] = {}
    for row in rows:
        out.setdefault(row["event_id"], []).append(Override(**row))
    return out


def _as_wall(value: datetime | date) -> datetime:
    return value if isinstance(value, datetime) else datetime.combine(value, time())


def _key(original: datetime | date) -> str:
    return original.isoformat() if isinstance(original, datetime) else original.isoformat()


def parse_original(value: str, all_day: bool) -> datetime | date:
    try:
        if all_day:
            return date.fromisoformat(value[:10])
        parsed = datetime.fromisoformat(value)
    except ValueError as error:
        raise Invalid(f"{value!r} no es el inicio de una ocurrencia") from error
    return parsed.replace(tzinfo=None)


def _single(row: Row) -> Occurrence:
    return Occurrence(
        id=row.id,
        event_id=row.id,
        calendar_id=row.calendar_id,
        title=row.title,
        all_day=row.all_day,
        start=_iso(row.start),
        end=_iso(row.end),
        tz=row.tz,
        location=row.location,
        notes=row.notes,
        url=row.url,
        status=row.status,
    )


def _expand(
    row: Row, overrides: list[Override], start: datetime, end: datetime
) -> list[Occurrence]:
    rule = row.rule
    assert rule is not None
    zone = row.zone
    duration = row.duration
    by_original = {o.original_start: o for o in overrides}
    cancelled = [o.original_start for o in overrides if o.cancelled]
    moved: dict[datetime | date, datetime | date] = {}
    for o in overrides:
        if o.cancelled:
            continue
        if row.all_day and o.start_date is not None:
            moved[o.original_start.date()] = o.start_date
        elif not row.all_day and o.start_at is not None:
            moved[o.original_start] = o.start_at.astimezone(zone).replace(tzinfo=None)

    if row.all_day:
        low = (start - duration).date() - timedelta(days=1)
        high = end.date() + timedelta(days=2)
        found = recurrence.expand(
            rule,
            row.wall_start,
            row.tz,
            low,
            high,
            cancelled=[c.date() for c in cancelled],
            moved=moved,
        )
    else:
        found = recurrence.expand(
            rule,
            row.wall_start,
            row.tz,
            start - duration,
            end,
            cancelled=cancelled,
            moved=moved,
        )

    out = []
    for occurrence in found:
        override = by_original.get(_as_wall(occurrence.original))
        if row.all_day:
            first: datetime | date = occurrence.start
            if override and override.end_date is not None:
                last: datetime | date = override.end_date
            else:
                last = occurrence.start + duration  # type: ignore[operator]
        else:
            first = occurrence.start
            if override and override.end_at is not None:
                last = override.end_at.astimezone(zone)
            else:
                last = (occurrence.start.astimezone(UTC) + duration).astimezone(zone)  # type: ignore[union-attr]
        key = _key(occurrence.original)
        out.append(
            Occurrence(
                id=f"{row.id}@{key}",
                event_id=row.id,
                calendar_id=row.calendar_id,
                title=(override.title if override and override.title else row.title),
                all_day=row.all_day,
                start=_iso(first),
                end=_iso(last),
                tz=row.tz,
                location=override.location if override and override.location else row.location,
                notes=override.notes if override and override.notes else row.notes,
                url=override.url if override and override.url else row.url,
                status=row.status,
                original_start=key,
                rrule=row.rrule,
                repeat=phrase(row.rrule),
                moved=occurrence.moved,
            )
        )
    return out


def _subscribed(row: feeds.FeedRow) -> Occurrence:
    payload = row.payload
    return Occurrence(
        id=f"feed:{row.id}",
        event_id=f"feed:{row.id}",
        calendar_id=row.calendar_id,
        title=payload.get("title") or "(sin título)",
        all_day=bool(payload.get("all_day")),
        start=payload["start"],
        end=payload["end"],
        tz=payload.get("tz") or "UTC",
        location=payload.get("location"),
        notes=payload.get("description"),
        url=payload.get("url"),
        status="confirmed",
    )


def from_app(row: apps.AppRow) -> Occurrence:
    item = row.payload
    return Occurrence(
        id=f"app:{row.id}",
        event_id=f"app:{row.id}",
        calendar_id=row.calendar_id,
        title=item["title"],
        all_day=bool(item.get("all_day")),
        start=item["start"],
        end=item["end"],
        tz=item.get("tz") or "UTC",
        location=item.get("location"),
        notes=None,
        url=None,
        status=item.get("status") or "confirmed",
        href=item.get("href"),
    )


def _overlaps(occurrence: Occurrence, start: datetime, end: datetime) -> bool:
    if occurrence.all_day:
        first = date.fromisoformat(occurrence.start)
        last = date.fromisoformat(occurrence.end)
        return first <= end.date() + timedelta(days=1) and last >= start.date()
    a = datetime.fromisoformat(occurrence.start)
    b = datetime.fromisoformat(occurrence.end)
    return a < end and (b > start or (a == b and a >= start))


async def occurrences(
    connection: AsyncConnection,
    start: datetime,
    end: datetime,
    calendar_ids: list[str] | None = None,
) -> list[Occurrence]:
    if start.tzinfo is None or end.tzinfo is None:
        raise Invalid("la ventana va con zona")
    if end <= start:
        raise Invalid("la ventana acaba después de empezar")
    if end - start > timedelta(days=MAX_WINDOW_DAYS):
        raise Invalid(f"como mucho {MAX_WINDOW_DAYS} días de una vez")
    found = await _collect(connection, start, end, calendar_ids)
    return await _without_days_off(connection, found, end)


async def _collect(
    connection: AsyncConnection,
    start: datetime,
    end: datetime,
    calendar_ids: list[str] | None,
) -> list[Occurrence]:
    only = "and calendar_id = any(cast(:calendars as uuid[]))" if calendar_ids else ""
    params: dict[str, Any] = {
        "start": start,
        "end": end,
        "first_day": start.date() - timedelta(days=1),
        "last_day": end.date() + timedelta(days=1),
        "calendars": calendar_ids or [],
    }
    singles = (
        await connection.execute(
            text(
                f"select {EVENT_COLUMNS} from planner.planner_event "
                "where rrule is null and status = 'confirmed' "
                "and ((not all_day and start_at < :end and end_at >= :start) "
                " or (all_day and start_date <= :last_day and end_date >= :first_day)) "
                f"{only}"
            ),
            params,
        )
    ).mappings()
    out = [_single(Row(**row)) for row in singles]
    series = [
        Row(**row)
        for row in (
            await connection.execute(
                text(
                    f"select {EVENT_COLUMNS} from planner.planner_event "
                    "where rrule is not null and status = 'confirmed' "
                    "and ((not all_day and start_at < :end) "
                    " or (all_day and start_date <= :last_day)) "
                    f"{only}"
                ),
                params,
            )
        ).mappings()
    ]
    changed = await _overrides(connection, [row.id for row in series])
    for row in series:
        out.extend(_expand(row, changed.get(row.id, []), start, end))
    out.extend(
        _subscribed(row)
        for row in await feeds.in_window(connection, start, end, calendar_ids or [])
    )
    out.extend(
        from_app(row) for row in await apps.in_window(connection, start, end, calendar_ids or [])
    )
    found = [o for o in out if _overlaps(o, start, end)]
    return sorted(found, key=lambda o: (not o.all_day, _sort_key(o.start), o.title))


def _day_of(occurrence: Occurrence) -> date:
    if occurrence.all_day:
        return date.fromisoformat(occurrence.start[:10])
    return datetime.fromisoformat(occurrence.start).date()


def _days(occurrence: Occurrence) -> list[date]:
    first = date.fromisoformat(occurrence.start[:10])
    last = date.fromisoformat(occurrence.end[:10])
    return [first + timedelta(days=n) for n in range((last - first).days)]


async def _without_days_off(
    connection: AsyncConnection, found: list[Occurrence], end: datetime
) -> list[Occurrence]:
    rules = {
        row.id: row.days_off_from
        for row in (
            await connection.execute(
                text(
                    "select id::text as id, days_off_from::text[] as days_off_from "
                    "from planner.planner_calendar where cardinality(days_off_from) > 0"
                )
            )
        )
    }
    repeated = [o for o in found if o.calendar_id in rules and o.rrule and not o.moved]
    if not repeated:
        return found
    first = min(_day_of(o) for o in repeated)
    since = datetime.combine(first, time(), UTC) - timedelta(days=1)
    sources = sorted({one for ids in rules.values() for one in ids})
    off: dict[str, set[date]] = {}
    for one in await _collect(connection, since, end, sources):
        if one.all_day and one.status == "confirmed":
            off.setdefault(one.calendar_id, set()).update(_days(one))
    free = {
        layer: set().union(*(off.get(source, set()) for source in ids))
        for layer, ids in rules.items()
    }

    def off_day(o: Occurrence) -> bool:
        return (
            o.calendar_id in free
            and bool(o.rrule)
            and not o.moved
            and _day_of(o) in free[o.calendar_id]
        )

    return [o for o in found if not off_day(o)]


def _sort_key(value: str) -> datetime:
    parsed = (
        datetime.fromisoformat(value)
        if len(value) > 10
        else datetime.fromisoformat(value + "T00:00:00+00:00")
    )
    return parsed.astimezone(UTC)


async def search(
    connection: AsyncConnection,
    query: str,
    start: datetime | None = None,
    end: datetime | None = None,
    limit: int = 30,
) -> list[Occurrence]:
    words = query.strip()
    if not words:
        return []
    pattern = "%" + words.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
    if start is not None and end is not None:
        found = await occurrences(connection, start, end)
        needle = words.casefold()
        return [
            o
            for o in found
            if needle in " ".join(filter(None, [o.title, o.location, o.notes])).casefold()
        ][:limit]

    rows = [
        Row(**row)
        for row in (
            await connection.execute(
                text(
                    f"select {EVENT_COLUMNS} from planner.planner_event where status = 'confirmed' "
                    "and (title ilike :p or location ilike :p or notes ilike :p) "
                    "order by coalesce(start_at, start_date::timestamptz) desc limit 200"
                ),
                {"p": pattern},
            )
        ).mappings()
    ]
    now = datetime.now(UTC)
    upcoming: list[Occurrence] = []
    past: list[Occurrence] = []
    for row in rows:
        if row.rrule is None:
            hit = _single(row)
        else:
            rule = row.rule
            assert rule is not None
            today_wall: datetime | date = (
                now.date() if row.all_day else now.astimezone(row.zone).replace(tzinfo=None)
            )
            upcoming_wall = recurrence.next_occurrence(rule, row.wall_start, today_wall)
            changed = (await _overrides(connection, [row.id])).get(row.id, [])
            if upcoming_wall is not None:
                around = _as_wall(upcoming_wall).replace(tzinfo=row.zone)
                mine = _expand(
                    row, changed, max(now, around - timedelta(days=1)), around + timedelta(days=2)
                )
            else:
                mine = _expand(row, changed, now - timedelta(days=MAX_WINDOW_DAYS), now)
            if not mine:
                continue
            hit = mine[0] if upcoming_wall is not None else mine[-1]
        (upcoming if _sort_key(hit.end) >= now else past).append(hit)
    for row in await feeds.matching(connection, pattern):
        hit = _subscribed(row)
        (upcoming if _sort_key(hit.end) >= now else past).append(hit)
    for row in await apps.matching(connection, pattern):
        hit = from_app(row)
        (upcoming if _sort_key(hit.end) >= now else past).append(hit)
    upcoming.sort(key=lambda o: _sort_key(o.start))
    past.sort(key=lambda o: _sort_key(o.start), reverse=True)
    return (upcoming + past)[:limit]


def _shift_rule(rule: recurrence.Rule, days: int) -> recurrence.Rule:
    if days % 7 == 0 or not rule.by_day or rule.freq != "weekly":
        return rule
    moved = []
    for day in rule.by_day:
        index = (recurrence.WEEKDAYS.index(day.weekday) + days) % 7
        moved.append(day.model_copy(update={"weekday": recurrence.WEEKDAYS[index]}))
    return rule.model_copy(update={"by_day": tuple(moved)})


def _new_timing(
    row: Row, patch: EventPatch, reference: datetime | date
) -> tuple[dict[str, Any], timedelta]:
    all_day = row.all_day if patch.all_day is None else patch.all_day
    tz = patch.tz or row.tz
    zone = _zone(tz)
    if patch.start is None and patch.end is None and patch.all_day in (None, row.all_day):
        return {}, timedelta(0)

    if all_day:
        start = (
            patch.start
            if patch.start is not None
            else (reference if not isinstance(reference, datetime) else reference.date())
        )
        if isinstance(start, datetime):
            start = start.astimezone(zone).date()
        if patch.end is not None:
            end = (
                patch.end
                if not isinstance(patch.end, datetime)
                else patch.end.astimezone(zone).date()
            )
        else:
            span = row.duration.days if row.all_day else 1
            end = start + timedelta(days=max(1, span))  # type: ignore[operator]
    else:
        if patch.start is not None:
            start = patch.start
        else:
            base = (
                reference
                if isinstance(reference, datetime)
                else datetime.combine(reference, time(9))
            )
            start = base.replace(tzinfo=zone) if base.tzinfo is None else base
        if isinstance(start, date) and not isinstance(start, datetime):
            start = datetime.combine(start, time(9), tzinfo=zone)
        if patch.end is not None:
            end = patch.end
            if isinstance(end, date) and not isinstance(end, datetime):
                end = datetime.combine(end, time(10), tzinfo=zone)
        else:
            duration = row.duration if not row.all_day else timedelta(hours=1)
            end = (start.astimezone(UTC) + duration).astimezone(zone)
    timing = _timing(all_day, start, end, tz)

    new_wall = (
        start if not isinstance(start, datetime) else start.astimezone(zone).replace(tzinfo=None)
    )
    delta = _as_wall(new_wall) - _as_wall(reference)
    return {**timing, "all_day": all_day, "tz": tz}, delta


def _plain_fields(patch: EventPatch) -> dict[str, Any]:
    given = patch.model_fields_set
    fields: dict[str, Any] = {}
    for name in ("title", "location", "notes", "url"):
        if name in given and not (name == "title" and patch.title is None):
            fields[name] = getattr(patch, name)
    return fields


async def _write(connection: AsyncConnection, event_id: str, fields: dict[str, Any]) -> None:
    if not fields:
        return
    sets = ", ".join(f"{name} = :{name}" for name in fields)
    await connection.execute(
        text(f"update planner.planner_event set {sets}, updated_at = now() where id = :id"),
        {**fields, "id": event_id},
    )


async def _shift_overrides(
    connection: AsyncConnection,
    event_id: str,
    delta: timedelta,
    *,
    since: datetime | None = None,
    to: str | None = None,
) -> None:
    if not delta and to is None:
        return
    where = "event_id = :id" + (" and original_start >= :since" if since is not None else "")
    await connection.execute(
        text(
            "update planner.planner_override set original_start = original_start + :delta"
            + (", event_id = :to" if to else "")
            + f", updated_at = now() where {where}"
        ),
        {"id": event_id, "delta": delta, "since": since, "to": to},
    )


async def update(
    connection: AsyncConnection,
    event_id: str,
    patch: EventPatch,
    scope: Scope = "all",
    original: str | None = None,
) -> Event:
    row = await _row(connection, event_id)
    if row.status == "cancelled":
        raise Invalid("el evento está cancelado")
    calendar_fields: dict[str, Any] = {}
    if "calendar_id" in patch.model_fields_set and patch.calendar_id is not None:
        calendar_fields["calendar_id"] = await _own_calendar(connection, patch.calendar_id)
    else:
        own = await calendar(connection, row.calendar_id)
        if own.origin != "own":
            raise Invalid("lo suscrito no se edita")

    rule_given = "rrule" in patch.model_fields_set

    if row.rrule is None or (scope == "all" and original is None):
        timing, delta = _new_timing(row, patch, row.wall_start)
        fields = {**_plain_fields(patch), **calendar_fields, **timing}
        if rule_given:
            fields["rrule"] = patch.rrule
        elif row.rrule and delta.days:
            fields["rrule"] = recurrence.to_rrule(_shift_rule(row.rule, delta.days))  # type: ignore[arg-type]
        _check_rule(fields.get("rrule", row.rrule), _new_start(row, timing))
        await _write(connection, row.id, fields)
        if row.rrule and delta:
            await _shift_overrides(connection, row.id, delta)
        return await _publish_event(connection, row.id, "updated")

    if original is None:
        raise Invalid(
            "en una serie, di qué ocurrencia (original_start) o que es la serie entera (all)"
        )
    at = parse_original(original, row.all_day)
    rule = row.rule
    assert rule is not None
    if at not in _occurrences_of(rule, row.wall_start, at):
        raise Invalid(f"{original} no es una ocurrencia de la serie")

    if scope == "all":
        timing, delta = _new_timing(row, patch, at)
        if timing:
            shifted = _as_wall(row.wall_start) + delta
            zone = _zone(timing["tz"])
            if timing["all_day"]:
                span = timing["end_date"] - timing["start_date"]
                timing["start_date"] = shifted.date()
                timing["end_date"] = shifted.date() + span
            else:
                span = timing["end_at"] - timing["start_at"]
                timing["start_at"] = shifted.replace(tzinfo=zone)
                timing["end_at"] = timing["start_at"] + span
        fields = {**_plain_fields(patch), **calendar_fields, **timing}
        if rule_given:
            fields["rrule"] = patch.rrule
        elif delta.days:
            fields["rrule"] = recurrence.to_rrule(_shift_rule(rule, delta.days))
        _check_rule(fields.get("rrule", row.rrule), _new_start(row, timing))
        await _write(connection, row.id, fields)
        if delta:
            await _shift_overrides(connection, row.id, delta)
        return await _publish_event(connection, row.id, "updated")

    if scope == "this":
        if rule_given or calendar_fields:
            raise Invalid("la repetición y la capa se cambian en la serie, no en una ocurrencia")
        timing, _ = _new_timing(row, patch, at)
        values = dict(_plain_fields(patch))
        if timing:
            values.update({k: timing[k] for k in ("start_at", "end_at", "start_date", "end_date")})
        if timing.get("all_day", row.all_day) != row.all_day:
            raise Invalid(
                "una ocurrencia no cambia entre todo el día y con hora: cámbialo en la serie"
            )
        await _upsert_override(connection, row.id, _as_wall(at), values)
        return await _publish_event(connection, row.id, "updated")

    head, tail = recurrence.split(rule, row.wall_start, at)
    if head is None:
        return await update(connection, event_id, patch, "all", None)
    timing, delta = _new_timing(row, patch, at)
    new_rule = patch.rrule if rule_given else recurrence.to_rrule(_shift_rule(tail, delta.days))
    base_timing = timing or _timing_at(row, at)
    new_id = (
        await connection.execute(
            text(
                "insert into planner.planner_event (calendar_id, title, all_day, start_at, end_at, "
                "start_date, end_date, tz, location, notes, url, rrule, source) "
                "select :calendar_id, coalesce(:title, title), :all_day, :start_at, :end_at, "
                ":start_date, :end_date, :tz, "
                "case when :set_location then :location else location end, "
                "case when :set_notes then :notes else notes end, "
                "case when :set_url then :url else url end, :rrule, source "
                "from planner.planner_event where id = :id returning id::text"
            ),
            {
                "id": row.id,
                "calendar_id": calendar_fields.get("calendar_id", row.calendar_id),
                "title": patch.title,
                "all_day": base_timing.get("all_day", row.all_day),
                "start_at": base_timing["start_at"],
                "end_at": base_timing["end_at"],
                "start_date": base_timing["start_date"],
                "end_date": base_timing["end_date"],
                "tz": base_timing.get("tz", row.tz),
                "set_location": "location" in patch.model_fields_set,
                "location": patch.location,
                "set_notes": "notes" in patch.model_fields_set,
                "notes": patch.notes,
                "set_url": "url" in patch.model_fields_set,
                "url": patch.url,
                "rrule": new_rule,
            },
        )
    ).scalar_one()
    await _write(connection, row.id, {"rrule": recurrence.to_rrule(head)})
    await _shift_overrides(connection, row.id, delta, since=_as_wall(at), to=new_id)
    await _publish_event(connection, row.id, "updated")
    return await _publish_event(connection, new_id, "created")


def _occurrences_of(
    rule: recurrence.Rule, start: datetime | date, at: datetime | date
) -> set[datetime | date]:
    found = recurrence.next_occurrence(rule, start, at)
    return {found} if found is not None else set()


def _timing_at(row: Row, at: datetime | date) -> dict[str, Any]:
    if row.all_day:
        return {
            "start_at": None,
            "end_at": None,
            "start_date": at,
            "end_date": at + row.duration,
            "all_day": True,
            "tz": row.tz,
        }  # type: ignore[operator]
    start = at.replace(tzinfo=row.zone)  # type: ignore[union-attr,call-arg]
    return {
        "start_at": start,
        "end_at": (start.astimezone(UTC) + row.duration).astimezone(row.zone),
        "start_date": None,
        "end_date": None,
        "all_day": False,
        "tz": row.tz,
    }


def _new_start(row: Row, timing: dict[str, Any]) -> datetime | date:
    if not timing:
        return row.start
    if timing.get("all_day", row.all_day):
        return timing["start_date"]
    return timing["start_at"].astimezone(_zone(timing.get("tz", row.tz)))


async def _upsert_override(
    connection: AsyncConnection, event_id: str, original: datetime, values: dict[str, Any]
) -> None:
    columns = [
        "cancelled",
        "start_at",
        "end_at",
        "start_date",
        "end_date",
        "title",
        "location",
        "notes",
        "url",
    ]
    data = {name: values.get(name) for name in columns}
    data["cancelled"] = bool(values.get("cancelled", False))
    keep = [name for name in columns if name not in values and name != "cancelled"]
    updates = ", ".join(
        [f"{name} = excluded.{name}" for name in columns if name not in keep]
        + ["updated_at = now()"]
    )
    await connection.execute(
        text(
            f"insert into planner.planner_override (event_id, original_start, {', '.join(columns)}) "
            f"values (:event_id, :original, {', '.join(':' + c for c in columns)}) "
            f"on conflict (event_id, original_start) do update set {updates}"
        ),
        {**data, "event_id": event_id, "original": original},
    )


async def cancel(
    connection: AsyncConnection, event_id: str, scope: Scope = "all", original: str | None = None
) -> Event:
    row = await _row(connection, event_id)
    own = await calendar(connection, row.calendar_id)
    if own.origin != "own":
        raise Invalid("lo suscrito no se cancela: se oculta")
    if row.rrule is None or scope == "all":
        await _write(connection, row.id, {"status": "cancelled"})
        return await _publish_event(connection, row.id, "cancelled")
    if original is None:
        raise Invalid(
            "en una serie, di qué ocurrencia (original_start) o que es la serie entera (all)"
        )
    at = parse_original(original, row.all_day)
    rule = row.rule
    assert rule is not None
    if at not in _occurrences_of(rule, row.wall_start, at):
        raise Invalid(f"{original} no es una ocurrencia de la serie")
    if scope == "this":
        await _upsert_override(connection, row.id, _as_wall(at), {"cancelled": True})
        return await _publish_event(connection, row.id, "updated")
    head, _ = recurrence.split(rule, row.wall_start, at)
    if head is None:
        await _write(connection, row.id, {"status": "cancelled"})
        return await _publish_event(connection, row.id, "cancelled")
    await _write(connection, row.id, {"rrule": recurrence.to_rrule(head)})
    return await _publish_event(connection, row.id, "updated")


async def _publish_event(connection: AsyncConnection, event_id: str, action: str) -> Event:
    row = await _row(connection, event_id)
    await publish(connection, row, action)
    return _event(row)


async def publish(connection: AsyncConnection, row: Row, action: str) -> None:
    payload = {
        "agenda": dated(
            uid=uid("planner", "event", row.id),
            title=row.title,
            start=_iso(row.start),
            end=_iso(row.end),
            all_day=row.all_day,
            tz=row.tz,
            location=row.location,
            status="cancelled" if row.status == "cancelled" else "confirmed",
            href=f"/planner?event={row.id}",
        ),
        "event_id": row.id,
        "calendar_id": row.calendar_id,
        "action": action,
        "rrule": row.rrule,
    }
    body = json.dumps(payload, sort_keys=True, default=str)
    stamp = datetime.now(UTC).isoformat()
    dedup = hashlib.sha256(f"{row.id}|{action}|{stamp}|{body}".encode()).hexdigest()
    await connection.execute(
        text(
            "insert into planner.planner_outbox (type, payload, dedup_hash) "
            "values ('planner.event', cast(:payload as jsonb), :dedup)"
        ),
        {"payload": body, "dedup": dedup},
    )


def _words(title: str) -> set[str]:
    folded = "".join(
        char
        for char in unicodedata.normalize("NFKD", title.casefold())
        if not unicodedata.combining(char)
    )
    cleaned = "".join(char if char.isalnum() else " " for char in folded)
    return {word for word in cleaned.split() if len(word) >= 4}


def similar(a: str, b: str) -> bool:
    left, right = _words(a), _words(b)
    if not left or not right:
        fold = lambda text: "".join(  # noqa: E731
            char for char in unicodedata.normalize("NFKD", text.casefold()) if char.isalnum()
        )
        return bool(fold(a)) and fold(a) == fold(b)
    if left <= right or right <= left:
        return True
    return len(left & right) / min(len(left), len(right)) >= 0.5


def _instant(value: str) -> str:
    if len(value) == 10:
        return value
    moment = datetime.fromisoformat(value)
    if moment.tzinfo is not None:
        moment = moment.astimezone(UTC)
    return moment.strftime("%Y-%m-%dT%H:%M")


async def duplicates(connection: AsyncConnection, event: Occurrence | Event) -> list[Occurrence]:
    start = (
        datetime.fromisoformat(event.start)
        if len(event.start) > 10
        else datetime.fromisoformat(f"{event.start}T00:00:00+00:00")
    )
    end = (
        datetime.fromisoformat(event.end)
        if len(event.end) > 10
        else datetime.fromisoformat(f"{event.end}T23:59:00+00:00")
    )
    if start.tzinfo is None:
        start = start.replace(tzinfo=UTC)
    if end.tzinfo is None:
        end = end.replace(tzinfo=UTC)
    found = await occurrences(connection, start - timedelta(minutes=1), end + timedelta(minutes=1))
    return [
        one
        for one in found
        if one.calendar_id != event.calendar_id
        and one.status != "cancelled"
        and _instant(one.start) == _instant(event.start)
        and _instant(one.end) == _instant(event.end)
        and similar(one.title, event.title)
    ]
