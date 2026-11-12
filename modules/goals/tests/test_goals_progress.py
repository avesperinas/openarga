from __future__ import annotations

from datetime import date, timedelta

from goals.progress import Check, GoalShape, evaluate, monday

TODAY = date(2026, 10, 15)


def days_back(n: int) -> date:
    return TODAY - timedelta(days=n)


def test_a_daily_goal_counts_its_streak_in_days_and_today_does_not_break_it() -> None:
    goal = GoalShape(kind="periodic", start_on=days_back(60), target=8000, period="day")
    steps = {days_back(n): 9000.0 for n in range(1, 6)}
    steps[days_back(6)] = 3000.0
    found = evaluate(goal, steps, {}, TODAY)
    assert found.today_met is False
    assert (found.streak, found.streak_unit) == (5, "days")
    assert [state for _, state in found.week][:4] == ["met", "met", "met", "today"]
    assert [state for _, state in found.week][4:] == ["future", "future", "future"]


def test_marking_by_hand_wins_over_the_figure() -> None:
    goal = GoalShape(kind="periodic", start_on=days_back(10), target=8000, period="day")
    steps = {TODAY: 2000.0, days_back(1): 2000.0}
    found = evaluate(goal, steps, {TODAY: Check(done=True)}, TODAY)
    assert found.today_met is True and found.today_manual is True
    assert found.streak == 1


def test_five_days_a_week_by_hand_counts_weeks() -> None:
    start = monday(TODAY) - timedelta(days=21)
    goal = GoalShape(kind="periodic", start_on=start, period="day", days_per_week=5)
    checks: dict[date, Check] = {}
    for week in (1, 2, 3):
        first = monday(TODAY) - timedelta(days=7 * week)
        for offset in range(5 if week != 3 else 4):
            checks[first + timedelta(days=offset)] = Check(done=True)
    found = evaluate(goal, {}, checks, TODAY)
    assert (found.streak, found.streak_unit) == (2, "weeks")
    assert found.constancy == 2 / 3
    assert found.week_target == 5 and found.week_count == 0


def test_a_weekly_total_adds_monday_to_sunday() -> None:
    goal = GoalShape(kind="periodic", start_on=days_back(30), target=40, period="week")
    km = {monday(TODAY): 12.0, monday(TODAY) + timedelta(days=2): 30.0}
    found = evaluate(goal, km, {}, TODAY)
    assert found.week_count == 42 and found.week_met is True
    assert found.streak == 1


def test_a_dated_level_goal_knows_its_pace_and_projects() -> None:
    goal = GoalShape(
        kind="dated",
        start_on=days_back(50),
        due_on=TODAY + timedelta(days=50),
        start_value=85,
        target=80,
        direction="at_most",
        metric_kind="level",
    )
    weights = {days_back(20): 83.0, days_back(10): 82.5, TODAY: 82.0}
    found = evaluate(goal, weights, {}, TODAY)
    assert found.expected == 82.5
    assert found.current == 82.0 and found.pace == "ahead"
    assert found.progress == 0.6
    assert round(found.projection, 1) == 79.5 and found.projection_reached is True


def test_behind_when_the_line_goes_faster() -> None:
    goal = GoalShape(
        kind="dated",
        start_on=days_back(50),
        due_on=TODAY + timedelta(days=50),
        start_value=85,
        target=80,
        direction="at_most",
        metric_kind="level",
    )
    found = evaluate(goal, {days_back(20): 84.2, TODAY: 84.0}, {}, TODAY)
    assert found.pace == "behind" and found.projection_reached is False


def test_an_amount_goal_adds_from_its_start() -> None:
    goal = GoalShape(
        kind="dated",
        start_on=date(2026, 1, 1),
        due_on=date(2026, 12, 31),
        target=30,
        metric_kind="amount",
    )
    books = {date(2025, 12, 20): 1.0, date(2026, 3, 1): 1.0, days_back(20): 1.0, days_back(2): 1.0}
    found = evaluate(goal, books, {}, TODAY)
    assert found.current == 3 and found.start == 0
    assert found.pace == "behind"


def test_without_two_recent_points_there_is_no_projection() -> None:
    goal = GoalShape(
        kind="dated",
        start_on=days_back(100),
        due_on=TODAY + timedelta(days=100),
        start_value=100,
        target=200,
        metric_kind="level",
    )
    found = evaluate(goal, {days_back(60): 120.0, days_back(2): 150.0}, {}, TODAY)
    assert found.current == 150 and found.projection is None


def test_a_milestone_is_done_when_marked() -> None:
    goal = GoalShape(kind="dated", start_on=days_back(10), due_on=TODAY + timedelta(days=200))
    assert evaluate(goal, {}, {}, TODAY).reached is False
    assert evaluate(goal, {}, {days_back(1): Check(done=True)}, TODAY).reached is True


def test_reaching_the_target_is_reached() -> None:
    goal = GoalShape(
        kind="dated",
        start_on=days_back(10),
        due_on=TODAY + timedelta(days=10),
        start_value=0,
        target=1,
        metric_kind="level",
    )
    found = evaluate(goal, {days_back(1): 1.0}, {}, TODAY)
    assert found.reached is True and found.pace == "ahead"


def test_a_mark_only_counts_what_comes_after_the_goal_starts() -> None:
    goal = GoalShape(
        kind="dated",
        start_on=date(2026, 10, 6),
        target=135,
        due_on=date(2026, 12, 31),
        metric_kind="peak",
    )
    values = {date(2023, 4, 2): 140.0, date(2026, 10, 8): 120.0, date(2026, 10, 15): 130.0}

    found = evaluate(goal, values, {}, date(2026, 10, 20))
    assert (found.start, found.current, found.reached) == (140.0, 130.0, False)

    values[date(2026, 10, 19)] = 137.5
    later = evaluate(goal, values, {}, date(2026, 10, 20))
    assert (later.current, later.reached) == (137.5, True)


def test_a_mark_without_anything_new_stays_where_it_started() -> None:
    goal = GoalShape(
        kind="dated", start_on=date(2026, 10, 6), target=100, due_on=None, metric_kind="peak"
    )
    found = evaluate(goal, {date(2025, 1, 1): 110.0}, {}, date(2026, 10, 7))
    assert found.reached is False
