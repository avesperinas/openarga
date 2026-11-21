from __future__ import annotations

import math
from datetime import date, time, timedelta
from pathlib import Path
from uuid import UUID, uuid5

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from arga_module.demo import Persona, localizer

say = localizer(Path(__file__).parent / "seed" / "i18n")

NAMESPACE = UUID("0b7c0de5-0000-4000-8000-0000000b17a1")
DAYS = 18 * 30

WEIGHT = text("""
    insert into vitals.vitals_weight (id, day, at, kg, source)
    values (:id, :day, :at, :kg, 'manual')
    on conflict do nothing
""")

GOAL = text("""
    insert into vitals.vitals_goal (steps_per_day, weight_min_kg, weight_max_kg)
    values (:steps, :low, :high)
    on conflict (user_id) do nothing
""")

CHECKUP = text("""
    insert into vitals.vitals_checkup (id, day, center, notes)
    values (:id, :day, :center, :notes)
    on conflict do nothing
""")

RESULT = text("""
    insert into vitals.vitals_lab_result
        (id, checkup_id, analyte_id, value, unit, ref_low, ref_high)
    values (:id, :checkup, :analyte, :value, :unit, :ref_low, :ref_high)
    on conflict do nothing
""")

ANALYTES = (
    ("glucose", "mg/dL", 70, 100),
    ("cholesterol", "mg/dL", None, 200),
    ("ldl", "mg/dL", None, 130),
    ("hdl", "mg/dL", 40, None),
    ("triglycerides", "mg/dL", None, 150),
    ("hemoglobin", "g/dL", 13, 17),
    ("creatinine", "mg/dL", 0.7, 1.2),
    ("alt", "U/L", None, 41),
    ("rbc", "10^6/µL", 4.5, 5.9),
    ("hematocrit", "%", 40, 52),
    ("wbc", "10^3/µL", 4, 11),
    ("platelets", "10^3/µL", 150, 400),
    ("urea", "mg/dL", 15, 45),
    ("uric_acid", "mg/dL", 3.5, 7.2),
    ("ast", "U/L", None, 40),
    ("ggt", "U/L", None, 60),
    ("vldl", "mg/dL", None, 30),
)


def _id(persona: Persona, key: str) -> UUID:
    return uuid5(NAMESPACE, f"{persona.seed_key}:{key}")


def _kg(persona: Persona, back: int) -> float:
    alex = persona.key == "alex"
    start, end = (84.0, 78.5) if alex else (64.0, 62.5)
    trend = end + (start - end) * back / DAYS
    wave = 0.6 * math.sin(back / 9) + 0.3 * math.sin(back / 2.3)
    return round(trend + wave, 1)


def _results(persona: Persona, visit: int) -> list[tuple[str, float]]:
    alex = persona.key == "alex"
    better = visit * (6 if alex else 2)
    return [
        ("glucose", (94 if alex else 86) - visit),
        ("cholesterol", (226 if alex else 188) - better),
        ("ldl", (148 if alex else 112) - better),
        ("hdl", (46 if alex else 62) + visit),
        ("triglycerides", (160 if alex else 90) - better),
        ("hemoglobin", 15.1 if alex else 13.4),
        ("creatinine", 1.0 if alex else 0.8),
        ("alt", (38 if alex else 21) - visit * 2),
        ("rbc", 5.1 if alex else 4.6),
        ("hematocrit", (45 if alex else 40.5) + visit * 0.2),
        ("wbc", (7.2 if alex else 6.1) + (0.9 if visit == 1 else 0)),
        ("platelets", (232 if alex else 268) + visit * 4),
        ("urea", (34 if alex else 27) + visit),
        ("uric_acid", (6.4 if alex else 4.2) - visit * 0.1),
        ("ast", (31 if alex else 19) - visit),
        ("ggt", (44 if alex else 17) - visit * 2),
        ("vldl", round(((160 if alex else 90) - better) / 5, 1)),
    ]


async def seed(connection: AsyncConnection, persona: Persona, today: date) -> None:
    alex = persona.key == "alex"
    await connection.execute(
        GOAL,
        {
            "steps": 9000 if alex else 8000,
            "low": 76 if alex else 60,
            "high": 80 if alex else 64,
        },
    )
    for back in range(DAYS, -1, -1):
        if back > 3 and back % 7 not in ((0, 3, 5) if alex else (1, 4)):
            continue
        await connection.execute(
            WEIGHT,
            {
                "id": _id(persona, f"weight-{back}"),
                "day": today - timedelta(days=back),
                "at": time(7, 30),
                "kg": _kg(persona, back),
            },
        )
    units = {analyte: (unit, low, high) for analyte, unit, low, high in ANALYTES}
    for visit, back in enumerate((520, 340, 160, 12)):
        checkup = _id(persona, f"checkup-{visit}")
        await connection.execute(
            CHECKUP,
            {
                "id": checkup,
                "day": today - timedelta(days=back),
                "center": say(persona, "Health centre"),
                "notes": say(
                    persona, "Yearly blood test." if visit % 2 == 0 else "Follow-up of the lipids."
                ),
            },
        )
        for analyte, value in _results(persona, visit):
            unit, low, high = units[analyte]
            await connection.execute(
                RESULT,
                {
                    "id": _id(persona, f"result-{visit}-{analyte}"),
                    "checkup": checkup,
                    "analyte": analyte,
                    "value": value,
                    "unit": unit,
                    "ref_low": low,
                    "ref_high": high,
                },
            )
