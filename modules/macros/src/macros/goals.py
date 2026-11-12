from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any, Literal
from zoneinfo import ZoneInfo

from pydantic import BaseModel, Field, model_validator
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

import arga_contracts as contracts
import arga_nutrients
from macros import weight
from macros.common import TZ, Conflict, today

Profile = Literal["any", "training", "rest"]
Kind = Literal["training", "rest"]
Basis = Literal["amount", "kcal_pct", "per_kg"]
PER_KG = ("kcal", "protein", "carbs", "fat")
PER_KG_MAX = {"kcal": 100.0, "protein": 10.0, "carbs": 15.0, "fat": 10.0}
Source = Literal["own", "legacy", "efsa"]
Status = Literal["low", "ok", "high", "none"]

LEGACY_MARGIN = 0.1


@dataclass(frozen=True)
class Resolved:
    goal: arga_nutrients.Goal | None
    source: Source
    profile: Profile
    valid_from: date | None
    per_kg: PerKg | None = None


class PerKg(BaseModel):
    min: float | None
    max: float | None
    kg: float


class Goal(BaseModel):
    nutrient: str
    name: str
    unit: str
    basis: Basis
    min: float | None
    max: float | None
    source: Source
    profile: Profile
    valid_from: date | None = None
    per_kg: PerKg | None = None


class GoalState(Goal):
    value: float | None
    share: float | None = None
    low: float | None = None
    high: float | None = None
    status: Status
    coverage: float | None = None


class DayKind(BaseModel):
    day: date
    kind: Kind
    source: Literal["manual", "workout", "none"]
    workouts: list[str] = []


class GoalIn(BaseModel):
    nutrient: str = Field(min_length=2, max_length=40)
    min: float | None = Field(default=None, ge=0, le=100_000)
    max: float | None = Field(default=None, ge=0, le=100_000)
    unit: Basis = "amount"
    profile: Profile = "any"
    valid_from: date | None = None
    reset: bool = False

    @model_validator(mode="after")
    def _coherent(self) -> GoalIn:
        if self.nutrient not in arga_nutrients.KEYS:
            raise ValueError(f"'{self.nutrient}' no es un nutriente de arga")
        if self.min is not None and self.max is not None and self.min > self.max:
            raise ValueError("el mínimo va por debajo del máximo")
        if self.unit == "per_kg":
            if self.nutrient not in PER_KG:
                raise ValueError("por kilo solo van las kcal, la proteína, los hidratos y la grasa")
            top = PER_KG_MAX[self.nutrient]
            if (self.min or 0) > top or (self.max or 0) > top:
                raise ValueError(f"más de {top:g} por kilo no es un objetivo: ¿era en gramos?")
        if self.unit == "kcal_pct":
            if self.nutrient not in arga_nutrients.KCAL_PER_GRAM:
                raise ValueError(f"{self.nutrient} no aporta kcal: su objetivo va en cantidad")
            if (self.min or 0) > 100 or (self.max or 0) > 100:
                raise ValueError("un % de las kcal va de 0 a 100")
        return self


OWN = text("""
    select distinct on (profile, nutrient) profile, nutrient, basis, min, max, valid_from
    from macros.macros_goal
    where valid_from <= :day
    order by profile, nutrient, valid_from desc, created_at desc
""")

SET_GOAL = text("""
    insert into macros.macros_goal (valid_from, profile, nutrient, basis, min, max)
    values (:valid_from, :profile, :nutrient, :basis, :min, :max)
    on conflict (user_id, profile, nutrient, valid_from) do update
       set basis = excluded.basis, min = excluded.min, max = excluded.max, created_at = now()
""")

LEGACY_TARGET = text("""
    select valid_from, kcal, protein, carbs, fat from macros.macros_target
    where valid_from <= :day order by valid_from desc limit 1
""")

LEGACY_REFERENCES = text("select nutrient, kind, value from macros.macros_reference")

EVER_SET = text("select distinct nutrient from macros.macros_goal")

SET_LEGACY_REFERENCE = text("""
    insert into macros.macros_reference (nutrient, kind, value) values (:nutrient, :kind, :value)
    on conflict (user_id, nutrient) do update set kind = excluded.kind, value = excluded.value
""")

DROP_LEGACY_REFERENCE = text("delete from macros.macros_reference where nutrient = :nutrient")

MANUAL_KIND = text("select kind from macros.macros_day_kind where day = :day")

SET_KIND = text("""
    insert into macros.macros_day_kind (day, kind) values (:day, :kind)
    on conflict (user_id, day) do update set kind = excluded.kind
""")

DROP_KIND = text("delete from macros.macros_day_kind where day = :day")

WORKOUTS = text("""
    select distinct on (payload->'workout'->>'id') payload->'workout' as workout
    from macros.events
    where payload ? 'workout'
      and (payload->'workout'->>'start')::timestamptz between :since and :until
    order by payload->'workout'->>'id', ts desc, ingested_at desc
""")


def _number(value: Any) -> float | None:
    return None if value is None else float(value)


