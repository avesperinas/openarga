from __future__ import annotations

import random
from datetime import date, timedelta

from insights import signals
from insights.signals import Goal, Series

TODAY = date(2026, 10, 13)


def days(n: int, end: date = TODAY) -> list[date]:
    return [end - timedelta(days=n - 1 - i) for i in range(n)]


def wobbly(n: int, around: float, spread: float, seed: int = 7, end: date = TODAY) -> dict:
    noise = random.Random(seed)
    return {d: around + noise.uniform(-spread, spread) for d in days(n, end)}


def weight(points: dict) -> Series:
    return Series("vitals.weight", "Weight", "kg", "level", points)


def kinds(found: list[signals.Signal]) -> list[tuple[str, str]]:
    return [(one.kind, one.keys[0] if one.keys else "") for one in found]


def test_a_jump_of_two_deviations_fires_and_a_normal_week_does_not() -> None:
    normal = wobbly(80, 80.0, 0.4)
    assert signals.detect([weight(normal)], [], TODAY) == []

    jumped = {**normal, TODAY: 82.0}
    [found] = signals.detect([weight(jumped)], [], TODAY)

    assert found.kind == "deviation"
    assert found.value == 82.0
    assert 79.6 < found.baseline < 80.4
    assert found.baseline_label == "your 90-day average"
    assert found.strength >= 2
    assert "82 kg" in found.text


def test_a_week_that_sums_far_from_the_usual_ones_fires() -> None:
    steps = Series("vitals.steps", "Steps", "steps", "amount", wobbly(120, 8000, 800, end=TODAY))
    assert [s for s in signals.detect([steps], [], TODAY) if s.kind == "deviation"] == []

    sunday = TODAY - timedelta(days=TODAY.weekday() + 1)
    for d in days(7, sunday):
        steps.points[d] = 2500
    [found] = [s for s in signals.detect([steps], [], TODAY) if s.kind == "deviation"]

    assert found.value == 17500
    assert found.since == sunday - timedelta(days=6)
    assert found.baseline_label.startswith("your weekly average")


def test_a_lab_that_moves_more_than_ten_percent_from_the_last_one_fires() -> None:
    ldl = Series(
        "vitals.ldl", "LDL", "mg/dL", "level", {date(2026, 5, 20): 133, date(2026, 9, 25): 151}
    )

    [found] = signals.detect([ldl], [], TODAY)

    assert (found.kind, found.value, found.baseline) == ("jump", 151, 133)
    assert found.baseline_label == "your measure of 20/05/2026"
    assert "+14%" in found.text


def test_a_daily_streak_cut_yesterday_fires_only_when_yesterday_is_known() -> None:
    done = {d: 3.0 for d in days(10, TODAY - timedelta(days=2))}
    unsure = Series("goals.tasks_done", "Tasks done", "count", "amount", dict(done))
    assert [s for s in signals.detect([unsure], [], TODAY) if s.kind == "streak"] == []

    known = Series("goals.tasks_done", "Tasks done", "count", "amount", {**done, TODAY: 1.0})
    [found] = [s for s in signals.detect([known], [], TODAY) if s.kind == "streak"]

    assert (found.value, found.baseline) == (0, 10)


def test_an_app_that_stops_says_so_once() -> None:
    before = TODAY - timedelta(days=10)
    protein = Series("macros.protein", "Protein", "g", "amount", wobbly(60, 120, 20, end=before))
    fat = Series("macros.fat", "Fat", "g", "amount", wobbly(40, 70, 10, end=before))

    stalls = [s for s in signals.detect([protein, fat], [], TODAY) if s.kind == "stall"]

    assert [(s.id, s.value) for s in stalls] == [("stall:macros", 10)]
    assert stalls[0].keys == ["macros.protein"]


def month_to_date(per_day: float, months: int, now_per_day: float) -> dict:
    points: dict = {}
    first = date(TODAY.year, TODAY.month, 1)
    for back in range(months, 0, -1):
        start = (first - timedelta(days=28 * back)).replace(day=1)
        total, d = 0.0, start
        while d.month == start.month:
            total += per_day
            points[d] = total
            d += timedelta(days=1)
    total, d = 0.0, first
    while d <= TODAY:
        total += now_per_day
        points[d] = total
        d += timedelta(days=1)
    return points


def test_a_month_that_runs_ahead_of_the_usual_pace_fires_and_nothing_else_does() -> None:
    spent = Series("money.month_expense", "Month spending", "EUR", "level", {})

    spent.points = month_to_date(40, 3, 41)
    assert signals.monthly(spent)
    assert signals.detect([spent], [], TODAY) == []

    spent.points = month_to_date(40, 3, 60)
    [found] = signals.detect([spent], [], TODAY)

    assert found.kind == "month_pace"
    assert found.value == 60 * 13
    assert found.baseline == 40 * 13
    assert found.domain == "money"
    assert "50% above" in found.text


def test_a_trend_that_turns_fires() -> None:
    points = {}
    for i, d in enumerate(days(90)):
        points[d] = 85 - 0.03 * i if i < 62 else 85 - 0.03 * 62 + 0.06 * (i - 62)

    found = [s for s in signals.detect([weight(points)], [], TODAY) if s.kind == "trend"]

    assert len(found) == 1
    assert found[0].value > 0 > found[0].baseline
    assert "rises" in found[0].text


def test_two_apps_that_start_going_together_fire() -> None:
    noise = random.Random(3)
    a, b = {}, {}
    for i, d in enumerate(days(365)):
        a[d] = noise.uniform(0, 10)
        b[d] = a[d] * 2 + noise.uniform(-1, 1) if i >= 275 else noise.uniform(0, 20)
    sleep = Series("vitals.sleep_hours", "Sleep", "count", "level", a)
    spent = Series("money.day_expense", "Day spending", "EUR", "level", b)

    found = signals.crosses([sleep, spent], TODAY)

    assert [one.keys for one in found] == [["vitals.sleep_hours", "money.day_expense"]]
    assert found[0].value > 0.9 > 0.5 > found[0].baseline


def test_a_goal_behind_carries_what_it_asked_for() -> None:
    behind = Goal(
        id="goal:1",
        title="Cholesterol under 200",
        unit="mg/dL",
        current=255,
        target=200,
        expected=221,
        progress=10,
        due_on=date(2026, 12, 31),
        metric="Colesterol total",
    )

    [found] = signals.detect([], [behind], TODAY)

    assert (found.kind, found.value, found.baseline) == ("goal", 255, 221)
    assert found.baseline_label == "what the goal asked for by now"
    assert "31/12/2026" in found.text


def test_a_period_keeps_each_signal_once_with_its_latest_reading() -> None:
    normal = wobbly(80, 80.0, 0.4)
    jumped = {**normal, TODAY - timedelta(days=3): 82.0, TODAY - timedelta(days=2): 82.3}

    found = signals.period([weight(jumped)], [], TODAY - timedelta(days=6), TODAY)

    assert [one.id for one in found] == ["deviation:vitals.weight"]


def test_numbers_are_said_the_spanish_way() -> None:
    assert signals.said(1234.5, "EUR") in ("1,234 €", "1,235 €")
    assert signals.said(82.4, "kg") == "82.4 kg"
    assert signals.said(7986, "steps") == "7,986 steps"
    assert signals.said(0.5) == "0.5"
