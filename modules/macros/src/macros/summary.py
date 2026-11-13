from __future__ import annotations

from datetime import date, timedelta
from typing import Any, Literal

from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

import arga_nutrients
from macros import catalog, detail
from macros import expenditure as spending
from macros import goals as ranges
from macros import meals as slots
from macros.common import Conflict, now, today
from macros.intake import Entry, entries

ENOUGH_COVERAGE = 0.8
ALCOHOL_UNIT_G = 10.0
TARGET_MARGIN = 0.1
KCAL_PER_GRAM = {"saturated_fat": 9.0, "sugars": 4.0}


class Target(BaseModel):
    valid_from: date
    kcal: float | None = None
    protein: float | None = None
    carbs: float | None = None
    fat: float | None = None


class TargetIn(BaseModel):
    valid_from: date | None = None
    kcal: float | None = Field(default=None, ge=500, le=10000)
    protein: float | None = Field(default=None, ge=0, le=1000)
    carbs: float | None = Field(default=None, ge=0, le=1000)
    fat: float | None = Field(default=None, ge=0, le=1000)


TARGET_ON = text("""
    select valid_from, kcal, protein, carbs, fat from macros.macros_target
    where valid_from <= :day order by valid_from desc limit 1
""")

SET_TARGET = text("""
    insert into macros.macros_target (valid_from, kcal, protein, carbs, fat)
    values (:valid_from, :kcal, :protein, :carbs, :fat)
    on conflict (user_id, valid_from) do update
       set kcal = excluded.kcal, protein = excluded.protein, carbs = excluded.carbs,
           fat = excluded.fat, created_at = now()
""")


def _float(value: Any) -> float | None:
    return None if value is None else float(value)


async def target_on(connection: AsyncConnection, day: date) -> Target | None:
    _, resolved = await ranges.resolve(connection, day)
    return target_from(resolved, day)


def target_from(resolved: dict[str, ranges.Resolved], day: date) -> Target | None:
    mine = {
        key: one
        for key, one in resolved.items()
        if key in arga_nutrients.MACROS and one.source != "efsa" and one.goal is not None
    }
    if not mine:
        return None
    kcal = ranges.aim(mine["kcal"].goal, None) if "kcal" in mine else None  # type: ignore[arg-type]
    values = {key: ranges.aim(one.goal, kcal) for key, one in mine.items()}  # type: ignore[arg-type]
    if all(value is None for value in values.values()):
        return None
    starts = [one.valid_from for one in mine.values() if one.valid_from is not None]
    return Target(valid_from=max(starts) if starts else day, **values)


async def set_target(connection: AsyncConnection, request: TargetIn) -> Target:
    if all(getattr(request, key) is None for key in ("kcal", "protein", "carbs", "fat")):
        raise Conflict("a target needs at least kcal or one macro")
    valid_from = request.valid_from or today()
    await connection.execute(
        SET_TARGET,
        {
            "valid_from": valid_from,
            "kcal": request.kcal,
            "protein": request.protein,
            "carbs": request.carbs,
            "fat": request.fat,
        },
    )
    for key in arga_nutrients.MACROS:
        value = getattr(request, key)
        if value is None:
            continue
        margin = ranges.LEGACY_MARGIN
        if key == "protein":
            low, high = value, None
        else:
            low, high = value * (1 - margin), value * (1 + margin)
        await connection.execute(
            ranges.SET_GOAL,
            {
                "valid_from": valid_from,
                "profile": "any",
                "nutrient": key,
                "basis": "amount",
                "min": round(low, 1),
                "max": None if high is None else round(high, 1),
            },
        )
    found = await target_on(connection, valid_from)
    assert found is not None
    return found


class Profile(BaseModel):
    sex: str | None = None
    age: int | None = None
    from_health: bool = False


PROFILE = text("""
    select payload from macros.events
    where type = 'health.profile'
    order by ingested_at desc, ts desc
    limit 1
""")

