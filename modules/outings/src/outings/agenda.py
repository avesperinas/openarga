from __future__ import annotations

import json
from datetime import date, datetime, timedelta
from typing import Any, Literal

from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from arga_agenda import KEY as AGENDA
from arga_agenda import dated, uid
from outings import profile
from outings.common import MADRID, TZ, Conflict, NotFound, enqueue, today
from outings.profile import fold

EVENT = "leisure.event"
CONNECTION = "hub.connection"
RUN = "hub.run"
PLAN = "outings.plan"
CATEGORIES = ("eat", "stage", "culture", "festival", "outdoors")
Category = Literal["eat", "stage", "culture", "festival", "outdoors"]
Period = Literal["weekend", "week", "month", "year"]


LATEST = text("""
    select distinct on (payload->>'connection', payload->>'key') payload, ts
    from outings.events
    where type = 'leisure.event'
    order by payload->>'connection', payload->>'key', ts desc, ingested_at desc
""")

STATES = text("""
    select distinct on (payload->>'connection') payload->>'connection' as connection, payload
    from outings.events
    where type = 'hub.connection'
    order by payload->>'connection', ts desc, ingested_at desc
""")

KNOWN = text("""
    select connection::text as connection, key, fingerprint, removed, event_id::text as event_id
    from outings.outings_event_source
    where connection is not null
""")

NEW_EVENT = text("""
    insert into outings.outings_event (title, starts_on, ends_on, category)
    values (:title, :starts_on, :ends_on, :category)
    returning id::text
""")

UPSERT_SOURCE = text("""
    insert into outings.outings_event_source (event_id, connection, key, fingerprint, payload)
    values (cast(:event as uuid), cast(:connection as uuid), :key, :fingerprint,
            cast(:payload as jsonb))
    on conflict (user_id, connection, key) do update
    set fingerprint = excluded.fingerprint, payload = excluded.payload, removed = false,
        last_seen = now()
""")

REMOVE_SOURCES = text("""
    update outings.outings_event_source set removed = true
    where connection = cast(:connection as uuid) and not removed
    returning event_id::text
""")


async def derive(connection: AsyncConnection) -> dict[str, int]:
    states = {row.connection: row.payload for row in await connection.execute(STATES)}
    gone = {key for key, state in states.items() if state.get("removed")}
    known = {(row.connection, row.key): row for row in await connection.execute(KNOWN)}
    touched: set[str] = set()
    added = changed = merged = 0
    for key in gone:
        for row in await connection.execute(REMOVE_SOURCES, {"connection": key}):
            touched.add(row.event_id)
    for row in await connection.execute(LATEST):
        payload = row.payload
        source = (payload["connection"], payload["key"])
        if payload["connection"] in gone:
            continue
        found = known.get(source)
        if found is not None and found.fingerprint == payload["fingerprint"] and not found.removed:
            continue
        if found is None:
            event_id = await twin(connection, payload)
        if found is None and event_id is not None:
            merged += 1
        elif found is None:
            event_id = await connection.scalar(
                NEW_EVENT,
                {
                    "title": payload["title"][:200],
                    "starts_on": date.fromisoformat(payload["starts_on"]),
                    "ends_on": date.fromisoformat(payload["ends_on"]),
                    "category": payload["category"],
                },
            )
            added += 1
        else:
            event_id = found.event_id
            changed += 1
        await connection.execute(
            UPSERT_SOURCE,
            {
                "event": event_id,
                "connection": payload["connection"],
                "key": payload["key"],
                "fingerprint": payload["fingerprint"],
                "payload": json.dumps(payload),
            },
        )
        touched.add(event_id)
    for event_id in touched:
        await refresh(connection, event_id)
    result = {"added": added, "changed": changed, "refreshed": len(touched)}
    if merged:
        result["merged"] = merged
    return result


NEAR = text("""
    select e.id::text as id, e.title, e.town, e.starts_on, e.ends_on
    from outings.outings_event e
    where not e.hidden
      and e.starts_on <= cast(:ends_on as date) + 1
      and e.ends_on >= cast(:starts_on as date) - 1
      and not exists (
          select 1 from outings.outings_event_source s where s.event_id = e.id and s.alone
      )
""")

FILLER = {"de", "del", "la", "las", "el", "los", "y", "en", "a", "al", "con", "por", "para"}


def haystack(event: Any) -> str:
    parts = (event.title, event.venue, event.town, event.summary, " ".join(event.programme))
    return f" {fold(' '.join(part for part in parts if part))} "


