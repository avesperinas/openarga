from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Any, Literal

from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from vitals import memo, steps
from vitals.steps import Period, start_of, today

Group = Literal["heart", "activity", "breath", "gait", "more", "history"]
Kind = Literal["mean", "sum", "last"]


@dataclass(frozen=True)
class Metric:
    id: str
    group: Group
    name: str
    unit: str
    digits: int
    kind: Kind
    about: str


METRICS: tuple[Metric, ...] = (
    Metric(
        "resting_heart_rate",
        "heart",
        "FC en reposo",
        "lpm",
        0,
        "mean",
        "Las pulsaciones por minuto en reposo que calcula el reloj cada día.",
    ),
    Metric(
        "sleep_heart_rate",
        "heart",
        "FC durmiendo",
        "lpm",
        0,
        "mean",
        "La media de pulsaciones durante el sueño no REM, que mide la pulsera.",
    ),
    Metric(
        "heart_rate_avg",
        "heart",
        "FC media",
        "lpm",
        0,
        "mean",
        "La media de todas las mediciones de vitals del día.",
    ),
    Metric("heart_rate_min", "heart", "FC mínima", "lpm", 0, "mean", "La más baja del día."),
    Metric("heart_rate_max", "heart", "FC máxima", "lpm", 0, "mean", "La más alta del día."),
    Metric(
        "walking_heart_rate",
        "heart",
        "FC caminando",
        "lpm",
        0,
        "mean",
        "La media de pulsaciones mientras se anda.",
    ),
    Metric(
        "hrv_ms",
        "heart",
        "Variabilidad (VFC)",
        "ms",
        0,
        "mean",
        "Cuánto varía el tiempo entre latidos. Hasta el cambio de aparato, la del Apple Watch "
        "durante el día (SDNN); desde entonces, la de la pulsera durante el sueño (RMSSD): son "
        "números distintos.",
    ),
    Metric(
        "hrv_deep_ms",
        "heart",
        "VFC en sueño profundo",
        "ms",
        0,
        "mean",
        "La variabilidad entre latidos (RMSSD) solo en el sueño profundo, que mide la pulsera.",
    ),
    Metric(
        "vo2max",
        "heart",
        "VO₂ máx.",
        "ml/kg·min",
        1,
        "mean",
        "La estimación de capacidad cardiorrespiratoria que hace el reloj o la pulsera. Cada marca "
        "la calcula a su manera.",
    ),
    Metric(
        "high_heart_rate_events",
        "heart",
        "Avisos de FC alta",
        "",
        0,
        "sum",
        "Las veces que el reloj avisó de vitals alto en reposo.",
    ),
    Metric(
        "low_heart_rate_events",
        "heart",
        "Avisos de FC baja",
        "",
        0,
        "sum",
        "Las veces que el reloj avisó de vitals bajo.",
    ),
    Metric(
        "active_kcal",
        "activity",
        "Calorías activas",
        "kcal",
        0,
        "sum",
        "La energía gastada moviéndose, sin contar la de estar en reposo.",
    ),
    Metric(
        "basal_kcal",
        "activity",
        "Calorías en reposo",
        "kcal",
        0,
        "sum",
        "La energía que gasta el cuerpo sin moverse.",
    ),
    Metric("distance_km", "activity", "Distancia a pie", "km", 1, "sum", "Lo andado y corrido."),
    Metric(
        "active_zone_min",
        "activity",
        "Minutos en zona",
        "min",
        0,
        "sum",
        "Los minutos con el vitals en zona de quema de grasa, que cuentan uno, o en cardio o pico, "
        "que cuentan dos. Lo mide la pulsera.",
    ),
    Metric(
        "light_active_min",
        "activity",
        "Minutos activos suaves",
        "min",
        0,
        "sum",
        "Los minutos de actividad ligera, como andar despacio, que cuenta la pulsera.",
    ),
    Metric(
        "moderate_active_min",
        "activity",
        "Minutos activos moderados",
        "min",
        0,
        "sum",
        "Los minutos de actividad moderada, como andar a paso ligero.",
    ),
    Metric(
        "vigorous_active_min",
        "activity",
        "Minutos activos intensos",
        "min",
        0,
        "sum",
        "Los minutos de actividad intensa, como correr.",
    ),
    Metric(
        "sedentary_min",
        "activity",
        "Tiempo sentado",
        "min",
        0,
        "sum",
        "Los minutos del día sin apenas moverse, despierto, que cuenta la pulsera.",
    ),
    Metric(
        "hr_zone_light_min",
        "activity",
        "Vitals en zona suave",
        "min",
        0,
        "sum",
        "Los minutos del día con el vitals en la zona más baja de las cuatro de la pulsera.",
    ),
    Metric(
        "hr_zone_moderate_min",
        "activity",
        "Vitals en zona moderada",
        "min",
        0,
        "sum",
        "Los minutos del día con el vitals en la segunda zona.",
    ),
    Metric(
        "hr_zone_vigorous_min",
        "activity",
        "Vitals en zona intensa",
        "min",
        0,
        "sum",
        "Los minutos del día con el vitals en la tercera zona.",
    ),
    Metric(
        "hr_zone_peak_min",
        "activity",
        "Vitals en zona pico",
        "min",
        0,
        "sum",
        "Los minutos del día con el vitals en la zona más alta.",
    ),
    Metric(
        "exercise_min",
        "activity",
        "Minutos de ejercicio",
        "min",
        0,
        "sum",
        "El anillo verde: minutos a paso ligero o más.",
    ),
    Metric(
        "stand_hours",
        "activity",
        "Horas de pie",
        "h",
        0,
        "sum",
        "El anillo azul: horas en las que se estuvo de pie al menos un minuto.",
    ),
    Metric("stand_min", "activity", "Minutos de pie", "min", 0, "sum", "El tiempo total de pie."),
    Metric(
        "flights",
        "activity",
        "Pisos subidos",
        "",
        0,
        "sum",
        "Tramos de unos tres metros de subida.",
    ),
    Metric(
        "cycling_km",
        "activity",
        "Distancia en bici",
        "km",
        1,
        "sum",
        "Lo pedaleado con el reloj puesto.",
    ),
    Metric(
        "physical_effort",
        "activity",
        "Esfuerzo",
        "MET",
        1,
        "mean",
        "La intensidad media del día, en MET.",
    ),
    Metric(
        "move_goal_kcal",
        "activity",
        "Objetivo de Moverse",
        "kcal",
        0,
        "last",
        "El objetivo del anillo rojo que había ese día.",
    ),
    Metric(
        "exercise_goal_min",
        "activity",
        "Objetivo de Ejercicio",
        "min",
        0,
        "last",
        "El objetivo del anillo verde que había ese día.",
    ),
    Metric(
        "stand_goal_hours",
        "activity",
        "Objetivo de De pie",
        "h",
        0,
        "last",
        "El objetivo del anillo azul que había ese día.",
    ),
    Metric(
        "respiratory_rate",
        "breath",
        "Respiración",
        "rpm",
        1,
        "mean",
        "Las respiraciones por minuto mientras se duerme.",
    ),
    Metric(
        "respiratory_rate_deep",
        "breath",
        "Respiración en sueño profundo",
        "rpm",
        1,
        "mean",
        "Las respiraciones por minuto durante el sueño profundo.",
    ),
    Metric(
        "respiratory_rate_light",
        "breath",
        "Respiración en sueño ligero",
        "rpm",
        1,
        "mean",
        "Las respiraciones por minuto durante el sueño ligero.",
    ),
    Metric(
        "respiratory_rate_rem",
        "breath",
        "Respiración en REM",
        "rpm",
        1,
        "mean",
        "Las respiraciones por minuto durante el sueño REM.",
    ),
    Metric(
        "spo2_pct",
        "breath",
        "Oxígeno en sangre (SpO₂)",
        "%",
        1,
        "mean",
        "La saturación media de oxígeno durante el sueño, que mide la pulsera.",
    ),
    Metric(
        "spo2_min_pct",
        "breath",
        "SpO₂ más baja",
        "%",
        1,
        "mean",
        "El extremo bajo de la saturación de oxígeno durante el sueño.",
    ),
    Metric(
        "spo2_max_pct",
        "breath",
        "SpO₂ más alta",
        "%",
        1,
        "mean",
        "El extremo alto de la saturación de oxígeno durante el sueño.",
    ),
    Metric(
        "skin_temp_delta_c",
        "breath",
        "Temperatura de la piel",
        "°C",
        1,
        "mean",
        "Cuánto se aparta la temperatura de la piel por la noche de tu base de las últimas "
        "semanas.",
    ),
    Metric(
        "walking_speed_kmh",
        "gait",
        "Velocidad al andar",
        "km/h",
        1,
        "mean",
        "La velocidad media al andar en llano, medida por el iPhone en el bolsillo.",
    ),
    Metric(
        "step_length_cm",
        "gait",
        "Longitud del paso",
        "cm",
        0,
        "mean",
        "La longitud media de cada paso.",
    ),
    Metric(
        "double_support_pct",
        "gait",
        "Doble apoyo",
        "%",
        1,
        "mean",
        "El tiempo de cada paso con los dos pies en el suelo.",
    ),
    Metric(
        "asymmetry_pct",
        "gait",
        "Asimetría al andar",
        "%",
        1,
        "mean",
        "Cuánto se diferencian los pasos de un pie y del otro.",
    ),
    Metric(
        "steadiness_pct",
        "gait",
        "Estabilidad al andar",
        "%",
        0,
        "last",
        "La puntuación de estabilidad que calcula el iPhone cada semana.",
    ),
    Metric(
        "six_minute_walk_m",
        "gait",
        "Test de 6 minutos",
        "m",
        0,
        "last",
        "Lo que el iPhone estima que se andaría en seis minutos.",
    ),
    Metric(
        "stair_up_ms",
        "gait",
        "Velocidad subiendo escaleras",
        "m/s",
        2,
        "mean",
        "La velocidad vertical al subir escaleras.",
    ),
    Metric(
        "stair_down_ms",
        "gait",
        "Velocidad bajando escaleras",
        "m/s",
        2,
        "mean",
        "La velocidad vertical al bajarlas.",
    ),
    Metric(
        "mindful_min",
        "more",
        "Minutos de atención plena",
        "min",
        0,
        "sum",
        "Las sesiones de Mindfulness del reloj.",
    ),
    Metric(
        "headphone_db",
        "more",
        "Ruido en auriculares",
        "dB",
        0,
        "mean",
        "El nivel medio del sonido que llegó por los auriculares.",
    ),
    Metric(
        "environment_db",
        "more",
        "Ruido ambiente",
        "dB",
        0,
        "mean",
        "El nivel medio del ruido alrededor, medido por el reloj.",
    ),
    Metric(
        "headphone_noise_events",
        "more",
        "Avisos de auriculares",
        "",
        0,
        "sum",
        "Las veces que se pasó del límite semanal de volumen en auriculares.",
    ),
    Metric(
        "environment_noise_events",
        "more",
        "Avisos de ruido",
        "",
        0,
        "sum",
        "Las veces que el reloj avisó de ruido ambiente alto.",
    ),
)