OWN_REFERENCES = text("select nutrient, kind, value from macros.macros_reference")

SET_REFERENCE = text("""
    insert into macros.macros_reference (nutrient, kind, value) values (:nutrient, :kind, :value)
    on conflict (user_id, nutrient) do update set kind = excluded.kind, value = excluded.value
""")

DROP_REFERENCE = text("delete from macros.macros_reference where nutrient = :nutrient")


async def profile(connection: AsyncConnection, on: date | None = None) -> Profile:
    row = (await connection.execute(PROFILE)).first()
    if row is None:
        return Profile()
    payload = row.payload or {}
    birth = payload.get("birth_date")
    try:
        born = date.fromisoformat(birth) if birth else None
    except ValueError:
        born = None
    sex = payload.get("sex") if payload.get("sex") in ("female", "male") else None
    return Profile(
        sex=sex,
        age=arga_nutrients.age_on(born, on or today()),
        from_health=bool(sex or born),
    )


class Reference(BaseModel):
    nutrient: str
    kind: Literal["min", "max", "energy_share"]
    value: float
    own: bool = False


class ReferenceIn(BaseModel):
    kind: Literal["min", "max", "energy_share"]
    value: float = Field(ge=0, le=100_000)


async def references(connection: AsyncConnection, person: Profile) -> dict[str, Reference]:
    found = {
        key: Reference(nutrient=key, kind=one.kind, value=one.value)
        for key, one in arga_nutrients.references(person.sex, person.age).items()
    }
    for row in (await connection.execute(OWN_REFERENCES)).all():
        found[row.nutrient] = Reference(
            nutrient=row.nutrient, kind=row.kind, value=float(row.value), own=True
        )
    return found


async def set_reference(
    connection: AsyncConnection, nutrient: str, request: ReferenceIn | None
) -> None:
    if nutrient not in arga_nutrients.KEYS:
        raise Conflict(f"'{nutrient}' is not an arga nutrient")
    if request is None:
        await ranges.set_goal(connection, ranges.GoalIn(nutrient=nutrient, reset=True))
        return
    if request.kind == "energy_share" and request.value > 1:
        raise Conflict("a share of kcal goes from 0 to 1: 0.1 is 10 %")
    if request.kind == "energy_share" and nutrient not in arga_nutrients.KCAL_PER_GRAM:
        raise Conflict(f"{nutrient} has no kcal: its reference is an amount")
    if request.kind == "min":
        one = ranges.GoalIn(nutrient=nutrient, min=request.value)
    elif request.kind == "max":
        one = ranges.GoalIn(nutrient=nutrient, max=request.value)
    else:
        one = ranges.GoalIn(nutrient=nutrient, max=request.value * 100, unit="kcal_pct")
    await ranges.set_goal(connection, one)


class Drinks(BaseModel):
    caffeine_mg: float | None
    alcohol_g: float | None
    alcohol_units: float | None
    water_l: float


class Day(BaseModel):
    day: date
    nutrients: dict[str, float]
    coverage: dict[str, float]
    target: Target | None
    remaining: dict[str, float]
    drinks: Drinks
    entries: list[Entry]
    goals: list[ranges.GoalState] = []
    day_kind: ranges.DayKind | None = None
    groups: list[detail.Group] = []
    caffeine: detail.Caffeine | None = None
    planned: list[Entry] = []
    meals: list[slots.MealOut] = []
    complete: bool = False


def coverage(found: list[Entry]) -> dict[str, float]:
    items = [item for entry in found for item in entry.items]
    kcal = sum(item.nutrients.get("kcal", 0.0) for item in items)
    keys = {key for item in items for key in item.nutrients}
    if kcal <= 0:
        return {key: 1.0 for key in keys}
    return {
        key: round(
            sum(item.nutrients.get("kcal", 0.0) for item in items if key in item.nutrients) / kcal,
            3,
        )
        for key in keys
    }


