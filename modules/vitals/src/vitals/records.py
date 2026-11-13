from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

import arga_contracts as contracts
from arga_contracts import records as write
from vitals import body, labs, sleep, steps, weight, workouts
from vitals.steps import today, zone

APP = "vitals"
DAY_PROPERTIES = {
    "resting_heart_rate": "resting_hr",
    "hrv_ms": "hrv_ms",
    "vo2max": "vo2max",
    "active_kcal": "active_kcal",
    "exercise_min": "exercise_min",
    "distance_km": "distance_km",
}

RESULTS = text("""
    select r.checkup_id, r.analyte_id, a.name, a.panel, a.position, r.value, r.value_text, r.unit,
           r.ref_low, r.ref_high
    from vitals.vitals_lab_result r
    join vitals.vitals_analyte a on a.id = r.analyte_id
    order by a.position
""")


def _number(value: float | None, digits: int = 2) -> str:
    return "" if value is None else write.trimmed(value, digits)


def _range(low: float | None, high: float | None) -> str:
    if low is not None and high is not None:
        return f"{_number(low)} – {_number(high)}"
    if low is not None:
        return f"≥ {_number(low)}"
    if high is not None:
        return f"≤ {_number(high)}"
    return ""


def _checkup_title(one: labs.Checkup) -> str:
    return (
        f"{one.day.isoformat()} {one.center}" if one.center else f"{one.day.isoformat()} Check-up"
    )


def checkup(one: labs.Checkup, results: list[Any]) -> dict[str, Any]:
    rows = []
    for row in results:
        value = labs._num(row.value)
        low, high = labs._num(row.ref_low), labs._num(row.ref_high)
        out = labs.out_of_range(value, low, high)
        shown = _number(value) if value is not None else (row.value_text or "")
        rows.append([row.name, f"**{shown}**" if out else shown, row.unit or "", _range(low, high)])
    properties: dict[str, Any] = {"date": one.day.isoformat(), "values": one.values}
    if one.center:
        properties["center"] = one.center
    if one.out:
        properties["out_of_range"] = one.out
    lead = f"Check-up of {write.long_date(one.day)}" + (f" at {one.center}" if one.center else "")
    outside = f"{one.out} out of range, in bold." if one.out else "Everything in range."
    return contracts.record(
        id=f"checkup:{one.id}",
        title=_checkup_title(one),
        kind="Check-up",
        href="/vitals/labs",
        folder="Check-ups",
        properties=properties,
        body=write.sections(
            f"{lead}. {one.values} {'value' if one.values == 1 else 'values'}. "
            + (outside if one.values else ""),
            write.table(["Analyte", "Value", "Unit", "Reference"], rows),
            f"## Notes\n\n{one.notes}" if one.notes else None,
        ),
    )


async def build(connection: AsyncConnection) -> list[dict[str, Any]]:
    checkups = await labs.checkups(connection)
    by_checkup: dict[str, list[Any]] = defaultdict(list)
    for row in (await connection.execute(RESULTS)).all():
        by_checkup[str(row.checkup_id)].append(row)
    found = [checkup(one, by_checkup[one.id]) for one in checkups]

    days: dict[date, dict[str, Any]] = defaultdict(dict)
    lines: dict[date, list[str]] = defaultdict(list)
    rows = (await connection.execute(weight.ALL)).all()
    for one in weight.daily([(row.day, float(row.kg)) for row in rows]):
        days[one.day]["weight_kg"] = one.kg
        lines[one.day].append(f"- Weight: {write.trimmed(one.kg)} kg")
    counted, _ = await steps.read(connection)
    for one in counted:
        days[one.day]["steps"] = one.steps
        lines[one.day].append(f"- Steps: {write.number(one.steps)}")
    measured = await body.read(connection)
    for metric in body.METRICS:
        for point in measured.get(metric.id, []):
            key = DAY_PROPERTIES.get(metric.id)
            if key:
                days[point.day][key] = round(point.value, max(metric.digits, 0))
            unit = f" {metric.unit}" if metric.unit else ""
            lines[point.day].append(
                f"- {metric.name}: {write.number(point.value, metric.digits)}{unit}"
            )
    for one in checkups:
        lines[one.day].append(
            f"- Check-up: {write.link(APP, f'checkup:{one.id}', _checkup_title(one))}"
        )
    found.extend(await weeks(connection, days))
    for day in sorted(set(days) | set(lines)):
        found.append(
            contracts.record(
                id=f"day:{day.isoformat()}",
                title="Health",
                kind="Day",
                href="/vitals/",
                day=day,
                properties=days.get(day, {}),
                body="\n".join(lines[day]),
            )
        )
    return found


WEEKS = 26


def _mean(values: list[float]) -> float | None:
    return sum(values) / len(values) if values else None


async def weeks(connection: AsyncConnection, days: dict[date, dict[str, Any]]) -> list[dict]:
    now = today()
    first = workouts.monday(now) - timedelta(weeks=WEEKS - 1)
    done = await workouts.between(connection, first, now)
    nights = await sleep.read(connection, first)
    out = []
    for index in range(WEEKS):
        start = first + timedelta(weeks=index)
        end = start + timedelta(days=6)
        mine = [one for one in done if start <= one.start.astimezone(zone()).date() <= end]
        slept = [one.minutes_asleep for one in nights if start <= one.day <= end]
        dates = [start + timedelta(days=i) for i in range(7)]
        span = [days[one] for one in dates if one in days]
        paces = _mean([one["steps"] for one in span if "steps" in one])
        kilos = _mean([one["weight_kg"] for one in span if "weight_kg" in one])
        if not (mine or slept or paces or kilos):
            continue
        properties: dict[str, Any] = {
            "week": start.isoformat(),
            "workouts": len(mine),
            "workout_min": sum(one.minutes for one in mine),
            "load": round(sum(one.heart.load for one in mine), 1),
        }
        lines = [
            f"- Workouts: {len(mine)}, {sum(one.minutes for one in mine)} min, load "
            f"{write.trimmed(properties['load'], 1)}"
        ]
        if slept:
            properties["sleep_min"] = round(_mean(slept))
            hours, minutes = divmod(properties["sleep_min"], 60)
            lines.append(f"- Average sleep: {hours} h {minutes:02d} min ({len(slept)} nights)")
        if paces:
            properties["average_steps"] = round(paces)
            lines.append(f"- Steps per day: {write.number(paces)}")
        if kilos:
            properties["weight_kg"] = round(kilos, 1)
            lines.append(f"- Average weight: {write.trimmed(kilos, 1)} kg")
        listed = [
            f"- {one.start.astimezone(zone()):%a %d} · {one.name} · {one.minutes} min"
            + (f" · average {round(one.heart.avg)} bpm" if one.heart.avg else "")
            for one in sorted(mine, key=lambda one: one.start)
        ]
        out.append(
            contracts.record(
                id=f"week:{start.isoformat()}",
                title=f"Week of {write.long_date(start)}",
                kind="Week",
                href="/vitals/training",
                folder="Weeks",
                properties=properties,
                body=write.sections("\n".join(lines), "\n".join(listed) if listed else None),
            )
        )
    return out
