from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel

from travel import geo
from travel.travel.common import MODES
from travel.travel.models import Trip
from travel.travel.others import OtherPlace


class AreaVisited(BaseModel):
    code: str
    name: str
    slept: bool
    trips: int
    nights: int
    first: date | None
    last: date | None
    places: list[str]


def areas_visited(
    trips: list[Trip],
    level: Literal["country", "region"],
    others: list[OtherPlace] | None = None,
) -> list[AreaVisited]:
    known = geo.names()
    found: dict[str, dict] = {}

    def note(code: str | None, trip_: Trip | None, nights: int, slept: bool, place: str) -> None:
        if not code:
            return
        entry = found.setdefault(
            code,
            {"trips": set(), "nights": 0, "slept": False, "dates": [], "places": []},
        )
        if trip_ is not None:
            entry["trips"].add(trip_.id)
            entry["dates"] += [trip_.starts_on, trip_.ends_on]
        entry["nights"] += nights
        entry["slept"] = entry["slept"] or slept
        if place not in entry["places"]:
            entry["places"].append(place)

    for one in trips:
        for stay in one.stays:
            code = stay.place.country_code if level == "country" else stay.place.region_code
            note(code, one, stay.nights, True, stay.place.name)
        for visit in one.visits:
            code = visit.place.country_code if level == "country" else visit.place.region_code
            note(code, one, 0, False, visit.place.name)
    for other in others or []:
        code = other.place.country_code if level == "country" else other.place.region_code
        note(code, None, 0, False, other.place.name)
    return sorted(
        (
            AreaVisited(
                code=code,
                name=known.get(code, code),
                slept=entry["slept"],
                trips=len(entry["trips"]),
                nights=entry["nights"],
                first=min(entry["dates"], default=None),
                last=max(entry["dates"], default=None),
                places=entry["places"],
            )
            for code, entry in found.items()
        ),
        key=lambda area: (-area.trips, -area.nights, area.name),
    )


class YearRow(BaseModel):
    year: int
    trips: int
    nights: int
    km: float
    spend_per_person: float


class Stats(BaseModel):
    trips: int
    nights: int
    km: float
    countries: int
    regions: int
    europe_visited: list[str]
    europe_total: int
    by_year: list[YearRow]
    km_by_mode: dict[str, float]
    top_countries: list[AreaVisited]
    cost_per_day: list[dict]
    average_cost_per_day: float | None
    spend_per_night_by_country: list[dict]
    nights_calendar: dict[str, int]


def stats(trips: list[Trip], others: list[OtherPlace] | None = None) -> Stats:
    countries = areas_visited(trips, "country", others)
    regions = areas_visited(trips, "region", others)
    years: dict[int, YearRow] = {}
    km_by_mode = {mode: 0.0 for mode in MODES}
    per_night: dict[str, list[float]] = {}
    calendar: dict[str, int] = {}
    for one in trips:
        row = years.setdefault(
            one.starts_on.year,
            YearRow(year=one.starts_on.year, trips=0, nights=0, km=0.0, spend_per_person=0.0),
        )
        row.trips += 1
        row.nights += one.nights
        row.km = round(row.km + one.km, 1)
        row.spend_per_person = round(row.spend_per_person + one.spend.per_person, 2)
        for leg in one.legs:
            km_by_mode[leg.mode] = round(km_by_mode[leg.mode] + (leg.km or 0), 1)
        slept = [s for s in one.stays if s.place.country_code and s.nights]
        total_nights = sum(s.nights for s in slept)
        if one.spend.per_person and total_nights:
            share: dict[str, int] = {}
            for s in slept:
                share[s.place.country_code] = share.get(s.place.country_code, 0) + s.nights  # type: ignore[index]
            for code, nights in share.items():
                amount = one.spend.per_person * nights / total_nights
                per_night.setdefault(code, [0.0, 0])  # type: ignore[arg-type]
                per_night[code][0] += amount
                per_night[code][1] += nights
        for offset in range(one.nights):
            day = date.fromordinal(one.starts_on.toordinal() + offset).isoformat()
            calendar[day] = calendar.get(day, 0) + 1
    costed = [one for one in trips if one.spend.per_day is not None]
    known = geo.names()
    return Stats(
        trips=len(trips),
        nights=sum(one.nights for one in trips),
        km=round(sum(one.km for one in trips), 1),
        countries=len(countries),
        regions=len(regions),
        europe_visited=sorted(area.code for area in countries if area.code in geo.EUROPE),
        europe_total=len(geo.EUROPE),
        by_year=sorted(years.values(), key=lambda row: row.year),
        km_by_mode=km_by_mode,
        top_countries=countries[:10],
        cost_per_day=[
            {
                "trip_id": one.id,
                "title": one.title,
                "starts_on": one.starts_on.isoformat(),
                "per_day": one.spend.per_day,
            }
            for one in sorted(costed, key=lambda one: one.starts_on)
        ],
        average_cost_per_day=(
            round(sum(one.spend.per_day or 0 for one in costed) / len(costed), 2)
            if costed
            else None
        ),
        spend_per_night_by_country=sorted(
            (
                {
                    "code": code,
                    "name": known.get(code, code),
                    "per_night": round(amount / nights, 2),
                    "nights": nights,
                }
                for code, (amount, nights) in per_night.items()
            ),
            key=lambda row: -row["per_night"],
        ),
        nights_calendar=calendar,
    )
