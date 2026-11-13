from __future__ import annotations

from recipes.gantt import Step, overlaps, schedule


def test_without_steps_there_is_no_diagram() -> None:
    plan = schedule([])

    assert plan.steps == ()
    assert plan.total_minutes == 0
    assert plan.lanes == ()


def test_one_step_starts_at_minute_zero() -> None:
    plan = schedule([Step(position=1, action="chop", text="Chop the leek", minutes=10)])

    assert plan.steps[0].start == 0
    assert plan.steps[0].end == 10
    assert plan.total_minutes == 10
    assert plan.active_minutes == 10


def test_what_depends_on_another_waits_for_it_to_finish() -> None:
    plan = schedule(
        [
            Step(position=1, action="chop", text="Chop", minutes=10),
            Step(position=2, action="saute", text="Pochar", minutes=15, after=(1,)),
        ]
    )

    assert [(one.start, one.end) for one in plan.steps] == [(0, 10), (10, 25)]


def test_two_attended_steps_do_not_overlap() -> None:
    plan = schedule(
        [
            Step(position=1, action="chop", text="Chop the leek", minutes=10),
            Step(position=2, action="peel", text="Peel the potato", minutes=8),
        ]
    )

    assert [(one.start, one.end) for one in plan.steps] == [(0, 10), (10, 18)]
    assert plan.total_minutes == 18
    assert plan.active_minutes == 18


def test_an_unattended_step_lets_you_go_on() -> None:
    plan = schedule(
        [
            Step(
                position=1,
                action="bake",
                text="In the oven",
                minutes=40,
                attended=False,
                equipment="oven",
            ),
            Step(position=2, action="chop", text="Chop the salad", minutes=10, equipment="board"),
        ]
    )

    assert [(one.start, one.end) for one in plan.steps] == [(0, 40), (0, 10)]
    assert plan.total_minutes == 40
    assert plan.active_minutes == 10


def test_what_comes_out_of_the_oven_waits_for_the_oven() -> None:
    plan = schedule(
        [
            Step(
                position=1,
                action="bake",
                text="In the oven",
                minutes=40,
                attended=False,
                equipment="oven",
            ),
            Step(position=2, action="chop", text="Chop", minutes=10, equipment="board"),
            Step(position=3, action="serve", text="Emplatar", minutes=5, after=(1, 2)),
        ]
    )

    emplatar = plan.steps[2]
    assert emplatar.start == 40
    assert plan.total_minutes == 45
    assert plan.active_minutes == 15


def test_a_busy_cook_delays_the_next_step_even_if_it_depends_on_nothing() -> None:
    plan = schedule(
        [
            Step(
                position=1,
                action="simmer",
                text="Cocer",
                minutes=30,
                attended=False,
                equipment="hob",
            ),
            Step(position=2, action="chop", text="Chop", minutes=10),
            Step(position=3, action="mix", text="Mix", minutes=5),
        ]
    )

    assert [(one.start, one.end) for one in plan.steps] == [(0, 30), (0, 10), (10, 15)]
    assert plan.total_minutes == 30


def test_the_lanes_are_those_used_in_their_order() -> None:
    plan = schedule(
        [
            Step(position=1, action="chop", text="Chop", minutes=5, equipment="board"),
            Step(
                position=2,
                action="bake",
                text="Bake",
                minutes=20,
                attended=False,
                equipment="oven",
            ),
            Step(position=3, action="rest", text="Reposar", minutes=10, attended=False),
        ]
    )

    assert plan.lanes == ("oven", "board", "none")


def test_two_things_on_the_same_hob_at_once_are_said() -> None:
    plan = schedule(
        [
            Step(
                position=1,
                action="simmer",
                text="Caldo",
                minutes=40,
                attended=False,
                equipment="hob",
            ),
            Step(position=2, action="fry", text="Sofrito", minutes=15, equipment="hob"),
        ]
    )

    assert [clash.equipment for clash in overlaps(plan)] == ["hob"]
    assert overlaps(plan)[0].positions == [1, 2]


def test_what_takes_nothing_never_clashes() -> None:
    plan = schedule(
        [
            Step(position=1, action="rest", text="Rest the dough", minutes=60, attended=False),
            Step(position=2, action="marinate", text="Marinar", minutes=30, attended=False),
        ]
    )

    assert overlaps(plan) == []


def test_a_whole_recipe_gives_its_two_numbers() -> None:
    plan = schedule(
        [
            Step(position=1, action="chop", text="Chop the leek", minutes=5, equipment="board"),
            Step(
                position=2, action="peel", text="Break the potatoes", minutes=5, equipment="board"
            ),
            Step(
                position=3,
                action="saute",
                text="Soften the leek",
                minutes=10,
                equipment="hob",
                after=(1,),
            ),
            Step(
                position=4,
                action="simmer",
                text="Cocer a fuego lento",
                minutes=30,
                attended=False,
                equipment="hob",
                after=(2, 3),
            ),
        ]
    )

    assert plan.total_minutes == 50
    assert plan.active_minutes == 20
    assert plan.steps[-1].start == 20
