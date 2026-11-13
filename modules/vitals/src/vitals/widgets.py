from __future__ import annotations

from datetime import date, timedelta

from sqlalchemy.ext.asyncio import AsyncConnection

from arga_widgets import envelope
from vitals import body, labs, rhythm, sleep, steps, stress, weight, workouts
from vitals.text import day_month, full_date, number, t, weekday

KINDS = {
    "steps_today": "ring",
    "weight": "kpi-delta",
    "ldl": "kpi-delta",
    "steps_year": "heatmap",
    "steps_week": "bars",
    "sleep": "kpi-delta",
    "sleep_score": "ring",
    "sleep_week": "bars",
    "readiness": "ring",
    "resting_heart": "kpi-delta",
    "hrv": "kpi-delta",
    "vo2max": "kpi-delta",
    "training_load": "progress",
    "training_week": "stats",
    "last_workout": "stats",
    "band": "ring",
}
WEIGHT_SERIES_DAYS = 90

GOOD_WHEN = {"above": "down", "below": "up", "inside": "neutral"}


def which_day(day: date, today: date) -> str:
    ago = (today - day).days
    if ago == 1:
        return t("day.yesterday")
    if ago < 7:
        return t("day.weekday", weekday=weekday(day), day=day.day)
    return t("day.date", date=day_month(day))


def last_steps(days: list[steps.StepsDay], today: date) -> tuple[steps.StepsDay, str | None] | None:
    known = [one for one in days if one.day <= today]
    if not known:
        return None
    last = max(known, key=lambda one: one.day)
    return last, None if last.day == today else which_day(last.day, today)


async def steps_today(connection: AsyncConnection) -> dict:
    now = steps.today()
    days, _ = await steps.read(connection, now - timedelta(days=6), now)
    found = last_steps(days, now)
    if found is None:
        days, _ = await steps.read(connection, until=now)
        found = last_steps(days, now)
    if found is None:
        return envelope(KINDS["steps_today"], "empty", {"detail": t("widget.connect")})
    goal = (await weight.goal(connection)).steps_per_day
    if not goal:
        return envelope(KINDS["steps_today"], "empty", {"detail": t("widget.steps_goal")})
    day, label = found
    body = {"value": day.steps, "target": goal, "show": "value"}
    if label:
        body["label"] = label
    return envelope(KINDS["steps_today"], "ready", body)


async def weight_trend(connection: AsyncConnection) -> dict:
    found = await weight.summary(connection, entries=0)
    if found.latest is None:
        return envelope(KINDS["weight"], "empty", {"detail": t("widget.first_weight")})
    last = found.latest
    week = [one for one in found.days if one.day > last.day - timedelta(days=weight.WINDOW_DAYS)]
    detail = (
        t("widget.weighed_on", date=day_month(last.day))
        if len(week) == 1
        else t("widget.weights_until", count=len(week), date=day_month(last.day))
    )
    before = weight.reference(found.days, 30) or (
        found.days[0] if found.days[0].day != last.day else None
    )
    since = last.day - timedelta(days=WEIGHT_SERIES_DAYS)
    series = [one.avg7 for one in found.days if one.day > since]
    return envelope(
        KINDS["weight"],
        "ready",
        {
            "value": last.avg7,
            "previous": before.avg7 if before else last.avg7,
            "unit": "kg",
            "since": t("widget.since", date=full_date(before.day))
            if before
            else t("widget.no_earlier"),
            "good_when": found.goal.weight_direction
            or GOOD_WHEN.get(found.against_goal or "", "neutral"),
            "detail": detail,
            **({"series": series} if len(series) > 1 else {}),
        },
    )


async def ldl(connection: AsyncConnection) -> dict:
    found = await labs.latest(connection, "ldl")
    if found is None:
        return envelope(KINDS["ldl"], "empty", {"detail": t("widget.no_labs")})
    if found.previous is None:
        return envelope(
            KINDS["ldl"],
            "empty",
            {"detail": t("widget.ldl_alone", value=number(found.value, 0))},
        )
    top = number(found.ref_high, 0) if found.ref_high is not None else None
    return envelope(
        KINDS["ldl"],
        "ready",
        {
            "value": found.value,
            "previous": found.previous,
            "unit": found.unit or "",
            "since": t("widget.checkup_of", date=full_date(found.previous_day)),
            "good_when": "down",
            "detail": t(
                ("widget.out_of" if found.out else "widget.in_range_of")
                if top
                else ("widget.out" if found.out else "widget.in_range"),
                top=top,
            ),
        },
    )


def hours(minutes: int) -> str:
    return f"{minutes // 60} h {minutes % 60:02d} min"