def mentions(event: Any, terms: list[str]) -> bool:
    text_ = haystack(event)
    return any(f" {term} " in text_ for term in terms)


MUTED = text("select folded from outings.outings_interest where kind = 'mute'")


async def muted_terms(connection: AsyncConnection) -> list[str]:
    return [row.folded for row in await connection.execute(MUTED)]


def _words(value: str) -> set[str]:
    return {word for word in fold(value).split() if word not in FILLER and len(word) > 1}


def same_title(one: str, other: str) -> bool:
    a, b = fold(one), fold(other)
    if not a or not b:
        return False
    if a == b or (min(len(a), len(b)) >= 8 and (a in b or b in a)):
        return True
    left, right = _words(one), _words(other)
    if len(left) < 2 or len(right) < 2:
        return False
    return len(left & right) / len(left | right) >= 0.6


def same_town(one: str | None, other: str | None) -> bool:
    return not one or not other or fold(one) == fold(other)


async def twin(connection: AsyncConnection, payload: dict[str, Any]) -> str | None:
    rows = await connection.execute(
        NEAR,
        {
            "starts_on": date.fromisoformat(payload["starts_on"]),
            "ends_on": date.fromisoformat(payload["ends_on"]),
        },
    )
    for row in rows:
        if same_town(row.town, payload.get("town")) and same_title(row.title, payload["title"]):
            return row.id
    return None


async def split(connection: AsyncConnection, event_id: str, source_id: str) -> Event:
    row = (
        await connection.execute(
            text("""
                select payload from outings.outings_event_source
                where id = cast(:source as uuid) and event_id = cast(:event as uuid)
            """),
            {"source": source_id, "event": event_id},
        )
    ).one_or_none()
    if row is None:
        raise NotFound(f"fuente {source_id} del evento {event_id}")
    others = await connection.scalar(
        text("""
            select count(*) from outings.outings_event_source
            where event_id = cast(:event as uuid) and id <> cast(:source as uuid) and not removed
        """),
        {"source": source_id, "event": event_id},
    )
    if not others:
        raise Conflict("ese evento solo tiene esa fuente", "ONLY_SOURCE")
    payload = row.payload
    created = await connection.scalar(
        NEW_EVENT,
        {
            "title": payload["title"][:200],
            "starts_on": date.fromisoformat(payload["starts_on"]),
            "ends_on": date.fromisoformat(payload["ends_on"]),
            "category": payload["category"],
        },
    )
    await connection.execute(
        text("""
            update outings.outings_event_source
            set event_id = cast(:created as uuid), alone = true
            where id = cast(:source as uuid)
        """),
        {"created": created, "source": source_id},
    )
    await refresh(connection, event_id)
    await refresh(connection, created)
    return await event(connection, created)


SOURCES_OF = text("""
    select payload, last_seen from outings.outings_event_source
    where event_id = cast(:id as uuid) and not removed
    order by last_seen desc, first_seen
""")


async def refresh(connection: AsyncConnection, event_id: str) -> None:
    rows = (await connection.execute(SOURCES_OF, {"id": event_id})).all()
    if not rows:
        await connection.execute(
            text("update outings.outings_event set hidden = true where id = cast(:id as uuid)"),
            {"id": event_id},
        )
        return
    main = rows[0].payload
    title = min((row.payload["title"] for row in rows), key=lambda one: (one.isupper(), len(one)))[
        :200
    ]
    links: list[dict[str, str]] = []
    for row in rows:
        link = {
            "name": row.payload.get("source_name") or "",
            "url": row.payload["link"],
            "page": row.payload.get("source_page") or row.payload["link"],
        }
        if link not in links:
            links.append(link)
    before = await connection.execute(
        text(
            "select starts_on, ends_on, start_time, title, in_calendar "
            "from outings.outings_event where id = cast(:id as uuid)"
        ),
        {"id": event_id},
    )
    previous = before.one()
    await connection.execute(
        text("""
            update outings.outings_event
            set title = :title, starts_on = :starts_on, ends_on = :ends_on, start_time = :time,
                venue = :venue, town = :town, category = :category, summary = :summary,
                links = cast(:links as jsonb), hidden = false,
                programme = cast(:programme as jsonb), highlight = :highlight,
                last_seen = now(), updated_at = now()
            where id = cast(:id as uuid)
        """),
        {
            "id": event_id,
            "title": title,
            "starts_on": date.fromisoformat(main["starts_on"]),
            "ends_on": date.fromisoformat(main["ends_on"]),
            "time": main.get("time")
            or next((row.payload["time"] for row in rows if row.payload.get("time")), None),
            "venue": main.get("venue"),
            "town": main.get("town"),
            "category": main["category"],
            "summary": main.get("summary"),
            "links": json.dumps(links),
            "programme": json.dumps(
                next((row.payload["programme"] for row in rows if row.payload.get("programme")), [])
            ),
            "highlight": any(bool(row.payload.get("highlight")) for row in rows),
        },
    )
    moved = (previous.starts_on, previous.ends_on, previous.start_time, previous.title) != (
        date.fromisoformat(main["starts_on"]),
        date.fromisoformat(main["ends_on"]),
        main.get("time"),
        title,
    )
    if previous.in_calendar and moved:
        await publish_plan(connection, await event(connection, event_id))