def drinks(found: list[Entry]) -> Drinks:
    total = arga_nutrients.added(*(entry.nutrients for entry in found))
    water = sum(item.quantity for entry in found for item in entry.items if item.kind == "water")
    alcohol = total.get("alcohol")
    return Drinks(
        caffeine_mg=None if "caffeine" not in total else round(total["caffeine"], 1),
        alcohol_g=None if alcohol is None else round(alcohol, 1),
        alcohol_units=None if alcohol is None else round(alcohol / ALCOHOL_UNIT_G, 1),
        water_l=round(water / 1000, 2),
    )


async def day_meals(
    connection: AsyncConnection, on: date, found: list[Entry], planned: list[Entry]
) -> list[slots.MealOut]:
    usual = await slots.usual_times(connection, on)
    moment = now()
    current = slots.meal_of(moment) if on == moment.date() else None
    out = []
    for key in slots.ORDER:
        mine = [entry for entry in found if entry.meal == key]
        later = [entry for entry in planned if entry.meal == key]
        if key == "night" and not mine and not later:
            continue
        total = arga_nutrients.added(*(entry.nutrients for entry in mine))
        out.append(
            slots.MealOut(
                meal=key,
                label=slots.label(key),
                usual_at=usual[key].strftime("%H:%M"),
                started=slots.started(key, on, moment),
                current=key == current,
                kcal=round(total.get("kcal", 0.0), 1),
                protein=round(total.get("protein", 0.0), 1),
                entry_ids=[entry.id for entry in mine],
                planned_ids=[entry.id for entry in later],
            )
        )
    return out


async def day(connection: AsyncConnection, on: date) -> Day:
    found = await entries(connection, on, on)
    total = arga_nutrients.added(*(entry.nutrients for entry in found))
    kind, resolved = await ranges.resolve(connection, on)
    goal = target_from(resolved, on)
    shares = coverage(found)
    kcal_goal = resolved.get("kcal")
    states = ranges.evaluate(
        resolved,
        total,
        shares,
        None if kcal_goal is None else ranges.aim(kcal_goal.goal, None),  # type: ignore[arg-type]
    )
    planned = await entries(connection, on, on, None, ("planned",))
    remaining = {}
    if goal is not None:
        for key in arga_nutrients.MACROS:
            wanted = getattr(goal, key)
            if wanted is not None:
                remaining[key] = round(wanted - total.get(key, 0.0), 1)
    return Day(
        day=on,
        nutrients={key: round(value, 2) for key, value in total.items()},
        coverage=shares,
        target=goal,
        remaining=remaining,
        drinks=drinks(found),
        entries=found,
        goals=states,
        day_kind=kind,
        groups=detail.groups(found, states),
        caffeine=detail.caffeine(found, on),
        planned=planned,
        meals=await day_meals(connection, on, found, planned),
        complete=await spending.is_complete(connection, on),
    )


class DayMark(BaseModel):
    day: date
    kcal: float | None
    against_target: Literal["over", "under", "on", "none"]


class Micro(BaseModel):
    key: str
    name: str
    unit: str
    value: float | None
    coverage: float
    reference: Reference | None
    status: Literal["low", "high", "ok", "none"]
    partial: bool
    missing: list[str]
    goal: ranges.GoalState | None = None


class Counted(BaseModel):
    days: int
    complete: bool


class Week(BaseModel):
    first: date
    last: date
    days_logged: int
    averages: dict[str, float]
    days: list[DayMark]
    micros: list[Micro]
    profile: Profile
    drinks: Drinks
    goals: list[ranges.GoalState] = []
    compliance: list[Compliance] = []
    expenditure: spending.Expenditure | None = None
    counted: Counted | None = None


class Compliance(BaseModel):
    nutrient: str
    name: str
    states: list[str]


COMPLIANCE_FRONT = ("kcal", "protein", "carbs", "fat", "fiber", "sugars", "saturated_fat", "sodium")


