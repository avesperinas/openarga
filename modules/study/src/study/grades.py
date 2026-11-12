from __future__ import annotations

import math
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel

Verdict = Literal[
    "empty",
    "not_started",
    "in_progress",
    "secured",
    "impossible",
    "passed",
    "failed",
    "below_minimum",
]


@dataclass(frozen=True)
class Item:
    title: str
    weight: float | None
    grade: float | None
    min_grade: float | None = None


class Minimum(BaseModel):
    title: str
    min_grade: float


class Grade(BaseModel):
    verdict: Verdict
    current: float | None
    secured: float | None
    graded_weight: float
    remaining_weight: float
    needed_to_pass: float | None
    needed_for_target: float | None
    target: float | None
    final: float | None
    final_source: Literal["record", "computed"] | None
    unweighted: int
    failed_minimums: list[Minimum]
    pending_minimums: list[Minimum]
    sentence: str


def _round(value: float | None, places: int = 2) -> float | None:
    return None if value is None else round(value + 0.0, places)


def ceil1(value: float) -> float:
    return math.ceil(round(value * 10, 4)) / 10


def number(value: float | None, scale_max: float = 10) -> str:
    if value is None:
        return "—"
    places = 0 if scale_max >= 100 else 1
    text = f"{value:.{places}f}".replace(".", ",")
    return text[:-2] if text.endswith(",0") else text


def percent(value: float) -> str:
    text = f"{value:.1f}".replace(".", ",")
    return (text[:-2] if text.endswith(",0") else text) + " %"


def _as_float(value: Decimal | float | None) -> float | None:
    return None if value is None else float(value)


def compute(
    items: Sequence[Item],
    *,
    scale_max: float,
    pass_mark: float,
    target: float | None = None,
    record: float | None = None,
) -> Grade:
    any_weight = any(item.weight for item in items)
    weights = [
        (item.weight or 0.0) if any_weight else (100.0 / len(items) if items else 0.0)
        for item in items
    ]
    unweighted = sum(1 for item in items if not item.weight) if any_weight else 0
    counted = [(item, w) for item, w in zip(items, weights, strict=True) if w > 0]
    total = max(sum(w for _, w in counted), 100.0) if counted else 0.0
    graded = [(item, w) for item, w in counted if item.grade is not None]
    graded_weight = sum(w for _, w in graded)
    points = sum(w * (item.grade or 0.0) for item, w in graded)
    remaining = max(total - graded_weight, 0.0)

    current = points / graded_weight if graded_weight else None
    secured = points / total if total else None

    def needed(goal: float) -> float | None:
        if remaining <= 1e-9:
            return None
        return (goal * total - points) / remaining

    to_pass = needed(pass_mark)
    to_target = needed(target) if target is not None else None

    failed_minimums = [
        Minimum(title=item.title, min_grade=item.min_grade)
        for item in items
        if item.min_grade is not None and item.grade is not None and item.grade < item.min_grade
    ]
    pending_minimums = [
        Minimum(title=item.title, min_grade=item.min_grade)
        for item in items
        if item.min_grade is not None and item.grade is None
    ]

    final: float | None = None
    source: Literal["record", "computed"] | None = None
    if record is not None:
        final, source = record, "record"
    elif counted and remaining <= 1e-9 and current is not None:
        final, source = current, "computed"

    if record is not None:
        verdict: Verdict = "passed" if record >= pass_mark else "failed"
    elif not items:
        verdict = "empty"
    elif failed_minimums:
        verdict = "below_minimum"
    elif not counted:
        verdict = "empty"
    elif final is not None:
        verdict = "passed" if final >= pass_mark else "failed"
    elif not graded:
        verdict = "not_started"
    elif to_pass is not None and to_pass <= 0 and not pending_minimums:
        verdict = "secured"
    elif to_pass is not None and to_pass > scale_max:
        verdict = "impossible"
    else:
        verdict = "in_progress"

    grade = Grade(
        verdict=verdict,
        current=_round(current),
        secured=_round(secured),
        graded_weight=_round(graded_weight if counted else 0.0) or 0.0,
        remaining_weight=_round(remaining) or 0.0,
        needed_to_pass=_round(to_pass),
        needed_for_target=_round(to_target),
        target=target,
        final=_round(final),
        final_source=source,
        unweighted=unweighted,
        failed_minimums=failed_minimums,
        pending_minimums=pending_minimums,
        sentence="",
    )
    grade.sentence = sentence(grade, scale_max=scale_max, pass_mark=pass_mark)
    return grade


