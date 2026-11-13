from __future__ import annotations

import pytest

from recipes.nutrition import (
    Convertible,
    Item,
    Per100g,
    per_serving,
    to_grams,
    totals,
    uncertainty,
)

LEEK = Per100g(kcal=61, protein=1.5, fat=0.3, carbs=14.15, fiber=1.8, salt=0.05)
OIL = Per100g(kcal=884, protein=0, fat=100, carbs=0)


def test_gramos_son_gramos() -> None:
    assert to_grams(300, "g", None) == 300


def test_a_liquid_needs_its_density() -> None:
    aceite = Convertible(density_g_ml=0.92)

    assert to_grams(100, "ml", aceite) == pytest.approx(92)
    assert to_grams(2, "tbsp", aceite) == pytest.approx(27.6)
    assert to_grams(1, "tsp", aceite) == pytest.approx(4.6)


def test_without_density_a_liquid_is_not_estimated() -> None:
    assert to_grams(100, "ml", Convertible()) is None


def test_a_unit_needs_what_one_weighs() -> None:
    huevo = Convertible(grams_per_unit=60)

    assert to_grams(2, "unit", huevo) == 120
    assert to_grams(0.5, "unit", Convertible()) is None


def test_a_pinch_weighs_the_same_for_everything() -> None:
    assert to_grams(1, "pinch", None) == 0.5


def test_the_sum_comes_from_each_ones_grams() -> None:
    total = totals(
        [
            Item(quantity=300, unit="g", macros=LEEK, measures=Convertible(), label="Leek"),
            Item(
                quantity=10,
                unit="ml",
                macros=OIL,
                measures=Convertible(density_g_ml=0.92),
                label="Oil",
            ),
        ]
    )

    assert total.kcal == pytest.approx(264.3, abs=0.2)
    assert total.grams == pytest.approx(309.2, abs=0.1)
    assert total.counted == 2
    assert total.complete


def test_what_cannot_be_converted_is_left_out_and_said() -> None:
    total = totals(
        [
            Item(quantity=300, unit="g", macros=LEEK, measures=Convertible(), label="Leek"),
            Item(quantity=1, unit="unit", macros=None, measures=None, label="home sofrito"),
            Item(quantity=0.5, unit="unit", macros=LEEK, measures=Convertible(), label="Onion"),
        ]
    )

    assert total.counted == 1
    assert total.total == 3
    assert total.missing == ("home sofrito", "Onion")
    assert not total.complete
    assert uncertainty(total) == "2 of 3 ingredients missing (home sofrito, Onion)"


def test_when_nothing_is_missing_there_is_nothing_to_say() -> None:
    total = totals([Item(quantity=100, unit="g", macros=LEEK, measures=Convertible(), label="P")])

    assert uncertainty(total) is None


def test_a_single_absence_is_said_in_the_singular() -> None:
    total = totals([Item(quantity=1, unit="unit", macros=None, label="sofrito")])

    assert uncertainty(total) == "1 of 1 ingredients missing (sofrito)"


def test_fibre_nobody_declares_is_not_zero() -> None:
    total = totals([Item(quantity=10, unit="g", macros=OIL, measures=Convertible(), label="A")])

    assert total.fiber is None
    assert total.salt is None


def test_scaling_multiplies_the_quantities() -> None:
    uno = Item(quantity=200, unit="g", macros=LEEK, measures=Convertible(), label="Leek")

    assert totals([uno], scale=1.5).grams == 300
    assert totals([uno], scale=1.5).kcal == pytest.approx(totals([uno]).kcal * 1.5, abs=0.2)


def test_per_serving_is_what_really_counts() -> None:
    total = totals([Item(quantity=400, unit="g", macros=LEEK, measures=Convertible(), label="P")])

    each = per_serving(total, 4)

    assert each.kcal == pytest.approx(total.kcal / 4, abs=0.1)
    assert each.grams == pytest.approx(100, abs=0.1)
    assert each.missing == total.missing


def test_a_recipe_for_zero_people_does_not_exist() -> None:
    with pytest.raises(ValueError, match="at least one"):
        per_serving(totals([]), 0)