def status(value: float | None, reference: Reference | None, kcal: float | None) -> str:
    if value is None or reference is None:
        return "none"
    if reference.kind == "min":
        return "low" if value < reference.value else "ok"
    if reference.kind == "max":
        return "high" if value > reference.value else "ok"
    share_of = KCAL_PER_GRAM.get(reference.nutrient)
    if not share_of or not kcal:
        return "none"
    return "high" if value * share_of / kcal > reference.value else "ok"


def _status(state: ranges.GoalState | None, value: float | None) -> str:
    if state is None or value is None:
        return "none"
    return {"low": "low", "high": "high", "ok": "ok"}.get(state.status, "none")


MIN_COMPLETE = 3


async def complete_days(connection: AsyncConnection, first: date, last: date) -> set[date]:
    found = await connection.execute(spending.COMPLETE, {"first": first, "last": last})
    return set(found.scalars())


async def week(
    connection: AsyncConnection, last: date, all_micros: bool = False, only_complete: bool = True
) -> Week:
    first = last - timedelta(days=6)
    every = await entries(connection, first, last)
    by_day: dict[date, list[Entry]] = {}
    for entry in every:
        by_day.setdefault(entry.day, []).append(entry)
    complete = await complete_days(connection, first, last) if only_complete else set()
    with_complete = {day for day in by_day if day in complete}
    counted = Counted(days=len(by_day), complete=False)
    found = every
    if only_complete and len(with_complete) >= MIN_COMPLETE:
        found = [entry for entry in every if entry.day in with_complete]
        counted = Counted(days=len(with_complete), complete=True)
    logged = counted.days
    total = arga_nutrients.added(*(entry.nutrients for entry in found))
    averages = {key: round(value / logged, 2) for key, value in total.items()} if logged else {}
    shares = coverage(found)

    marks = []
    daily: list[dict[str, str]] = []
    for offset in range(7):
        on = first + timedelta(days=offset)
        eaten = by_day.get(on)
        kcal = round(sum(entry.nutrients.get("kcal", 0.0) for entry in eaten), 1) if eaten else None
        _, resolved = await ranges.resolve(connection, on)
        if eaten:
            eaten_total = arga_nutrients.added(*(entry.nutrients for entry in eaten))
            daily.append(
                {
                    one.nutrient: one.status
                    for one in ranges.evaluate(resolved, eaten_total, coverage(eaten))
                }
            )
        else:
            daily.append({})
        kcal_goal = resolved.get("kcal")
        mark: Literal["over", "under", "on", "none"] = "none"
        if kcal is not None and kcal_goal is not None and kcal_goal.goal is not None:
            low, high = kcal_goal.goal.min, kcal_goal.goal.max
            if high is not None and kcal > high:
                mark = "over"
            elif low is not None and kcal < low:
                mark = "under"
            else:
                mark = "on"
        marks.append(DayMark(day=on, kcal=kcal, against_target=mark))

    person = await profile(connection, last)
    refs = await references(connection, person)
    _, resolved = await ranges.resolve(connection, last)
    kcal_goal = resolved.get("kcal")
    week_goals = ranges.evaluate(
        resolved,
        averages,
        shares if logged else None,
        None if kcal_goal is None else ranges.aim(kcal_goal.goal, None),  # type: ignore[arg-type]
    )
    rows = [
        key
        for key in arga_nutrients.KEYS
        if key in resolved and (key in COMPLIANCE_FRONT or resolved[key].source == "own")
    ]
    order = {one.key: index for index, one in enumerate(arga_nutrients.NUTRIENTS)}
    compliance = [
        Compliance(
            nutrient=key,
            name=catalog.nutrient(key),
            states=[day.get(key, "none") for day in daily],
        )
        for key in sorted(rows, key=lambda one: order[one])
    ]
    states = {
        one.nutrient: one for one in ranges.evaluate(resolved, averages, shares if logged else None)
    }
    items = [item for entry in found for item in entry.items]
    micros = []
    for nutrient in arga_nutrients.NUTRIENTS:
        if nutrient.key in arga_nutrients.MACROS or not (nutrient.front or all_micros):
            continue
        value = averages.get(nutrient.key)
        share = shares.get(nutrient.key, 0.0) if logged else 0.0
        missing = sorted(
            {
                item.name
                for item in items
                if nutrient.key not in item.nutrients and item.nutrients.get("kcal", 0) > 0
            }
        )
        reference = refs.get(nutrient.key)
        state = states.get(nutrient.key)
        micros.append(
            Micro(
                key=nutrient.key,
                name=catalog.nutrient(nutrient.key),
                unit=nutrient.unit,
                value=value,
                coverage=share,
                reference=reference,
                goal=state,
                status=_status(state, value),
                partial=bool(logged) and share < ENOUGH_COVERAGE,
                missing=missing[:10],
            )
        )
    average_drinks = drinks(found)
    if logged:
        average_drinks = Drinks(
            caffeine_mg=None
            if average_drinks.caffeine_mg is None
            else round(average_drinks.caffeine_mg / logged, 1),
            alcohol_g=None
            if average_drinks.alcohol_g is None
            else round(average_drinks.alcohol_g / logged, 1),
            alcohol_units=None
            if average_drinks.alcohol_units is None
            else round(average_drinks.alcohol_units / logged, 1),
            water_l=round(average_drinks.water_l / logged, 2),
        )
    return Week(
        first=first,
        last=last,
        days_logged=logged,
        averages=averages,
        days=marks,
        micros=micros,
        profile=person,
        drinks=average_drinks,
        goals=week_goals,
        compliance=compliance,
        expenditure=await spending.estimate(connection, last + timedelta(days=1)),
        counted=counted,
    )


