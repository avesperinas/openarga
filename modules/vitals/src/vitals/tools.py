from __future__ import annotations

import datetime as dt
import os
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncConnection

from vitals import (
    body,
    heart,
    kpis,
    labs,
    patterns,
    rhythm,
    sleep,
    steps,
    stress,
    today,
    weight,
    workouts,
)
from vitals.weight import Conflict, NotFound

MODULE = "vitals"
WRITE_ROLE = f"mod_{MODULE}"
READ_ROLE = f"mod_{MODULE}_read"


def role_for_scopes(scopes: set[str]) -> str | None:
    if f"{MODULE}:write" in scopes:
        return WRITE_ROLE
    if f"{MODULE}:read" in scopes:
        return READ_ROLE
    return None


class GetKpis(BaseModel):
    pass


async def get_kpis(connection: AsyncConnection, arguments: GetKpis) -> dict[str, Any]:
    return (await kpis.read(connection)).model_dump(mode="json")


class GetSteps(BaseModel):
    since: dt.date | None = Field(default=None, description="From which day, `YYYY-MM-DD`.")
    until: dt.date | None = Field(default=None, description="Up to which day, inclusive.")
    group_by: steps.Period = Field(
        default="day",
        description=(
            "`day` gives each day; `week`, `month` and `year`, the total and the daily average."
        ),
    )


async def get_steps(connection: AsyncConnection, arguments: GetSteps) -> dict[str, Any]:
    goal = (await weight.goal(connection)).steps_per_day
    since = arguments.since or dt.date.min
    until = arguments.until or dt.date.max
    shown, received = await steps.read(connection, since, until)
    total = sum(one.steps for one in shown)
    return {
        "goal_per_day": goal,
        "days_with_data": len(shown),
        "total": total,
        "mean_per_day": round(total / len(shown)) if shown else None,
        "days_over_goal": sum(one.steps >= goal for one in shown) if goal else None,
        "items": (
            [{"date": one.day.isoformat(), "steps": one.steps} for one in shown[-400:]]
            if arguments.group_by == "day"
            else [one.model_dump(mode="json") for one in steps.buckets(shown, arguments.group_by)]
        ),
        "last_received": received.isoformat() if received else None,
    }


class GetWeight(BaseModel):
    since: dt.date | None = Field(default=None, description="From which day, `YYYY-MM-DD`.")
    until: dt.date | None = Field(default=None, description="Up to which day, inclusive.")


async def get_weight(connection: AsyncConnection, arguments: GetWeight) -> dict[str, Any]:
    found = await weight.summary(connection, entries=0)
    since = arguments.since or dt.date.min
    until = arguments.until or dt.date.max
    shown = [one for one in found.days if since <= one.day <= until]
    return {
        "days": [one.model_dump(mode="json") for one in shown[-400:]],
        "min": min(shown, key=lambda one: one.kg).model_dump(mode="json") if shown else None,
        "max": max(shown, key=lambda one: one.kg).model_dump(mode="json") if shown else None,
        "latest_average_7d": found.latest.avg7 if found.latest else None,
        "change_30d": found.change_30,
        "change_90d": found.change_90,
        "goal_band_kg": {"min": found.goal.weight_min_kg, "max": found.goal.weight_max_kg},
        "against_goal": found.against_goal,
    }


class GetBody(BaseModel):
    metrics: list[str] = Field(
        default_factory=list,
        max_length=10,
        description=(
            "Figure ids: `resting_heart_rate`, `hrv_ms`, `vo2max`, `active_kcal`, "
            "`walking_speed_kmh`... Empty, the card and summary of every figure with data, with "
            "their ids."
        ),
    )
    since: dt.date | None = Field(default=None, description="From which day, `YYYY-MM-DD`.")
    until: dt.date | None = Field(default=None, description="Up to which day, inclusive.")
    group_by: steps.Period = Field(
        default="day",
        description=(
            "`day` gives each day; `week`, `month` and `year`, the daily average of each period "
            "(and the total, for what adds up)."
        ),
    )


async def get_body(connection: AsyncConnection, arguments: GetBody) -> dict[str, Any]:
    if not arguments.metrics:
        return (await body.overview(connection)).model_dump(mode="json")
    unknown = [one for one in arguments.metrics if one not in body.BY_ID]
    if unknown:
        return {
            "unknown": unknown,
            "known": {one.id: one.name for one in body.METRICS},
        }
    out = {}
    for metric in arguments.metrics:
        found = await body.series(
            connection, metric, arguments.since, arguments.until, arguments.group_by
        )
        out[metric] = {
            **found.figure.model_dump(mode="json", exclude={"about"}),
            "points": [
                one.model_dump(mode="json", exclude_none=True) for one in found.points[-400:]
            ],
        }
    return {"metrics": out}


