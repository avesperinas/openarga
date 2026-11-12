from datetime import date

import pytest

import arga_nutrients as nutrients

LENTILS_USDA = [
    {"nutrientId": 1008, "value": 352},
    {"nutrientId": 1003, "value": 24.6},
    {"nutrientId": 1004, "value": 1.06},
    {"nutrientId": 1005, "value": 63.4},
    {"nutrientId": 1079, "value": 10.7},
    {"nutrientId": 1089, "value": 6.51},
    {"nutrientId": 1190, "value": 479},
    {"nutrientId": 1177, "value": 479},
    {"nutrientId": 1093, "value": 6},
    {"nutrientId": 9999, "value": 1},
    {"nutrientId": 1114, "value": None},
]


def test_every_key_is_unique_and_the_front_ones_are_the_agreed_list() -> None:
    assert len(nutrients.KEYS) == len(nutrients.NUTRIENTS)
    assert [one.key for one in nutrients.FRONT] == [
        "kcal", "protein", "carbs", "fat", "fiber", "sugars", "saturated_fat", "cholesterol",
        "sodium", "potassium", "calcium", "iron", "magnesium", "zinc", "vitamin_a", "vitamin_c",
        "vitamin_d", "vitamin_b12", "folate", "caffeine", "alcohol",
    ]  # fmt: skip
    assert len(nutrients.NUTRIENTS) - len(nutrients.FRONT) >= 30


def test_usda_lentils_bring_iron_and_folate() -> None:
    found = nutrients.from_usda(LENTILS_USDA)
    assert found["iron"] == 6.51
    assert found["folate"] == 479
    assert found["kcal"] == 352
    assert found["sodium"] == 6


def test_what_usda_does_not_bring_is_missing_not_zero() -> None:
    found = nutrients.from_usda(LENTILS_USDA)
    assert "vitamin_d" not in found
    assert "caffeine" not in found


def test_usda_food_details_read_the_same_as_search_results() -> None:
    found = nutrients.from_usda([{"nutrient": {"id": 1089}, "amount": 6.51}])
    assert found == {"iron": 6.51}


def test_usda_energy_falls_back_to_atwater_when_there_is_no_plain_kcal() -> None:
    assert nutrients.from_usda([{"nutrientId": 2047, "value": 120}]) == {"kcal": 120}


def test_off_values_come_in_grams_and_are_converted() -> None:
    found = nutrients.from_off(
        {
            "energy-kcal_100g": 43,
            "proteins_100g": 0.5,
            "sodium_100g": 0.004,
            "vitamin-c_100g": 0.012,
            "vitamin-d_100g": 0.0000015,
            "caffeine_100g": 0.032,
            "alcohol_100g": 5,
        }
    )
    assert found["sodium"] == 4
    assert found["vitamin_c"] == 12
    assert found["vitamin_d"] == 1.5
    assert found["caffeine"] == 32
    assert found["alcohol"] == pytest.approx(3.95, abs=0.01)


def test_off_sodium_from_salt_and_kcal_from_kilojoules() -> None:
    found = nutrients.from_off({"energy_100g": 418.4, "salt_100g": 1.25})
    assert found == {"kcal": 100.0, "sodium": 500.0}


def test_a_branded_product_with_three_figures_has_only_those() -> None:
    found = nutrients.from_off(
        {"sodium_100g": 0.2, "sugars_100g": 12, "saturated-fat_100g": 3, "iron_100g": "?"}
    )
    assert set(found) == {"sodium", "sugars", "saturated_fat"}


def test_scaling_and_adding_keep_what_is_missing_missing() -> None:
    lentils = nutrients.scaled({"kcal": 352, "iron": 6.51}, 50)
    coffee = nutrients.scaled({"kcal": 2, "caffeine": 40}, 200)
    assert nutrients.added(lentils, coffee) == {"kcal": 180, "iron": 3.255, "caffeine": 80}


def test_only_known_drops_unknown_keys_and_bad_numbers() -> None:
    assert nutrients.only_known({"iron": "2", "vitamin_x": 1, "zinc": -1, "fat": "nan"}) == {
        "iron": 2.0
    }


def test_references_depend_on_sex_and_age() -> None:
    young_woman = nutrients.references("female", 32)
    older_woman = nutrients.references("female", 55)
    man = nutrients.references("male", 22)
    assert young_woman["iron"].value == 16
    assert older_woman["iron"].value == 11
    assert man["calcium"].value == 1000
    assert young_woman["calcium"].value == 950
    assert man["sodium"] == nutrients.Reference("sodium", "max", 2000)
    assert man["saturated_fat"].kind == "energy_share"
    assert "alcohol" not in man and "kcal" not in man


def test_without_a_profile_an_adult_and_the_strictest_of_both_sexes() -> None:
    unknown = nutrients.references(None, None)
    assert unknown["iron"].value == 16
    assert unknown["vitamin_c"].value == 110
    assert unknown["calcium"].value == 950


def test_age_is_counted_on_the_birthday() -> None:
    assert nutrients.age_on(date(1990, 10, 1), date(2026, 9, 30)) == 35
    assert nutrients.age_on(date(1990, 10, 1), date(2026, 10, 1)) == 36
    assert nutrients.age_on(None, date(2026, 10, 1)) is None


def test_salt_and_sodium_go_both_ways() -> None:
    assert nutrients.salt_from_sodium(400) == 1.0
    assert nutrients.sodium_from_salt(1.0) == 400


def test_typed_nutrients_go_in_the_unit_of_their_key() -> None:
    found = nutrients.typed(
        {
            "omega3_epa": {"amount": 250, "unit": "mg"},
            "vitamin_d": {"amount": 5, "unit": "mcg"},
            "caffeine": 80,
            "kcal": {"amount": 418.4, "unit": "kJ"},
        }
    )

    assert found == {"omega3_epa": 0.25, "vitamin_d": 5.0, "caffeine": 80.0, "kcal": 100.0}


def test_typed_nutrients_say_everything_that_does_not_fit_at_once() -> None:
    with pytest.raises(nutrients.Invalid) as raised:
        nutrients.typed(
            {
                "vitamina_x": 1,
                "iron": 300_000,
                "vitamin_d": {"amount": 5, "unit": "kcal"},
                "zinc": -1,
            }
        )

    assert len(raised.value.problems) == 4
    assert "vitamina_x" in raised.value.problems[0]


def test_default_goals_are_ranges_with_the_macros_as_shares_of_energy() -> None:
    found = nutrients.default_goals("male", 40, 80)

    assert found["fat"] == nutrients.Goal("fat", "kcal_pct", 20.0, 35.0)
    assert found["carbs"] == nutrients.Goal("carbs", "kcal_pct", 45.0, 60.0)
    assert found["protein"] == nutrients.Goal("protein", "amount", 66.4, None)
    assert found["sodium"] == nutrients.Goal("sodium", "amount", None, 2000.0)
    assert found["saturated_fat"] == nutrients.Goal("saturated_fat", "kcal_pct", None, 10.0)
    assert "kcal" not in found
    assert "protein" not in nutrients.default_goals("male", 40, None)
