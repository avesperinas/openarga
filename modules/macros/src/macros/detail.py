from __future__ import annotations

import math
from datetime import date, datetime, time, timedelta
from typing import Any

from pydantic import BaseModel

import arga_nutrients
from macros.common import MADRID, now
from macros.intake import Entry

EPA_DHA = "omega3_epa_dha"
ENOUGH_COVERAGE = 0.8
CAFFEINE_HALF_LIFE_H = 5.0
CURVE_STEP = timedelta(minutes=30)

GROUPS: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    (
        "vitamins",
        "Vitaminas",
        tuple(one.key for one in arga_nutrients.NUTRIENTS if one.group == "vitamin"),
    ),
    (
        "minerals",
        "Minerales",
        tuple(one.key for one in arga_nutrients.NUTRIENTS if one.group == "mineral"),
    ),
    (
        "fats",
        "Ácidos grasos",
        (
            "saturated_fat",
            "monounsaturated_fat",
            "polyunsaturated_fat",
            "trans_fat",
            "omega3_ala",
            EPA_DHA,
        ),
    ),
    ("sugars", "Azúcares", ("sugars", "added_sugars", "lactose", "fructose")),
    ("other", "Otros", ("caffeine", "cholesterol", "alcohol", "water")),
)


class GroupItem(BaseModel):
    key: str
    name: str
    unit: str
    value: float | None
    coverage: float
    partial: bool
    status: str = "none"
    min: float | None = None
    max: float | None = None
    goal_unit: str | None = None


class Group(BaseModel):
    key: str
    name: str
    items: list[GroupItem]


class Contributor(BaseModel):
    name: str
    value: float
    share: float
    times: int


class Contributors(BaseModel):
    nutrient: str
    name: str
    unit: str
    total: float | None
    coverage: float
    items: list[Contributor]
    without: list[str]


class CaffeinePoint(BaseModel):
    at: datetime
    mg: float


class Caffeine(BaseModel):
    total_mg: float
    last_at: datetime | None
    now_mg: float
    half_life_h: float = CAFFEINE_HALF_LIFE_H
    curve: list[CaffeinePoint]


def _per_item(entries: list[Entry]) -> list[tuple[Entry, Any, dict[str, float]]]:
    found = []
    for entry in entries:
        for item in entry.items:
            values = dict(item.nutrients)
            if "omega3_epa" in values or "omega3_dha" in values:
                values[EPA_DHA] = values.get("omega3_epa", 0.0) + values.get("omega3_dha", 0.0)
            if item.kind == "water":
                values["water"] = values.get("water", 0.0) + item.quantity
            found.append((entry, item, values))
    return found


def _coverage(lines: list[tuple[Entry, Any, dict[str, float]]], key: str) -> float:
    kcal = sum(values.get("kcal", 0.0) for _, _, values in lines)
    if kcal <= 0:
        return 1.0 if any(key in values for _, _, values in lines) else 0.0
    having = sum(values.get("kcal", 0.0) for _, _, values in lines if key in values)
    return round(having / kcal, 3)


def _name_unit(key: str) -> tuple[str, str]:
    if key == EPA_DHA:
        return "Omega 3 (EPA + DHA)", "g"
    if key == "water":
        return "Agua", "ml"
    nutrient = arga_nutrients.BY_KEY[key]
    return nutrient.name, nutrient.unit


def groups(entries: list[Entry], states: list[Any]) -> list[Group]:
    lines = _per_item(entries)
    by_goal = {one.nutrient: one for one in states}
    out = []
    for key, name, keys in GROUPS:
        items = []
        for nutrient in keys:
            having = [values[nutrient] for _, _, values in lines if nutrient in values]
            share = _coverage(lines, nutrient)
            label, unit = _name_unit(nutrient)
            state = by_goal.get(nutrient)
            items.append(
                GroupItem(
                    key=nutrient,
                    name=label,
                    unit=unit,
                    value=round(sum(having), 3) if having else None,
                    coverage=share,
                    partial=bool(lines) and share < ENOUGH_COVERAGE,
                    status=state.status if state else "none",
                    min=state.min if state else None,
                    max=state.max if state else None,
                    goal_unit=state.basis if state else None,
                )
            )
        out.append(Group(key=key, name=name, items=items))
    return out


def contributors(entries: list[Entry], key: str, limit: int = 10) -> Contributors:
    if key != EPA_DHA and key != "water" and key not in arga_nutrients.KEYS:
        raise ValueError(f"'{key}' no es un nutriente de arga")
    lines = _per_item(entries)
    total = sum(values.get(key, 0.0) for _, _, values in lines)
    by_name: dict[str, list[float]] = {}
    for _, item, values in lines:
        if values.get(key):
            by_name.setdefault(item.name, []).append(values[key])
    ranked = sorted(by_name.items(), key=lambda pair: sum(pair[1]), reverse=True)
    name, unit = _name_unit(key)
    without = sorted(
        {
            item.name
            for _, item, values in lines
            if key not in values and values.get("kcal", 0.0) > 0
        }
    )
    return Contributors(
        nutrient=key,
        name=name,
        unit=unit,
        total=round(total, 3) if any(key in values for _, _, values in lines) else None,
        coverage=_coverage(lines, key),
        items=[
            Contributor(
                name=one,
                value=round(sum(values), 3),
                share=round(sum(values) / total * 100, 1) if total else 0.0,
                times=len(values),
            )
            for one, values in ranked[:limit]
        ],
        without=without[:10],
    )


def _remaining(doses: list[tuple[datetime, float]], at: datetime) -> float:
    rate = math.log(2) / CAFFEINE_HALF_LIFE_H
    return sum(
        mg * math.exp(-rate * (at - taken).total_seconds() / 3600)
        for taken, mg in doses
        if taken <= at
    )


def caffeine(entries: list[Entry], day: date) -> Caffeine:
    doses = sorted(
        (entry.eaten_at.astimezone(MADRID), item.nutrients["caffeine"])
        for entry in entries
        for item in entry.items
        if item.nutrients.get("caffeine")
    )
    end = datetime.combine(day + timedelta(days=1), time.min, MADRID)
    moment = now()
    until = min(end, moment) if day == moment.date() else end
    curve: list[CaffeinePoint] = []
    if doses:
        start = doses[0][0].replace(minute=0 if doses[0][0].minute < 30 else 30, second=0)
        start = start.replace(microsecond=0)
        at = start
        while at <= until:
            curve.append(CaffeinePoint(at=at, mg=round(_remaining(doses, at), 1)))
            at += CURVE_STEP
    return Caffeine(
        total_mg=round(sum(mg for _, mg in doses), 1),
        last_at=doses[-1][0] if doses else None,
        now_mg=round(_remaining(doses, until), 1),
        curve=curve,
    )
