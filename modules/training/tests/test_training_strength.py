from __future__ import annotations

import math
from datetime import date, timedelta
from itertools import count

import pytest

from training import stats, strength
from training.strength import Bodyweights, Entry, LoggedSet, Mark

LUNES = date(2025, 1, 6)
_ids = count()


def entry(
    *sets: tuple[int | None, float | None],
    day: date = LUNES,
    variant: str = "bench",
    gym: str | None = "gym",
    muscle: str = "chest",
    load_type: str = "external",
    factor: float | None = None,
    weight: int = 3,
) -> Entry:
    return Entry(
        id=f"e{next(_ids)}",
        session_id=f"s{next(_ids)}",
        variant_id=variant,
        gym_id=gym,
        day=day,
        muscle=muscle,
        index_weight=weight,
        load_type=load_type,
        bodyweight_factor=factor,
        sets=tuple(
            LoggedSet(reps=reps, weight=load if load_type == "external" else None, added_load=None)
            if load_type == "external"
            else LoggedSet(reps=reps, weight=None, added_load=load)
            for reps, load in sets
        ),
    )


def point(e1rm: float, day: date, variant: str = "bench", gym: str | None = "gym", **extra):
    load = e1rm / (1 + 8 / 30)
    return strength.Point(
        id=f"p{next(_ids)}",
        session_id="s",
        variant_id=variant,
        gym_id=gym,
        day=day,
        muscle=extra.get("muscle", "chest"),
        index_weight=extra.get("weight", 3),
        reps=8,
        load=load,
        e1rm=e1rm,
    )


def weekly(values: list[float], start: date = LUNES, **extra) -> list[strength.Point]:
    return [point(value, start + timedelta(weeks=n), **extra) for n, value in enumerate(values)]


def test_a_failed_rep_does_not_count_as_a_one_rep_max() -> None:
    best = strength.best_set(entry((0, 125), (3, 100)), None)

    assert best is not None
    assert best.load == 100
    assert best.e1rm == pytest.approx(110.0)


def test_more_than_fifteen_reps_counts_for_volume_but_not_for_strength() -> None:
    assert strength.best_set(entry((20, 40)), None) is None
    assert strength.best_set(entry((15, 40)), None) is not None


def test_a_warm_up_is_not_the_best_set_of_the_day() -> None:
    best = strength.best_set(entry((12, 20), (5, 100), (5, 100)), None)

    assert best.load == 100


def test_pull_ups_count_the_body_and_the_belt() -> None:
    dips = entry((5, 10), load_type="weighted_bodyweight", factor=0.95)

    best = strength.best_set(dips, 80)

    assert best.load == pytest.approx(80 * 0.95 + 10)


def test_without_a_bodyweight_a_bodyweight_exercise_does_not_count() -> None:
    dips = entry((5, 10), load_type="weighted_bodyweight", factor=1.0)

    assert strength.best_set(dips, None) is None


def test_the_bodyweight_of_a_day_is_the_last_one_before_or_the_first_one() -> None:
    weights = Bodyweights([(date(2025, 3, 1), 80.0), (date(2025, 6, 1), 78.0)])

    assert weights.on(date(2025, 1, 1)) == 80.0
    assert weights.on(date(2025, 4, 1)) == 80.0
    assert weights.on(date(2025, 7, 1)) == 78.0
    assert Bodyweights([]).on(date(2025, 7, 1)) is None


def test_the_same_variant_in_two_gyms_is_two_machines() -> None:
    points = weekly([100, 101, 102], gym="uno") + weekly([45, 46, 47], gym="other")

    series = strength.build(points)

    assert len(series) == 2
    assert all(p.counted for segment in series for p in segment.points)


def test_a_typo_is_set_aside_with_the_level_it_was_judged_against() -> None:
    values = [110, 112, 111, 150, 112, 113, 111]
    (segment,) = strength.build(weekly(values))

    flagged = [p for p in segment.points if not p.counted]
    assert [p.e1rm for p in flagged] == [150]
    assert flagged[0].status == "high"
    assert flagged[0].reference == pytest.approx(111.5)


