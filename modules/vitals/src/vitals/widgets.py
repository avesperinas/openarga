from __future__ import annotations

from datetime import date, timedelta

from sqlalchemy.ext.asyncio import AsyncConnection

from arga_widgets import envelope
from vitals import body, labs, rhythm, sleep, steps, stress, weight, workouts

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


def _es(value: float, decimals: int = 1) -> str:
    return f"{value:,.{decimals}f}".replace(",", " ").replace(".", ",").replace(" ", ".")


MONTHS = [
    "enero",
    "febrero",
    "marzo",
    "abril",
    "mayo",
    "junio",
    "julio",
    "agosto",
    "septiembre",
    "octubre",
    "noviembre",
    "diciembre",
]


def which_day(day: date, today: date) -> str:
    ago = (today - day).days
    if ago == 1:
        return "de ayer"
    if ago < 7:
        return f"del {steps.WEEKDAYS[day.weekday()]} {day.day}"
    return f"del {day.day} de {MONTHS[day.month - 1]}"


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
        return envelope(KINDS["steps_today"], "empty", {"detail": "conecta Google Health en Hub"})
    goal = (await weight.goal(connection)).steps_per_day
    if not goal:
        return envelope(KINDS["steps_today"], "empty", {"detail": "pon un objetivo de pasos"})
    day, label = found
    body = {"value": day.steps, "target": goal, "show": "value"}
    if label:
        body["label"] = label
    return envelope(KINDS["steps_today"], "ready", body)


async def weight_trend(connection: AsyncConnection) -> dict:
    found = await weight.summary(connection, entries=0)
    if found.latest is None:
        return envelope(KINDS["weight"], "empty", {"detail": "apunta tu primera pesada"})
    last = found.latest
    week = [one for one in found.days if one.day > last.day - timedelta(days=weight.WINDOW_DAYS)]
    detail = (
        f"pesada del {last.day:%d/%m}"
        if len(week) == 1
        else f"media de {len(week)} pesadas hasta el {last.day:%d/%m}"
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
            "since": f"desde el {before.day:%d/%m/%Y}" if before else "sin pesadas anteriores",
            "good_when": found.goal.weight_direction
            or GOOD_WHEN.get(found.against_goal or "", "neutral"),
            "detail": detail,
            **({"series": series} if len(series) > 1 else {}),
        },
    )


async def ldl(connection: AsyncConnection) -> dict:
    found = await labs.latest(connection, "ldl")
    if found is None:
        return envelope(KINDS["ldl"], "empty", {"detail": "sin analíticas todavía"})
    if found.previous is None:
        return envelope(
            KINDS["ldl"],
            "empty",
            {"detail": f"LDL {_es(found.value, 0)} mg/dL; falta otra revisión para comparar"},
        )
    top = f"de {_es(found.ref_high, 0)}" if found.ref_high is not None else ""
    return envelope(
        KINDS["ldl"],
        "ready",
        {
            "value": found.value,
            "previous": found.previous,
            "unit": found.unit or "",
            "since": f"la revisión del {found.previous_day.strftime('%d/%m/%Y')}",
            "good_when": "down",
            "detail": f"{'fuera' if found.out else 'dentro'} de rango {top}".strip(),
        },
    )


def hours(minutes: int) -> str:
    return f"{minutes // 60} h {minutes % 60:02d} min"


async def last_sleep(connection: AsyncConnection) -> dict:
    found = await sleep.summary(connection)
    if found.last is None:
        return envelope(KINDS["sleep"], "empty", {"detail": "conecta Google Health en Hub"})
    last, mean = found.last, found.mean_30
    stages = last.stages or {}
    detail = " · ".join(
        f"{name} {stages[key]} min"
        for key, name in (("deep", "profundo"), ("rem", "REM"))
        if key in stages
    )
    if mean.asleep is None or mean.nights < 2:
        return envelope(
            KINDS["sleep"], "empty", {"detail": f"{hours(last.minutes_asleep)} la última noche"}
        )
    return envelope(
        KINDS["sleep"],
        "ready",
        {
            "value": round(last.minutes_asleep / 60, 1),
            "previous": round(mean.asleep / 60, 1),
            "unit": "h",
            "since": f"tu media de {mean.nights} noches",
            "good_when": "up",
            "detail": detail
            or ("anoche" if last.day == steps.today() else which_day(last.day, steps.today())),
        },
    )


async def steps_year(connection: AsyncConnection) -> dict:
    last = steps.today()
    start = last - timedelta(days=last.weekday() + 7 * 25)
    days, _ = await steps.read(connection, start, last)
    if not days and not await steps.any_steps(connection):
        return envelope(KINDS["steps_year"], "empty", {"detail": "conecta Google Health en Hub"})
    by_day = {one.day: one.steps for one in days}
    values = [by_day.get(start + timedelta(days=n), 0) for n in range((last - start).days + 1)]
    return envelope(
        KINDS["steps_year"],
        "ready",
        {"values": values, "columns": 7, "detail": "los últimos seis meses"},
    )