class Link(BaseModel):
    name: str
    url: str
    page: str


class EventSource(BaseModel):
    id: str
    name: str
    page: str


class Event(BaseModel):
    id: str
    title: str
    starts_on: date
    ends_on: date
    time: str | None
    venue: str | None
    town: str | None
    category: Category
    summary: str | None
    links: list[Link]
    in_calendar: bool
    wish_id: str | None
    first_seen: datetime
    last_seen: datetime
    lat: float | None = None
    lon: float | None = None
    sources: list[EventSource] = []
    programme: list[str] = []
    highlight: bool = False
    dismissed: bool = False
    zone: profile.Zone = "region"


COLUMNS = """
    e.id::text as id, e.title, e.starts_on, e.ends_on, e.start_time, e.venue, e.town, e.category,
    e.summary, e.links, e.in_calendar, e.first_seen, e.last_seen,
    e.programme, e.highlight, e.dismissed_at,
    (select w.id::text from outings.outings_wish w where w.event_id = e.id) as wish_id,
    (select v.lat from outings.outings_venue v
     where v.name = coalesce(e.venue, e.town) and v.town = coalesce(e.town, '')) as lat,
    (select v.lon from outings.outings_venue v
     where v.name = coalesce(e.venue, e.town) and v.town = coalesce(e.town, '')) as lon
"""


def _event(row: Any) -> Event:
    return Event(
        id=row.id,
        title=row.title,
        starts_on=row.starts_on,
        ends_on=row.ends_on,
        time=row.start_time,
        venue=row.venue,
        town=row.town,
        category=row.category,
        summary=row.summary,
        links=[Link(**link) for link in row.links or []],
        in_calendar=row.in_calendar,
        wish_id=row.wish_id,
        lat=row.lat,
        lon=row.lon,
        first_seen=row.first_seen,
        last_seen=row.last_seen,
        programme=list(row.programme or []),
        highlight=row.highlight,
        dismissed=row.dismissed_at is not None,
        zone=profile.current().zone(row.town),
    )


def window(period: Period, day: date | None = None) -> tuple[date, date]:
    day = day or today()
    if period == "weekend":
        friday = day + timedelta(days=(4 - day.weekday()) % 7) if day.weekday() < 4 else day
        sunday = day + timedelta(days=6 - day.weekday())
        return friday, sunday
    span = {"week": 6, "month": 30, "year": 365}[period]
    return day, day + timedelta(days=span)


async def events(
    connection: AsyncConnection,
    first: date,
    last: date,
    category: str | None = None,
    town: str | None = None,
    everything: bool = False,
) -> list[Event]:
    where = ["not e.hidden", "e.starts_on <= :last", "e.ends_on >= :first"]
    if not everything:
        where.append("e.dismissed_at is null")
    params: dict[str, Any] = {"first": first, "last": last}
    if category:
        where.append("e.category = :category")
        params["category"] = category
    if town:
        where.append("e.town ilike :town")
        params["town"] = f"%{town.strip()}%"
    rows = await connection.execute(
        text(
            f"select {COLUMNS} from outings.outings_event e where {' and '.join(where)} "
            "order by e.starts_on, e.start_time nulls first, e.title"
        ),
        params,
    )
    found = [_event(row) for row in rows]
    if everything:
        return found
    muted = await muted_terms(connection)
    return [one for one in found if one.in_calendar or one.wish_id or not mentions(one, muted)]


