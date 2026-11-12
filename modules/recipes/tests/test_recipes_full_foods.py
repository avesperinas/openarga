from __future__ import annotations

import pytest

READ = {"x-arga-scopes": "recipes:read"}
WRITE = {"x-arga-scopes": "recipes:read recipes:write"}

FISH_OIL_CAPSULE = {
    "name": "Omega 3 sintético",
    "category_id": "other",
    "provenance": "etiqueta del bote",
    "macros": {"kcal": 900, "protein": 0, "fat": 100, "carbs": 0},
    "nutrients": {
        "omega3_epa": {"amount": 18000, "unit": "mg"},
        "omega3_dha": 12,
        "vitamin_e": {"amount": 1, "unit": "mg"},
    },
}


def call(api, name: str, arguments: dict, headers: dict = WRITE):
    return api.post(f"/tools/{name}", json=arguments, headers=headers)


async def manual(api, **overrides) -> dict:
    body = {**FISH_OIL_CAPSULE, **overrides}
    response = await call(api, "add_manual_food", body)
    assert response.status_code == 200, response.text
    food = response.json()["content"]["food"]
    assert food is not None, response.json()
    return food


async def test_what_no_source_has_is_created_with_every_nutrient_and_where_it_comes_from(
    api,
) -> None:
    food = await manual(api)

    assert food["source"] == "manual"
    assert food["provenance"] == "etiqueta del bote"
    assert food["nutrients"]["omega3_epa"] == 18
    assert food["nutrients"]["omega3_dha"] == 12
    assert food["nutrients"]["vitamin_e"] == 1
    listed = (await call(api, "find_foods", {"query": "omega"}, READ)).json()["content"]["foods"]
    assert listed[0]["provenance"] == "etiqueta del bote"


async def test_a_key_or_a_unit_that_does_not_fit_is_refused_with_its_reason(api) -> None:
    wrong = await call(
        api,
        "add_manual_food",
        {
            **FISH_OIL_CAPSULE,
            "nutrients": {"vitamina_d": 5, "caffeine": {"amount": 3, "unit": "kcal"}},
        },
    )

    assert wrong.status_code == 422
    detail = wrong.text
    assert "vitamina_d" in detail and "list_nutrients" in detail
    assert "caffeine: va en mg" in detail


async def test_more_of_something_than_the_100_g_it_weighs_is_refused(api) -> None:
    wrong = await call(api, "add_manual_food", {**FISH_OIL_CAPSULE, "nutrients": {"iron": 200_000}})

    assert wrong.status_code == 422
    assert "pesa más que los 100 g" in wrong.text


async def test_the_nutrient_keys_are_listed_with_their_units(api) -> None:
    found = (await call(api, "list_nutrients", {}, READ)).json()["content"]["nutrients"]

    by_key = {one["key"]: one for one in found}
    assert by_key["vitamin_d"]["unit"] == "µg"
    assert by_key["caffeine"]["unit"] == "mg"
    assert by_key["omega3_epa"]["unit"] == "g"


async def test_correcting_changes_only_what_is_sent(api) -> None:
    food = await manual(api, grams_per_unit=1, density_g_ml=0.92)

    corrected = (
        await call(
            api,
            "correct_food",
            {"food_id": food["food_id"], "nutrients": {"vitamin_d": 10, "vitamin_e": None}},
        )
    ).json()["content"]["food"]

    assert corrected["corrected"] is True
    assert corrected["per_100g"]["kcal"] == 900
    assert (corrected["grams_per_unit"], corrected["density_g_ml"]) == (1, 0.92)
    assert corrected["nutrients"]["vitamin_d"] == 10
    assert "vitamin_e" not in corrected["nutrients"]
    assert corrected["nutrients"]["omega3_epa"] == 18
    assert corrected["provenance"] == "etiqueta del bote"


async def test_portions_are_not_a_correction_of_the_figures(api, schema) -> None:
    created = await api.post(
        "/foods/manual",
        json={
            "name": "Jamón sintético",
            "category_id": "protein",
            "macros": {"kcal": 250, "protein": 30, "fat": 14, "carbs": 0},
        },
    )
    food_id = created.json()["id"]
    async with schema.begin() as connection:
        from sqlalchemy import text

        await connection.execute(
            text("update recipes.recipes_food set corrected = false where id = :id"),
            {"id": food_id},
        )

    saved = (
        await call(
            api,
            "correct_food",
            {"food_id": food_id, "portions": [{"name": "loncha", "grams": 15}]},
        )
    ).json()["content"]["food"]

    assert saved["portions"] == [{"name": "loncha", "grams": 15}]
    assert saved["corrected"] is False


async def test_micros_are_borrowed_where_missing_never_the_macros(api) -> None:
    generic = await manual(
        api,
        name="Salmón genérico",
        provenance="ficha de referencia",
        macros={"kcal": 208, "protein": 20, "fat": 13, "carbs": 0},
        nutrients={"vitamin_d": 11, "omega3_epa": 0.86, "sodium": 59},
    )
    branded = await manual(
        api,
        name="Salmón ahumado de marca",
        provenance="etiqueta",
        macros={"kcal": 180, "protein": 22, "fat": 10, "carbs": 0.5},
        nutrients={"sodium": 1200},
        micros_from=generic["food_id"],
    )

    assert branded["per_100g"]["kcal"] == 180
    assert branded["nutrients"]["kcal"] == 180
    assert branded["nutrients"]["sodium"] == 1200
    assert branded["nutrients"]["vitamin_d"] == 11
    assert branded["micros_from"] == generic["food_id"]
    assert set(branded["borrowed"]) == {"vitamin_d", "omega3_epa"}

    alone = (
        await call(api, "correct_food", {"food_id": branded["food_id"], "micros_from": None})
    ).json()["content"]["food"]
    assert "vitamin_d" not in alone["nutrients"]
    assert alone["borrowed"] == []


