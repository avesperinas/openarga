from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Literal

Pace = Literal["ahead", "on_track", "behind"]
DayState = Literal["met", "missed", "today", "future", "before"]

WINDOW_DAYS = 28
TOLERANCE = 0.02


@dataclass(frozen=True)
class Check:
    done: bool | None = None
    value: float | None = None


@dataclass(frozen=True)
class GoalShape:
    kind: Literal["periodic", "dated"]
    start_on: date
    direction: Literal["at_least", "at_most"] = "at_least"
    target: float | None = None
    period: Literal["day", "week"] | None = None
    days_per_week: int | None = None
    due_on: date | None = None
    start_value: float | None = None
    metric_kind: Literal["level", "amount", "peak"] | None = None


@dataclass
class Evaluation:
    today_met: bool | None = None
    today_value: float | None = None
    today_manual: bool = False
    week: list[tuple[date, DayState]] = field(default_factory=list)
    week_count: float | None = None
    week_target: float | None = None
    week_met: bool | None = None
    streak: int | None = None
    streak_unit: Literal["days", "weeks"] | None = None
    constancy: float | None = None
    current: float | None = None
    start: float | None = None
    expected: float | None = None
    pace: Pace | None = None
    progress: float | None = None
    projection: float | None = None
    projection_reached: bool | None = None
    reached: bool | None = None
    last_day: date | None = None
    days_left: int | None = None


def monday(day: date) -> date:
    return day - timedelta(days=day.weekday())


def meets(value: float | None, target: float | None, direction: str) -> bool:
    if value is None or target is None:
        return False
    return value >= target if direction == "at_least" else value <= target


def day_values(values: dict[date, float], checks: dict[date, Check]) -> dict[date, float]:
    merged = dict(values)
    for day, check in checks.items():
        if check.value is not None:
            merged[day] = check.value
    return merged


def evaluate(
    goal: GoalShape,
    values: dict[date, float],
    checks: dict[date, Check],
    today: date,
) -> Evaluation:
    if goal.kind == "periodic":
        return _periodic(goal, values, checks, today)
    return _dated(goal, values, checks, today)


def _day_met(
    goal: GoalShape, merged: dict[date, float], checks: dict[date, Check], day: date
) -> bool:
    check = checks.get(day)
    if check is not None and check.done is not None:
        return check.done
    return meets(merged.get(day), goal.target, goal.direction)


def _week_total(merged: dict[date, float], start: date, until: date) -> float:
    total = 0.0
    day = start
    while day <= until:
        total += merged.get(day, 0.0)
        day += timedelta(days=1)
    return total


def _week_met(
    goal: GoalShape, merged: dict[date, float], checks: dict[date, Check], start: date, until: date
) -> tuple[float, bool]:
    if goal.period == "week":
        total = _week_total(merged, start, until)
        return total, meets(total, goal.target, goal.direction)
    count = 0
    day = start
    while day <= until:
        if day >= goal.start_on and _day_met(goal, merged, checks, day):
            count += 1
        day += timedelta(days=1)
    return float(count), count >= (goal.days_per_week or 7)