class GetLabResults(BaseModel):
    analytes: list[str] = Field(
        default_factory=list,
        max_length=20,
        description=(
            "Analyte ids or names: `ldl`, `hdl`, `cholesterol`, `glucose`... Empty, every one "
            "that has been measured."
        ),
    )


async def get_lab_results(connection: AsyncConnection, arguments: GetLabResults) -> dict[str, Any]:
    found = await labs.table(connection)
    days = {one.id: one.day.isoformat() for one in found.checkups}
    wanted: set[str] | None = None
    if arguments.analytes:
        try:
            wanted = {(await labs.find(connection, one)).id for one in arguments.analytes}
        except NotFound as error:
            return {"results": [], "note": f"unknown {error}"}
    return {
        "results": [
            {
                "analyte": row.analyte.id,
                "name": row.analyte.name,
                "about": row.analyte.about,
                "canonical_unit": row.analyte.unit,
                "values": [
                    {
                        "date": days[checkup],
                        **cell.model_dump(mode="json"),
                        "out_of_range": cell.out,
                    }
                    for checkup, cell in sorted(row.cells.items(), key=lambda item: days[item[0]])
                ],
            }
            for row in found.rows
            if wanted is None or row.analyte.id in wanted
        ],
        "note": "The range is the one in each check-up report. Vitals does not diagnose.",
    }


class GetCheckups(BaseModel):
    pass


async def get_checkups(connection: AsyncConnection, arguments: GetCheckups) -> dict[str, Any]:
    return {
        "checkups": [
            {
                "checkup_id": one.id,
                "date": one.day.isoformat(),
                "center": one.center,
                "values": one.values,
                "out_of_range": one.out,
                "has_pdf": one.document is not None,
            }
            for one in await labs.checkups(connection)
        ]
    }


class LogWeight(BaseModel):
    kg: float = Field(ge=20, le=400, description="The weight in kilograms, with decimals: `78.4`.")
    date: dt.date | None = Field(
        default=None,
        description="The day of the weigh-in, `YYYY-MM-DD`. Without it, today for the person.",
    )
    time: dt.time | None = Field(default=None, description="The time, `HH:MM`, if known.")
    note: str | None = Field(default=None, max_length=200, description="Only if something is said.")
    from_history: bool = Field(
        default=False,
        description=(
            "`true` when loading old weigh-ins from another app (MyFitnessPal), so they are told "
            "apart from those logged on the spot."
        ),
    )


async def log_weight(connection: AsyncConnection, arguments: LogWeight) -> dict[str, Any]:
    weighing = weight.WeightIn(
        kg=arguments.kg, day=arguments.date, at=arguments.time, note=arguments.note
    )
    logged = await weight.log(
        connection,
        weighing,
        source="history" if arguments.from_history else "claude",
    )
    found = await weight.summary(connection, entries=0)
    return {
        "logged": {
            "date": logged.entry.day.isoformat(),
            "kg": logged.entry.kg,
            "already_there": logged.already,
        },
        "latest_average_7d": found.latest.avg7 if found.latest else None,
        "change_30d": found.change_30,
    }


class RecordCheckup(BaseModel):
    date: dt.date = Field(description="The day of the check-up or the blood draw, `YYYY-MM-DD`.")
    center: str | None = Field(
        default=None, max_length=120, description="The occupational health service or the lab."
    )
    notes: str | None = Field(default=None, max_length=2000)


async def record_checkup(connection: AsyncConnection, arguments: RecordCheckup) -> dict[str, Any]:
    found, existed = await labs.record_checkup(
        connection,
        labs.CheckupIn(day=arguments.date, center=arguments.center, notes=arguments.notes),
    )
    base = os.environ.get("PUBLIC_URL", "http://localhost:8000").rstrip("/")
    return {
        "checkup_id": found,
        "already_existed": existed,
        "attach_pdf_url": f"{base}/vitals/labs?attach={found}",
    }


class AddLabResult(BaseModel):
    checkup_id: UUID = Field(description="The one `record_checkup` returns.")
    analyte: str = Field(
        min_length=1,
        max_length=80,
        description=(
            "The analyte id (`ldl`, `hemoglobin`, `urine_ph`...) or its name as the report writes "
            "it: `LDL cholesterol`, `GOT`. If it does not know it, it says which ones exist."
        ),
    )
    value: float | None = Field(default=None, description="The number, exactly as in the report.")
    value_text: str | None = Field(
        default=None, max_length=80, description="Only if there is no number: `Negative`, `Normal`."
    )
    unit: str | None = Field(default=None, max_length=30, description="As written: `mg/dL`.")
    ref_low: float | None = Field(default=None, description="The low end of the report range.")
    ref_high: float | None = Field(default=None, description="The high end of the report range.")