async def last_sleep(connection: AsyncConnection) -> dict:
    found = await sleep.summary(connection)
    if found.last is None:
        return envelope(KINDS["sleep"], "empty", {"detail": t("widget.connect")})
    last, mean = found.last, found.mean_30
    stages = last.stages or {}
    detail = " · ".join(
        f"{name} {stages[key]} min"
        for key, name in (("deep", t("sleep.deep")), ("rem", "REM"))
        if key in stages
    )
    if mean.asleep is None or mean.nights < 2:
        return envelope(
            KINDS["sleep"],
            "empty",
            {"detail": t("widget.last_night", hours=hours(last.minutes_asleep))},
        )
    return envelope(
        KINDS["sleep"],
        "ready",
        {
            "value": round(last.minutes_asleep / 60, 1),
            "previous": round(mean.asleep / 60, 1),
            "unit": "h",
            "since": t("widget.your_mean", count=mean.nights),
            "good_when": "up",
            "detail": detail
            or (
                t("day.last_night")
                if last.day == steps.today()
                else which_day(last.day, steps.today())
            ),
        },
    )


async def steps_year(connection: AsyncConnection) -> dict:
    last = steps.today()
    start = last - timedelta(days=last.weekday() + 7 * 25)
    days, _ = await steps.read(connection, start, last)
    if not days and not await steps.any_steps(connection):
        return envelope(KINDS["steps_year"], "empty", {"detail": t("widget.connect")})
    by_day = {one.day: one.steps for one in days}
    values = [by_day.get(start + timedelta(days=n), 0) for n in range((last - start).days + 1)]
    return envelope(
        KINDS["steps_year"],
        "ready",
        {"values": values, "columns": 7, "detail": t("widget.six_months")},
    )


async def steps_week(connection: AsyncConnection) -> dict:
    last = steps.today()
    days, _ = await steps.read(connection, last - timedelta(days=6), last)
    by_day = {one.day: one.steps for one in days}
    week = [last - timedelta(days=offset) for offset in range(6, -1, -1)]
    values = [by_day.get(day, 0) for day in week]
    if not any(values):
        return envelope(KINDS["steps_week"], "empty", {"detail": t("widget.no_steps_week")})
    known = [value for value in values if value]
    goal = (await weight.goal(connection)).steps_per_day
    met = sum(1 for value in values if goal and value >= goal)
    detail = t("widget.daily_goal", met=met) if goal else t("widget.daily")
    return envelope(
        KINDS["steps_week"],
        "ready",
        {
            "series": [float(value) for value in values],
            "labels": [t("weekday.letters")[day.weekday()] for day in week],
            "highlight": 6,
            "value": round(sum(known) / len(known)),
            "detail": detail,
        },
    )


RENDERERS = {
    "steps_week": steps_week,
    "steps_today": steps_today,
    "weight": weight_trend,
    "ldl": ldl,
    "steps_year": steps_year,
    "sleep": last_sleep,
}


def _night_label(minutes: int) -> str:
    return f"{minutes // 60} h {minutes % 60:02d}"


async def sleep_score(connection: AsyncConnection) -> dict:
    nights = await sleep.read(connection, steps.today() - timedelta(days=6))
    last = next((one for one in reversed(nights) if one.score), None)
    if last is None:
        nights = await sleep.read(connection)
        last = next((one for one in reversed(nights) if one.score), None)
    if last is None or last.score is None:
        return envelope(KINDS["sleep_score"], "empty", {"detail": t("widget.no_staged_nights")})
    label = f"{t(f'quality.{last.score.quality}')} · {_night_label(last.minutes_asleep)}"
    if last.day != steps.today():
        label = f"{label} · {which_day(last.day, steps.today())}"
    return envelope(
        KINDS["sleep_score"],
        "ready",
        {"value": last.score.value, "target": 100, "show": "value", "label": label},
    )


async def sleep_week(connection: AsyncConnection) -> dict:
    last = steps.today()
    by_day = {one.day: one for one in await sleep.read(connection, last - timedelta(days=6), last)}
    week = [last - timedelta(days=offset) for offset in range(6, -1, -1)]
    values = [round(by_day[day].minutes_asleep / 60, 1) if day in by_day else 0.0 for day in week]
    known = [value for value in values if value]
    if not known:
        return envelope(KINDS["sleep_week"], "empty", {"detail": t("widget.no_nights_week")})
    return envelope(
        KINDS["sleep_week"],
        "ready",
        {
            "series": values,
            "labels": [t("weekday.letters")[day.weekday()] for day in week],
            "highlight": 6,
            "value": round(sum(known) / len(known), 1),
            "unit": "h",
            "detail": t("widget.mean_nights", count=len(known)),
        },
    )


async def readiness(connection: AsyncConnection) -> dict:
    found = await stress.morning(connection, steps.today())
    if found.score is None:
        left = found.days_left
        detail = (
            t("widget.ready_in.one" if left == 1 else "widget.ready_in.other", count=left)
            if left
            else t("widget.missing_hrv")
        )
        return envelope(KINDS["readiness"], "empty", {"detail": detail})
    word = t(
        "readiness.better"
        if found.score >= 60
        else "readiness.worse"
        if found.score <= 40
        else "readiness.usual"
    )
    return envelope(
        KINDS["readiness"],
        "ready",
        {"value": found.score, "target": 100, "show": "value", "label": word},
    )


