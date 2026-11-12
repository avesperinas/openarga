from __future__ import annotations

READ = {"x-arga-scopes": "recipes:read"}
WRITE = {"x-arga-scopes": "recipes:read recipes:write"}


def call(api, name: str, arguments: dict, headers: dict = WRITE):
    return api.post(f"/tools/{name}", json=arguments, headers=headers)


async def manual(api, name: str, **extra) -> dict:
    body = {
        "name": name,
        "category_id": "dairy",
        "provenance": "etiqueta",
        "macros": {"kcal": 64, "protein": 3.2, "fat": 3.6, "carbs": 4.7},
        **extra,
    }
    response = await call(api, "add_manual_food", body)
    assert response.json()["content"]["food"] is not None, response.text
    return response.json()["content"]["food"]


async def recipe_with(api, food_id: str) -> str:
    body = {
        "name": "Natillas",
        "servings": 4,
        "tags": ["postre"],
        "ingredients": [
            {"food_id": food_id, "quantity": 500, "unit": "ml"},
            {"name": "Canela", "quantity": 1, "unit": "pinch"},
        ],
        "steps": [
            {
                "action": "boil",
                "text": "Hervir la leche",
                "minutes": 10,
                "equipment": "hob",
                "ingredients": [1],
            },
            {
                "action": "chill",
                "text": "Enfriar",
                "minutes": 120,
                "attended": False,
                "equipment": "fridge",
                "after": [1],
            },
        ],
    }
    saved = (await call(api, "create_recipe", body)).json()["content"]["saved"]
    return saved["recipe_id"]


async def test_recipes_get_a_new_version_and_the_old_food_is_archived(api, hub) -> None:
    old = await manual(
        api, "Leche de marca equivocada", alias="leche", portions=[{"name": "vaso", "grams": 250}]
    )
    new = await manual(api, "Leche entera de la buena")
    lender = await manual(api, "Yogur", micros_from=old["food_id"])
    recipe_id = await recipe_with(api, old["food_id"])

    done = (
        await call(
            api, "replace_food", {"old_food_id": old["food_id"], "new_food_id": new["food_id"]}
        )
    ).json()["content"]["replaced"]

    assert [(one["name"], one["version"]) for one in done["recipes"]] == [("Natillas", 2)]
    assert done["macros"]["done"] is False
    recipe = (await call(api, "get_recipe", {"recipe_id": recipe_id}, READ)).json()["content"][
        "recipe"
    ]
    ids = [one["food_id"] for group in recipe["groups"] for one in group["ingredients"]]
    assert new["food_id"] in ids and old["food_id"] not in ids
    assert "sustituido" in recipe["note"]
    assert [step["uses"] for step in recipe["kitchen"]["steps"]] == [[1], []]
    assert [tag["name"] for tag in recipe["tags"]] == ["postre"]
    assert "Canela" in [one["name"] for group in recipe["groups"] for one in group["ingredients"]]

    pantry = (await call(api, "find_foods", {}, READ)).json()["content"]["foods"]
    by_id = {one["food_id"]: one for one in pantry}
    assert old["food_id"] not in by_id
    assert by_id[new["food_id"]]["alias"] == "leche"
    assert by_id[new["food_id"]]["portions"] == [{"name": "vaso", "grams": 250}]
    assert by_id[lender["food_id"]]["micros_from"] == new["food_id"]


async def test_repeating_it_redoes_nothing(api, hub) -> None:
    old = await manual(api, "Uno")
    new = await manual(api, "Otro")
    await recipe_with(api, old["food_id"])
    body = {"old_food_id": old["food_id"], "new_food_id": new["food_id"]}

    await call(api, "replace_food", body)
    again = (await call(api, "replace_food", body)).json()["content"]["replaced"]

    assert again["recipes"] == []


async def test_an_old_food_or_its_alias_now_write_the_new_one(api, hub) -> None:
    old = await manual(api, "Leche vieja", alias="leche")
    new = await manual(api, "Leche nueva")
    await call(api, "replace_food", {"old_food_id": old["food_id"], "new_food_id": new["food_id"]})

    by_id = await recipe_with(api, old["food_id"])
    by_name = (
        await call(
            api,
            "create_recipe",
            {
                "name": "Café con leche",
                "servings": 1,
                "ingredients": [{"name": "leche", "quantity": 200, "unit": "g"}],
            },
        )
    ).json()["content"]["saved"]["recipe_id"]

    for recipe_id in (by_id, by_name):
        recipe = (await call(api, "get_recipe", {"recipe_id": recipe_id}, READ)).json()["content"][
            "recipe"
        ]
        ids = [one["food_id"] for group in recipe["groups"] for one in group["ingredients"]]
        assert new["food_id"] in ids


async def test_what_does_not_fit_is_refused(api, hub) -> None:
    milk = await manual(api, "Leche")
    capsule = await manual(api, "Omega 3", category_id="supplement", per_unit="cápsula")
    other = await manual(api, "Leche de otra")
    third = await manual(api, "Leche de la tercera")
    await call(
        api, "replace_food", {"old_food_id": milk["food_id"], "new_food_id": other["food_id"]}
    )

    mixed = await call(
        api, "replace_food", {"old_food_id": other["food_id"], "new_food_id": capsule["food_id"]}
    )
    itself = await call(
        api, "replace_food", {"old_food_id": milk["food_id"], "new_food_id": milk["food_id"]}
    )
    elsewhere = await call(
        api, "replace_food", {"old_food_id": milk["food_id"], "new_food_id": third["food_id"]}
    )
    archived = await call(
        api, "replace_food", {"old_food_id": third["food_id"], "new_food_id": milk["food_id"]}
    )

    assert "por unidad" in mixed.json()["content"]["note"]
    assert "sí mismo" in itself.json()["content"]["note"]
    assert "ya se sustituyó" in elsewhere.json()["content"]["note"]
    assert "ya está sustituido" in archived.json()["content"]["note"]


async def test_reading_it_is_not_enough(api, hub) -> None:
    old = await manual(api, "Uno")
    new = await manual(api, "Otro")

    refused = await call(
        api, "replace_food", {"old_food_id": old["food_id"], "new_food_id": new["food_id"]}, READ
    )

    assert refused.status_code == 403