BY_ID = {one.id: one for one in METRICS}
GROUPS: tuple[tuple[Group, str], ...] = (
    ("heart", "Corazón"),
    ("activity", "Actividad"),
    ("breath", "Respiración y temperatura"),
    ("gait", "Marcha"),
    ("more", "Más"),
    ("history", "Histórico de Apple Salud"),
)
CHANGES = frozenset({"hrv_ms", "vo2max", "active_kcal", "basal_kcal"})

LATEST = text("""
    with ranked as (
        select (payload->>'date')::date as day, source, ingested_at, ts,
               coalesce(payload->'metrics', '{}') as metrics,
               row_number() over (
                   partition by (payload->>'date')::date, source
                   order by ingested_at desc, ts desc
               ) as n
        from vitals.events
        where type = 'health.daily' and ingested_at >= :arrived
          and (payload->>'date')::date between :since and :until
    ),
    marked as (
        select *, max(case when n = 1 then array(
            select key from unnest(cast(:keys as text[])) as key where not metrics ? key
        ) end) over (partition by day, source) as missing
        from ranked
    )
    select distinct on (day, source, metric.key)
        day, source, metric.key as metric, metric.value::float as value, ingested_at, ts
    from marked, jsonb_each_text(metrics) as metric
    where (n = 1 or metrics ?| missing) and metric.key = any(cast(:keys as text[]))
    order by day, source, metric.key, n
""")