async def add_lab_result(connection: AsyncConnection, arguments: AddLabResult) -> dict[str, Any]:
    try:
        result = await labs.add_result(
            connection,
            str(arguments.checkup_id),
            labs.ResultIn(**arguments.model_dump(exclude={"checkup_id"})),
        )
    except (NotFound, Conflict, ValueError) as error:
        return {"added": None, "note": f"not logged: {error}"}
    return {"added": result.model_dump(mode="json")}


class GetSleep(BaseModel):
    since: dt.date | None = Field(default=None, description="From which night, `YYYY-MM-DD`.")
    until: dt.date | None = Field(default=None, description="Up to which night, inclusive.")
    group_by: steps.Period = Field(
        default="day",
        description=(
            "`day` gives each night; `week`, `month` and `year`, the average of their nights."
        ),
    )


async def get_sleep(connection: AsyncConnection, arguments: GetSleep) -> dict[str, Any]:
    found = await sleep.summary(connection, arguments.since, arguments.until)
    nights = found.nights[-400:]
    return {
        "last_night": (
            found.last.model_dump(mode="json", exclude={"segments"}) if found.last else None
        ),
        "mean_7_nights": found.mean_7.model_dump(mode="json"),
        "mean_30_nights": found.mean_30.model_dump(mode="json"),
        "items": (
            [one.model_dump(mode="json") for one in nights]
            if arguments.group_by == "day"
            else [one.model_dump(mode="json") for one in sleep.buckets(nights, arguments.group_by)]
        ),
        "note": "A night belongs to the day one wakes up; times are minutes from midnight "
        "(negative, before). The `score` is Vitals' own with the sum in view: duration against "
        "8 h up to 50, deep and REM full at 45 % up to 25, and time awake in bed, full at 5 % "
        "and empty at 25 %, up to 25.",
    }


class GetHeartDay(BaseModel):
    date: dt.date | None = Field(
        default=None, description="The day, `YYYY-MM-DD`. Without it, the last one with data."
    )


async def get_heart_day(connection: AsyncConnection, arguments: GetHeartDay) -> dict[str, Any]:
    day = arguments.date
    if day is None:
        known = await heart.days(connection, 1)
        if not known:
            return {"day": None, "note": "no day of heart rate has arrived yet"}
        day = known[0]
    found = await heart.of_day(connection, day)
    if found is None:
        return {"day": day.isoformat(), "note": "no heart rate on that day"}
    return {
        "day": day.isoformat(),
        "step_minutes": found.step,
        "lowest": found.min.model_dump() if found.min else None,
        "highest": found.max.model_dump() if found.max else None,
        "hours": [one.model_dump() for one in heart.hours(found)],
        "note": "Per hour: minimum, average and maximum of the spans (of `step_minutes` "
        "minutes). `minute` is the minute of the day the span starts.",
    }


class GetToday(BaseModel):
    pass


async def get_today(connection: AsyncConnection, arguments: GetToday) -> dict[str, Any]:
    found = await today.read(connection)
    out = found.model_dump(mode="json", exclude={"load": {"weeks"}})
    out["note"] = (
        "Each figure, against the average of your previous 60 days ± one standard deviation: "
        "`status` says whether it is inside, above or below. Without 14 days of data there is "
        "no band. It is neither a diagnosis nor a score."
    )
    return out


class GetStress(BaseModel):
    date: dt.date | None = Field(
        default=None, description="The day, `YYYY-MM-DD`. Without it, today."
    )


async def get_stress(connection: AsyncConnection, arguments: GetStress) -> dict[str, Any]:
    out = (await stress.read(connection, arguments.date)).model_dump(mode="json")
    out["note"] = (
        "An arga estimate, not Fitbit stress. `tension.minutes`: minutes awake and still with "
        "the heart rate above `threshold` (resting + 25 % of the heart rate reserve). "
        "`morning.score`: 50 + 12.5 × (HRV z − resting HR z) against your normal; 50 is the "
        "usual and higher is better recovered. It cannot tell stress from caffeine, heat or a "
        "cold."
    )
    return out


class GetWorkouts(BaseModel):
    since: dt.date | None = Field(default=None, description="From which day, `YYYY-MM-DD`.")
    until: dt.date | None = Field(default=None, description="Up to which day, inclusive.")
    id: str | None = Field(
        default=None,
        max_length=200,
        description="The id of a workout (from a call without it) for its heart rate minute by "
        "minute and its series.",
    )