async def _legacy(connection: AsyncConnection, day: date) -> dict[str, Resolved]:
    found: dict[str, Resolved] = {}
    managed = set((await connection.execute(EVER_SET)).scalars().all())
    for row in (await connection.execute(LEGACY_REFERENCES)).all():
        if row.nutrient in managed:
            continue
        value = float(row.value)
        if row.kind == "min":
            goal = arga_nutrients.Goal(row.nutrient, "amount", value, None)
        elif row.kind == "max":
            goal = arga_nutrients.Goal(row.nutrient, "amount", None, value)
        else:
            goal = arga_nutrients.Goal(row.nutrient, "kcal_pct", None, round(value * 100, 3))
        found[row.nutrient] = Resolved(goal, "legacy", "any", None)
    target = (await connection.execute(LEGACY_TARGET, {"day": day})).first()
    if target is not None:
        for key in arga_nutrients.MACROS:
            value = _number(getattr(target, key))
            if value is None:
                continue
            if key == "protein":
                goal = arga_nutrients.Goal(key, "amount", value, None)
            else:
                goal = arga_nutrients.Goal(
                    key,
                    "amount",
                    round(value * (1 - LEGACY_MARGIN), 1),
                    round(value * (1 + LEGACY_MARGIN), 1),
                )
            found[key] = Resolved(goal, "legacy", "any", target.valid_from)
    return found


async def day_kind(connection: AsyncConnection, day: date) -> DayKind:
    manual = await connection.scalar(MANUAL_KIND, {"day": day})
    workouts = await _workouts_on(connection, day)
    if manual is not None:
        return DayKind(day=day, kind=manual, source="manual", workouts=workouts)
    if workouts:
        return DayKind(day=day, kind="training", source="workout", workouts=workouts)
    return DayKind(day=day, kind="rest", source="none")


async def _workouts_on(connection: AsyncConnection, day: date) -> list[str]:
    zone = ZoneInfo(TZ)
    since = datetime.combine(day - timedelta(days=1), datetime.min.time(), zone)
    until = datetime.combine(day + timedelta(days=2), datetime.min.time(), zone)
    names = []
    for row in (await connection.execute(WORKOUTS, {"since": since, "until": until})).all():
        try:
            one = contracts.Workout.model_validate(row.workout)
        except ValueError:
            continue
        if one.removed:
            continue
        if one.start.astimezone(ZoneInfo(one.tz)).date() == day:
            names.append(one.name)
    return sorted(names)


async def set_day_kind(connection: AsyncConnection, day: date, kind: Kind | None) -> DayKind:
    if kind is None:
        await connection.execute(DROP_KIND, {"day": day})
    else:
        await connection.execute(SET_KIND, {"day": day, "kind": kind})
    return await day_kind(connection, day)


async def resolve(connection: AsyncConnection, day: date) -> tuple[DayKind, dict[str, Resolved]]:
    from macros import summary

    kind = await day_kind(connection, day)
    person = await summary.profile(connection, day)
    history = await weight.history(connection)
    kg = next((one.kg for one in reversed(history.days) if one.day <= day), None)
    defaults = arga_nutrients.default_goals(person.sex, person.age, kg)
    legacy = await _legacy(connection, day)
    own: dict[tuple[str, str], Any] = {
        (row.profile, row.nutrient): row
        for row in (await connection.execute(OWN, {"day": day})).all()
    }

    found: dict[str, Resolved] = {}
    for key in arga_nutrients.KEYS:
        chosen: Resolved | None = None
        for profile in (kind.kind, "any"):
            row = own.get((profile, key))
            if row is None:
                continue
            if row.basis == "default":
                chosen = Resolved(defaults.get(key), "efsa", profile, row.valid_from)
            elif row.min is None and row.max is None:
                chosen = Resolved(None, "own", profile, row.valid_from)
            elif row.basis == "per_kg":
                low, high = _number(row.min), _number(row.max)
                if kg:
                    goal = arga_nutrients.Goal(
                        key,
                        "amount",
                        None if low is None else round(low * kg, 1),
                        None if high is None else round(high * kg, 1),
                    )
                    per = PerKg(min=low, max=high, kg=kg)
                    chosen = Resolved(goal, "own", profile, row.valid_from, per)
                else:
                    chosen = Resolved(None, "own", profile, row.valid_from)
            else:
                goal = arga_nutrients.Goal(key, row.basis, _number(row.min), _number(row.max))
                chosen = Resolved(goal, "own", profile, row.valid_from)
            break
        if chosen is None:
            chosen = legacy.get(key) or Resolved(defaults.get(key), "efsa", "any", None)
        if chosen.goal is not None:
            found[key] = chosen
    return kind, found


def _goal(key: str, resolved: Resolved) -> Goal:
    nutrient = arga_nutrients.BY_KEY[key]
    assert resolved.goal is not None
    return Goal(
        nutrient=key,
        name=nutrient.name,
        unit=nutrient.unit,
        basis=resolved.goal.basis,
        min=resolved.goal.min,
        max=resolved.goal.max,
        source=resolved.source,
        profile=resolved.profile,
        valid_from=resolved.valid_from,
        per_kg=resolved.per_kg,
    )