async def steps_week(connection: AsyncConnection) -> dict:
    last = steps.today()
    days, _ = await steps.read(connection, last - timedelta(days=6), last)
    by_day = {one.day: one.steps for one in days}
    week = [last - timedelta(days=offset) for offset in range(6, -1, -1)]
    values = [by_day.get(day, 0) for day in week]
    if not any(values):
        return envelope(KINDS["steps_week"], "empty", {"detail": "sin pasos esta semana"})
    known = [value for value in values if value]
    goal = (await weight.goal(connection)).steps_per_day
    met = sum(1 for value in values if goal and value >= goal)
    detail = f"media diaria · objetivo cumplido {met} de 7" if goal else "media diaria"
    return envelope(
        KINDS["steps_week"],
        "ready",
        {
            "series": [float(value) for value in values],
            "labels": ["LMXJVSD"[day.weekday()] for day in week],
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


QUALITY = {"excellent": "excelente", "good": "buena", "fair": "regular", "poor": "mala"}


def _night_label(minutes: int) -> str:
    return f"{minutes // 60} h {minutes % 60:02d}"


async def sleep_score(connection: AsyncConnection) -> dict:
    nights = await sleep.read(connection, steps.today() - timedelta(days=6))
    last = next((one for one in reversed(nights) if one.score), None)
    if last is None:
        nights = await sleep.read(connection)
        last = next((one for one in reversed(nights) if one.score), None)
    if last is None or last.score is None:
        return envelope(KINDS["sleep_score"], "empty", {"detail": "todavía sin noches con fases"})
    label = f"{QUALITY[last.score.quality]} · {_night_label(last.minutes_asleep)}"
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
        return envelope(KINDS["sleep_week"], "empty", {"detail": "sin noches esta semana"})
    return envelope(
        KINDS["sleep_week"],
        "ready",
        {
            "series": values,
            "labels": ["LMXJVSD"[day.weekday()] for day in week],
            "highlight": 6,
            "value": round(sum(known) / len(known), 1),
            "unit": "h",
            "detail": f"media de {len(known)} noches",
        },
    )


async def readiness(connection: AsyncConnection) -> dict:
    found = await stress.morning(connection, steps.today())
    if found.score is None:
        left = found.days_left
        detail = (
            f"en {left} {'día' if left == 1 else 'días'}, con tu VFC de la pulsera"
            if left
            else "falta la VFC o la FC en reposo de hoy"
        )
        return envelope(KINDS["readiness"], "empty", {"detail": detail})
    word = (
        "mejor que de costumbre"
        if found.score >= 60
        else "peor que de costumbre"
        if found.score <= 40
        else "como de costumbre"
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
        return envelope(kind, "empty", {"detail": "sin dato de la última semana"})
    series = [one.value for one in points if one.day > last - timedelta(days=30)]
    out: dict = {
        "value": round(sum(recent) / len(recent), digits or None),
        "unit": unit,
        "series": series,
        "good_when": good,
        "detail": "media de 7 días",
    }
    if before:
        out["previous"] = round(sum(before) / len(before), digits or None)
        out["since"] = "los 30 días de antes"
    return envelope(kind, "ready", out)


async def resting_heart(connection: AsyncConnection) -> dict:
    return await _figure_delta(
        connection, KINDS["resting_heart"], "resting_heart_rate", "lpm", "down"
    )


async def hrv(connection: AsyncConnection) -> dict:
    return await _figure_delta(connection, KINDS["hrv"], "hrv_ms", "ms", "up")


async def vo2max(connection: AsyncConnection) -> dict:
    return await _figure_delta(connection, KINDS["vo2max"], "vo2max", "", "up", digits=1)


async def training_load(connection: AsyncConnection) -> dict:
    found = await workouts.load(connection, weeks=5)
    if not found.mean_4:
        return envelope(
            KINDS["training_load"], "empty", {"detail": "hacen falta cuatro semanas de entrenos"}
        )
    return envelope(
        KINDS["training_load"],
        "ready",
        {
            "value": round(found.this_week),
            "target": round(found.mean_4),
            "label": "contra tu media de 4 semanas",
        },
    )


async def training_week(connection: AsyncConnection) -> dict:
    found = await workouts.load(connection, weeks=1)
    week = found.weeks[-1] if found.weeks else None
    if week is None or week.workouts == 0:
        return envelope(KINDS["training_week"], "empty", {"detail": "sin entrenos esta semana"})
    hard = round(sum(week.zones[2:]))
    return envelope(
        KINDS["training_week"],
        "ready",
        {
            "stats": [
                {"label": "Entrenos", "value": week.workouts},
                {"label": "Tiempo", "value": _night_label(week.minutes)},
                {"label": "Zona 3+", "value": hard, "unit": "min"},
                {"label": "Carga", "value": round(week.load)},
            ],
            "detail": "de lunes a hoy",
        },
    )


async def last_workout(connection: AsyncConnection) -> dict:
    last = steps.today()
    done = await workouts.between(connection, last - timedelta(days=14), last)
    if not done:
        return envelope(KINDS["last_workout"], "empty", {"detail": "sin entrenos en dos semanas"})
    one = done[0]
    stats = [{"label": "Tiempo", "value": f"{one.minutes} min"}]
    if one.heart.avg is not None:
        stats.append({"label": "Media", "value": round(one.heart.avg), "unit": "lpm"})
    if one.heart.max is not None:
        stats.append({"label": "Máximo", "value": round(one.heart.max), "unit": "lpm"})
    if one.kcal is not None:
        stats.append({"label": "Calorías", "value": round(one.kcal), "unit": "kcal"})
    when = which_day(one.start.astimezone(steps.MADRID).date(), last)
    return envelope(
        KINDS["last_workout"], "ready", {"stats": stats, "detail": f"{one.name} · {when}"}
    )


async def band(connection: AsyncConnection) -> dict:
    found = await rhythm.devices(connection)
    if not found or found[0].battery_pct is None:
        return envelope(KINDS["band"], "empty", {"detail": "la pulsera no ha dicho su batería"})
    device = found[0]
    detail = device.name
    if device.last_sync:
        detail = (
            f"{device.name} · sincronizó a las {device.last_sync.astimezone(steps.MADRID):%H:%M}"
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