def sentence(grade: Grade, *, scale_max: float, pass_mark: float) -> str:
    n = lambda value: number(value, scale_max)  # noqa: E731
    left = percent(grade.remaining_weight)
    minimums = "".join(
        f", y al menos un {n(m.min_grade)} en {m.title}" for m in grade.pending_minimums
    )
    match grade.verdict:
        case "empty":
            return "Sin evaluables todavía. Añade las entregas y los exámenes con su peso."
        case "passed" if grade.final_source == "record":
            return f"Aprobada con un {n(grade.final)} en el acta."
        case "failed" if grade.final_source == "record":
            return f"Suspensa con un {n(grade.final)} en el acta."
        case "passed":
            return f"Aprobada con un {n(grade.final)}."
        case "failed":
            return f"Suspensa con un {n(grade.final)}: no queda nada por calificar."
        case "below_minimum":
            first = grade.failed_minimums[0]
            return f"Suspensa: {first.title} no llega al {n(first.min_grade)} que pide."
        case "impossible":
            return (
                f"Aprobar ya no es posible: harían falta {n(grade.needed_to_pass)} de media "
                f"en lo que queda ({left})."
            )
        case "secured":
            base = "Aprobada pase lo que pase."
            if grade.target is not None and grade.needed_for_target is not None:
                return f"{base} {_target_sentence(grade, n, left)}"
            return base
        case "not_started":
            return (
                f"Necesitas un {n(ceil1(pass_mark))} de media para aprobar{minimums}."
                if not grade.target
                else f"Necesitas un {n(ceil1(pass_mark))} de media para aprobar{minimums}. "
                f"{_target_sentence(grade, n, left)}"
            )
        case _:
            needed = grade.needed_to_pass or 0.0
            text = (
                f"Necesitas un {n(ceil1(needed))} de media en lo que queda ({left}) "
                f"para aprobar{minimums}."
            )
            if grade.target is not None:
                text += f" {_target_sentence(grade, n, left)}"
            return text


def _target_sentence(grade: Grade, n, left: str) -> str:
    needed = grade.needed_for_target
    if needed is None:
        return ""
    if needed <= 0:
        return f"Tu objetivo del {n(grade.target)} ya está asegurado."
    return f"Para tu {n(grade.target)}, un {n(ceil1(needed))} ({left})."


@dataclass(frozen=True)
class SubjectResult:
    credits: float | None
    final: float | None
    passed: bool


class CourseGrade(BaseModel):
    average: float | None
    average_source: Literal["record", "subjects", "assessments"] | None
    counted: int
    subjects: int


def course_average(results: Iterable[SubjectResult], *, record: float | None = None) -> CourseGrade:
    results = list(results)
    with_final = [r for r in results if r.final is not None]
    if record is not None:
        return CourseGrade(
            average=record, average_source="record", counted=len(with_final), subjects=len(results)
        )
    if not with_final:
        return CourseGrade(average=None, average_source=None, counted=0, subjects=len(results))
    if all(r.credits for r in with_final):
        weight = sum(r.credits or 0 for r in with_final)
        value = sum((r.credits or 0) * (r.final or 0) for r in with_final) / weight
    else:
        value = sum(r.final or 0 for r in with_final) / len(with_final)
    return CourseGrade(
        average=_round(value),
        average_source="subjects",
        counted=len(with_final),
        subjects=len(results),
    )


__all__ = [
    "CourseGrade",
    "Grade",
    "Item",
    "Minimum",
    "SubjectResult",
    "ceil1",
    "compute",
    "course_average",
    "number",
    "percent",
]