def aim(goal: arga_nutrients.Goal, kcal: float | None) -> float | None:
    sides = [one for one in (goal.min, goal.max) if one is not None]
    if not sides:
        return None
    value = sum(sides) / len(sides)
    if goal.basis == "kcal_pct":
        factor = arga_nutrients.KCAL_PER_GRAM.get(goal.key)
        if not factor or not kcal:
            return None
        return round(value / 100 * kcal / factor, 1)
    return round(value, 1)


def _grams(pct: float | None, kcal: float, factor: float) -> float | None:
    return None if pct is None else round(pct / 100 * kcal / factor, 1)


def evaluate(
    resolved: dict[str, Resolved],
    totals: dict[str, float],
    coverage: dict[str, float] | None = None,
    kcal_goal: float | None = None,
) -> list[GoalState]:
    eaten_kcal = totals.get("kcal") or 0.0
    reference_kcal = kcal_goal or eaten_kcal
    states = []
    for nutrient in arga_nutrients.NUTRIENTS:
        one = resolved.get(nutrient.key)
        if one is None or one.goal is None:
            continue
        goal = one.goal
        value = totals.get(nutrient.key)
        share = low = high = None
        if goal.basis == "kcal_pct":
            factor = arga_nutrients.KCAL_PER_GRAM[nutrient.key]
            if value is not None and eaten_kcal > 0:
                share = round(value * factor / eaten_kcal * 100, 1)
            measured = share
            if reference_kcal:
                low = _grams(goal.min, reference_kcal, factor)
                high = _grams(goal.max, reference_kcal, factor)
        else:
            measured = value
            low, high = goal.min, goal.max
        status: Status = "none"
        if measured is not None:
            if goal.min is not None and measured < goal.min:
                status = "low"
            elif goal.max is not None and measured > goal.max:
                status = "high"
            else:
                status = "ok"
        states.append(
            GoalState(
                **_goal(nutrient.key, one).model_dump(),
                value=None if value is None else round(value, 2),
                share=share,
                low=low,
                high=high,
                status=status,
                coverage=None if coverage is None else coverage.get(nutrient.key, 0.0),
            )
        )
    return states


async def current(connection: AsyncConnection, day: date | None = None) -> dict[str, Any]:
    on = day or today()
    kind, resolved = await resolve(connection, on)
    return {
        "day_kind": kind.model_dump(mode="json"),
        "goals": [
            as_said(_goal(nutrient.key, resolved[nutrient.key]))
            for nutrient in arga_nutrients.NUTRIENTS
            if nutrient.key in resolved
        ],
    }


def as_said(goal: Goal) -> dict[str, Any]:
    if goal.per_kg is not None:
        return {
            "nutrient": goal.nutrient,
            "name": goal.name,
            "min": goal.per_kg.min,
            "max": goal.per_kg.max,
            "unit": "per_kg",
            "nutrient_unit": goal.unit,
            "kg": goal.per_kg.kg,
            "amount": {"min": goal.min, "max": goal.max},
            "source": goal.source,
            "profile": goal.profile,
            "valid_from": None if goal.valid_from is None else goal.valid_from.isoformat(),
        }
    return {
        "nutrient": goal.nutrient,
        "name": goal.name,
        "min": goal.min,
        "max": goal.max,
        "unit": goal.basis,
        "nutrient_unit": goal.unit,
        "source": goal.source,
        "profile": goal.profile,
        "valid_from": None if goal.valid_from is None else goal.valid_from.isoformat(),
    }


async def set_goal(connection: AsyncConnection, request: GoalIn) -> dict[str, Any]:
    valid_from = request.valid_from or today()
    if request.reset:
        basis, low, high = "default", None, None
    else:
        basis, low, high = request.unit, request.min, request.max
    await connection.execute(
        SET_GOAL,
        {
            "valid_from": valid_from,
            "profile": request.profile,
            "nutrient": request.nutrient,
            "basis": basis,
            "min": low,
            "max": high,
        },
    )
    if request.profile == "any" and request.nutrient not in arga_nutrients.MACROS:
        await _write_legacy_reference(connection, request)
    return await current(connection, valid_from)


async def _write_legacy_reference(connection: AsyncConnection, request: GoalIn) -> None:
    if request.reset:
        await connection.execute(DROP_LEGACY_REFERENCE, {"nutrient": request.nutrient})
        return
    kind = value = None
    if request.unit == "kcal_pct" and request.max is not None and request.min is None:
        kind, value = "energy_share", request.max / 100
    elif request.unit == "amount" and request.min is not None and request.max is None:
        kind, value = "min", request.min
    elif request.unit == "amount" and request.max is not None and request.min is None:
        kind, value = "max", request.max
    if kind is None:
        return
    await connection.execute(
        SET_LEGACY_REFERENCE, {"nutrient": request.nutrient, "kind": kind, "value": value}
    )


def check_known(nutrient: str) -> None:
    if nutrient not in arga_nutrients.KEYS:
        raise Conflict(f"'{nutrient}' no es un nutriente de arga")