async def test_borrowing_does_not_chain_and_not_from_itself(api) -> None:
    first = await manual(api, name="Uno")
    second = await manual(api, name="Dos", micros_from=first["food_id"])

    chained = (
        await call(
            api,
            "add_manual_food",
            {**FISH_OIL_CAPSULE, "name": "Tres", "micros_from": second["food_id"]},
        )
    ).json()
    itself = (
        await call(
            api, "correct_food", {"food_id": first["food_id"], "micros_from": first["food_id"]}
        )
    ).json()

    assert chained["content"]["food"] is None
    assert "apunta al original" in chained["content"]["note"]
    assert itself["content"]["food"] is None
    assert "sí mismo" in itself["content"]["note"]


async def test_a_recipe_counts_house_portions_and_what_is_eaten_of_a_whole_piece(api) -> None:
    ham = await manual(
        api,
        name="Jamón",
        provenance="etiqueta",
        macros={"kcal": 250, "protein": 30, "fat": 14, "carbs": 0},
        nutrients={},
        portions=[{"name": "Loncha", "grams": 15}, {"name": "taco", "grams": 40}],
    )
    tuna = await manual(
        api,
        name="Bonito",
        provenance="etiqueta",
        macros={"kcal": 140, "protein": 24, "fat": 5, "carbs": 0},
        nutrients={},
        edible_fraction=0.82,
    )
    body = {
        "name": "Bonito con jamón",
        "servings": 2,
        "ingredients": [
            {"food_id": ham["food_id"], "quantity": 3, "unit": "unit", "portion": "loncha"},
            {"food_id": tuna["food_id"], "quantity": 730, "unit": "g", "as_purchased": True},
        ],
    }

    created = (await call(api, "create_recipe", body)).json()["content"]["saved"]
    recipe = (await call(api, "get_recipe", {"recipe_id": created["recipe_id"]}, READ)).json()[
        "content"
    ]["recipe"]

    grams = {
        one["name"]: one["grams"] for group in recipe["groups"] for one in group["ingredients"]
    }
    assert grams["Jamón"] == 45
    assert grams["Bonito"] == pytest.approx(598.6)
    assert recipe["nutrition"]["per_serving"]["kcal"] == pytest.approx(
        (45 * 2.5 + 598.6 * 1.4) / 2, abs=0.2
    )


async def test_a_portion_goes_with_units_only(api) -> None:
    wrong = await call(
        api,
        "create_recipe",
        {
            "name": "Mal",
            "servings": 1,
            "ingredients": [{"name": "Jamón", "quantity": 3, "unit": "g", "portion": "loncha"}],
        },
    )

    assert wrong.status_code == 422
    assert "una porción cuenta unidades" in wrong.text


CAPSULE = {
    "name": "Omega 3 en cápsulas",
    "category_id": "supplement",
    "provenance": "etiqueta del bote",
    "per_unit": "cápsula",
    "macros": {"kcal": 9, "protein": 0, "fat": 1, "carbs": 0},
    "nutrients": {
        "omega3_epa": {"amount": 330, "unit": "mg"},
        "omega3_dha": {"amount": 220, "unit": "mg"},
        "vitamin_d": 5,
    },
}


async def test_a_supplement_keeps_its_figures_per_unit(api) -> None:
    food = await manual(api, **CAPSULE)

    assert food["category"] == "supplement"
    assert food["per"] == "cápsula"
    assert food["per_100g"]["kcal"] == 9
    assert food["nutrients"]["omega3_epa"] == 0.33
    listed = (await call(api, "find_foods", {"query": "omega 3 en"}, READ)).json()["content"]
    assert listed["foods"][0]["per"] == "cápsula"


async def test_a_supplement_neither_borrows_nor_lends_micros(api) -> None:
    capsule = await manual(api, **CAPSULE)
    generic = await manual(api, name="Salmón genérico", nutrients={"vitamin_d": 11})

    borrowing = await call(
        api, "add_manual_food", {**CAPSULE, "name": "Otro", "micros_from": generic["food_id"]}
    )
    lending = (
        await call(
            api, "correct_food", {"food_id": generic["food_id"], "micros_from": capsule["food_id"]}
        )
    ).json()["content"]

    assert borrowing.status_code == 422
    assert "por unidad" in borrowing.text
    assert lending["food"] is None
    assert "por unidad" in lending["note"]


async def test_a_recipe_counts_a_supplement_by_units_and_not_in_grams(api) -> None:
    capsule = await manual(api, **CAPSULE)
    body = {
        "name": "Batido con omega",
        "servings": 1,
        "ingredients": [{"food_id": capsule["food_id"], "quantity": 2, "unit": "unit"}],
    }
    in_grams = {
        "name": "Batido mal medido",
        "servings": 1,
        "ingredients": [{"food_id": capsule["food_id"], "quantity": 2, "unit": "g"}],
    }

    good = (await call(api, "create_recipe", body)).json()["content"]["saved"]
    bad = (await call(api, "create_recipe", in_grams)).json()["content"]["saved"]
    counted = (await call(api, "get_recipe", {"recipe_id": good["recipe_id"]}, READ)).json()[
        "content"
    ]["recipe"]["nutrition"]
    missing = (await call(api, "get_recipe", {"recipe_id": bad["recipe_id"]}, READ)).json()[
        "content"
    ]["recipe"]["nutrition"]

    assert counted["per_serving"]["kcal"] == 18
    assert counted["nutrients"]["omega3_epa"] == pytest.approx(0.66)
    assert missing["counted"] == 0