SWITCH = text(f"""
    with {steps.STARTED}
    select max(since) from started having count(*) > 1
""")

PROFILE = text("""
    select payload, ingested_at from vitals.events
    where type = 'health.profile'
    order by ingested_at desc, ts desc
""")


class Point(BaseModel):
    day: date
    value: float
    total: float | None = None


class Figure(BaseModel):
    id: str
    group: Group
    name: str
    unit: str
    digits: int
    kind: Kind
    about: str
    latest: Point | None
    mean_30: float | None
    mean_365: float | None
    days: int
    changed_on: date | None = None
    historic: bool = False
    weeks: list[float | None] = []


WEEKS = 26


def weekly(points: list[Point], now: date, weeks: int = WEEKS) -> list[float | None]:
    first = now - timedelta(days=now.weekday()) - timedelta(weeks=weeks - 1)
    sums = [0.0] * weeks
    counts = [0] * weeks
    for one in points:
        if one.day < first or one.day > now:
            continue
        index = (one.day - first).days // 7
        sums[index] += one.value
        counts[index] += 1
    return [round(sums[i] / counts[i], 4) if counts[i] else None for i in range(weeks)]


class Section(BaseModel):
    id: Group
    name: str
    figures: list[Figure]


class Profile(BaseModel):
    blood_type: str | None = None
    sex: Literal["female", "male", "other"] | None = None
    birth_date: date | None = None
    age: int | None = None
    height_cm: float | None = None
    cardio_medications: str | None = None
    walking_stride_cm: float | None = None
    running_stride_cm: float | None = None
    irn_enrolled: bool | None = None