def _periodic(
    goal: GoalShape, values: dict[date, float], checks: dict[date, Check], today: date
) -> Evaluation:
    merged = day_values(values, checks)
    result = Evaluation()
    daily = goal.period == "day" and (goal.days_per_week or 7) == 7

    result.today_value = merged.get(today)
    result.today_manual = today in checks
    result.today_met = _day_met(goal, merged, checks, today) if goal.period == "day" else None

    this_week = monday(today)
    for offset in range(7):
        day = this_week + timedelta(days=offset)
        if day < goal.start_on:
            state: DayState = "before"
        elif day > today:
            state = "future"
        elif goal.period == "day":
            met = _day_met(goal, merged, checks, day)
            state = "met" if met else ("today" if day == today else "missed")
        else:
            done = merged.get(day, 0.0) > 0 or (checks.get(day) or Check()).done is True
            state = "met" if done else ("today" if day == today else "missed")
        result.week.append((day, state))

    count, met = _week_met(goal, merged, checks, this_week, today)
    result.week_count = count
    result.week_target = goal.target if goal.period == "week" else float(goal.days_per_week or 7)
    result.week_met = met

    if daily:
        result.streak_unit = "days"
        day = today if result.today_met else today - timedelta(days=1)
        streak = 0
        while day >= goal.start_on and _day_met(goal, merged, checks, day):
            streak += 1
            day -= timedelta(days=1)
        result.streak = streak

        first = max(goal.start_on, today - timedelta(days=WINDOW_DAYS))
        span = (today - first).days
        if span > 0:
            hits = sum(
                1
                for offset in range(span)
                if _day_met(goal, merged, checks, first + timedelta(days=offset))
            )
            result.constancy = hits / span
    else:
        result.streak_unit = "weeks"
        start = this_week if met else this_week - timedelta(days=7)
        streak = 0
        while start + timedelta(days=6) >= goal.start_on:
            _, done = _week_met(goal, merged, checks, start, start + timedelta(days=6))
            if not done:
                break
            streak += 1
            start -= timedelta(days=7)
        result.streak = streak

        weeks = [this_week - timedelta(days=7 * n) for n in range(1, WINDOW_DAYS // 7 + 1)]
        counted = [start for start in weeks if start >= monday(goal.start_on)]
        if counted:
            hits = sum(
                1
                for start in counted
                if _week_met(goal, merged, checks, start, start + timedelta(days=6))[1]
            )
            result.constancy = hits / len(counted)
    return result


def _regression(points: list[tuple[int, float]]) -> tuple[float, float] | None:
    n = len(points)
    if n < 2:
        return None
    mean_x = sum(x for x, _ in points) / n
    mean_y = sum(y for _, y in points) / n
    spread = sum((x - mean_x) ** 2 for x, _ in points)
    if spread == 0:
        return None
    slope = sum((x - mean_x) * (y - mean_y) for x, y in points) / spread
    return slope, mean_y - slope * mean_x


def _dated(
    goal: GoalShape, values: dict[date, float], checks: dict[date, Check], today: date
) -> Evaluation:
    result = Evaluation()
    merged = {day: value for day, value in day_values(values, checks).items() if day <= today}
    due = goal.due_on or today
    result.days_left = (due - today).days

    if goal.target is None:
        done = any(check.done for check in checks.values())
        result.reached = done
        result.progress = 1.0 if done else 0.0
        return result

    amount = goal.metric_kind == "amount"
    since_start = {day: value for day, value in merged.items() if day >= goal.start_on}
    if goal.metric_kind == "peak":
        best = max if goal.direction == "at_least" else min
        before = [value for day, value in merged.items() if day < goal.start_on]
        start = goal.start_value
        if start is None:
            start = best(before) if before else None
        if since_start:
            result.last_day = max(since_start)
            current = best(since_start.values())
        else:
            current = start
        if start is None:
            start = current
    elif amount:
        start = goal.start_value if goal.start_value is not None else 0.0
        current = start + sum(since_start.values())
        result.last_day = max(since_start) if since_start else None
    else:
        before = [day for day in merged if day <= goal.start_on]
        start = goal.start_value
        if start is None:
            first = min(since_start) if since_start else (max(before) if before else None)
            start = merged[first] if first is not None else None
        result.last_day = max(merged) if merged else None
        current = merged[result.last_day] if result.last_day is not None else start
    result.start = start
    result.current = current

    if current is None or start is None:
        return result

    result.reached = meets(current, goal.target, goal.direction)
    if goal.metric_kind == "peak" and not since_start:
        result.reached = False
    whole = goal.target - start
    total_days = max((due - goal.start_on).days, 1)
    elapsed = min(max((today - goal.start_on).days, 0), total_days)
    result.expected = start + whole * elapsed / total_days
    if whole != 0:
        result.progress = min(max((current - start) / whole, 0.0), 1.0)
    elif result.reached:
        result.progress = 1.0

    sign = 1 if goal.direction == "at_least" else -1
    gap = (current - result.expected) * sign
    tolerance = abs(whole) * TOLERANCE if whole else 0.0
    if result.reached or gap > tolerance:
        result.pace = "ahead"
    elif gap < -tolerance:
        result.pace = "behind"
    else:
        result.pace = "on_track"

    window_start = today - timedelta(days=WINDOW_DAYS)
    source = since_start if amount else merged
    recent = sorted((day, value) for day, value in source.items() if day > window_start)
    if len(recent) >= 2 and today < due:
        if amount:
            span = min(WINDOW_DAYS, max((today - goal.start_on).days, 1))
            rate = sum(value for _, value in recent) / span
            result.projection = current + rate * (due - today).days
        else:
            line = _regression([((day - today).days, value) for day, value in recent])
            if line is not None:
                slope, intercept = line
                result.projection = intercept + slope * (due - today).days
        if result.projection is not None:
            result.projection_reached = meets(result.projection, goal.target, goal.direction)
    return result
