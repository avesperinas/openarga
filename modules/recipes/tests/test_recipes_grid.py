from __future__ import annotations

from recipes import grid
from recipes.gantt import Step

INGREDIENTS = [
    grid.Ingredient(1, "Butter"),
    grid.Ingredient(2, "Sugar"),
    grid.Ingredient(3, "Vanilla"),
    grid.Ingredient(4, "Coffee"),
    grid.Ingredient(5, "Eggs"),
    grid.Ingredient(6, "Flour"),
    grid.Ingredient(7, "Cacao"),
    grid.Ingredient(8, "Bicarbonato"),
    grid.Ingredient(9, "Salt"),
]

STEPS = [
    Step(1, "coat", "Grease and flour the tin", 3, equipment="none"),
    Step(2, "bake", "Preheat the oven to 170 C", 10, attended=False, equipment="oven"),
    Step(3, "mix", "Melt the butter", 3, equipment="hob", uses=(1,)),
    Step(
        4,
        "mix",
        "Mix with sugar, vanilla and coffee",
        3,
        equipment="bowl",
        after=(3,),
        uses=(2, 3, 4),
    ),
    Step(5, "mix", "Beat the eggs in", 2, equipment="bowl", after=(4,), uses=(5,)),
    Step(
        6, "mix", "Fold in the dry ingredients", 4, equipment="bowl", after=(5,), uses=(6, 7, 8, 9)
    ),
    Step(7, "bake", "Bake", 35, attended=False, equipment="oven", after=(2, 6)),
]


def test_the_grid_comes_out_like_the_recipe_that_was_asked_for() -> None:
    made = grid.build(STEPS, INGREDIENTS)

    assert [row.name for row in made.rows] == [
        "Butter",
        "Sugar",
        "Vanilla",
        "Coffee",
        "Eggs",
        "Flour",
        "Cacao",
        "Bicarbonato",
        "Salt",
    ]
    assert [(cell.position, cell.column, cell.row, cell.span) for cell in made.cells] == [
        (3, 1, 1, 1),
        (4, 2, 1, 4),
        (5, 3, 1, 5),
        (6, 4, 1, 9),
        (7, 5, 1, 9),
    ]
    assert made.columns == 5
    assert made.notes == ()


def test_a_step_that_touches_no_ingredient_is_a_band_and_not_a_cell() -> None:
    made = grid.build(STEPS, INGREDIENTS)

    assert [(band.position, band.text) for band in made.bands] == [
        (1, "Grease and flour the tin"),
        (2, "Preheat the oven to 170 C"),
    ]


def test_the_rows_of_a_step_always_come_out_together() -> None:
    made = grid.build(STEPS, INGREDIENTS)

    for cell in made.cells:
        assert 1 <= cell.row <= len(made.rows)
        assert cell.row + cell.span - 1 <= len(made.rows)


def test_an_ingredient_used_twice_is_drawn_once_and_said_with_words() -> None:
    twice = [
        Step(1, "season", "Salt the water", 1, equipment="hob", uses=(1, 2)),
        Step(2, "season", "Adjust the salt", 1, equipment="hob", after=(1,), uses=(2,)),
    ]

    made = grid.build(twice, [grid.Ingredient(1, "Water"), grid.Ingredient(2, "Salt")])

    assert [row.position for row in made.rows] == [1, 2]
    assert made.notes == ("ingredient 2 also goes into step 2",)


def test_a_result_that_feeds_two_steps_is_said_too() -> None:
    split = [
        Step(1, "saute", "Make the sofrito", 10, equipment="hob", uses=(1,)),
        Step(2, "mix", "One pot", 2, equipment="hob", after=(1,), uses=(2,)),
        Step(3, "mix", "The other", 2, equipment="hob", after=(1,), uses=(3,)),
    ]

    made = grid.build(
        split,
        [grid.Ingredient(1, "Onion"), grid.Ingredient(2, "Rice"), grid.Ingredient(3, "Pasta")],
    )

    assert made.notes == ("what comes from step 1 also goes into step 3",)
    assert made.columns == 2


def test_an_ingredient_that_no_step_uses_is_still_a_row() -> None:
    made = grid.build(
        [Step(1, "chop", "Chop the leek", 5, equipment="board", uses=(1,))],
        [grid.Ingredient(1, "Leek"), grid.Ingredient(2, "Parsley")],
    )

    assert [(row.name, row.orphan) for row in made.rows] == [("Leek", False), ("Parsley", True)]
    assert made.notes == ("goes into no step: Parsley",)


def test_steps_that_do_not_say_what_goes_in_them_get_a_grid_that_says_so() -> None:
    made = grid.build(
        [
            Step(1, "chop", "Chop", 5, equipment="board"),
            Step(2, "simmer", "Cocer", 30, attended=False, equipment="hob", after=(1,)),
        ],
        [grid.Ingredient(1, "Leek"), grid.Ingredient(2, "Potato")],
    )

    assert made.cells == ()
    assert made.columns == 0
    assert len(made.bands) == 2
    assert "say it in each step" in made.notes[0]


def test_a_recipe_without_steps_is_just_its_ingredients() -> None:
    made = grid.build([], [grid.Ingredient(1, "Leek")])

    assert [row.name for row in made.rows] == ["Leek"]
    assert made.cells == ()
    assert made.bands == ()


def test_a_recipe_without_ingredients_has_no_grid_at_all() -> None:
    assert grid.build([Step(1, "rest", "Reposar", 10)], []) == grid.Grid()
