from __future__ import annotations

import hashlib
import json
from datetime import date, timedelta
from typing import Annotated, Any
from urllib.parse import urlsplit

from pydantic import BaseModel, Field, field_validator
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from outings import agenda, explore, profile
from outings.common import today


class EventIn(BaseModel):
    title: Annotated[str, Field(min_length=2, max_length=200)]
    starts_on: date
    ends_on: date | None = None
    time: Annotated[str, Field(pattern=r"^\d{1,2}:\d{2}$")] | None = None
    venue: Annotated[str, Field(max_length=200)] | None = None
    town: Annotated[str, Field(max_length=120)] | None = None
    category: agenda.Category
    summary: Annotated[str, Field(max_length=400)] | None = None
    link: Annotated[str, Field(max_length=1000)] = Field(
        description="La página que anuncia el evento, la que lo respalda."
    )
    programme: Annotated[
        list[Annotated[str, Field(min_length=2, max_length=160)]], Field(max_length=40)
    ] = Field(
        default_factory=list,
        description='Los actos de una fiesta, un festival o un ciclo: "Sáb 3, 12:00 · Concurso".',
    )
    highlight: bool = Field(
        default=False, description="De lo grande: lo que merece ir aunque haya que moverse."
    )

    @field_validator("link")
    @classmethod
    def _link(cls, value: str) -> str:
        parts = urlsplit(value.strip())
        if parts.scheme not in ("http", "https") or not parts.netloc:
            raise ValueError("el enlace es la dirección de la página que lo anuncia, con https://")
        return value.strip()


class Outcome(BaseModel):
    title: str
    outcome: str
    event_id: str | None = None
    reason: str | None = None


KNOWN = text("""
    select event_id::text as event_id, fingerprint from outings.outings_event_source
    where connection is null and key = :key
""")

SAVE = text("""
    insert into outings.outings_event_source
        (event_id, connection, origin, key, fingerprint, payload)
    values (cast(:event as uuid), null, 'tool', :key, :fingerprint, cast(:payload as jsonb))
    on conflict (user_id, key) where connection is null do update
    set fingerprint = excluded.fingerprint, payload = excluded.payload, removed = false,
        last_seen = now()
""")


def payload_of(item: EventIn) -> dict[str, Any]:
    host = urlsplit(item.link).netloc.removeprefix("www.")
    body = {
        "title": " ".join(item.title.split()),
        "starts_on": item.starts_on.isoformat(),
        "ends_on": (item.ends_on or item.starts_on).isoformat(),
        "time": item.time,
        "venue": item.venue,
        "town": item.town,
        "category": item.category,
        "summary": item.summary,
        "link": item.link,
        "source_name": f"Claude · {host}",
        "source_page": item.link,
        "programme": [" ".join(one.split()) for one in item.programme],
        "highlight": item.highlight,
    }
    body["key"] = hashlib.sha256(
        f"{agenda.fold(body['title'])}\n{body['starts_on']}".encode()
    ).hexdigest()[:24]
    body["fingerprint"] = hashlib.sha256(
        json.dumps(body, sort_keys=True, ensure_ascii=False).encode()
    ).hexdigest()[:32]
    return body


async def add(connection: AsyncConnection, items: list[EventIn]) -> list[Outcome]:
    first = today() - timedelta(days=1)
    last = today() + timedelta(days=366)
    out: list[Outcome] = []
    for item in items:
        ends = item.ends_on or item.starts_on
        if ends < item.starts_on:
            out.append(
                Outcome(title=item.title, outcome="dropped", reason="acaba antes de empezar")
            )
            continue
        if ends < first or item.starts_on > last:
            out.append(
                Outcome(
                    title=item.title,
                    outcome="dropped",
                    reason="fuera de fechas: ya pasó o es de dentro de más de un año",
                )
            )
            continue
        body = payload_of(item)
        found = (await connection.execute(KNOWN, {"key": body["key"]})).one_or_none()
        if found is not None and found.fingerprint == body["fingerprint"]:
            out.append(Outcome(title=item.title, outcome="unchanged", event_id=found.event_id))
            continue
        if found is not None:
            event_id, outcome = found.event_id, "updated"
        else:
            twin = await agenda.twin(connection, body)
            if twin is not None:
                event_id, outcome = twin, "joined"
            else:
                event_id = await connection.scalar(
                    agenda.NEW_EVENT,
                    {
                        "title": body["title"],
                        "starts_on": item.starts_on,
                        "ends_on": ends,
                        "category": item.category,
                    },
                )
                outcome = "added"
        await connection.execute(
            SAVE,
            {
                "event": event_id,
                "key": body["key"],
                "fingerprint": body["fingerprint"],
                "payload": json.dumps(body),
            },
        )
        await agenda.refresh(connection, event_id)
        out.append(Outcome(title=item.title, outcome=outcome, event_id=event_id))
    return out


