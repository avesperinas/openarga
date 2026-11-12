from __future__ import annotations

from datetime import date
from typing import Any

from sqlalchemy.ext.asyncio import AsyncConnection

import arga_contracts as contracts
from arga_contracts import metrics as cifras
from study import studies

APP = "study"
LABEL = 80


def _point(key: str, label: str, unit: str, day: date, value: float) -> dict[str, Any]:
    return contracts.metric(
        APP,
        key=f"{APP}.{key}",
        label=label[:LABEL],
        unit=unit,
        kind="level",
        day=day,
        value=round(value, 2),
    )


async def build(connection: AsyncConnection) -> list[dict[str, Any]]:
    today = studies.today()
    found: list[dict[str, Any]] = []
    for course in await studies.courses(connection, "all"):
        if course.status == "planned":
            continue
        done = course.status == "finished"
        found.append(
            _point(
                f"finished:{course.id}",
                f"Terminado · {course.name}",
                "count",
                course.closed_on if done and course.closed_on else today,
                1 if done else 0,
            )
        )
        if "progress" in course.tracks and course.progress is not None:
            found.append(
                _point(
                    f"progress:{course.id}",
                    f"Progreso · {course.name}",
                    "percent",
                    today,
                    course.progress.ratio * 100,
                )
            )
        if "grades" not in course.tracks:
            continue
        detail = await studies.course(connection, course.id)
        grade = course.final_grade if course.final_grade is not None else course.average.average
        if grade is not None:
            found.append(
                _point(f"average:{course.id}", f"Media · {course.name}", "points", today, grade)
            )
        passed_subjects = sum(
            1
            for one in detail.subjects
            if one.final_grade is not None and one.final_grade >= course.pass_mark
        )
        if detail.subjects:
            found.append(
                _point(
                    f"subjects_passed:{course.id}",
                    f"Asignaturas aprobadas · {course.name}",
                    "count",
                    today,
                    passed_subjects,
                )
            )
        passed = course.status == "finished" and (grade is None or grade >= course.pass_mark)
        found.append(
            _point(
                f"passed:{course.id}",
                f"Aprobado · {course.name}",
                "count",
                course.closed_on if passed and course.closed_on else today,
                1 if passed else 0,
            )
        )
    return await cifras.steady(connection, APP, found)