class Overview(BaseModel):
    profile: Profile | None
    sections: list[Section]


class Series(BaseModel):
    figure: Figure
    points: list[Point]


def age(born: date, now: date) -> int:
    return now.year - born.year - ((now.month, now.day) < (born.month, born.day))


async def profile(connection: AsyncConnection) -> Profile | None:
    merged: dict = {}
    for row in (await connection.execute(PROFILE)).all():
        for key, value in row.payload.items():
            merged.setdefault(key, value)
    if not merged:
        return None
    found = Profile.model_validate(merged)
    if found.birth_date:
        found.age = age(found.birth_date, today())
    return found


async def switched_on(connection: AsyncConnection) -> date | None:
    return await connection.scalar(SWITCH)


async def read(
    connection: AsyncConnection,
    only: str | None = None,
    since: date = date.min,
    until: date = date.max,
    started: steps.Started | None = None,
) -> dict[str, list[Point]]:
    if only is not None and only not in BY_ID:
        return {}
    found = await kept(connection, since)
    if started is None and found.two_sources(since, until):
        started = await steps.started(connection)
    return found.points(since, until, started or {}, only)


async def raw(connection: AsyncConnection, since: date, until: date) -> list[Any]:
    bounds = {"arrived": steps.arrived(since), "since": since, "until": until}
    return (await connection.execute(LATEST, {**bounds, "keys": list(BY_ID)})).all()


ARRIVED = text("""
    select (payload->>'date')::date as day, max(ingested_at) as last
    from vitals.events
    where type = 'health.daily' and ingested_at > :after
    group by 1
""")


@dataclass
class Kept(memo.Read):
    first: date
    days: dict[date, list[Any]] = field(default_factory=dict)
    last: datetime | None = None
    chosen: dict[date, dict[str, Point]] = field(default_factory=dict)
    chosen_with: steps.Started | None = None
    mixed: set[date] = field(default_factory=set)

    def store(self, day: date, rows: list[Any]) -> None:
        self.days[day] = rows
        self.chosen.pop(day, None)
        if len({row.source for row in rows}) > 1:
            self.mixed.add(day)
        else:
            self.mixed.discard(day)

    def two_sources(self, since: date, until: date) -> bool:
        return any(since <= day <= until for day in self.mixed)

    def points(
        self, since: date, until: date, started: steps.Started, only: str | None = None
    ) -> dict[str, list[Point]]:
        if self.chosen_with != started:
            for day in self.mixed:
                self.chosen.pop(day, None)
            self.chosen_with = dict(started)
        out: dict[str, list[Point]] = {}
        for day in sorted(one for one in self.days if since <= one <= until):
            picked = self.chosen.get(day)
            if picked is None:
                picked = self.chosen[day] = pick(self.days[day], started)
            for metric, point in picked.items():
                if only is None or metric == only:
                    out.setdefault(metric, []).append(point)
        return out