def test_what_you_say_about_a_day_wins_over_what_was_detected() -> None:
    points = weekly([110, 112, 111, 150, 112, 113, 111])
    odd, normal = points[3], points[1]

    (segment,) = strength.build(points, verdicts={odd.id: "counted", normal.id: "excluded"})
    status = {p.id: p.status for p in segment.points}

    assert status[odd.id] == "counted"
    assert status[normal.id] == "excluded"


def test_a_clean_jump_that_stays_is_another_machine() -> None:
    points = weekly([100, 101, 100, 102, 160, 161, 160, 162])

    series = strength.build(points)

    assert [segment.start for segment in series] == ["first", "detected"]
    assert series[1].since == points[4].day
    assert all(p.counted for segment in series for p in segment.points)


def test_saying_the_machine_did_not_change_joins_it_back() -> None:
    points = weekly([100, 101, 100, 102, 160, 161, 160, 162])
    join = Mark(id="m", variant_id="bench", gym_id="gym", day=points[4].day, kind="join")

    series = strength.build(points, [join])

    assert len(series) == 1


def test_saying_the_machine_changed_splits_it_where_you_say() -> None:
    points = weekly([100, 101, 100, 102, 103, 104])
    split = Mark(id="m", variant_id="bench", gym_id="gym", day=points[3].day, kind="split")

    series = strength.build(points, [split])

    assert [segment.start for segment in series] == ["first", "mark"]
    assert series[1].since == points[3].day


def test_a_drop_after_a_long_break_is_detraining_not_another_machine() -> None:
    before = weekly([100, 101, 100, 102])
    after = weekly([60, 61, 60, 62], start=before[-1].day + timedelta(days=120))

    series = strength.build(before + after)

    assert len(series) == 1


def test_a_jump_hidden_behind_a_typo_is_still_found() -> None:
    points = weekly([100, 101, 180, 100, 102, 160, 161, 160, 162])

    series = strength.build(points)

    assert [segment.start for segment in series] == ["first", "detected"]


def change(curve: strength.Curve, since: date, until: date) -> float:
    return math.exp(curve.at(until) - curve.at(since)) - 1


def test_a_muscle_moves_with_what_its_machines_move() -> None:
    weeks = 26
    rise = [100 * 1.1 ** (n / (weeks - 1)) for n in range(weeks)]
    series = strength.build(
        weekly(rise, variant="bench") + weekly([v * 0.5 for v in rise], variant="flyes")
    )

    curve = strength.fit(series, LUNES + timedelta(weeks=weeks))

    measured = change(curve, LUNES + timedelta(weeks=4), LUNES + timedelta(weeks=weeks - 1))
    expected = 1.1 ** ((weeks - 5) / (weeks - 1)) - 1
    assert measured == pytest.approx(expected, abs=0.015)


def test_changing_gym_does_not_move_the_muscle() -> None:
    here = weekly([100] * 12, gym="uno")
    there = weekly([50] * 12, gym="other", start=LUNES + timedelta(weeks=12))

    curve = strength.fit(strength.build(here + there), LUNES + timedelta(weeks=24))

    assert change(curve, LUNES, LUNES + timedelta(weeks=23)) == pytest.approx(0, abs=0.005)


def test_the_first_weeks_of_a_new_exercise_do_not_count_as_strength() -> None:
    old = weekly([100] * 12, variant="bench")
    new = weekly(
        [60, 70, 80, 80, 80, 80, 80, 80], variant="inclinado", start=LUNES + timedelta(weeks=12)
    )

    curve = strength.fit(strength.build(old + new), LUNES + timedelta(weeks=20))

    assert change(curve, LUNES, LUNES + timedelta(weeks=19)) == pytest.approx(0, abs=0.01)


def test_one_machine_that_jumps_undetected_does_not_drag_the_muscle() -> None:
    steady = [p for n in range(3) for p in weekly([100] * 24, variant=f"v{n}")]
    odd = weekly([100] * 6 + [125] * 6 + [155] * 12, variant="rara")

    curve = strength.fit(strength.build(steady + odd), LUNES + timedelta(weeks=24))

    assert change(curve, LUNES, LUNES + timedelta(weeks=23)) < 0.08


def test_a_muscle_without_counted_days_has_no_curve() -> None:
    assert strength.fit([], LUNES) is None