class TrendDay(BaseModel):
    day: date
    kcal: float | None
    complete: bool


class TrendWeek(BaseModel):
    first: date
    last: date
    counted: int


class Trend(BaseModel):
    days: list[TrendDay]
    weeks: list[TrendWeek]
    nutrients: dict[str, list[float | None]]


async def trend(connection: AsyncConnection, last: date, weeks: int = 8) -> Trend:
    first = last - timedelta(days=7 * weeks - 1)
    found = await entries(connection, first, last)
    complete = await complete_days(connection, first, last)
    by_day: dict[date, list[Entry]] = {}
    for entry in found:
        by_day.setdefault(entry.day, []).append(entry)
    days = []
    for offset in range(7 * weeks):
        on = first + timedelta(days=offset)
        eaten = by_day.get(on)
        kcal = round(sum(one.nutrients.get("kcal", 0.0) for one in eaten), 1) if eaten else None
        days.append(TrendDay(day=on, kcal=kcal, complete=on in complete and eaten is not None))
    person = await profile(connection, last)
    refs = {
        key: one
        for key, one in (await references(connection, person)).items()
        if one.kind in ("min", "max") and one.value > 0
    }
    shares: dict[str, list[float | None]] = {key: [] for key in refs}
    spans = []
    for index in range(weeks):
        start = first + timedelta(days=7 * index)
        end = start + timedelta(days=6)
        chosen = [entry for entry in found if start <= entry.day <= end and entry.day in complete]
        count = len({entry.day for entry in chosen})
        spans.append(TrendWeek(first=start, last=end, counted=count))
        total = arga_nutrients.added(*(entry.nutrients for entry in chosen)) if chosen else {}
        cover = coverage(chosen) if chosen else {}
        for key, reference in refs.items():
            if count < MIN_COMPLETE or cover.get(key, 0.0) < ENOUGH_COVERAGE or key not in total:
                shares[key].append(None)
            else:
                shares[key].append(round(total[key] / count / reference.value, 3))
    return Trend(days=days, weeks=spans, nutrients=shares)