def pick(rows: list[Any], started: steps.Started) -> dict[str, Point]:
    chosen = steps.choose(rows, key=lambda row: row.metric, known=started)
    return {row.metric: Point(day=row.day, value=row.value) for row in chosen}


async def kept(connection: AsyncConnection, since: date) -> Kept:
    found: Kept | None = memo.get("daily")
    if found is None or since < found.first or found.expired():
        found = Kept(first=since, last=await memo.last_arrival(connection, ("health.daily",)))
        by_day: dict[date, list[Any]] = {}
        for row in await raw(connection, since, date.max):
            by_day.setdefault(row.day, []).append(row)
        for day, rows in by_day.items():
            found.store(day, rows)
    else:
        touched = (await connection.execute(ARRIVED, {"after": memo.after(found.last)})).all()
        days = sorted(row.day for row in touched if row.day >= found.first)
        if days:
            fresh: dict[date, list[Any]] = {day: [] for day in days}
            for row in await raw(connection, days[0], days[-1]):
                if row.day in fresh:
                    fresh[row.day].append(row)
            for day, rows in fresh.items():
                found.store(day, rows)
        found.last = memo.latest(found.last, *(row.last for row in touched))
    memo.put("daily", None, found)
    return found


def mean(points: list[Point], since: date) -> float | None:
    values = [one.value for one in points if one.day >= since]
    return sum(values) / len(values) if values else None


def figure(metric: Metric, points: list[Point], now: date, switch: date | None = None) -> Figure:
    latest = points[-1] if points else None
    changes = switch is not None and metric.id in CHANGES
    side = points
    if changes and latest is not None:
        after = latest.day >= switch
        side = [one for one in points if (one.day >= switch) == after]
    return Figure(
        id=metric.id,
        group=metric.group,
        name=metric.name,
        unit=metric.unit,
        digits=metric.digits,
        kind=metric.kind,
        about=metric.about,
        latest=latest,
        mean_30=mean(side, now - timedelta(days=29)),
        mean_365=mean(side, now - timedelta(days=364)),
        days=len(points),
        changed_on=switch if changes else None,
        historic=(historic := switch is not None and latest is not None and latest.day < switch),
        weeks=[] if historic else weekly(points, now),
    )


async def overview(connection: AsyncConnection) -> Overview:
    started = await steps.started(connection)
    series = await read(connection, started=started)
    switch = steps.switch(started)
    now = today()
    figures = [
        figure(metric, series[metric.id], now, switch)
        for metric in METRICS
        if series.get(metric.id)
    ]
    return Overview(
        profile=await profile(connection),
        sections=[
            Section(
                id=group,
                name=name,
                figures=[
                    one
                    for one in figures
                    if (one.historic and group == "history")
                    or (not one.historic and one.group == group)
                ],
            )
            for group, name in GROUPS
        ],
    )


def grouped(
    points: list[Point], kind: Kind, period: Period, switch: date | None = None
) -> list[Point]:
    if period == "day":
        return points
    buckets: dict[date, list[float]] = {}
    for one in points:
        start = start_of(one.day, period)
        if switch is not None and one.day >= switch > start:
            start = switch
        buckets.setdefault(start, []).append(one.value)
    out = []
    for start, values in sorted(buckets.items()):
        if kind == "last":
            out.append(Point(day=start, value=values[-1]))
            continue
        total = round(sum(values), 2) if kind == "sum" else None
        out.append(Point(day=start, value=round(sum(values) / len(values), 2), total=total))
    return out


async def series(
    connection: AsyncConnection,
    metric_id: str,
    since: date | None = None,
    until: date | None = None,
    period: Period = "day",
) -> Series:
    metric = BY_ID[metric_id]
    started = await steps.started(connection)
    points = (await read(connection, metric_id, started=started)).get(metric_id, [])
    switch = steps.switch(started)
    kept = [
        one
        for one in points
        if (since is None or one.day >= since) and (until is None or one.day <= until)
    ]
    found = figure(metric, points, today(), switch)
    return Series(figure=found, points=grouped(kept, metric.kind, period, found.changed_on))