async def _figure_delta(
    connection: AsyncConnection, kind: str, metric: str, unit: str, good: str, digits: int = 0
):
    last = steps.today()
    points = (await body.read(connection, metric, since=last - timedelta(days=36))).get(metric, [])
    recent = [one.value for one in points if one.day > last - timedelta(days=7)]
    before = [
        one.value
        for one in points
        if last - timedelta(days=37) < one.day <= last - timedelta(days=7)
    ]
    if not recent:
        return envelope(kind, "empty", {"detail": t("widget.no_week_data")})
    series = [one.value for one in points if one.day > last - timedelta(days=30)]
    out: dict = {
        "value": round(sum(recent) / len(recent), digits or None),
        "unit": unit,
        "series": series,
        "good_when": good,
        "detail": t("widget.mean_7"),
    }
    if before:
        out["previous"] = round(sum(before) / len(before), digits or None)
        out["since"] = t("widget.previous_30")
    return envelope(kind, "ready", out)


async def resting_heart(connection: AsyncConnection) -> dict:
    return await _figure_delta(
        connection, KINDS["resting_heart"], "resting_heart_rate", "bpm", "down"
    )


async def hrv(connection: AsyncConnection) -> dict:
    return await _figure_delta(connection, KINDS["hrv"], "hrv_ms", "ms", "up")


async def vo2max(connection: AsyncConnection) -> dict:
    return await _figure_delta(connection, KINDS["vo2max"], "vo2max", "", "up", digits=1)


async def training_load(connection: AsyncConnection) -> dict:
    found = await workouts.load(connection, weeks=5)
    if not found.mean_4:
        return envelope(KINDS["training_load"], "empty", {"detail": t("widget.four_weeks")})
    return envelope(
        KINDS["training_load"],
        "ready",
        {
            "value": round(found.this_week),
            "target": round(found.mean_4),
            "label": t("widget.against_4"),
        },
    )


async def training_week(connection: AsyncConnection) -> dict:
    found = await workouts.load(connection, weeks=1)
    week = found.weeks[-1] if found.weeks else None
    if week is None or week.workouts == 0:
        return envelope(KINDS["training_week"], "empty", {"detail": t("widget.no_workouts_week")})
    hard = round(sum(week.zones[2:]))
    return envelope(
        KINDS["training_week"],
        "ready",
        {
            "stats": [
                {"label": t("stat.workouts"), "value": week.workouts},
                {"label": t("stat.time"), "value": _night_label(week.minutes)},
                {"label": t("stat.zone3"), "value": hard, "unit": "min"},
                {"label": t("stat.load"), "value": round(week.load)},
            ],
            "detail": t("widget.monday_to_today"),
        },
    )


async def last_workout(connection: AsyncConnection) -> dict:
    last = steps.today()
    done = await workouts.between(connection, last - timedelta(days=14), last)
    if not done:
        return envelope(
            KINDS["last_workout"], "empty", {"detail": t("widget.no_workouts_two_weeks")}
        )
    one = done[0]
    stats = [{"label": t("stat.time"), "value": f"{one.minutes} min"}]
    if one.heart.avg is not None:
        stats.append({"label": t("stat.average"), "value": round(one.heart.avg), "unit": "bpm"})
    if one.heart.max is not None:
        stats.append({"label": t("stat.max"), "value": round(one.heart.max), "unit": "bpm"})
    if one.kcal is not None:
        stats.append({"label": t("stat.calories"), "value": round(one.kcal), "unit": "kcal"})
    when = which_day(one.start.astimezone(steps.zone()).date(), last)
    return envelope(
        KINDS["last_workout"], "ready", {"stats": stats, "detail": f"{one.name} · {when}"}
    )


async def band(connection: AsyncConnection) -> dict:
    found = await rhythm.devices(connection)
    if not found or found[0].battery_pct is None:
        return envelope(KINDS["band"], "empty", {"detail": t("widget.no_battery")})
    device = found[0]
    detail = device.name
    if device.last_sync:
        detail = t(
            "widget.synced",
            name=device.name,
            time=f"{device.last_sync.astimezone(steps.zone()):%H:%M}",
        )
    return envelope(
        KINDS["band"],
        "ready",
        {"value": device.battery_pct, "target": 100, "show": "percent", "label": detail},
    )


RENDERERS.update(
    {
        "sleep_score": sleep_score,
        "sleep_week": sleep_week,
        "readiness": readiness,
        "resting_heart": resting_heart,
        "hrv": hrv,
        "vo2max": vo2max,
        "training_load": training_load,
        "training_week": training_week,
        "last_workout": last_workout,
        "band": band,
    }
)
