from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta
from typing import Any

from sqlalchemy.ext.asyncio import AsyncConnection

import arga_contracts as contracts
from arga_contracts import records as write
from travel import journal, travel

APP = "travel"
MODES = {"plane": "plane", "train": "train", "car": "car", "bus": "bus", "boat": "boat"}
CATEGORIES = {"transport": "Transport", "lodging": "Lodging", "other": "Other"}


def _trip_id(trip: travel.Trip) -> str:
    return f"trip:{trip.id}"


def _title(trip: travel.Trip) -> str:
    return f"{trip.starts_on:%Y-%m} {trip.title}"


def _country(code: str, name: str) -> str:
    return write.link(APP, f"country:{code}", name)


def _upper_first(text: str) -> str:
    return text[:1].upper() + text[1:]


def _span(first: date, last: date) -> str:
    if first == last:
        return f"on {write.long_date(first)}"
    return f"from {write.long_date(first)} to {write.long_date(last)}"


def trip(one: travel.Trip, countries: dict[str, str]) -> dict[str, Any]:
    lead = [
        _upper_first(_span(one.starts_on, one.ends_on)),
        f"{one.days} {'day' if one.days == 1 else 'days'}, "
        f"{one.nights} {'night' if one.nights == 1 else 'nights'}",
    ]
    if one.travellers > 1:
        lead.append(f"{one.travellers} people")
    if one.companions:
        lead.append("with " + ", ".join(one.companions))
    codes = list(one.countries)
    places = []
    if codes:
        places.append(
            "Countries: " + ", ".join(_country(code, countries.get(code, code)) for code in codes)
        )
    stays = "\n".join(
        f"- {stay.place.name}"
        + (f", {stay.place.country}" if stay.place.country else "")
        + f": {_span(stay.arrives_on, stay.leaves_on)}, {stay.nights} "
        + ("night" if stay.nights == 1 else "nights")
        + (f" · {stay.accommodation}" if stay.accommodation else "")
        for stay in one.stays
    )
    visits = "\n".join(
        f"- {visit.place.name}"
        + (f" ({write.long_date(visit.visited_on)})" if visit.visited_on else "")
        + (f" · {visit.note}" if visit.note else "")
        for visit in one.visits
    )
    legs = write.table(
        ["Day", "Leg", "How", "Km"],
        [
            [
                leg.travelled_on.isoformat() if leg.travelled_on else "",
                f"{leg.from_place.name} → {leg.to_place.name}",
                MODES[leg.mode],
                write.number(leg.km) if leg.km is not None else "",
            ]
            for leg in one.legs
        ],
    )
    expenses = write.table(
        ["Category", "Concept", "Per person"],
        [
            [CATEGORIES[expense.category], expense.concept, write.euros(expense.amount_eur)]
            for expense in one.expenses
        ],
    )
    spend = None
    if one.expenses:
        spend = f"{write.euros(one.spend.per_person)} per person"
        if one.travellers > 1:
            spend += f", {write.euros(one.spend.group)} the group"
        if one.spend.per_day is not None:
            spend += f", {write.euros(one.spend.per_day)} a day"
        spend += "."
    properties: dict[str, Any] = {
        "start": one.starts_on.isoformat(),
        "end": one.ends_on.isoformat(),
        "days": one.days,
        "nights": one.nights,
        "travellers": one.travellers,
        "countries": [countries.get(code, code) for code in one.countries],
        "km": round(one.km),
    }
    if one.companions:
        properties["companions"] = one.companions
    if one.expenses:
        properties["spend_per_person_eur"] = one.spend.per_person
    if one.tags:
        properties["tags"] = one.tags
    if one.archived:
        properties["archived"] = True
    return contracts.record(
        id=_trip_id(one),
        title=_title(one),
        kind="Trip",
        href=f"/travel/trips/{one.id}",
        folder="Trips",
        properties=properties,
        body=write.sections(
            " · ".join(lead) + ".",
            "\n".join(places) if places else None,
            f"## Where you slept\n\n{stays}" if stays else None,
            f"## What you visited\n\n{visits}" if visits else None,
            f"## Legs\n\n{legs}" if legs else None,
            f"## Expenses\n\n{spend}\n\n{expenses}" if spend else None,
            f"## Notes\n\n{one.notes}" if one.notes else None,
        ),
    )


def country(area: travel.AreaVisited, trips: list[travel.Trip]) -> dict[str, Any]:
    mine = [one for one in trips if area.code in one.countries]
    lines = "\n".join(
        f"- {write.link(APP, _trip_id(one), _title(one))}"
        for one in sorted(mine, key=lambda one: one.starts_on)
    )
    lead = f"{area.trips} {'trip' if area.trips == 1 else 'trips'}"
    if area.nights:
        lead += f", {area.nights} {'night' if area.nights == 1 else 'nights'}"
    properties: dict[str, Any] = {
        "code": area.code,
        "trips": area.trips,
        "nights": area.nights,
        "slept": area.slept,
    }
    if area.first:
        properties["first_time"] = area.first.isoformat()
    if area.last:
        properties["last_time"] = area.last.isoformat()
    return contracts.record(
        id=f"country:{area.code}",
        title=area.name,
        kind="Country",
        href="/travel/",
        folder="Countries",
        properties=properties,
        body=write.sections(
            lead + ".",
            "Places: " + ", ".join(area.places) + "." if area.places else None,
            f"## Trips\n\n{lines}" if lines else None,
        ),
    )


def days(trips: list[travel.Trip]) -> list[dict[str, Any]]:
    lines: dict[date, list[str]] = defaultdict(list)
    for one in sorted(trips, key=lambda one: one.starts_on):
        for index in range(one.days):
            day = one.starts_on + timedelta(days=index)
            where = next(
                (stay.place.name for stay in one.stays if stay.arrives_on <= day < stay.leaves_on),
                None,
            )
            shown = write.link(APP, _trip_id(one), one.title)
            line = f"- Travelling: {shown} (day {index + 1} of {one.days})"
            if where:
                line += f" · sleeping in {where}"
            lines[day].append(line)
        for leg in one.legs:
            if leg.travelled_on is not None:
                lines[leg.travelled_on].append(
                    f"- {MODES[leg.mode].capitalize()}: {leg.from_place.name} → {leg.to_place.name}"
                )
    return [
        contracts.record(
            id=f"day:{day.isoformat()}",
            title="Travel",
            kind="Day",
            href="/travel/trips",
            day=day,
            body="\n".join(found),
        )
        for day, found in sorted(lines.items())
    ]


def journal_days(entries: list[journal.Entry], titles: dict[str, str]) -> list[dict[str, Any]]:
    return [
        contracts.record(
            id=f"journal:{one.trip_id}:{one.day.isoformat()}",
            title=f"Journal · {titles.get(one.trip_id, 'Trip')}",
            kind="Journal",
            href=f"/travel/trips/{one.trip_id}/journal",
            day=one.day,
            body=one.body,
        )
        for one in entries
    ]


async def build(connection: AsyncConnection) -> list[dict[str, Any]]:
    every = await travel.all_trips(connection)
    trips = travel.lived(every)
    others = await travel.other_places(connection)
    areas = travel.areas_visited(trips, "country", others)
    names = {area.code: area.name for area in areas}
    return (
        [trip(one, names) for one in trips]
        + [country(area, trips) for area in areas]
        + days(trips)
        + journal_days(await journal.every_entry(connection), {one.id: one.title for one in every})
    )