NEAR_DAYS = 90
FAR_DAYS = 365

LANGUAGES = {"es": "Spanish", "de": "German", "en": "English", "fr": "French", "it": "Italian"}


def months_between(first: date, last: date) -> list[tuple[int, int]]:
    out: list[tuple[int, int]] = []
    year, month = first.year, first.month
    while (year, month) <= (last.year, last.month):
        out.append((year, month))
        year, month = (year + 1, 1) if month == 12 else (year, month + 1)
    return out


def searches(
    first: date, last: date, far: date | None = None, area: profile.Profile | None = None
) -> list[str]:
    area = area or profile.current()
    asked = area.searches
    out = list(asked.always)
    near = months_between(first, last)
    for year, month in near:
        name = area.months[month - 1]
        out.extend(one.format(month=name, year=year) for one in asked.monthly)
        out.extend(
            asked.season.format(thing=thing, month=name, year=year)
            for thing in area.season.get(month, [])
        )
    for year, month in months_between(first, far or last):
        if (year, month) in near:
            continue
        name = area.months[month - 1]
        out.extend(one.format(month=name, year=year) for one in asked.yearly)
        out.extend(
            asked.tradition.format(thing=one, year=year) for one in area.traditions.get(month, [])
        )
    return out


def _day(day: date) -> str:
    return day.isoformat()


def prompt(
    day: date | None = None,
    days: int = NEAR_DAYS,
    liked: list[str] | None = None,
    muted: list[str] | None = None,
    area: profile.Profile | None = None,
) -> str:
    area = area or profile.current()
    day = day or today()
    until = day + timedelta(days=days)
    far = day + timedelta(days=FAR_DAYS)
    language = LANGUAGES.get(area.language, area.language)
    agendas = "\n".join(f"- {one.name}: {one.url}" for one in area.agendas)
    looked = "\n".join(f"- {one}" for one in searches(day, until, far, area))
    extra = ""
    if liked:
        extra += "\nI am especially interested in: " + ", ".join(liked) + ". Look for it.\n"
    if muted:
        extra += "\nI am not interested in anything to do with: " + ", ".join(muted) + ".\n"
    return f"""Fill the Outings agenda, in OpenArga, with things to go out to in {area.name} \
and {area.region.name}: in detail from {_day(day)} to {_day(until)}, and from then to \
{_day(far)}, what comes back every year and already has a date.

{area.focus}

1. Look at what is already there with the find_events tool (when: quarter and when: year), so you
   do not repeat it.
2. Read these agendas:
{agendas}
3. Search the web, one by one, in {language} (and follow the links you find to other agendas: the
   town's, the neighbourhood's, the fair's):
{looked}
{extra}
What to add: everything that would get someone from {area.name} out of the house, in \
{area.near.name}, anywhere in {area.region.name}, and anything special less than two hours away.
- Yes: {area.include}
- Far ahead: for the months not looked at in detail, add what already has the date of its new
  edition on a page (the organiser's, the town hall's or the press). If you only find last year's,
  do not add it: it will show up when it is announced.
- A fiesta, a festival, a fair or a week is ONE event, with its dates from start to end and its
  acts in programme ("Sat 3, 12:00 · Contest"), never one event per act. A town's fiestas are one
  row, with what is special in its programme. A market that repeats every week or month is one
  row, with its next date and how often in the summary.
- highlight: true for the big things: a famous fiesta, a named fair, a festival, anything with a
  numbered edition, a concert by someone very well known.
- Do not add: {area.skip}

4. Add them with the add_events tool, in batches of up to 40. For each event: the title as its page
   writes it, start and end dates (YYYY-MM-DD), the time if there is one, the venue, the town, the
   category, a one-sentence summary in {language}, programme if it has acts, highlight and, always,
   the link to the page that announces it. Categories: eat (food and drink), stage (music,
   theatre, dance, cinema), culture (exhibitions, talks, tours), festival (fiestas, fairs, markets
   and street events) and outdoors (sport and nature).
5. If find_events shows single acts of something that is already an event with its programme, or
   things that should not be there, set them aside with the hide_events tool.

Only what you read on a page, nothing from memory: if you cannot find the page, do not add it. At
the end, tell me how many you added (and how many of them are not concerts), how many were
already there, how many you set aside, and which were dropped and why."""


async def brief(connection: AsyncConnection, days: int = NEAR_DAYS) -> str:
    found = await explore.interests(connection)
    return prompt(
        today(),
        days,
        [one.term for one in found if one.kind == "like"],
        [one.term for one in found if one.kind == "mute"],
    )