def per_minute(beats: list[workouts.Beat]) -> list[dict[str, Any]]:
    grouped: dict[int, list[float]] = {}
    for one in beats:
        grouped.setdefault(one.s // 60, []).append(one.bpm)
    return [
        {"minute": minute, "avg": round(sum(found) / len(found)), "max": round(max(found))}
        for minute, found in sorted(grouped.items())
    ]


async def get_workouts(connection: AsyncConnection, arguments: GetWorkouts) -> dict[str, Any]:
    if arguments.id:
        found = await workouts.one(connection, arguments.id)
        if found is None:
            return {"note": "no such workout"}
        out = found.model_dump(mode="json", exclude={"beats"})
        out["heart_per_minute"] = per_minute(found.beats)
        return out
    last = arguments.until or steps.today()
    first = arguments.since or last - dt.timedelta(days=29)
    found = await workouts.between(connection, first, last)
    return {
        "since": first.isoformat(),
        "until": last.isoformat(),
        "total": len(found),
        "workouts": [one.model_dump(mode="json") for one in found],
        "note": "Zones 1 to 5 over the theoretical max heart rate (220 minus age): 50, 60, 70, "
        "80 and 90 %. `load` adds each minute times its zone (Edwards). `recovery_2min`, how "
        "much the heart rate dropped in the two minutes after.",
    }


class GetTrainingLoad(BaseModel):
    pass


async def get_training_load(
    connection: AsyncConnection, arguments: GetTrainingLoad
) -> dict[str, Any]:
    return (await workouts.load(connection)).model_dump(mode="json")


class GetSleepPatterns(BaseModel):
    pass


async def get_sleep_patterns(
    connection: AsyncConnection, arguments: GetSleepPatterns
) -> dict[str, Any]:
    out = (await patterns.read(connection)).model_dump(mode="json")
    out["note"] = "Averages of what happened in the last 90 days; they do not say why."
    return out


class GetCheckupChanges(BaseModel):
    pass


async def get_checkup_changes(
    connection: AsyncConnection, arguments: GetCheckupChanges
) -> dict[str, Any]:
    return (await labs.changes(connection)).model_dump(mode="json")


class GetHeartRhythm(BaseModel):
    pass


async def get_heart_rhythm(
    connection: AsyncConnection, arguments: GetHeartRhythm
) -> dict[str, Any]:
    found = await rhythm.ecgs(connection)
    alerts = await rhythm.irns(connection)
    profile = await body.profile(connection)
    return {
        "ecgs": [one.model_dump(mode="json") for one in found[:50]],
        "irregular_rhythm_alerts": [one.model_dump(mode="json") for one in alerts[:50]],
        "alerts_enabled": profile.irn_enrolled if profile else None,
        "note": "`result_text` is what the band's algorithm said, as is. `positive_windows` "
        "are the alert windows where it detected an irregular rhythm. Vitals neither "
        "interprets nor diagnoses.",
    }


class GetBand(BaseModel):
    pass


async def get_band(connection: AsyncConnection, arguments: GetBand) -> dict[str, Any]:
    found = await rhythm.devices(connection)
    if not found:
        return {"devices": [], "note": "no Google Health device has arrived yet"}
    return {
        "devices": [one.model_dump(mode="json") for one in found],
        "note": "`last_sync` is the last time the device passed its data to the phone; the "
        "battery, the one it had then.",
    }


@dataclass(frozen=True)
class Tool:
    arguments: type[BaseModel]
    run: Callable[..., Awaitable[dict[str, Any]]]


TOOLS: dict[str, Tool] = {
    "get_kpis": Tool(GetKpis, get_kpis),
    "get_steps": Tool(GetSteps, get_steps),
    "get_weight": Tool(GetWeight, get_weight),
    "get_body": Tool(GetBody, get_body),
    "get_sleep": Tool(GetSleep, get_sleep),
    "get_heart_day": Tool(GetHeartDay, get_heart_day),
    "get_heart_rhythm": Tool(GetHeartRhythm, get_heart_rhythm),
    "get_today": Tool(GetToday, get_today),
    "get_stress": Tool(GetStress, get_stress),
    "get_workouts": Tool(GetWorkouts, get_workouts),
    "get_training_load": Tool(GetTrainingLoad, get_training_load),
    "get_sleep_patterns": Tool(GetSleepPatterns, get_sleep_patterns),
    "get_checkup_changes": Tool(GetCheckupChanges, get_checkup_changes),
    "get_band": Tool(GetBand, get_band),
    "get_lab_results": Tool(GetLabResults, get_lab_results),
    "get_checkups": Tool(GetCheckups, get_checkups),
    "log_weight": Tool(LogWeight, log_weight),
    "record_checkup": Tool(RecordCheckup, record_checkup),
    "add_lab_result": Tool(AddLabResult, add_lab_result),
}
