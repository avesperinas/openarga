from __future__ import annotations

import pytest

from study.grades import Item, SubjectResult, ceil1, compute, course_average, number


def grade(items, **options):
    return compute(
        items,
        scale_max=options.pop("scale_max", 10),
        pass_mark=options.pop("pass_mark", 5),
        **options,
    )


def test_with_forty_percent_graded_it_says_what_is_needed_to_pass() -> None:
    result = grade(
        [
            Item("Práctica 1", weight=20, grade=6),
            Item("Práctica 2", weight=20, grade=4),
            Item("Examen final", weight=60, grade=None),
        ]
    )

    assert result.verdict == "in_progress"
    assert result.current == 5.0
    assert result.secured == 2.0
    assert (result.graded_weight, result.remaining_weight) == (40, 60)
    assert result.needed_to_pass == 5.0
    assert result.sentence == "Necesitas un 5 de media en lo que queda (60 %) para aprobar."


def test_it_says_impossible_when_it_is() -> None:
    result = grade([Item("Parcial", weight=70, grade=1), Item("Final", weight=30, grade=None)])

    assert result.verdict == "impossible"
    assert result.needed_to_pass == pytest.approx(14.33, abs=0.01)
    assert result.sentence.startswith("Aprobar ya no es posible")


def test_it_says_when_it_is_passed_whatever_happens() -> None:
    result = grade([Item("Parcial", weight=80, grade=9), Item("Final", weight=20, grade=None)])

    assert result.verdict == "secured"
    assert result.needed_to_pass is not None and result.needed_to_pass <= 0
    assert result.sentence == "Aprobada pase lo que pase."


def test_a_target_gets_its_own_figure() -> None:
    result = grade(
        [Item("Trabajo", weight=40, grade=8), Item("Examen", weight=60, grade=None)],
        target=9,
    )

    assert result.needed_to_pass == 3.0
    assert result.needed_for_target == pytest.approx(9.67, abs=0.01)
    assert "Para tu 9, un 9,7 (60 %)." in result.sentence


def test_what_is_needed_rounds_up_never_down() -> None:
    assert ceil1(6.13) == 6.2
    assert ceil1(6.1) == 6.1
    assert ceil1(6.0000001) == 6.0


def test_a_minimum_not_reached_fails_it_even_if_the_average_passes() -> None:
    result = grade(
        [
            Item("Trabajo", weight=50, grade=10),
            Item("Examen", weight=50, grade=3, min_grade=4),
        ]
    )

    assert result.current == 6.5
    assert result.verdict == "below_minimum"
    assert result.sentence == "Suspensa: Examen no llega al 4 que pide."


def test_a_pending_minimum_is_said_and_keeps_it_from_being_secured() -> None:
    result = grade(
        [
            Item("Trabajo", weight=60, grade=10),
            Item("Examen", weight=40, grade=None, min_grade=4),
        ]
    )

    assert result.verdict == "in_progress"
    assert result.sentence.endswith("para aprobar, y al menos un 4 en Examen.")


def test_the_record_grade_overrides_the_computed_one() -> None:
    result = grade(
        [Item("Examen", weight=100, grade=4.5)],
        record=5,
    )

    assert (result.verdict, result.final, result.final_source) == ("passed", 5, "record")
    assert result.sentence == "Aprobada con un 5 en el acta."


def test_all_graded_gives_the_final_grade() -> None:
    result = grade([Item("A", weight=50, grade=7), Item("B", weight=50, grade=8)])

    assert (result.verdict, result.final, result.final_source) == ("passed", 7.5, "computed")


def test_without_weights_they_all_weigh_the_same() -> None:
    result = grade([Item("A", None, 6), Item("B", None, 8), Item("C", None, None)])

    assert result.current == 7.0
    assert result.graded_weight == pytest.approx(66.67, abs=0.01)
    assert result.unweighted == 0


def test_a_missing_weight_among_weighted_ones_does_not_count_and_is_said() -> None:
    result = grade([Item("A", 50, 6), Item("B", None, 10), Item("C", 50, None)])

    assert result.current == 6.0
    assert result.unweighted == 1


def test_weights_under_a_hundred_leave_the_rest_for_what_is_missing() -> None:
    result = grade([Item("Examen", weight=60, grade=7)])

    assert result.verdict == "in_progress"
    assert result.secured == 4.2
    assert result.remaining_weight == 40


def test_on_a_hundred_point_scale() -> None:
    result = grade(
        [Item("Midterm", weight=50, grade=40), Item("Final", weight=50, grade=None)],
        scale_max=100,
        pass_mark=50,
    )

    assert result.needed_to_pass == 60
    assert result.sentence == "Necesitas un 60 de media en lo que queda (50 %) para aprobar."


def test_nothing_to_grade_says_so() -> None:
    assert grade([]).verdict == "empty"
    assert grade([Item("A", None, None)]).verdict == "not_started"


def test_the_course_average_weighs_by_credits() -> None:
    result = course_average(
        [
            SubjectResult(credits=6, final=8, passed=True),
            SubjectResult(credits=3, final=5, passed=True),
            SubjectResult(credits=6, final=None, passed=False),
        ]
    )

    assert (result.average, result.counted, result.subjects) == (7.0, 2, 3)


def test_without_credits_subjects_weigh_the_same() -> None:
    result = course_average(
        [SubjectResult(credits=None, final=8, passed=True), SubjectResult(6, 5, True)]
    )

    assert result.average == 6.5


def test_numbers_read_in_spanish() -> None:
    assert number(6.24) == "6,2"
    assert number(7.0) == "7"
    assert number(85.0, 100) == "85"