def test_every_muscle_weighs_the_same_in_the_index() -> None:
    up = stats.Strength(value=110, delta=10, direction="up", trend=[])
    flat = stats.Strength(value=100, delta=0, direction="flat", trend=[])

    index = stats.overall([up, flat])

    assert index.value == 105
    assert index.muscles == 2
    assert index.direction == "up"


def test_without_any_muscle_there_is_no_index_instead_of_a_zero() -> None:
    index = stats.overall([])

    assert index.value is None
    assert index.direction is None


def _dense_fit(series: list[strength.Series], until: date) -> list[float]:
    import numpy as np

    used = [
        counted
        for segment in series
        if (
            counted := [p for p in segment.counted if p.day - segment.since >= strength.CALIBRATION]
        )
    ]
    start = strength.monday(min(counted[0].day for counted in used))
    weeks = (strength.monday(until) - start).days // 7 + 1
    rows = [
        (min((strength.monday(point.day) - start).days // 7, weeks - 1), weeks + index, point)
        for index, counted in enumerate(used)
        for point in counted
    ]
    values = np.array([math.log(point.e1rm) for _, _, point in rows])
    base = np.array([point.index_weight / 3 for _, _, point in rows])
    weeks_of = np.array([week for week, _, _ in rows])
    levels_of = np.array([level for _, level, _ in rows])
    size = weeks + len(used)
    weights = base.copy()
    for _ in range(4):
        matrix = np.zeros((size, size))
        target = np.zeros(size)
        np.add.at(matrix, (weeks_of, weeks_of), weights)
        np.add.at(matrix, (levels_of, levels_of), weights)
        np.add.at(matrix, (weeks_of, levels_of), weights)
        np.add.at(matrix, (levels_of, weeks_of), weights)
        np.add.at(target, weeks_of, weights * values)
        np.add.at(target, levels_of, weights * values)
        steps = np.arange(1, weeks)
        np.add.at(matrix, (steps, steps), strength.SMOOTHING)
        np.add.at(matrix, (steps - 1, steps - 1), strength.SMOOTHING)
        np.add.at(matrix, (steps, steps - 1), -strength.SMOOTHING)
        np.add.at(matrix, (steps - 1, steps), -strength.SMOOTHING)
        matrix[np.diag_indices(size)] += 1e-6
        solution = np.linalg.solve(matrix, target)
        residuals = np.abs(values - solution[weeks_of] - solution[levels_of])
        weights = base * np.minimum(1.0, strength.ROBUST / np.maximum(residuals, 1e-12))
    return [float(value) for value in solution[:weeks]]


def _many_series(count: int, points: int) -> list[strength.Series]:
    import random

    rng = random.Random(7)
    out = []
    for index in range(count):
        first = LUNES + timedelta(days=rng.randint(0, 1300))
        days = sorted({first + timedelta(days=rng.randint(0, 200)) for _ in range(points)})
        level = rng.uniform(40, 140)
        out.append(
            strength.Series(
                variant_id=f"v{index}",
                gym_id="gym",
                points=[
                    strength.Point(
                        id=f"p{index}-{n}",
                        session_id=f"s{index}-{n}",
                        variant_id=f"v{index}",
                        gym_id="gym",
                        day=day,
                        muscle="chest",
                        index_weight=rng.choice([1, 2, 3]),
                        reps=8,
                        load=level,
                        e1rm=level * (1 + n * 0.002) * rng.uniform(0.93, 1.07),
                    )
                    for n, day in enumerate(days)
                ],
            )
        )
    return out


def test_the_curve_solved_by_blocks_is_the_same_curve() -> None:
    series = _many_series(60, 20)
    until = LUNES + timedelta(days=1500)

    blocks = strength.fit(series, until)

    assert blocks is not None
    assert blocks.values == pytest.approx(_dense_fit(series, until), abs=1e-9)


def test_with_hundreds_of_series_the_system_solved_is_the_size_of_the_weeks(monkeypatch) -> None:
    import numpy as np

    sizes = []
    solve = np.linalg.solve

    def recorded(matrix, target):
        sizes.append(matrix.shape[0])
        return solve(matrix, target)

    monkeypatch.setattr(np.linalg, "solve", recorded)
    until = LUNES + timedelta(days=1500)
    curve = strength.fit(_many_series(500, 15), until)

    assert curve is not None
    assert set(sizes) == {len(curve.values)}
    assert len(curve.values) < 230