async def event(connection: AsyncConnection, event_id: str) -> Event:
    found = await _bare(connection, event_id)
    rows = await connection.execute(
        text("""
            select id::text as id, payload from outings.outings_event_source
            where event_id = cast(:id as uuid) and not removed order by first_seen
        """),
        {"id": event_id},
    )
    found.sources = [
        EventSource(
            id=row.id,
            name=row.payload.get("source_name") or "",
            page=row.payload.get("source_page") or row.payload["link"],
        )
        for row in rows
    ]
    return found


async def _bare(connection: AsyncConnection, event_id: str) -> Event:
    row = (
        await connection.execute(
            text(f"select {COLUMNS} from outings.outings_event e where e.id = cast(:id as uuid)"),
            {"id": event_id},
        )
    ).one_or_none()
    if row is None:
        raise NotFound(f"evento {event_id}")
    return _event(row)


def _dated(found: Event, cancelled: bool = False) -> dict[str, Any]:
    where = ", ".join(part for part in (found.venue, found.town) if part) or None
    common = {
        "uid": uid("outings", "event", found.id),
        "title": found.title,
        "tz": TZ,
        "location": where[:300] if where else None,
        "status": "cancelled" if cancelled else "confirmed",
        "href": f"/outings/eventos/{found.id}",
    }
    if found.time and found.starts_on == found.ends_on:
        hour, minute = (int(part) for part in found.time.split(":"))
        start = datetime(
            found.starts_on.year, found.starts_on.month, found.starts_on.day, hour % 24, minute,
            tzinfo=MADRID,
        )  # fmt: skip
        return dated(**common, start=start, end=start + timedelta(hours=2), all_day=False)
    return dated(
        **common, start=found.starts_on, end=found.ends_on + timedelta(days=1), all_day=True
    )


async def publish_plan(connection: AsyncConnection, found: Event) -> None:
    await enqueue(
        connection,
        PLAN,
        f"plan:{found.id}",
        {
            "event_id": found.id,
            "title": found.title,
            "category": found.category,
            AGENDA: _dated(found, cancelled=not found.in_calendar),
        },
    )


async def to_calendar(connection: AsyncConnection, event_id: str, on: bool) -> Event:
    updated = await connection.execute(
        text("""
            update outings.outings_event set in_calendar = :on, updated_at = now()
            where id = cast(:id as uuid)
        """),
        {"id": event_id, "on": on},
    )
    if updated.rowcount == 0:
        raise NotFound(f"evento {event_id}")
    found = await event(connection, event_id)
    await publish_plan(connection, found)
    return found


SAVE = text("""
    insert into outings.outings_wish
        (kind, name, body, place_name, place_town, event_id, starts_on, ends_on, source)
    values ('plan', :name, :body, :place, :town, cast(:event as uuid), :starts_on, :ends_on,
            :source)
    on conflict (user_id, event_id) where event_id is not null do nothing
    returning id::text
""")


async def save(connection: AsyncConnection, event_id: str, source: str = "app") -> str:
    found = await event(connection, event_id)
    if found.wish_id:
        return found.wish_id
    place = found.venue or found.town
    created = await connection.scalar(
        SAVE,
        {
            "name": found.title[:120],
            "body": found.summary,
            "place": place[:200] if place else None,
            "town": found.town if found.venue else None,
            "event": found.id,
            "starts_on": found.starts_on,
            "ends_on": found.ends_on,
            "source": source,
        },
    )
    return created or (await event(connection, event_id)).wish_id or ""


RUNS = text("""
    select distinct on (payload->>'connection') payload->>'connection' as connection, payload
    from outings.events
    where type = 'hub.run'
    order by payload->>'connection', ts desc, ingested_at desc
""")


class Source(BaseModel):
    connection: str
    label: str
    state: str
    missing: list[str]
    paused: bool
    last_run_at: datetime | None
    last_outcome: str | None
    last_detail: str | None


async def sources(connection: AsyncConnection) -> list[Source]:
    runs = {row.connection: row.payload for row in await connection.execute(RUNS)}
    out: list[Source] = []
    for row in await connection.execute(STATES):
        state = row.payload
        if state.get("removed") or EVENT not in (state.get("produces") or []):
            continue
        run = runs.get(row.connection) or {}
        finished = run.get("finished_at")
        out.append(
            Source(
                connection=row.connection,
                label=state.get("label") or "Agenda",
                state=state.get("state") or "active",
                missing=state.get("missing") or [],
                paused=bool(state.get("paused")),
                last_run_at=datetime.fromisoformat(finished) if finished else None,
                last_outcome=run.get("outcome"),
                last_detail=run.get("detail"),
            )
        )
    return sorted(out, key=lambda one: one.label.casefold())
